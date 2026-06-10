"""Strip reasoning/channel control markup that some models leak into text.

Harmony-style serving stacks (gpt-oss and compatible local servers) frame
model output as channels::

    <|channel|>analysis<|message|>…thinking…<|end|>
    <|start|>assistant<|channel|>final<|message|>the actual reply

When the server fails to consume those control tokens they arrive verbatim in
``message.content`` — sometimes with a pipe dropped on one side
(``<|channel>``, ``<channel|>``). Reasoning models similarly leak
``<think>…</think>`` blocks. ``strip_reasoning_markup`` removes the markers
and drops reasoning-channel content, keeping only the reply meant for the
user. Pure stdlib, conservative (a pipe is required on at least one side so
ordinary angle-bracket text is never touched), and idempotent on clean text.
"""
from __future__ import annotations

import re

# Control-token names from the Harmony format.
_NAMES = r"(?:start|channel|message|constrain|end|return|call)"
# A control token, tolerant of one missing pipe: <|channel|>, <|channel>, <channel|>.
_TOKEN = re.compile(rf"<\|{_NAMES}\|>|<\|{_NAMES}>|<{_NAMES}\|>", re.IGNORECASE)
_CHANNEL = r"(?:<\|channel\|>|<\|channel>|<channel\|>)"
_MESSAGE = r"(?:<\|message\|>|<\|message>|<message\|>)"

# A reasoning channel and everything inside it, up to the next channel marker
# (usually the final channel) or end of string.
_REASONING_BLOCK = re.compile(
    rf"{_CHANNEL}\s*(?:analysis|thought|thinking|commentary|reflection)\b"
    rf".*?(?={_CHANNEL}|\Z)",
    re.IGNORECASE | re.DOTALL,
)
# The final-channel header — its content IS the reply, so only the header goes.
_FINAL_HEADER = re.compile(rf"{_CHANNEL}\s*final\s*{_MESSAGE}?", re.IGNORECASE)
# <|start|>assistant role prefixes.
_START_ROLE = re.compile(
    r"(?:<\|start\|>|<\|start>|<start\|>)\s*(?:assistant|user|system|tool)?",
    re.IGNORECASE,
)
# DeepSeek/Qwen-style closed reasoning blocks.
_THINK_BLOCK = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.IGNORECASE | re.DOTALL)


def strip_reasoning_markup(text):
    """Return ``text`` with leaked reasoning/control markup removed.

    Non-string and markup-free input is returned unchanged. If stripping
    would leave nothing (e.g. the whole reply sat in a thought channel with
    no final channel), the content is kept and only the control tokens are
    removed — a slightly noisy reply beats an empty one.
    """
    if not isinstance(text, str) or "<" not in text:
        return text
    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = _REASONING_BLOCK.sub("", cleaned)
    cleaned = _FINAL_HEADER.sub("", cleaned)
    cleaned = _START_ROLE.sub("", cleaned)
    cleaned = _TOKEN.sub("", cleaned)
    cleaned = cleaned.strip()
    if cleaned:
        return cleaned
    fallback = _TOKEN.sub("", _THINK_BLOCK.sub("", text)).strip()
    return fallback
