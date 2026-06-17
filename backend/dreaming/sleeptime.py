"""Sleep-time compute — anticipate + precompute during idle — 033 Wave-2 (C-N11).

During idle time the "dreaming" sweep anticipates likely next questions and
precomputes derived facts/answers so a later turn is instant. This module is
the PURE candidate-generation + scheduling logic — it derives likely follow-up
questions from recent turns and durable memories, scores them deterministically,
and decides which are worth precomputing this idle cycle. The actual idle
execution (running the precompute) lives in the dreaming sweep, not here.

Pure and deterministic: stdlib only, no DB / network / LLM. Recent turns are
plain strings and memories are plain dicts, so every function is unit-testable
and produces identical output for identical input.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List

# --- Tunables (module-level so behavior is explicit and testable) ------------

# Recency weight for the most-recent message; older messages decay linearly.
_MESSAGE_BASE_PRIORITY = 1.0
_MESSAGE_RECENCY_STEP = 0.1

# Salience floor for memory-derived questions and the bump per salience point.
_MEMORY_BASE_PRIORITY = 0.5
_MEMORY_SALIENCE_STEP = 0.25

# A quoted phrase is a stronger topic signal than a bare capitalized token.
_QUOTED_PHRASE_BONUS = 0.3

# Tokens that look capitalized but carry no topic value.
_STOPWORDS = frozenset(
    {
        "I",
        "A",
        "The",
        "This",
        "That",
        "These",
        "Those",
        "It",
        "We",
        "You",
        "They",
        "He",
        "She",
        "What",
        "When",
        "Where",
        "Why",
        "How",
        "Who",
        "Which",
        "Can",
        "Could",
        "Would",
        "Should",
        "Do",
        "Does",
        "Did",
        "Is",
        "Are",
        "Was",
        "Were",
        "Will",
        "Please",
        "Thanks",
        "Thank",
        "Ok",
        "Okay",
        "Yes",
        "No",
        "And",
        "But",
        "Or",
        "If",
        "So",
        "Then",
    }
)

# Capitalized noun-ish token: starts uppercase, allows internal caps/digits.
_CAP_TOKEN_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\b")
# Quoted phrase: single or double quotes, non-greedy, non-empty.
_QUOTED_RE = re.compile(r"[\"'“‘]([^\"'”’]+?)[\"'”’]")
_WS_RE = re.compile(r"\s+")


def sleeptime_enabled() -> bool:
    """Return whether sleep-time compute is enabled via ``FF_SLEEPTIME_COMPUTE``.

    Off by default (fail-closed). Truthy values: ``1``, ``true``, ``yes``, ``on``
    (case-insensitive, surrounding whitespace ignored).
    """
    return os.getenv("FF_SLEEPTIME_COMPUTE", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@dataclass(frozen=True)
class Anticipated:
    """A likely follow-up question, with why it was surfaced and its priority.

    ``priority`` is a deterministic score (higher = more worth precomputing);
    message-derived candidates are weighted by recency, memory-derived ones by
    salience.
    """

    question: str
    rationale: str
    priority: float


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace + strip trailing punctuation for dedup."""
    collapsed = _WS_RE.sub(" ", (text or "").strip()).lower()
    return collapsed.rstrip("?.!,; ")


def _clean_topic(topic: str) -> str:
    """Collapse internal whitespace in an extracted topic phrase."""
    return _WS_RE.sub(" ", (topic or "").strip())


def _message_candidates(recent_messages: List[str]) -> List[Anticipated]:
    """Derive candidate questions from recent message topics.

    More-recent messages (later in the list) weigh more. Quoted phrases score
    above bare capitalized tokens. Within a single message, the first-seen topic
    keeps the highest score for that message.
    """
    out: List[Anticipated] = []
    total = len(recent_messages)
    for idx, message in enumerate(recent_messages):
        if not message or not message.strip():
            continue
        # Recency: the last message (idx == total - 1) gets full weight.
        recency = max(0.0, total - 1 - idx)
        recency_weight = _MESSAGE_BASE_PRIORITY - (_MESSAGE_RECENCY_STEP * recency)
        if recency_weight <= 0.0:
            recency_weight = _MESSAGE_RECENCY_STEP  # floor so old topics still register

        seen_in_message: set[str] = set()

        for match in _QUOTED_RE.finditer(message):
            topic = _clean_topic(match.group(1))
            if not topic or topic.lower() in seen_in_message:
                continue
            seen_in_message.add(topic.lower())
            out.append(
                Anticipated(
                    question=f"Do you want to know more about {topic}?",
                    rationale=f"Quoted phrase {topic!r} in a recent message",
                    priority=round(recency_weight + _QUOTED_PHRASE_BONUS, 6),
                )
            )

        for match in _CAP_TOKEN_RE.finditer(message):
            topic = _clean_topic(match.group(1))
            if not topic:
                continue
            # Skip pure stopwords (single-word, in the stoplist).
            if " " not in topic and topic in _STOPWORDS:
                continue
            if topic.lower() in seen_in_message:
                continue
            seen_in_message.add(topic.lower())
            out.append(
                Anticipated(
                    question=f"Do you want to know more about {topic}?",
                    rationale=f"Topic {topic!r} mentioned in a recent message",
                    priority=round(recency_weight, 6),
                )
            )
    return out


