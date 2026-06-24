"""Feature 068 (US1) — in-process registry of the bundled first-party agents.

The nine first-party agents that ship with the product run *inside* the
orchestrator process (no per-agent uvicorn port) when ``FF_INPROCESS_AGENTS`` is
on. This module discovers and instantiates them (without calling ``.run()``),
then registers them through the orchestrator's normal ``register_agent`` path
(``websocket=None``) so the card, tool→scope map, security flags, ownership, and
ECIES public key are all set up exactly as for a networked agent — and records
each live instance in ``orchestrator.local_agents`` for the dispatch branch.

Externally-hosted A2A agents and user-created draft agents are untouched: the
in-process path is selected only by a positive ``local_agents`` membership check.
"""
from __future__ import annotations

import importlib
import inspect
import logging
import os
from typing import List, Optional

logger = logging.getLogger("LocalAgents")

#: The nine bundled first-party agent directory names. ``etf_tracker_1`` was
#: retired in feature 068. This is the canonical built-in set (BUILT_IN_AGENT_IDS
#: equivalent) referenced by the in-process registry.
BUILT_IN_AGENT_DIRS = (
    "connectors",
    "dice_roller",
    "general",
    "journal_review",
    "medical",
    "ml_services",
    "summarizer",
    "weather",
    "web_research",
)


def _agents_root() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "agents")


def discover_built_in_agent_dirs(agents_root: Optional[str] = None) -> List[str]:
    """Return the bundled agent dir names that are present with an agent module."""
    root = agents_root or _agents_root()
    found = []
    for name in BUILT_IN_AGENT_DIRS:
        d = os.path.join(root, name)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, f"{name}_agent.py")):
            found.append(name)
    return found


def _load_agent_class(dir_name: str):
    """Import ``agents.<dir>.<dir>_agent`` and return its BaseA2AAgent subclass."""
    from shared.base_agent import BaseA2AAgent

    mod = importlib.import_module(f"agents.{dir_name}.{dir_name}_agent")
    for _, obj in inspect.getmembers(mod, inspect.isclass):
        if issubclass(obj, BaseA2AAgent) and obj is not BaseA2AAgent and obj.__module__ == mod.__name__:
            return obj
    return None


async def register_built_ins(orch) -> List[str]:
    """Instantiate + register every bundled built-in agent in-process.

    Returns the list of agent ids registered. Per-agent failures are logged and
    skipped (never fatal). Idempotent: re-registering an already-present agent
    simply refreshes its registration side-effects.
    """
    from shared.protocol import RegisterAgent

    registered: List[str] = []
    for dir_name in discover_built_in_agent_dirs():
        try:
            cls = _load_agent_class(dir_name)
            if cls is None:
                logger.warning("Feature 068: no BaseA2AAgent subclass found in '%s'", dir_name)
                continue
            agent = cls()  # builds the MCP server + ECIES keys; does NOT start uvicorn
            await orch.register_agent(
                None,
                RegisterAgent(agent_card=agent.card, api_key=os.getenv("AGENT_API_KEY") or None),
            )
            orch.local_agents[agent.card.agent_id] = agent
            registered.append(agent.card.agent_id)
        except Exception:  # noqa: BLE001 — a bad agent must not break the others or boot
            logger.exception("Feature 068: failed to load built-in agent '%s' in-process", dir_name)
    if registered:
        logger.info("Feature 068: %d built-in agents registered in-process: %s",
                    len(registered), registered)
    return registered
