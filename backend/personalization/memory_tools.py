"""Orchestrator-callable memory tools.

``remember`` (explicit), ``memory_search`` and ``memory_get`` (recall), plus
``capture_signal`` (post-turn auto-capture). Every write passes the PHI gate:
PHI-flagged content is used live but never persisted. The class is constructed
with a repository and (optionally) an injected gate so it is unit-testable
without Presidio.

Reconcile-don't-append: ``remember_reconciled`` adds an LLM-mediated ADD /
UPDATE / DELETE / NOOP decision over related existing memories, with
supersession (soft-delete + ``superseded_by``) instead of monotonic growth.
Strictly fail-open: with the flag off, no injected LLM, no related candidates,
or any error, it degrades to the legacy append.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional

from . import memory_guard
from .phi_gate import PHIGate, get_phi_gate
from .repository import MEMORY_CATEGORIES
from .retrieval_scoring import multisignal_enabled, score_memory_row

logger = logging.getLogger("personalization.memory")

#: Cap on related memories shown to the reconcile LLM (keeps the prompt cheap).
RECONCILE_MAX_CANDIDATES = 8


def reconcile_enabled() -> bool:
    """FF_MEMORY_RECONCILE feature flag (default ON).

    When on — AND an LLM is injected AND there are related existing memories —
    a durable write is reconciled (ADD/UPDATE/DELETE/NOOP with supersession)
    rather than always appended. Fail-open: off / no LLM / no candidates / any
    error all fall back to the legacy append, so the flag never loses a write."""
    return os.getenv("FF_MEMORY_RECONCILE", "true").strip().lower() not in ("0", "false", "no", "off")


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


#: Linked-note tuning.
LINK_MIN_OVERLAP = 1      # shared content keywords required to link two memories
LINK_MAX_NEIGHBORS = 5    # max links created per new memory

_KEYWORD_STOPWORDS = frozenset(
    "the a an of to in on at for and or but with from into about as is are was "
    "were be been being i you he she it we they me my your his her our their "
    "this that these those prefer prefers like likes want wants use uses using "
    "have has had do does did will would can could should note remember".split()
)


def linking_enabled() -> bool:
    """FF_MEMORY_LINKING feature flag (default ON). When on, a new memory is
    linked to keyword-overlapping neighbours and recall pulls in a hit's linked
    neighbours (single-step multi-hop). Fail-open: off or any error leaves
    memory unlinked and retrieval unchanged."""
    return os.getenv("FF_MEMORY_LINKING", "true").strip().lower() not in ("0", "false", "no", "off")


def derive_keywords(value: str, *, limit: int = 8) -> str:
    """Deterministic content keywords for a memory note (space-joined): the
    first ``limit`` distinct ≥3-char non-stopword tokens. The self-organizing
    retrieval/link signal."""
    out: List[str] = []
    for t in re.findall(r"[a-z0-9]{3,}", (value or "").lower()):
        if t in _KEYWORD_STOPWORDS or t in out:
            continue
        out.append(t)
        if len(out) >= limit:
            break
    return " ".join(out)


def pagerank_enabled() -> bool:
    """FF_MEMORY_PAGERANK feature flag (default ON). When on and the user has a
    link graph, ``memory_search`` ranks by Personalized PageRank over the memory
    graph (single-step multi-hop), seeded by the query's direct matches.
    Fail-open: off / no graph / any error → the 1-hop expansion."""
    return os.getenv("FF_MEMORY_PAGERANK", "true").strip().lower() not in ("0", "false", "no", "off")


def personalized_pagerank(adjacency: Dict[str, List[str]], seeds: Dict[str, float],
                          *, alpha: float = 0.85, iters: int = 20) -> Dict[str, float]:
    """Personalized PageRank over an (undirected) memory graph.

    ``adjacency``: ``{node: [neighbour, …]}``. ``seeds``: ``{node: weight>0}`` —
    the restart (personalization) distribution. Returns ``{node: score}``. Pure
    and deterministic; ~O((nodes+edges) × iters). Dangling nodes redistribute
    their mass over the restart distribution so total mass is conserved. With an
    empty seed set it degrades to uniform restart (ordinary PageRank)."""
    nodes = set(adjacency)
    nodes.update(seeds)
    for nbrs in adjacency.values():
        nodes.update(nbrs)
    if not nodes:
        return {}
    seed_total = sum(w for w in seeds.values() if w > 0)
    if seed_total > 0:
        restart = {n: (max(seeds.get(n, 0.0), 0.0) / seed_total) for n in nodes}
    else:
        restart = {n: 1.0 / len(nodes) for n in nodes}
    rank = dict(restart)
    for _ in range(max(1, iters)):
        nxt = {n: (1.0 - alpha) * restart[n] for n in nodes}
        for n in nodes:
            nbrs = adjacency.get(n) or []
            if nbrs:
                share = alpha * rank[n] / len(nbrs)
                for m in nbrs:
                    nxt[m] = nxt.get(m, 0.0) + share
            else:  # dangling node — spread mass over the restart distribution
                mass = alpha * rank[n]
                for m in nodes:
                    nxt[m] += mass * restart[m]
        rank = nxt
    return rank


def _extract_json(content: str) -> Optional[dict]:
    """Pull the first balanced JSON object from a string that may be fenced or
    wrapped in prose. Returns the parsed dict, or None."""
    if not isinstance(content, str):
        return None
    s = content.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        s = s.strip()
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(s[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except (ValueError, TypeError):
                    return None
    return None


def build_reconcile_messages(value: str, category: str,
                             candidates: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Chat messages asking the LLM how a NEW fact relates to EXISTING ones."""
    existing = "\n".join(
        f"{i + 1}. [{c.get('category')}] {c.get('value')}"
        for i, c in enumerate(candidates)
    ) or "(none)"
    system = (
        "You maintain a user's long-term memory. Decide how the NEW fact relates "
        "to the EXISTING facts and reply with ONLY a JSON object — no prose.\n"
        "Actions:\n"
        '- "ADD": the new fact is genuinely new; keep it alongside the others.\n'
        '- "UPDATE": the new fact replaces or refines ONE existing fact (same '
        'fact, changed/➜more-precise value). Set "target" to that fact\'s number '
        'and "value" to the single best merged statement.\n'
        '- "DELETE": the new fact says an existing fact is no longer true and is '
        'not itself worth keeping. Set "target" to that fact\'s number.\n'
        '- "NOOP": the new fact is already captured by an existing one; change '
        "nothing.\n"
        'Reply EXACTLY: {"action":"ADD|UPDATE|DELETE|NOOP","target":<number or '
        'null>,"value":"<text or null>"}'
    )
    user = f"NEW FACT [{category}]: {value}\n\nEXISTING FACTS:\n{existing}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_reconcile_decision(content: str) -> Optional[Dict[str, Any]]:
    """Parse the LLM's reconcile reply into ``{"action","target","value"}`` or
    None. ``action`` ∈ {ADD,UPDATE,DELETE,NOOP}; ``target`` is a 1-based
    candidate number or None; ``value`` is the optional updated text."""
    obj = _extract_json(content)
    if not isinstance(obj, dict):
        return None
    action = str(obj.get("action") or "").strip().upper()
    if action not in ("ADD", "UPDATE", "DELETE", "NOOP"):
        return None
    raw_target = obj.get("target")
    try:
        target = int(raw_target) if raw_target is not None else None
    except (TypeError, ValueError):
        target = None
    raw_value = obj.get("value")
    value = raw_value.strip() if isinstance(raw_value, str) and raw_value.strip() else None
    return {"action": action, "target": target, "value": value}


