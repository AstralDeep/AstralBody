"""Inline prompt-injection / nefarious-behavior screen for feedback comments.

Pure-Python heuristic. No LLM call, no network I/O, no new dependency. The
LLM-based pre-pass that runs inside the synthesizer (loop pre-pass) is a
separate defense-in-depth layer in :mod:`backend.orchestrator.knowledge_synthesis`.

Recall on the test payload corpus is required to be ≥ 99% (FR-021).
Precision is allowed to be lower — false positives are quarantined, not
discarded; an admin can release them. The set of patterns is intentionally
conservative so an ops update is only needed if a new attack family appears.
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .schemas import COMMENT_MAX_CHARS

logger = logging.getLogger("Feedback.Safety")

# ---------------------------------------------------------------------------
# Reason codes — also used as quarantine_entry.reason values
# ---------------------------------------------------------------------------

REASON_JAILBREAK_PHRASE = "jailbreak_phrase"
REASON_ROLE_OVERRIDE_MARKER = "role_override_marker"
REASON_UNICODE_CONTROL = "unicode_control"
REASON_OVER_LENGTH = "over_length"
REASON_PRE_PASS_FLAG = "pre_pass_flag"
REASON_PRE_PASS_DISAGREEMENT = "pre_pass_disagreement"


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Jailbreak / instruction-override phrasing. All matched case-insensitively.
# These are deliberately broad — the cost of a false positive is one admin
# click to release; the cost of a false negative is a successful injection.
_JAILBREAK_PATTERNS: Tuple[str, ...] = (
    # "Ignore previous instructions" family
    r"ignore\s+(all\s+)?(the\s+)?previous\s+(instruction|prompt|rule|context)s?",
    r"disregard\s+(all\s+)?(the\s+)?(previous|prior|above)\s+(instruction|prompt)s?",
    r"disregard\s+(all\s+)?(the\s+)?(above|prior)\b",
    r"forget\s+(all\s+)?(the\s+)?previous\s+(instruction|prompt|rule)s?",
    # "You are now" / role override
    r"you\s+are\s+now\s+(?!feeling|happy|sad|able)",
    r"act\s+as\s+(if\s+you\s+(were|are)|though\s+you\s+(were|are))",
    r"pretend\s+(to\s+be|you\s+are|you'?re)",
    r"from\s+now\s+on\s+you\s+(are|will|must|should)",
    # Direct system-prompt manipulation
    r"\bsystem\s+prompt\b",
    r"new\s+(instruction|directive)s?\s*[:.\-]",
    r"override\s+(your|the)\s+(instruction|rule|guideline)s?",
    # DAN / jailbreak names
    r"\bdan\s+mode\b",
    r"\bdeveloper\s+mode\b",
    r"jailbreak\b",
    # Prompt-leak
    r"reveal\s+(your|the)\s+(system\s+)?prompt",
    r"print\s+(your|the)\s+(system\s+)?(prompt|instruction)s?",
    r"(what\s+were|what\s+are)\s+(your|the)\s+(original|initial|system|first)\s+(instruction|prompt|directive)s?",
    r"show\s+me\s+(the\s+)?(entire|whole|full|original|system)\s+(prompt|instruction)s?",
    r"tell\s+me\s+(your|the)\s+(training\s+data|system\s+prompt|initial\s+(instruction|prompt))",
    # Direct address to admin / reviewer
    r"\b(dear|hi|hello|attention)\s+(admin|reviewer|moderator|operator)\b",
    r"\bto\s+the\s+(admin|reviewer|moderator|developer)\b",
    # Embedded instructions to modify other tools
    r"(modify|change|update|rewrite|delete)\s+(the\s+)?tool",
    r"(modify|change|update|rewrite|delete)\s+(the\s+)?(prompt|knowledge|policy)",
)

_JAILBREAK_RE = re.compile("|".join(_JAILBREAK_PATTERNS), re.IGNORECASE)


# Role-override delimiter markers. These are exact substrings (case-insensitive).
_ROLE_OVERRIDE_MARKERS: Tuple[str, ...] = (
    "<|system|>",
    "<|user|>",
    "<|assistant|>",
    "<|im_start|>",
    "<|im_end|>",
    "### system",
    "### instruction",
    "[system]",
    "[/system]",
    "<system>",
    "</system>",
    "[INST]",
    "[/INST]",
    "<<SYS>>",
    "<</SYS>>",
)


# Unicode control / format characters that are commonly abused for hidden
# instruction-injection (zero-width, RLO/LRO, bidi controls).
_FORBIDDEN_UNICODE_CATEGORIES = {"Cc", "Cf"}
# But normal whitespace control chars are fine.
_ALLOWED_UNICODE_CHARS = {"\n", "\r", "\t"}


# Optional ops-managed pattern overlay. If present, lines are loaded and
# joined into the jailbreak regex on import. JSON shape:
#   { "jailbreak_patterns": [..regex strings..],
#     "role_override_markers": [..exact substrings..] }
_OVERLAY_PATH = Path(__file__).parent / "safety_patterns.json"


def _load_overlay() -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Load optional pattern overlay; returns (extra_jailbreak, extra_markers)."""
    if not _OVERLAY_PATH.exists():
        return (), ()
    try:
        data = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        logger.warning("safety_patterns.json failed to load: %s", exc)
        return (), ()
    extra_jb = tuple(data.get("jailbreak_patterns", []))
    extra_mk = tuple(data.get("role_override_markers", []))
    return extra_jb, extra_mk


