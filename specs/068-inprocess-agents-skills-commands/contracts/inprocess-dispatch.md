# Contract: In-Process Dispatch (local-agent registry + loopback transport)

## LocalAgentRegistry (orchestrator/local_agents.py)

Owns the in-process built-in fleet. Built at orchestrator boot when `FF_INPROCESS_AGENTS` is on.

- `discover() -> list[str]`: enumerate the bundled first-party agent directories (the nine; `etf_tracker_1` removed) by the same `*_agent.py` convention `start.py` uses.
- `instantiate(agent_id) -> BaseA2AAgent`: import the agent class and construct it WITHOUT calling `.run()`/uvicorn. The instance owns its ECIES private key (`backend/data/agent_keys/<agent_id>.pem`) and predecessor fallback keys, its `MCPServer`, and its `AgentCard`.
- `register_into(orchestrator)`: replicate the registration side-effects `register_agent` performs over WS — store the card, build the tool→scope map, run `tool_security.analyze_agent` to populate `security_flags`, auto-assign ownership (`is_public=true`) — but for an in-process object. Records the agent in `orchestrator.local_agents[agent_id] = instance`. Does NOT perform the `AGENT_API_KEY` WS handshake (tracked posture note 1).
- `is_local(agent_id) -> bool`: positive registry check used at the dispatch seam.

## Dispatch branch (orchestrator/_execute_via_websocket)

```
if self.local_agents.is_local(agent_id):
    return await self._execute_in_process(agent_id, request, timeout)
# else existing WS path (external A2A / any non-local)
```

`_execute_in_process(agent_id, request, timeout)` MUST:

1. Resolve `agent = self.local_agents[agent_id]`.
2. Build a `LoopbackSocket` bound to the orchestrator's running loop + this request's chat/user context.
3. Run the agent-side pre-steps exactly as `base_agent.handle_mcp_request` does for `tools/call`: decrypt `_credentials` inside the agent (its own key; preserve `_credentials_stale`), build `AgentRuntime(ws=loopback, msg=request, agent_id, loop)`, inject `_runtime` into `arguments`, and apply the agent's per-server kwarg filtering.
4. `result = await asyncio.wait_for(asyncio.to_thread(agent.mcp_server.process_request, request), timeout)` (preserve `TOOL_TIMEOUT_OVERRIDES`).
5. Catch tool exceptions and classify retryable/non-retryable identically to `mcp_server._classify_error`.
6. Return the `MCPResponse` (result, ui_components, error{code,message,retryable}); `correlation_id` is set by the caller as today.

For streaming tools, mirror `_dispatch_stream_request`: launch the agent's streaming generator as a task that emits `ToolStreamData` into the `LoopbackSocket`; honor `ToolStreamCancel` → cancel the generator task (`_handle_stream_cancel`).

For long-running tools, the unary call returns the agent's prompt "started" response; the `JobPoller` continues and emits terminal `ToolProgress` through the loopback.

## LoopbackSocket (shared/local_transport.py)

Implements the subset the agent side uses: `send_text(str)`, `send_json(dict)`, and a `client` attribute (for audit-shaped callers). On each frame it decodes the message type and calls:

- `ToolProgress` → `orchestrator._handle_tool_progress(...)` (fan-out to the user's chat sockets, terminal → workspace persist + concurrency-cap release).
- `ToolStreamData` / `ToolStreamEnd` → `StreamManager.handle_agent_chunk` / `handle_agent_end`.
- `MCPResponse` frames are NOT sent over the loopback for unary calls (the response is returned directly).

It captures the orchestrator's running loop at construction so worker-thread emitters (`agent_runtime`, `stream_sdk`) can `run_coroutine_threadsafe`.

## Invariants (MUST hold; covered by tests)

- Identical `MCPResponse` shape and `correlation_id` propagation vs the WS path.
- `execute_single_tool` remains the entry, so all gates + `ToolDispatchAudit` are unchanged.
- Blocking tool bodies run via `to_thread` (no event-loop stall).
- Concurrency cap acquire-pre-dispatch / release-on-terminal preserved.
- Per-agent kwarg filtering preserved (no stray `_runtime`/`_credentials` into tools that reject them).
- External A2A + draft subprocess paths untouched; selection is the positive `is_local` check only.
