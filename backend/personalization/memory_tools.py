"""Orchestrator-callable memory tools (feature 025, US4/T035).

``remember`` (explicit), ``memory_search`` and ``memory_get`` (recall), plus
``capture_signal`` (post-turn auto-capture). Every write passes the PHI gate
(FR-016/FR-017): PHI-flagged content is used live but never persisted. The
class is constructed with a repository and (optionally) an injected gate so it
is unit-testable without Presidio.

Feature 033 (C-M1) — reconcile-don't-append. ``remember_reconciled`` adds an
LLM-mediated ADD / UPDATE / DELETE / NOOP decision over related existing
memories, with supersession (soft-delete + ``superseded_by``) instead of
monotonic growth. Strictly fail-open: with the flag off, no injected LLM, no
related candidates, or any error, it degrades to the legacy append.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .phi_gate import PHIGate, get_phi_gate
from .repository import MEMORY_CATEGORIES
from .retrieval_scoring import multisignal_enabled, score_memory_row

logger = logging.getLogger("personalization.memory")

#: Cap on related memories shown to the reconcile LLM (keeps the prompt cheap).
RECONCILE_MAX_CANDIDATES = 8


def reconcile_enabled() -> bool:
    """FF_MEMORY_RECONCILE feature flag (default ON; feature 033 C-M1).

    When on — AND an LLM is injected AND there are related existing memories —
    a durable write is reconciled (ADD/UPDATE/DELETE/NOOP with supersession)
    rather than always appended. Fail-open: off / no LLM / no candidates / any
    error all fall back to the legacy append, so the flag never loses a write."""
    return os.getenv("FF_MEMORY_RECONCILE", "true").strip().lower() not in ("0", "false", "no", "off")


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


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
        """Normalize category, strip value, and PHI-gate. Returns
        ``(category, value, refusal_dict_or_None)``."""
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
        return category, value, None

    def _do_add(self, user_id: str, category: str, value: str) -> Dict[str, Any]:
        item = self.repo.create_memory(user_id, category, value, source="explicit")
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
        """C-M1: reconcile a durable write against related memories via an
        injected ``llm_call``, applying ADD/UPDATE/DELETE/NOOP with
        supersession. Fail-open to a plain append at every step."""
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
            item = self.repo.create_memory(user_id, category, new_value, source="explicit")
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
        # 030 FR-017: structured observability for short-term signal capture.
        logger.info("memory.signal_captured",
                    extra={"user_id": user_id, "category": category})
        return True

    def memory_get(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all durable memory items (for prompt recall)."""
        return self.repo.list_memory(user_id)

    def memory_search(self, user_id: str, query: str, *, limit: int = 10) -> List[Dict[str, Any]]:
        """Token-overlap search over durable memory, ranked by a multi-signal
        recency × importance × relevance composite (feature 036 C-M4) when
        FF_MEMORY_MULTISIGNAL is on; fail-open to the legacy overlap-only rank."""
        q = _tokens(query)
        items = self.repo.list_memory(user_id)  # recency DESC (created_at)
        if not q:
            return items[:limit]
        use_ms = multisignal_enabled()
        total = len(items)
        scored = []
        for idx, it in enumerate(items):
            overlap = len(q & _tokens(f"{it.get('category','')} {it.get('value','')}"))
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
            scored.append((score, idx, it))
        # higher score first; ties keep recency order (idx asc)
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [it for _, _, it in scored[:limit]]
