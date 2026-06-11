"""Feature 028 — per-chat persistent workspace (research D11/D13/D14).

The workspace is the durable, ordered set of rich components a user sees on
the canvas for one chat. ``saved_components`` is its store (rows gain a
stable ``component_id``, ``position`` and ``updated_at`` — see data-model.md);
``workspace_snapshot`` records the full workspace state at every turn
boundary and component-action mutation for the read-only timeline.

Component identity (FR-019, research D11)
-----------------------------------------
Resolution order for a top-level component entering the workspace:

1. **Author identity** — an explicit astralprims ``id`` on the primitive wins
   (namespaced ``au_<id>``), letting agents/LLM target a component across
   parameter changes.
2. **Fingerprint** — ``wc_<sha1(agent|tool|canonical-params)[:16]>``. Two
   outputs of the same tool with different parameters get different
   fingerprints and coexist (fixing the pre-028 ``(tool, agent)`` clobber).
3. **Single-source supersede** — when a fingerprint is new but the workspace
   holds exactly ONE live component from the same (agent, tool) and this
   batch carries exactly one component for that pair, the new content
   *updates that component in place* (keeping its identity). This is the
   existing system-prompt contract ("re-call the SAME tool with corrected
   parameters — do NOT create duplicates") made real. With zero or multiple
   candidates the component appends as new (ambiguity ⇒ safest behavior).
   Applies ONLY to fingerprint-derived identities: a component carrying an
   explicit author/echoed id never supersedes a different identity — a new
   explicit id appends (FR-019 "a new identity MUST append").

Deterministic component actions bypass all of this: they target an explicit
``component_id`` and the result inherits it (contracts/component-action.md).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("orchestrator.workspace")

# Private/system keys excluded from identity fingerprints.
_PRIVATE_PARAM_PREFIX = "_"


def _now_ms() -> int:
    return int(time.time() * 1000)


def canonical_params(params: Optional[Dict[str, Any]]) -> str:
    """Stable JSON form of tool params for fingerprinting (private keys dropped)."""
    if not isinstance(params, dict):
        return "{}"
    clean = {k: v for k, v in sorted(params.items()) if not str(k).startswith(_PRIVATE_PARAM_PREFIX)}
    try:
        return json.dumps(clean, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return "{}"


def fingerprint(agent_id: str, tool_name: str, params: Optional[Dict[str, Any]]) -> str:
    basis = f"{agent_id or ''}|{tool_name or ''}|{canonical_params(params)}"
    return "wc_" + hashlib.sha1(basis.encode()).hexdigest()[:16]


def ordinal_identity(base_cid: str, ordinal: int) -> str:
    """Identity for the Nth same-identity component within one upsert batch.

    One round may carry MANY components that resolve to a single identity —
    a multi-component tool result (shared source fingerprint) or parallel
    calls to a tool that hardcodes an author id (the general agent's
    ``chart-card``). Without disambiguation each would supersede the previous
    down to a single surviving row. Ordinal 0 keeps the plain identity (full
    backward compatibility for the common one-per-batch case); later
    occurrences get a deterministic ``~N`` suffix — prefix-preserving (an
    echoed ``wc_…~1``/``au_…~1`` still resolves verbatim) and stable, so
    re-running the same round supersedes slot-for-slot.
    """
    if ordinal <= 0:
        return base_cid
    return f"{base_cid}~{ordinal}"


def layout_key_for(chat_id: str, turn_marker: str) -> str:
    """Deterministic per-round layout key (feature 029).

    Re-designing the same round (same chat + turn marker) upserts the same
    row, so garnish updates in place instead of duplicating (FR-019).
    """
    basis = f"{chat_id or ''}|{turn_marker or ''}"
    return "ly_" + hashlib.sha1(basis.encode()).hexdigest()[:16]


def iter_layout_refs(node: Any):
    """Yield every ``ref`` node's component_id in a layout tree (depth-first).

    Layout trees nest through the same keys the component validator walks:
    ``children``, ``content``, and ``tabs[*].content``.
    """
    if isinstance(node, list):
        for item in node:
            yield from iter_layout_refs(item)
        return
    if not isinstance(node, dict):
        return
    if node.get("type") == "ref":
        cid = node.get("component_id")
        if cid:
            yield str(cid)
        return
    for key in ("children", "content"):
        nested = node.get(key)
        if isinstance(nested, list):
            yield from iter_layout_refs(nested)
    tabs = node.get("tabs")
    if isinstance(tabs, list):
        for tab in tabs:
            if isinstance(tab, dict):
                yield from iter_layout_refs(tab.get("content"))


def prune_layout_refs(node: Any, drop: set) -> Any:
    """Return a copy of a layout tree with ``ref`` nodes in ``drop`` removed.

    Containers that end up empty are kept (they may carry garnish text);
    materialization simply renders them without the pruned leaves.
    """
    if isinstance(node, list):
        out = []
        for item in node:
            pruned = prune_layout_refs(item, drop)
            if pruned is not None:
                out.append(pruned)
        return out
    if not isinstance(node, dict):
        return node
    if node.get("type") == "ref":
        return None if str(node.get("component_id")) in drop else node
    result = dict(node)
    for key in ("children", "content"):
        nested = node.get(key)
        if isinstance(nested, list):
            result[key] = prune_layout_refs(nested, drop)
    tabs = node.get("tabs")
    if isinstance(tabs, list):
        new_tabs = []
        for tab in tabs:
            if isinstance(tab, dict):
                tab = dict(tab)
                tab["content"] = prune_layout_refs(tab.get("content") or [], drop)
            new_tabs.append(tab)
        result["tabs"] = new_tabs
    return result


class WorkspaceManager:
    """Owns workspace identity, upserts, ordering, snapshots and timeline reads."""

    def __init__(self, history):
        self.history = history
        self.db = history.db

    # ── identity ─────────────────────────────────────────────────────────
    def resolve_identity(self, comp: Dict[str, Any]) -> str:
        """Compute (and stamp) the stable component_id for one component."""
        existing = comp.get("component_id")
        if existing:
            return existing
        author_id = comp.get("id")
        if author_id:
            author_id = str(author_id)
            # An author echoing back a workspace identity (the system prompt
            # instructs the LLM to do exactly this for in-place updates) is
            # honored verbatim; anything else gets the au_ namespace.
            cid = author_id if author_id.startswith(("wc_", "au_")) else f"au_{author_id}"
        else:
            cid = fingerprint(
                comp.get("_source_agent", ""),
                comp.get("_source_tool", ""),
                comp.get("_source_params"),
            )
        comp["component_id"] = cid
        return cid

    # ── live workspace reads ─────────────────────────────────────────────
    def live_rows(self, chat_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Ordered workspace rows (legacy NULL-position rows sort by created_at)."""
        rows = self.db.fetch_all(
            "SELECT * FROM saved_components WHERE chat_id = ? AND user_id = ? "
            "ORDER BY COALESCE(position, 2147483647) ASC, created_at ASC",
            (chat_id, user_id),
        )
        out = []
        for row in rows:
            try:
                data = json.loads(row["component_data"])
            except (json.JSONDecodeError, TypeError):
                data = row["component_data"]
            out.append({
                "id": row["id"],
                "chat_id": row["chat_id"],
                "component_id": row.get("component_id"),
                "component_data": data,
                "component_type": row["component_type"],
                "title": row["title"],
                "position": row.get("position"),
                "created_at": row["created_at"],
                "updated_at": row.get("updated_at"),
            })
        return out

    def live_components(self, chat_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Ordered structured component dicts (each carrying component_id)."""
        comps = []
        for row in self.live_rows(chat_id, user_id):
            data = row["component_data"]
            if isinstance(data, dict):
                if row.get("component_id") and not data.get("component_id"):
                    data["component_id"] = row["component_id"]
                comps.append(data)
        return comps

    def get_by_component_id(self, chat_id: str, user_id: str, component_id: str) -> Optional[Dict[str, Any]]:
        for row in self.live_rows(chat_id, user_id):
            if row.get("component_id") == component_id:
                return row
        return None

    # ── upsert / remove ──────────────────────────────────────────────────
    def upsert(self, chat_id: str, user_id: str, components: List[Dict[str, Any]],
               *, force_component_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Persist a batch of components into the workspace.

        Returns the ordered op list for a ``ui_upsert`` message:
        ``[{op:'upsert', component_id, component}]``. ``force_component_id``
        (deterministic component actions) pins the FIRST component of the
        batch onto an existing identity regardless of its own fingerprint.
        """
        if not chat_id or not components:
            return []
        live = self.live_rows(chat_id, user_id)
        by_cid = {r["component_id"]: r for r in live if r.get("component_id")}
        by_source: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for r in live:
            data = r["component_data"]
            if isinstance(data, dict):
                key = (data.get("_source_agent", ""), data.get("_source_tool", ""))
                if key != ("", ""):
                    by_source.setdefault(key, []).append(r)

        # Count same-(agent,tool) components within THIS batch — parallel
        # same-tool calls in one turn must coexist, never supersede.
        batch_source_counts: Dict[Tuple[str, str], int] = {}
        for comp in components:
            if isinstance(comp, dict):
                key = (comp.get("_source_agent", ""), comp.get("_source_tool", ""))
                batch_source_counts[key] = batch_source_counts.get(key, 0) + 1

        ops: List[Dict[str, Any]] = []
        next_pos = 1 + max([r.get("position") or 0 for r in live], default=0)
        batch_fp_seen: Dict[str, int] = {}
        for i, comp in enumerate(components):
            if not isinstance(comp, dict):
                continue
            if force_component_id and i == 0:
                cid = force_component_id
                comp["component_id"] = cid
            else:
                explicit_identity = bool(comp.get("component_id") or comp.get("id"))
                cid = self.resolve_identity(comp)
                # Same resolved identity twice in ONE batch (multi-component
                # tool result, or parallel calls of a tool with a hardcoded
                # author id): the 2nd+ occurrence gets a deterministic ordinal
                # identity instead of superseding its batch siblings.
                seen = batch_fp_seen.get(cid, 0)
                batch_fp_seen[cid] = seen + 1
                if seen:
                    cid = ordinal_identity(cid, seen)
                    comp["component_id"] = cid
                if cid not in by_cid and not explicit_identity:
                    # Single-source supersede (docstring rule 3) — only for
                    # fingerprint-derived identities. An author-declared id is
                    # authoritative (FR-019): a NEW explicit identity appends,
                    # never steals an existing component's place.
                    key = (comp.get("_source_agent", ""), comp.get("_source_tool", ""))
                    candidates = by_source.get(key, [])
                    if (key != ("", "") and len(candidates) == 1
                            and batch_source_counts.get(key, 0) == 1):
                        cid = candidates[0]["component_id"] or cid
                        comp["component_id"] = cid
            existing = by_cid.get(cid)
            created = existing is None
            if existing:
                self.db.execute(
                    "UPDATE saved_components SET component_data = ?, component_type = ?, "
                    "title = ?, updated_at = ? WHERE chat_id = ? AND component_id = ? AND user_id = ?",
                    (json.dumps(comp), comp.get("type", existing["component_type"]),
                     comp.get("title", existing["title"]), _now_ms(), chat_id, cid, user_id),
                )
            else:
                row_id = str(uuid.uuid4())
                title = comp.get("title") or str(comp.get("type", "Component")).replace("_", " ").title()
                self.db.execute(
                    "INSERT INTO saved_components (id, chat_id, user_id, component_data, "
                    "component_type, title, created_at, component_id, position, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (row_id, chat_id, user_id, json.dumps(comp), comp.get("type", "unknown"),
                     title, _now_ms(), cid, next_pos, _now_ms()),
                )
                by_cid[cid] = {"id": row_id, "component_id": cid,
                               "component_data": comp,
                               "component_type": comp.get("type", "unknown"),
                               "title": title, "position": next_pos}
                key = (comp.get("_source_agent", ""), comp.get("_source_tool", ""))
                if key != ("", ""):
                    by_source.setdefault(key, []).append(by_cid[cid])
                next_pos += 1
            ops.append({"op": "upsert", "component_id": cid, "component": comp, "created": created})
        if ops:
            self.db.execute(
                "UPDATE chats SET has_saved_components = TRUE WHERE id = ? AND user_id = ?",
                (chat_id, user_id),
            )
        return ops

    # ── canvas arrangements (feature 029, adaptive UI designer) ──────────
    def live_layouts(self, chat_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Ordered designed arrangements for a chat (overlay over components)."""
        rows = self.db.fetch_all(
            "SELECT layout_key, position, layout FROM workspace_layout "
            "WHERE chat_id = ? AND user_id = ? ORDER BY position ASC, id ASC",
            (chat_id, user_id),
        )
        out = []
        for row in rows:
            try:
                tree = json.loads(row["layout"])
            except (json.JSONDecodeError, TypeError):
                continue
            out.append({"layout_key": row["layout_key"], "position": row["position"],
                        "layout": tree})
        return out

    def next_canvas_position(self, chat_id: str, user_id: str) -> int:
        """Next position in the SHARED ordering space of components + layouts."""
        comp_max = self.db.fetch_one(
            "SELECT MAX(position) AS p FROM saved_components WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        lay_max = self.db.fetch_one(
            "SELECT MAX(position) AS p FROM workspace_layout WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        return 1 + max((comp_max or {}).get("p") or 0, (lay_max or {}).get("p") or 0)

    def upsert_layout(self, chat_id: str, user_id: str, layout_key: str,
                      layout: List[Dict[str, Any]]) -> bool:
        """Persist one designed arrangement; later layouts steal claimed refs.

        A component_id may be claimed by at most one live arrangement: refs
        the new layout claims are pruned from earlier layouts (later wins —
        re-designing a round that re-uses an old component moves it).
        Existing (chat, layout_key) rows update in place keeping position.
        """
        if not chat_id or not layout_key or not isinstance(layout, list):
            return False
        claimed = set(iter_layout_refs(layout))
        if claimed:
            for other in self.live_layouts(chat_id, user_id):
                if other["layout_key"] == layout_key:
                    continue
                other_refs = set(iter_layout_refs(other["layout"]))
                overlap = other_refs & claimed
                if overlap:
                    pruned = prune_layout_refs(other["layout"], overlap)
                    self.db.execute(
                        "UPDATE workspace_layout SET layout = ?, updated_at = ? "
                        "WHERE chat_id = ? AND user_id = ? AND layout_key = ?",
                        (json.dumps(pruned), _now_ms(), chat_id, user_id, other["layout_key"]),
                    )
        existing = self.db.fetch_one(
            "SELECT id FROM workspace_layout WHERE chat_id = ? AND user_id = ? AND layout_key = ?",
            (chat_id, user_id, layout_key),
        )
        if existing:
            self.db.execute(
                "UPDATE workspace_layout SET layout = ?, updated_at = ? "
                "WHERE chat_id = ? AND user_id = ? AND layout_key = ?",
                (json.dumps(layout), _now_ms(), chat_id, user_id, layout_key),
            )
        else:
            self.db.execute(
                "INSERT INTO workspace_layout (chat_id, user_id, layout_key, position, "
                "layout, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chat_id, user_id, layout_key, self.next_canvas_position(chat_id, user_id),
                 json.dumps(layout), _now_ms(), _now_ms()),
            )
        return True

    def remove(self, chat_id: str, user_id: str, component_id: str) -> bool:
        cur = self.db.execute(
            "DELETE FROM saved_components WHERE chat_id = ? AND component_id = ? AND user_id = ?",
            (chat_id, component_id, user_id),
        )
        removed = bool(getattr(cur, "rowcount", 0))
        if removed:
            # Feature 029: a deleted component's refs vanish from arrangements
            # (materialization would drop them anyway; pruning keeps stored
            # layouts honest for snapshots/timeline).
            try:
                for lay in self.live_layouts(chat_id, user_id):
                    if component_id in set(iter_layout_refs(lay["layout"])):
                        pruned = prune_layout_refs(lay["layout"], {component_id})
                        self.db.execute(
                            "UPDATE workspace_layout SET layout = ?, updated_at = ? "
                            "WHERE chat_id = ? AND user_id = ? AND layout_key = ?",
                            (json.dumps(pruned), _now_ms(), chat_id, user_id, lay["layout_key"]),
                        )
            except Exception:
                logger.debug("layout ref pruning failed on remove", exc_info=True)
        if removed:
            count = self.db.fetch_one(
                "SELECT COUNT(*) as count FROM saved_components WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )
            if count and count["count"] == 0:
                self.db.execute(
                    "UPDATE chats SET has_saved_components = FALSE WHERE id = ? AND user_id = ?",
                    (chat_id, user_id),
                )
        return removed

    # ── snapshots / timeline (D14, FR-030..FR-033) ───────────────────────
    def snapshot(self, chat_id: str, user_id: str, cause: str,
                 turn_message_id: Optional[int] = None) -> Optional[int]:
        """Record the full current workspace state. Returns the snapshot id."""
        if not chat_id:
            return None
        components = self.live_components(chat_id, user_id)
        # Feature 029: arrangements snapshot alongside components so the
        # timeline can materialize historical designed states. NULL-tolerant
        # readers treat missing/NULL layouts as "render flat" (pre-029 rows).
        layouts = self.live_layouts(chat_id, user_id)
        self.db.execute(
            "INSERT INTO workspace_snapshot (chat_id, user_id, turn_message_id, cause, "
            "components, layouts, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, turn_message_id, cause, json.dumps(components),
             json.dumps(layouts) if layouts else None, _now_ms()),
        )
        # RealDictCursor rows; psycopg2 cursors expose lastrowid unreliably —
        # callers only need success/failure, the id is for tests/diagnostics.
        try:
            row = self.db.fetch_one(
                "SELECT id FROM workspace_snapshot WHERE chat_id = ? AND user_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (chat_id, user_id),
            )
            return row["id"] if row else None
        except Exception:
            return None

    def list_snapshots(self, chat_id: str, user_id: str, limit: int = 50,
                       offset: int = 0) -> List[Dict[str, Any]]:
        """Snapshot metadata for the timeline list (newest first; no payloads)."""
        rows = self.db.fetch_all(
            "SELECT id, chat_id, turn_message_id, cause, created_at "
            "FROM workspace_snapshot WHERE chat_id = ? AND user_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            (chat_id, user_id, limit, offset),
        )
        return [dict(r) for r in rows]

    def count_snapshots(self, chat_id: str, user_id: str) -> int:
        row = self.db.fetch_one(
            "SELECT COUNT(*) as count FROM workspace_snapshot WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        return int(row["count"]) if row else 0

    def get_snapshot(self, snapshot_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.fetch_one(
            "SELECT * FROM workspace_snapshot WHERE id = ? AND user_id = ?",
            (snapshot_id, user_id),
        )
        if not row:
            return None
        try:
            components = json.loads(row["components"])
        except (json.JSONDecodeError, TypeError):
            components = []
        try:
            layouts = json.loads(row["layouts"]) if row.get("layouts") else []
        except (json.JSONDecodeError, TypeError):
            layouts = []
        return {
            "id": row["id"],
            "chat_id": row["chat_id"],
            "turn_message_id": row.get("turn_message_id"),
            "cause": row["cause"],
            "components": components,
            "layouts": layouts,
            "created_at": row["created_at"],
        }
