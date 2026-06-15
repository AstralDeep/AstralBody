# Contract: Memory Meta-Tool Module (FR-007/FR-008)

New module `backend/orchestrator/memory_chat.py`, mirroring `backend/orchestrator/scheduling_chat.py`. Makes the existing `personalization/memory_tools.py` reachable as LLM tool calls, in addition to the existing passive prompt-injected recall.

## Module surface (mirrors scheduling_chat.py)

```python
META_AGENT_ID = "__memory__"

def should_inject(user_id: str) -> bool:
    """True when memory is enabled/scoped for this user (else tools are hidden)."""

def meta_tool_definitions() -> list[dict]:
    """Tool schemas injected into the chat LLM tool list:
       - remember(content, ...)        -> store a non-PHI memory
       - memory_search(query, ...)     -> search stored memories
       - memory_get(id)                -> fetch a specific memory
       (capture_signal optional)
    """

async def handle_meta_tool(orch, user_id, tool_name, arguments) -> dict:
    """Dispatch a memory tool call to personalization/memory_tools.py through the
       PHI gate + audit, returning a result/UI payload. Mirrors
       scheduling_chat.handle_meta_tool dispatch semantics."""
```

## Injection point

Injected into the chat LLM tool list at the same orchestrator site that injects the scheduling/agentic-creation meta-tools (`orchestrator.py` ~lines 2814-2820), and dispatched at the `agent_id == META_AGENT_ID` branch (~lines 4199-4210) alongside `__scheduler__` / `__orchestrator__`.

## Behavior requirements

- `remember` MUST pass content through the existing PHI gate; disallowed content is refused (not persisted) and the refusal is graceful + audited (FR-008).
- Tool availability MUST respect the user's enablement/scope (`should_inject`).
- All operations MUST be audited (existing audit class).
- MUST NOT duplicate or replace the passive recall prompt fragment (that stays).
- Structured log/metric emitted on memory write (FR-017).

## Tests

- Unit: `meta_tool_definitions()` shape; `should_inject` gating; `handle_meta_tool` dispatch + PHI refusal.
- Integration: LLM tool-call round-trip (remember → memory_get/search) via the orchestrator path.
