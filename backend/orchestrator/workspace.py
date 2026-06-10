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
        for i, comp in enumerate(components):
            if not isinstance(comp, dict):
                continue
            if force_component_id and i == 0:
                cid = force_component_id
                comp["component_id"] = cid
            else:
                cid = self.resolve_identity(comp)
                if cid not in by_cid:
                    # Single-source supersede (docstring rule 3).
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

    def remove(self, chat_id: str, user_id: str, component_id: str) -> bool:
        cur = self.db.execute(
            "DELETE FROM saved_components WHERE chat_id = ? AND component_id = ? AND user_id = ?",
            (chat_id, component_id, user_id),
        )
        removed = bool(getattr(cur, "rowcount", 0))
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
        self.db.execute(
            "INSERT INTO workspace_snapshot (chat_id, user_id, turn_message_id, cause, "
            "components, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, turn_message_id, cause, json.dumps(components), _now_ms()),
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
        return {
            "id": row["id"],
            "chat_id": row["chat_id"],
            "turn_message_id": row.get("turn_message_id"),
            "cause": row["cause"],
            "components": components,
            "created_at": row["created_at"],
        }
