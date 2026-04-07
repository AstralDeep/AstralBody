"""
Message Compaction — Intelligent context window management.

When the conversation history approaches the LLM context limit, older turns
are summarized into a compact representation while preserving tool-call /
tool-result pairing integrity.

Inspired by Claude Code's auto-compaction strategy.
"""
import json
import logging
from typing import List, Dict, Optional, Tuple, Callable, Awaitable

logger = logging.getLogger("Orchestrator.Compaction")

# Rough chars-per-token heuristic (conservative — errs on the side of
# compacting earlier rather than blowing the context window).
CHARS_PER_TOKEN = 4

# Default budget: 80% of model context window (in tokens).
DEFAULT_CONTEXT_BUDGET_RATIO = 0.80

# Known context window sizes by model family keyword.
_MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5": 16_384,
    "llama-3.2-90b": 131_072,
    "llama-3.1": 131_072,
    "llama-3": 8_192,
    "deepseek": 65_536,
    "qwen": 32_768,
    "mistral": 32_768,
    "mixtral": 32_768,
}

# Fallback if model is unknown
_DEFAULT_CONTEXT_WINDOW = 32_768


def estimate_tokens(messages: List[Dict]) -> int:
    """Estimate the token count for a list of OpenAI-style messages."""
    total_chars = 0
    for msg in messages:
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                total_chars += len(json.dumps(content))
        else:
            # ChatCompletionMessage object — serialize it
            total_chars += len(str(msg))
    return total_chars // CHARS_PER_TOKEN


def get_context_window(model_name: str) -> int:
    """Look up context window size for a model name."""
    model_lower = model_name.lower()
    for keyword, size in _MODEL_CONTEXT_WINDOWS.items():
        if keyword in model_lower:
            return size
    return _DEFAULT_CONTEXT_WINDOW


def _identify_turns(messages: List[Dict]) -> List[List[int]]:
    """Group messages into atomic turns that should never be split.

    A turn is:
      - A single user message, OR
      - A single system message, OR
      - An assistant message followed by any tool-result messages that
        reference tool_calls in that assistant message.

    Returns a list of turns, where each turn is a list of message indices.
    """
    turns: List[List[int]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")

        if role == "assistant":
            # Group assistant + its tool results
            turn_indices = [i]
            j = i + 1
            while j < len(messages):
                next_msg = messages[j]
                next_role = next_msg.get("role", "") if isinstance(next_msg, dict) else getattr(next_msg, "role", "")
                if next_role == "tool":
                    turn_indices.append(j)
                    j += 1
                else:
                    break
            turns.append(turn_indices)
            i = j
        else:
            turns.append([i])
            i += 1

    return turns


async def compact_messages(
    messages: List[Dict],
    model_name: str,
    llm_call: Callable,
    budget_ratio: float = DEFAULT_CONTEXT_BUDGET_RATIO,
    min_recent_turns: int = 4,
) -> Tuple[List[Dict], bool]:
    """Compact message history if it exceeds the token budget.

    Args:
        messages: Full message list (system + history + current user).
        model_name: Model identifier for context window lookup.
        llm_call: Async callable(messages, tools_desc=None) -> (response, usage).
                  Used to generate the summary via the LLM.
        budget_ratio: Fraction of context window to use as budget.
        min_recent_turns: Minimum number of recent turns to always preserve.

    Returns:
        (possibly_compacted_messages, was_compacted)
    """
    context_window = get_context_window(model_name)
    budget_tokens = int(context_window * budget_ratio)
    current_tokens = estimate_tokens(messages)

    if current_tokens <= budget_tokens:
        return messages, False

    logger.info(
        f"Compaction triggered: {current_tokens} tokens > {budget_tokens} budget "
        f"(model={model_name}, window={context_window})"
    )

    # Identify the system prompt (always index 0) and the current user message (always last)
    system_msg = messages[0] if messages else None
    current_user_msg = messages[-1] if messages else None

    # Everything in between is history
    history = messages[1:-1] if len(messages) > 2 else []
    if not history:
        return messages, False

    # Group into turns
    turns = _identify_turns(history)

    # Preserve the most recent N turns
    if len(turns) <= min_recent_turns:
        return messages, False

    compact_turn_count = len(turns) - min_recent_turns
    compact_indices = set()
    for turn in turns[:compact_turn_count]:
        compact_indices.update(turn)

    # Extract messages to summarize
    to_summarize = [history[i] for i in sorted(compact_indices)]
    preserved = [history[i] for i in range(len(history)) if i not in compact_indices]

    # Build summarization prompt
    summary_input = []
    for msg in to_summarize:
        if isinstance(msg, dict):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "role", "unknown")
            content = getattr(msg, "content", "")
        if isinstance(content, list):
            content = json.dumps(content)
        # Truncate very long individual messages for the summary call
        if len(str(content)) > 3000:
            content = str(content)[:3000] + "... [truncated]"
        summary_input.append(f"[{role}]: {content}")

    summary_prompt = [
        {
            "role": "system",
            "content": (
                "Summarize the following conversation history into a concise paragraph. "
                "Preserve all factual results, data points, file paths, and key decisions. "
                "Do NOT include tool names, turn counts, or system mechanics. "
                "Write as a factual summary that would help an AI assistant continue the conversation."
            ),
        },
        {
            "role": "user",
            "content": "\n\n".join(summary_input),
        },
    ]

    try:
        response, _ = await llm_call(None, summary_prompt)
        if response and hasattr(response, "content") and response.content:
            summary_text = response.content
        else:
            summary_text = "Prior conversation context was summarized but the summary could not be generated."
    except Exception as e:
        logger.warning(f"Compaction LLM call failed: {e}")
        # Fallback: just drop the old messages with a note
        summary_text = f"[{compact_turn_count} earlier conversation turns were removed to fit context window]"

    # Build compacted message list
    summary_msg = {
        "role": "system",
        "content": f"[Summary of prior conversation]:\n{summary_text}",
    }

    compacted = [system_msg, summary_msg, *preserved, current_user_msg]

    new_tokens = estimate_tokens(compacted)
    logger.info(
        f"Compaction complete: {current_tokens} → {new_tokens} tokens "
        f"({compact_turn_count} turns summarized, {min_recent_turns} preserved)"
    )

    return compacted, True