class MemoryTools:
    def __init__(self, repo, phi_gate: Optional[PHIGate] = None) -> None:
        self.repo = repo
        self.gate = phi_gate or get_phi_gate()

    # ── shared write helpers ────────────────────────────────────────────────

    def _gate_value(self, category: str, value: str):
        """Normalize category, strip value, and gate (PHI + poisoning).
        Returns ``(category, value, refusal_dict_or_None)``."""
        if category not in MEMORY_CATEGORIES:
            category = "context"
        value = (value or "").strip()
        if not value:
            return category, value, {"stored": False, "reason": "nothing to remember"}
        if self.gate.contains_phi(value):
            logger.info("memory.write_refused_phi",
                        extra={"user_id": "?", "category": category})
            return category, value, {
                "stored": False,
                "reason": "That looked like protected health information, so I did not "
                          "save it to long-term memory. I can still use it for this task.",
            }
        # Never persist assistant-directed instructions as a durable "fact" —
        # the memory-poisoning vector. Used live, never written.
        if memory_guard.guard_enabled() and memory_guard.is_poisoning_attempt(value):
            logger.warning("memory.write_refused_poison",
                           extra={"user_id": "?", "category": category})
            return category, value, {
                "stored": False,
                "refused": "poisoning",
                "reason": "That reads like an instruction rather than a fact about you, "
                          "so I didn't save it to long-term memory.",
            }
        return category, value, None

    def _create_linked(self, user_id: str, category: str, value: str) -> Dict[str, Any]:
        """Create a memory note (with derived keywords) and link it into the
        keyword-overlap graph. Linking failures never block the write."""
        keywords = derive_keywords(value)
        item = self.repo.create_memory(user_id, category, value,
                                       source="explicit", keywords=keywords)
        if linking_enabled():
            try:
                self._link_new(user_id, item["id"], value, keywords)
            except Exception:
                logger.debug("memory.link_failed", exc_info=True)
        return item

    def _link_new(self, user_id: str, new_id: str, value: str, keywords: str) -> int:
        """Link a just-created memory to its keyword-overlapping live neighbours
        (strongest first, capped). Returns the number of links created."""
        kw = _tokens(keywords) or _tokens(value)
        if not kw:
            return 0
        scored = []
        for it in self.repo.list_memory(user_id):
            if it.get("id") == new_id:
                continue
            other = _tokens(it.get("keywords") or "") or _tokens(it.get("value", ""))
            overlap = len(kw & other)
            if overlap >= LINK_MIN_OVERLAP:
                scored.append((overlap, it["id"]))
        scored.sort(key=lambda t: -t[0])
        linked = 0
        for _, oid in scored[:LINK_MAX_NEIGHBORS]:
            if self.repo.add_link(user_id, new_id, oid):
                linked += 1
        return linked

    def _do_add(self, user_id: str, category: str, value: str) -> Dict[str, Any]:
        item = self._create_linked(user_id, category, value)
        logger.info("memory.remembered",
                    extra={"user_id": user_id, "category": category, "memory_id": item["id"]})
        return {"stored": True, "id": item["id"], "category": category}

    # ── writes ──────────────────────────────────────────────────────────────

    def remember(self, user_id: str, category: str, value: str) -> Dict[str, Any]:
        """Explicitly remember a durable fact (legacy append). PHI is refused."""
        category, value, refusal = self._gate_value(category, value)
        if refusal is not None:
            return refusal
        return self._do_add(user_id, category, value)

    def _candidates(self, user_id: str, category: str, value: str) -> List[Dict[str, Any]]:
        """Related live memories for reconciliation: same category and/or
        token-overlap, best first, capped at RECONCILE_MAX_CANDIDATES."""
        vt = _tokens(value)
        scored = []
        for it in self.repo.list_memory(user_id):  # live only (superseded excluded)
            overlap = len(vt & _tokens(it.get("value", "")))
            same_cat = it.get("category") == category
            if overlap or same_cat:
                scored.append((overlap + (1 if same_cat else 0), it))
        scored.sort(key=lambda t: -t[0])
        return [it for _, it in scored[:RECONCILE_MAX_CANDIDATES]]

    async def remember_reconciled(
        self, user_id: str, category: str, value: str, *,
        llm_call: Optional[Callable[[List[Dict[str, str]]], Awaitable[Optional[str]]]] = None,
    ) -> Dict[str, Any]:
        """Reconcile a durable write against related memories via an injected
        ``llm_call``, applying ADD/UPDATE/DELETE/NOOP with supersession.
        Fail-open to a plain append at every step."""
        category, value, refusal = self._gate_value(category, value)
        if refusal is not None:
            return refusal

        candidates = (self._candidates(user_id, category, value)
                      if (reconcile_enabled() and llm_call is not None) else [])
        if not candidates:
            return self._do_add(user_id, category, value)

        try:
            content = await llm_call(build_reconcile_messages(value, category, candidates))
            decision = parse_reconcile_decision(content) if content else None
        except Exception:
            logger.debug("memory.reconcile_llm_failed — appending", exc_info=True)
            decision = None
        if not decision:
            return self._do_add(user_id, category, value)

        action = decision["action"]
        target = decision["target"]
        tgt = (candidates[target - 1]
               if isinstance(target, int) and 1 <= target <= len(candidates) else None)

        if action == "NOOP":
            logger.info("memory.reconcile_noop",
                        extra={"user_id": user_id, "category": category})
            return {"stored": False, "action": "noop",
                    "reason": "already remembered"}
        if action == "DELETE" and tgt is not None:
            self.repo.supersede_memory(user_id, tgt["id"], None)
            logger.info("memory.reconcile_delete",
                        extra={"user_id": user_id, "superseded": tgt["id"]})
            return {"stored": False, "action": "delete", "superseded": tgt["id"]}
        if action == "UPDATE" and tgt is not None:
            new_value = decision.get("value") or value
            item = self._create_linked(user_id, category, new_value)
            self.repo.supersede_memory(user_id, tgt["id"], item["id"])
            logger.info("memory.reconcile_update",
                        extra={"user_id": user_id, "category": category,
                               "memory_id": item["id"], "superseded": tgt["id"]})
            return {"stored": True, "id": item["id"], "category": category,
                    "action": "update", "superseded": tgt["id"]}
        # ADD, or UPDATE/DELETE with no resolvable target → safe append.
        result = self._do_add(user_id, category, value)
        result["action"] = "add"
        return result

    def capture_signal(self, user_id: str, category: str, value: str) -> bool:
        """Auto-capture a short-term signal (non-durable). PHI is dropped."""
        if category not in MEMORY_CATEGORIES:
            category = "context"
        value = (value or "").strip()
        if not value or self.gate.contains_phi(value):
            return False
        self.repo.add_signal(user_id, category, value)
        logger.info("memory.signal_captured",
                    extra={"user_id": user_id, "category": category})
        return True

    def _live_memory(self, user_id: str) -> List[Dict[str, Any]]:
        """Live memories with tamper-filtering: a row whose HMAC signature no
        longer matches its fields is dropped from recall (and logged)."""
        items = self.repo.list_memory(user_id)
        if not memory_guard.guard_enabled():
            return items
        kept = []
        for it in items:
            if memory_guard.trust_of(it) == "tampered":
                logger.warning("memory.tampered_excluded",
                               extra={"user_id": user_id, "memory_id": it.get("id")})
                continue
            kept.append(it)
        return kept

    def memory_get(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all durable memory items (for prompt recall), tamper-filtered."""
        return self._live_memory(user_id)

    def memory_search(self, user_id: str, query: str, *, limit: int = 10) -> List[Dict[str, Any]]:
        """Token-overlap search over durable memory, ranked by a multi-signal
        recency × importance × relevance composite when FF_MEMORY_MULTISIGNAL is
        on; fail-open to the legacy overlap-only rank."""
        q = _tokens(query)
        items = self._live_memory(user_id)  # recency DESC, tamper-filtered
        if not q:
            return items[:limit]
        use_ms = multisignal_enabled()
        total = len(items)
        scored = []
        seed_scores: Dict[str, float] = {}
        order: Dict[str, int] = {}
        for idx, it in enumerate(items):
            order[str(it.get("id"))] = idx
            overlap = len(q & _tokens(
                f"{it.get('category','')} {it.get('value','')} {it.get('keywords') or ''}"))
            if not overlap:
                continue
            score = float(overlap)
            if use_ms:
                try:
                    score = score_memory_row(it, index=idx, total=total,
                                             overlap=overlap, query_size=len(q))
                except Exception:
                    logger.debug("memory_search: multi-signal scoring failed — overlap only",
                                 exc_info=True)
                    score = float(overlap)
            seed_scores[str(it.get("id"))] = score
            scored.append((score, idx, it))
        if not seed_scores:
            return []
        # Rank by Personalized PageRank over the link graph (single-step
        # multi-hop), seeded by the direct matches. Returns None (→ fallback)
        # when there is no graph or the repo predates links.
        if pagerank_enabled():
            try:
                ranked = self._pagerank_rank(user_id, items, seed_scores, order, limit)
                if ranked is not None:
                    return ranked
            except Exception:
                logger.debug("memory_search: pagerank failed — falling back", exc_info=True)
        # Fallback: direct hits (ties keep recency), then the 1-hop expansion.
        scored.sort(key=lambda t: (-t[0], t[1]))
        results = [it for _, _, it in scored[:limit]]
        if linking_enabled() and results and len(results) < limit:
            try:
                results = self._expand_with_links(user_id, results, items, limit)
            except Exception:
                logger.debug("memory_search: link expansion failed — direct hits only",
                             exc_info=True)
        return results

    def _pagerank_rank(self, user_id: str, items: List[Dict[str, Any]],
                       seed_scores: Dict[str, float], order: Dict[str, int],
                       limit: int) -> Optional[List[Dict[str, Any]]]:
        """Rank memories by Personalized PageRank over the user's link graph,
        seeded by ``seed_scores``. Returns None when there is no graph (the
        caller then uses the direct/expansion fallback)."""
        list_links = getattr(self.repo, "list_links", None)
        if list_links is None:
            return None
        edges = list_links(user_id)
        if not edges:
            return None
        adjacency: Dict[str, List[str]] = {}
        for e in edges:
            adjacency.setdefault(str(e["memory_id"]), []).append(str(e["linked_id"]))
        ppr = personalized_pagerank(adjacency, seed_scores)
        by_id = {str(it.get("id")): it for it in items}
        ranked_ids = [nid for nid in by_id
                      if nid in seed_scores or ppr.get(nid, 0.0) > 1e-9]
        # Direct matches (seeds) lead, ordered by their match strength; then the
        # associated (non-seed) memories the graph surfaced, ordered by PageRank
        # mass. (Pure PPR can rank a degree-1 seed's neighbour above the seed —
        # not what recall wants, so seeds are pinned ahead.)
        ranked_ids.sort(key=lambda nid: (
            0 if nid in seed_scores else 1,
            -seed_scores.get(nid, 0.0),
            -ppr.get(nid, 0.0),
            order.get(nid, 1 << 30),
        ))
        return [by_id[nid] for nid in ranked_ids[:limit]]

    def _expand_with_links(self, user_id: str, results: List[Dict[str, Any]],
                           all_items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """Append the 1-hop linked neighbours of the current hits (not already
        present), best matches first, up to ``limit``."""
        by_id = {it.get("id"): it for it in all_items}
        seen = {it.get("id") for it in results}
        expanded = list(results)
        for it in results:
            if len(expanded) >= limit:
                break
            for lid in self.repo.linked_ids(user_id, it.get("id")):
                if lid not in seen and lid in by_id:
                    expanded.append(by_id[lid])
                    seen.add(lid)
                    if len(expanded) >= limit:
                        break
        return expanded[:limit]
