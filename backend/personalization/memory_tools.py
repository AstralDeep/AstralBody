"""Orchestrator-callable memory tools (feature 025, US4/T035).

``remember`` (explicit), ``memory_search`` and ``memory_get`` (recall), plus
``capture_signal`` (post-turn auto-capture). Every write passes the PHI gate
(FR-016/FR-017): PHI-flagged content is used live but never persisted. The
class is constructed with a repository and (optionally) an injected gate so it
is unit-testable without Presidio.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .phi_gate import PHIGate, get_phi_gate
from .repository import MEMORY_CATEGORIES

logger = logging.getLogger("personalization.memory")


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


class MemoryTools:
    def __init__(self, repo, phi_gate: Optional[PHIGate] = None) -> None:
        self.repo = repo
        self.gate = phi_gate or get_phi_gate()

    def remember(self, user_id: str, category: str, value: str) -> Dict[str, Any]:
        """Explicitly remember a durable fact. PHI is refused (not persisted)."""
        if category not in MEMORY_CATEGORIES:
            category = "context"
        value = (value or "").strip()
        if not value:
            return {"stored": False, "reason": "nothing to remember"}
        if self.gate.contains_phi(value):
            logger.info("memory.write_refused_phi",
                        extra={"user_id": user_id, "category": category})
            return {
                "stored": False,
                "reason": "That looked like protected health information, so I did not "
                          "save it to long-term memory. I can still use it for this task.",
            }
        item = self.repo.create_memory(user_id, category, value, source="explicit")
        # 030 FR-017: structured observability for memory writes.
        logger.info("memory.remembered",
                    extra={"user_id": user_id, "category": category, "memory_id": item["id"]})
        return {"stored": True, "id": item["id"], "category": category}

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
        """Lightweight token-overlap search over durable memory items."""
        q = _tokens(query)
        items = self.repo.list_memory(user_id)
        if not q:
            return items[:limit]
        scored = []
        for it in items:
            overlap = len(q & _tokens(f"{it.get('category','')} {it.get('value','')}"))
            if overlap:
                scored.append((overlap, it))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [it for _, it in scored[:limit]]