def _memory_candidates(memories: List[Dict]) -> List[Anticipated]:
    """Derive candidate questions from memory categories/values.

    Recognized categories: ``goal`` (next-step prompt) and ``workflow_tag`` /
    ``workflow`` (re-run prompt). Priority is driven by the memory's salience
    (defaulting to a neutral 1.0 when absent).
    """
    out: List[Anticipated] = []
    for mem in memories:
        if not isinstance(mem, dict):
            continue
        category = str(mem.get("category", "") or "").strip().lower()
        value = mem.get("value")
        if value is None:
            value = mem.get("content", "")
        value = _clean_topic(str(value))
        if not value:
            continue

        try:
            salience = float(mem.get("salience", 1.0))
        except (TypeError, ValueError):
            salience = 1.0
        priority = round(_MEMORY_BASE_PRIORITY + (_MEMORY_SALIENCE_STEP * salience), 6)

        if category == "goal":
            out.append(
                Anticipated(
                    question=f"What's the next step toward {value}?",
                    rationale=f"Goal memory: {value}",
                    priority=priority,
                )
            )
        elif category in ("workflow_tag", "workflow"):
            out.append(
                Anticipated(
                    question=f"Want me to run the {value} workflow again?",
                    rationale=f"Workflow-tag memory: {value}",
                    priority=priority,
                )
            )
    return out


def anticipate_questions(
    recent_messages: List[str],
    memories: List[Dict],
    *,
    k: int = 5,
) -> List[Anticipated]:
    """Deterministically anticipate up to ``k`` likely follow-up questions.

    Candidates are derived from (a) recent message topics (capitalized noun-ish
    tokens and quoted phrases, weighted by recency) and (b) memory categories /
    values (``goal`` -> next-step prompt, ``workflow_tag`` -> re-run prompt,
    weighted by salience). Results are sorted by priority DESC, deduplicated by
    normalized question (first/highest-priority wins), and capped at ``k``.

    Pure and deterministic: identical inputs always yield identical output, and
    ties break on a stable secondary key (normalized question text) rather than
    on input order or hashing.
    """
    if k <= 0:
        return []

    candidates: List[Anticipated] = []
    candidates.extend(_message_candidates(recent_messages or []))
    candidates.extend(_memory_candidates(memories or []))

    # Stable, deterministic order: priority DESC, then normalized question ASC.
    candidates.sort(key=lambda a: (-a.priority, _normalize(a.question)))

    deduped: List[Anticipated] = []
    seen: set[str] = set()
    for cand in candidates:
        key = _normalize(cand.question)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(cand)
        if len(deduped) >= k:
            break
    return deduped


def precompute_plan(
    anticipated: List[Anticipated],
    *,
    budget: int = 3,
) -> List[Anticipated]:
    """Select the top ``budget`` anticipated questions worth precomputing now.

    Takes the highest-priority items (the input is expected to already be
    priority-sorted by :func:`anticipate_questions`, but this re-sorts defensively
    with the same stable key so it is correct on any input). Pure function.
    """
    if budget <= 0 or not anticipated:
        return []
    ordered = sorted(anticipated, key=lambda a: (-a.priority, _normalize(a.question)))
    return ordered[:budget]


def is_idle(
    last_activity_ms: int,
    now_ms: int,
    *,
    idle_after_ms: int = 300_000,
) -> bool:
    """Return True once the user has been idle for at least ``idle_after_ms``.

    Idle when ``now_ms - last_activity_ms >= idle_after_ms`` (default 5 minutes).
    The boundary is inclusive: exactly ``idle_after_ms`` elapsed counts as idle.
    """
    return (now_ms - last_activity_ms) >= idle_after_ms
