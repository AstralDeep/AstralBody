"""
Hook/Event System — Extensible lifecycle events for the orchestrator.

Hooks allow external code to observe and modify orchestrator behavior
without changing the orchestrator source. Inspired by Claude Code's
PreToolUse / PostToolUse / SessionStart pattern.

Usage:
    manager = HookManager()
    manager.register(HookEvent.PRE_TOOL_USE, my_audit_hook)

    # In orchestrator code:
    response = await manager.emit(HookContext(
        event=HookEvent.PRE_TOOL_USE,
        user_id="...",
        agent_id="...",
        tool_name="search_patients",
        tool_args={"query": "..."},
    ))
    if response.action == "block":
        # Don't execute the tool
        ...

Hook handlers are async callables: async (HookContext) -> Optional[HookResponse]
"""
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable, Dict, List, Optional

logger = logging.getLogger("Orchestrator.Hooks")


class HookEvent(str, Enum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    POST_TOOL_FAILURE = "post_tool_failure"
    PERMISSION_DENIED = "permission_denied"
    AGENT_REGISTERED = "agent_registered"
    AGENT_DISCONNECTED = "agent_disconnected"


@dataclass
class HookContext:
    """Context passed to hook handlers."""
    event: HookEvent
    user_id: str = ""
    agent_id: str = ""
    tool_name: str = ""
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HookResponse:
    """Response returned by hook handlers to modify orchestrator behavior.

    Actions:
      - "continue": proceed normally (default)
      - "block": prevent the action (only meaningful for PRE_TOOL_USE)
      - "modify": proceed with modified tool args
    """
    action: str = "continue"
    modified_args: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


# Type alias for hook handler callables
HookHandler = Callable[[HookContext], Awaitable[Optional[HookResponse]]]


class HookManager:
    """Registry and dispatcher for lifecycle hooks."""

    def __init__(self):
        self._hooks: Dict[HookEvent, List[HookHandler]] = defaultdict(list)

    def register(self, event: HookEvent, handler: HookHandler):
        """Register a hook handler for a specific event."""
        self._hooks[event].append(handler)
        logger.info(f"Hook registered: {event.value} -> {handler.__name__}")

    def unregister(self, event: HookEvent, handler: HookHandler):
        """Remove a previously registered hook handler."""
        handlers = self._hooks.get(event, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, context: HookContext) -> HookResponse:
        """Emit an event and run all registered handlers.

        Handlers run in registration order. For PRE_TOOL_USE events, the first
        handler that returns "block" or "modify" wins — subsequent handlers
        still run but cannot override a block.

        Returns the merged HookResponse.
        """
        handlers = self._hooks.get(context.event, [])
        if not handlers:
            return HookResponse()

        final = HookResponse()

        for handler in handlers:
            try:
                response = await handler(context)
                if response is None:
                    continue

                # "block" takes highest priority
                if response.action == "block" and final.action != "block":
                    final.action = "block"
                    final.reason = response.reason
                    logger.info(
                        f"Hook {handler.__name__} blocked {context.event.value}: "
                        f"tool={context.tool_name} reason={response.reason}"
                    )

                # "modify" only applies if not already blocked
                if response.action == "modify" and final.action == "continue":
                    final.action = "modify"
                    final.modified_args = response.modified_args

            except Exception as e:
                logger.error(
                    f"Hook handler {handler.__name__} failed for "
                    f"{context.event.value}: {e}"
                )

        return final

    @property
    def registered_events(self) -> List[HookEvent]:
        """Return list of events that have at least one handler registered."""
        return [event for event, handlers in self._hooks.items() if handlers]
