"""Eager, safe auto-creation of a backend parser for an uncovered file type.

Feature 031-attachment-upload-parsing (User Story 2). When an accepted file
type has no built-in or globally-promoted parser, uploading one *eagerly*
drafts a parser by reusing the feature-027 agentic-creation lifecycle
(draft -> security gate -> isolated VirtualWebSocket self-test -> ADMIN
approval -> global promotion). This module is the programmatic, format-seeded
entry point — it does NOT rely on the LLM deciding to call ``create_capability``
during a chat turn.

Lifecycle contract: specs/031-attachment-upload-parsing/contracts/parser-autocreate.md

NOTE: the deep lifecycle wiring (create_draft/generate_code/self-test/promote)
is implemented in the US2 phase; this module defines the public surface the
upload endpoint and approval handlers call.
"""

from __future__ import annotations

import logging
from typing import Optional, TypedDict

logger = logging.getLogger("attachment_autoparse")


class CoverageStatus(TypedDict):
    status: str  # "covered" | "preparing" | "pending_admin_approval" | "unavailable"
    gap_fingerprint: Optional[str]


async def start(orch, attachment, *, user_id: str, chat_id: Optional[str]) -> CoverageStatus:
    """Eagerly begin drafting a parser for an uncovered uploaded *attachment*.

    Returns the ``parser_status`` to surface in the upload response. Implemented
    in the US2 phase (T024–T032).
    """
    raise NotImplementedError("attachment_autoparse.start — implemented in US2 (T025/T026)")


def coverage_status(orch, *, extension: Optional[str], category: str) -> CoverageStatus:
    """Resolve the current parser-coverage status for a type without side effects.

    Implemented in the US2 phase (T024).
    """
    raise NotImplementedError("attachment_autoparse.coverage_status — implemented in US2 (T024)")


__all__ = ["CoverageStatus", "start", "coverage_status"]