_overlay_jb, _overlay_mk = _load_overlay()
if _overlay_jb:
    _JAILBREAK_RE = re.compile(
        "|".join(list(_JAILBREAK_PATTERNS) + list(_overlay_jb)), re.IGNORECASE
    )
_ROLE_OVERRIDE_MARKERS_FULL = _ROLE_OVERRIDE_MARKERS + _overlay_mk


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify(text: Optional[str]) -> Tuple[str, Optional[str]]:
    """Classify a single comment.

    Returns ``(safety, reason)`` where ``safety`` is ``"clean"`` or
    ``"quarantined"``. ``reason`` is non-None only when ``safety``
    is ``"quarantined"``.

    Empty / ``None`` input is always clean — there is nothing to attack.
    """
    if text is None or text == "":
        return "clean", None
    if not isinstance(text, str):  # defense-in-depth — pydantic should catch this
        return "quarantined", REASON_JAILBREAK_PHRASE

    # 1. Length cap. Pydantic enforces the same cap at API ingress; this is a
    # second line of defense in case some path sidesteps the model.
    if len(text) > COMMENT_MAX_CHARS:
        return "quarantined", REASON_OVER_LENGTH

    # 2. Forbidden unicode controls (zero-width, bidi, etc.)
    for ch in text:
        if ch in _ALLOWED_UNICODE_CHARS:
            continue
        cat = unicodedata.category(ch)
        if cat in _FORBIDDEN_UNICODE_CATEGORIES:
            return "quarantined", REASON_UNICODE_CONTROL

    # 3. Role-override markers — exact substring match, case-insensitive.
    lower = text.lower()
    for marker in _ROLE_OVERRIDE_MARKERS_FULL:
        if marker.lower() in lower:
            return "quarantined", REASON_ROLE_OVERRIDE_MARKER

    # 4. Jailbreak / instruction-override phrasing — regex.
    if _JAILBREAK_RE.search(text):
        return "quarantined", REASON_JAILBREAK_PHRASE

    return "clean", None


def classify_many(texts: Iterable[Optional[str]]) -> List[Tuple[str, Optional[str]]]:
    """Convenience wrapper for batch classification (used by the loop pre-pass)."""
    return [classify(t) for t in texts]
