"""Context engineering — 033 Wave-0 (C-N16).

Two pure, opt-in helpers for keeping the chat ReAct loop's context window
cache-stable and lean. Both are *fail-open* and produce **byte-identical**
output to the legacy code path unless explicitly engaged, so they are safe to
land dormant behind ``FF_CONTEXT_ENGINEERING`` (default off):

1. :func:`compose_system_prompt` — assemble the chat system prompt with the
   per-turn-volatile sections (the file-mapping list, the live-canvas listing)
   moved to the *end*, leaving a deterministic, stable instruction prefix at
   the front. A stable prefix is what a KV-cache / prefix-cache keys on, so the
   most-volatile content (the canvas listing changes every turn) no longer
   invalidates the cached reasoning preamble.

2. :func:`edit_context` — in-loop context editing: once a tool-calling loop has
   produced several rounds of output, the *older* tool results are rarely
   needed verbatim (the model has already observed and acted on them) yet they
   dominate the token budget and pin volatile — often untrusted — text in the
   window. This replaces the *content* of stale tool-role messages with a short
   tombstone while preserving each message's ``role`` / ``tool_call_id`` /
   ``name`` so the assistant→tool pairing the Chat Completions API requires
   stays intact.

The reasoning-budget knob named in the C-N16 cluster already shipped as C-U12
(``_call_llm(reasoning_effort=…)``); the catalog tool-search / ``defer_loading``
meta-tool sub-item is intentionally left for a follow-on (it changes tool
dispatch, out of scope for a Wave-0 quick win).

No new third-party dependency (Constitution V).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("Orchestrator.ContextEngineering")

# Placeholder marks embedded in the chat system-prompt template in
# ``orchestrator.py`` where the two volatile sections are interpolated. Using
# opaque marks (not ``str.format`` fields) keeps the template robust to literal
# braces elsewhere in the prompt text.
FILE_CONTEXT_MARK = "%%ASTRAL_FILE_CONTEXT%%"
CANVAS_CONTEXT_MARK = "%%ASTRAL_CANVAS_CONTEXT%%"

# Default tombstone text substituted for stale tool output.
TOMBSTONE = "[older tool output cleared to save context]"


def compose_system_prompt(
    template: str,
    *,
    file_context: str = "",
    canvas_context: str = "",
    cache_stable: bool = False,
) -> str:
    """Render the chat system-prompt ``template``.

    ``template`` carries :data:`FILE_CONTEXT_MARK` and
    :data:`CANVAS_CONTEXT_MARK` where the two volatile sections sit today.

    * ``cache_stable=False`` (default): substitute each mark in place —
      **byte-identical** to the legacy ``f""`` interpolation.
    * ``cache_stable=True``: blank the marks (leaving a deterministic
      instruction prefix) and append the non-empty volatile sections, in a
      fixed order (file context, then canvas), at the very end.

    Pure; never raises on normal inputs.
    """
    file_context = file_context or ""
    canvas_context = canvas_context or ""
    if not cache_stable:
        return template.replace(FILE_CONTEXT_MARK, file_context).replace(
            CANVAS_CONTEXT_MARK, canvas_context
        )
    core = template.replace(FILE_CONTEXT_MARK, "").replace(CANVAS_CONTEXT_MARK, "")
    trailing = [s.strip() for s in (file_context, canvas_context) if s and s.strip()]
    if trailing:
        core = core.rstrip() + "\n\n" + "\n\n".join(trailing) + "\n"
    return core


def _role_of(msg: Any) -> str:
    """Role of an OpenAI-style message that may be a dict or a
    ``ChatCompletionMessage`` object (the assistant turn the loop appends)."""
    if isinstance(msg, dict):
        return msg.get("role", "") or ""
    return getattr(msg, "role", "") or ""


def _content_len(msg: Dict[str, Any]) -> int:
    content = msg.get("content")
    if isinstance(content, str):
        return len(content)
    if content is None:
        return 0
    try:
        return len(str(content))
    except Exception:  # pragma: no cover - defensive
        return 0


def edit_context(
    messages: List[Any],
    *,
    keep_last_tool_rounds: int = 3,
    min_tombstone_chars: int = 400,
    tombstone: str = TOMBSTONE,
) -> Tuple[List[Any], int]:
    """Tombstone stale tool outputs in a running ReAct ``messages`` list.

    A *tool round* advances at each ``assistant`` message (the model turn that
    issued the tool calls). Tool-role messages belonging to rounds older than
    the most recent ``keep_last_tool_rounds`` have their ``content`` replaced
    with ``tombstone`` — but only when the existing content is at least
    ``min_tombstone_chars`` long (tiny outputs cost nothing to keep, and
    tombstoning them would just add noise without saving tokens).

    Returns ``(new_messages, n_tombstoned)``. The input list and its message
    dicts are never mutated — tombstoned messages are shallow-copied. Only the
    ``content`` field changes, so ``role`` / ``tool_call_id`` / ``name`` (the
    fields the API pairs on) are preserved. System / user / assistant messages
    are never touched. Total over malformed input: anything unexpected is
    passed through unchanged.
    """
    if not isinstance(messages, list) or not messages:
        return messages, 0

    # Tag each tool message with the round it belongs to (rounds advance at
    # every assistant message). Track the highest round seen for tool output.
    round_idx = 0
    tool_rounds: Dict[int, int] = {}  # message index -> round
    max_tool_round = -1
    for i, msg in enumerate(messages):
        role = _role_of(msg)
        if role == "assistant":
            round_idx += 1
        elif role == "tool":
            tool_rounds[i] = round_idx
            if round_idx > max_tool_round:
                max_tool_round = round_idx

    if max_tool_round < 0:
        return messages, 0  # no tool output to edit

    cutoff = max_tool_round - keep_last_tool_rounds  # rounds <= cutoff are stale
    if cutoff < 0:
        return messages, 0  # everything is within the keep window

    out: List[Any] = list(messages)
    n = 0
    for i, rnd in tool_rounds.items():
        if rnd > cutoff:
            continue
        msg = out[i]
        if not isinstance(msg, dict):
            continue
        if msg.get("content") == tombstone:
            continue  # already tombstoned — idempotent
        if _content_len(msg) < min_tombstone_chars:
            continue
        edited = dict(msg)
        edited["content"] = tombstone
        out[i] = edited
        n += 1
    return out, n
