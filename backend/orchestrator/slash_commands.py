"""Feature 068 (US5) — user-typed /slash-commands.

A curated, first-party command set. A leading ``/command`` typed in chat is
expanded into a normal prompt BEFORE any processing, so the rewritten turn flows
through the exact same permission / audit / PHI / taint gates as any message —
slash commands are a convenience, never a privileged bypass (they never invoke
a tool directly; they only shape the prompt the model then acts on under the
user's existing scopes).

Unknown or malformed commands produce a friendly relay (the model tells the user
it wasn't recognized and lists the available commands) rather than an error.
A leading ``/`` that is not a clean command token (e.g. a file path
``/usr/local/bin``) is left untouched and treated as ordinary text.
"""
from __future__ import annotations

import re
from typing import Dict, List

#: Command name → spec. ``template(args) -> prompt`` shapes the LLM-facing text.
_COMMAND_NAME = re.compile(r"[a-z][a-z0-9_-]*")


def _t_help(_args: str) -> str:
    listing = "; ".join(f"{c['usage']} — {c['description']}" for c in _ordered())
    return ("The user asked for help with slash commands. Briefly tell them the "
            f"available commands are: {listing}.")


def _t_agents(_args: str) -> str:
    return ("List the agents currently enabled for me and, in one line each, what "
            "they can help with. If none are enabled, say so and explain how to enable one.")


def _t_summarize(args: str) -> str:
    target = args or "the content I will provide next"
    return f"Please summarize the following clearly and concisely: {target}"


def _t_research(args: str) -> str:
    topic = args or "the topic I will provide next"
    return (f"Research the following and give me a concise, cited brief: {topic}. "
            "Use web research tools and do not fabricate sources.")


def _t_weather(args: str) -> str:
    where = args or "my location"
    return f"What's the current weather and short-term forecast for: {where}?"


COMMANDS: Dict[str, Dict] = {
    "help": {"usage": "/help", "description": "show available commands", "template": _t_help},
    "agents": {"usage": "/agents", "description": "list your enabled agents", "template": _t_agents},
    "summarize": {"usage": "/summarize <url|text>", "description": "summarize a link or text", "template": _t_summarize},
    "research": {"usage": "/research <topic>", "description": "research + cited brief", "template": _t_research},
    "weather": {"usage": "/weather <location>", "description": "weather + forecast", "template": _t_weather},
}


def _ordered() -> List[Dict]:
    return [COMMANDS[n] for n in COMMANDS]


def command_list() -> List[Dict]:
    """Public command metadata for discovery surfaces (name + usage + description)."""
    return [{"name": n, "usage": c["usage"], "description": c["description"]}
            for n, c in COMMANDS.items()]


def parse(message: str):
    """Return ``(name, args)`` for a recognizable ``/command`` token, else ``None``.

    Only a LEADING slash followed by a clean command-style token is treated as a
    command; a leading slash that is part of a path or other text returns None.
    """
    if not message:
        return None
    stripped = message.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped[1:].split(maxsplit=1)
    if not parts:
        return None
    name = parts[0].lower()
    if not _COMMAND_NAME.fullmatch(name):
        return None  # e.g. "/usr/local/bin" — not a command, leave as text
    args = parts[1].strip() if len(parts) > 1 else ""
    return name, args


def expand_message(message: str) -> str:
    """Expand a ``/command`` into an LLM-facing prompt.

    Returns the original message unchanged when it is not a command token.
    Recognized commands return their expanded prompt; an unrecognized clean
    command token returns a friendly relay listing the available commands. The
    result is always a prompt string — never a direct tool invocation.
    """
    parsed = parse(message)
    if parsed is None:
        return message
    name, args = parsed
    cmd = COMMANDS.get(name)
    if cmd is None:
        listing = ", ".join(f"/{n}" for n in COMMANDS)
        return (f'The user typed an unrecognized command "/{name}". Briefly tell '
                f"them it isn't a known command and list the available ones: {listing}.")
    return cmd["template"](args)
