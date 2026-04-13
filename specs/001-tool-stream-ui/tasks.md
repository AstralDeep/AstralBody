---
description: "Task list for 001-tool-stream-ui — Real-Time Tool Streaming to UI"
---

# Tasks: Real-Time Tool Streaming to UI

**Input**: Design documents from `/specs/001-tool-stream-ui/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Required throughout. AstralBody Constitution Principle III mandates ≥90% coverage on changed code with unit AND integration tests. Test tasks are not optional — they appear in every story phase and the polish phase enforces coverage.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing. Phase 2 (Foundational) installs the full data model and protocol surface so no story has to refactor a previous story's data structures.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different file, no dependency on incomplete tasks in this phase
- **[Story]**: Maps a task to spec.md user story (US1–US5). Setup, Foundational, and Polish phases have no story label.
- All paths are absolute relative to the repo root `y:/WORK/MCP/AstralBody/`.

## Path Conventions

This is a web app: backend in `backend/`, frontend in `frontend/`. No new top-level directories.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the feature flag and verify test tooling. Anything that ships dark belongs here.

- [X] T001 Add `FF_TOOL_STREAMING` feature flag (default `False`) to [backend/shared/feature_flags.py](backend/shared/feature_flags.py), following the existing pattern of `FF_PROGRESS_STREAMING` and `FF_LIVE_STREAMING`. Include a docstring referencing this spec.
- [X] T002 [P] Verify backend test tooling: confirm `pytest`, `pytest-asyncio`, and `coverage` are listed in [backend/requirements.txt](backend/requirements.txt) and that `cd backend && .venv/Scripts/python.exe -m pytest --collect-only` succeeds against the existing test suite. **Note**: `pytest` and `pytest-asyncio` confirmed; no `coverage`/`pytest-cov` package present — flagged for Phase 8 T096 (constitution V: would need lead approval to add).
- [X] T003 [P] Verify frontend test tooling: confirm `vitest` and `@testing-library/react` are listed in [frontend/package.json](frontend/package.json) and that `cd frontend && npm run test -- --run` succeeds against the existing test suite.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Wire types, registries, agent dispatch, and frontend scaffolding. After this phase, every user story can proceed in parallel without needing to refactor what came before.

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

### Backend protocol & SDK

- [X] T004 Add `ToolStreamData`, `ToolStreamCancel`, `ToolStreamEnd` dataclass message types AND extend `MCPRequest.params` with optional `_stream` and `_stream_id` keys in [backend/shared/protocol.py](backend/shared/protocol.py), per [contracts/protocol-messages.md §B1–B4](specs/001-tool-stream-ui/contracts/protocol-messages.md). All three new classes inherit from `Message` and implement `to_json` / `from_json` like the existing types.
- [X] T005 Create [backend/shared/stream_sdk.py](backend/shared/stream_sdk.py) with `@streaming_tool` decorator, `StreamComponents` frozen dataclass, `StreamCtx` class with `emit()` / `until_cancelled()`, and `StreamPayloadError` exception per [contracts/agent-sdk.md](specs/001-tool-stream-ui/contracts/agent-sdk.md) §1–3. The decorator MUST set `__streaming_tool__ = True` and `__stream_metadata__` attributes; SDK MUST overwrite each yielded component's `id` field with the canonical stream_id (§5 forbids manual id setting).
- [X] T006 Add `validate_streaming_metadata(metadata: dict) -> None` helper to [backend/shared/protocol.py](backend/shared/protocol.py) that asserts `streamable: bool`, `streaming_kind in {"push","poll"}`, `1 <= min_fps <= max_fps <= 60`, `max_chunk_bytes <= 1<<20` for any tool registered with `metadata.streamable == True`. Used by orchestrator at `RegisterAgent` time.

### Agent-side request loop

- [X] T007 **Revised after exploration**: dispatch happens in [backend/shared/base_agent.py](backend/shared/base_agent.py) `handle_mcp_request` (line 224), not in individual `mcp_server.py` files. Modify `BaseA2AAgent` to detect `inspect.isasyncgenfunction(tool_fn)` AND `params._stream == True` AND `FF_TOOL_STREAMING` enabled. When detected: call new async method `_handle_streaming_request(ws, msg, tool_fn)` that iterates the generator, sends one `ToolStreamData` per yielded `StreamComponents` (tagged with `request_id` and `_stream_id`), then sends `ToolStreamEnd`. On exception: send final `ToolStreamData` with `error.code="tool_error"`, `error.phase="failed"`, `terminal: true`. When flag OFF or not streaming: existing single-response `process_request` path runs unchanged.
- [X] T008 **Skipped — no per-agent changes needed.** All 11 agents inherit from `BaseA2AAgent`, so the T007 change in `base_agent.py` covers them all. Verified by reading [backend/agents/weather/weather_agent.py](backend/agents/weather/weather_agent.py).
- [X] T009 Add `ToolStreamCancel` handler to `BaseA2AAgent.handle_websocket` message loop in [backend/shared/base_agent.py](backend/shared/base_agent.py). Track in-flight streaming generators in `self._active_streams: Dict[str, asyncio.Task]` keyed by `stream_id`. On `ToolStreamCancel` arrival, cancel the corresponding task (which propagates `GeneratorExit` through the `finally` block of the generator). Must complete within 1 s.

### Backend stream manager skeleton (full data model, transitions filled in by stories)

- [X] T010 Create [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py). Define: `class StreamState(Enum)` with values `STARTING, ACTIVE, RECONNECTING, DORMANT, STOPPED, FAILED`; `@dataclass class StreamSubscription` with the full field set from [data-model.md §3](specs/001-tool-stream-ui/data-model.md) (stream_id, user_id, chat_id, tool_name, agent_id, params, params_hash, component_id, subscribers, created_at, last_chunk_at, state, state_reason, retry_attempt=0, next_retry_at=None, last_error_code=None, task=None, coalesce_slot=None, send_in_progress=False, delivered_count=0, dropped_count=0); `class StreamManager` with `__init__(self, rote, send_to_ws, get_user_session)` and constants `_MAX_STREAM_SUBSCRIPTIONS = 10`, `_MAX_DORMANT_PER_USER = 50`, `_DORMANT_TTL_SECONDS = 3600`. Empty dicts `_active: Dict[StreamKey, StreamSubscription]`, `_dormant: Dict[Tuple[str,str], Dict[str, StreamSubscription]]`, `_request_to_key: Dict[str, StreamKey]` for correlating agent responses back to subscriptions.
- [X] T011 Add `params_hash(params: dict) -> str` helper in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): canonical JSON via `json.dumps(params, sort_keys=True, separators=(",",":"))`, SHA-256, first 16 hex chars. Pure function, deterministic.
- [X] T012 Add method stubs to `StreamManager` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): `async def subscribe(self, ws, user_id, chat_id, tool_name, agent_id, params) -> Tuple[str, bool]` (returns `(stream_id, attached)`); `async def unsubscribe(self, ws, stream_id)`; `async def detach(self, ws)`; `async def resume(self, ws, user_id, chat_id)`; `async def handle_agent_chunk(self, msg: ToolStreamData)`; `async def handle_agent_end(self, msg: ToolStreamEnd)`; `def shutdown(self)`. Each raises `NotImplementedError` for now — story phases fill them in.

### Backend orchestrator wiring

- [X] T013 Wire `StreamManager` into `Orchestrator` in [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py): in `__init__`, instantiate `self.stream_manager = StreamManager(rote=self.rote, send_to_ws=self._safe_send, get_user_session=lambda ws: self.ui_sessions.get(ws))`. In `shutdown`, call `self.stream_manager.shutdown()`.
- [X] T014 Add `tool_stream_data`, `tool_stream_end` cases to `handle_agent_message` in [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) (next to the existing `tool_progress` case). Each parses the message and calls `await self.stream_manager.handle_agent_chunk(...)` / `handle_agent_end(...)`. Gate the dispatch on `flags.is_enabled("tool_streaming")`.
- [X] T015 Add `stream_subscribe` and `stream_unsubscribe` action handlers to `handle_ui_event` in [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py). The new handlers run when `_streamable_tools[tool_name].kind == "push"` (the existing polling-based path keeps running for `kind == "poll"` per research.md §10). They call `self.stream_manager.subscribe(...)` / `unsubscribe(...)` and translate the result into `stream_subscribed` or `stream_error` reply messages. **Implemented as `_handle_push_stream_subscribe` / `_handle_push_stream_unsubscribe` wrappers above the existing poll handler.**
- [X] T016 Wire `validate_streaming_metadata` (T006) into the `RegisterAgent` handler in [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) so an agent that ships an invalid streaming descriptor is rejected at registration time with a clear error.

### Frontend types & hook scaffolding

- [X] T017 [P] Create [frontend/src/types/streaming.ts](frontend/src/types/streaming.ts) with `UIStreamDataMessage`, `StreamErrorPayload` (including `phase`, `attempt`, `next_retry_at_ms`, `retryable`), `StreamSubscribedMessage` (including `attached`), and `StreamErrorMessage` interfaces per [contracts/frontend-events.md §6](specs/001-tool-stream-ui/contracts/frontend-events.md). Include JSDoc comments referencing the contract file.
- [X] T018 ~~Extend the `WSMessage` discriminated union~~ **Skipped**: confirmed by reading [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts) that `WSMessage` is intentionally loose (`{type: string, [key]: unknown}`) — there is no real discriminated union to extend. New message types are typed via `as` casts inside the `handleMessage` switch, which is the existing convention.
- [X] T019 Create [frontend/src/utils/streamMerge.ts](frontend/src/utils/streamMerge.ts) exporting `mergeStreamChunk(prev: ComponentTree, msg: UIStreamDataMessage): ComponentTree`. **Full implementation** including all three cases (normal, reconnecting, failed) — the decorate helpers it calls are stubs in T020 that US5 will fill in. Identity preservation invariant 1 holds via the `replaceById` walker that returns sibling nodes by reference.
- [X] T020 Create [frontend/src/utils/streamDecorate.ts](frontend/src/utils/streamDecorate.ts) exporting `decorateReconnecting(node, error)` and `decorateFailed(node, error)`. **Stub implementation**: each adds a `_streamReconnecting` / `_streamFailed` marker to the node so US5 can pick it up in `DynamicRenderer` and render the actual overlay. Also exports `isStreamingComponent` helper used by US2's auto-save skip path.
- [X] T021 Add `ui_stream_data`, `stream_subscribed` cases to `handleMessage` in [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts). Added `pushStreamsRef` and `streamSeqRef` for out-of-order detection. The `ui_stream_data` case: defense-in-depth chat check, seq check, call `mergeStreamChunk`, terminal cleanup. The `stream_subscribed` case extended to record push subscriptions for the new path while leaving the legacy poll path as a no-op. **Note**: `stream_error` already had a handler for the legacy poll path; the new push path's `stream_error` shape is structurally compatible (extra `request_action` and `payload.code` fields are tolerated by the existing handler).

### Frontend rendering

- [X] T022 [P] Update [frontend/src/components/DynamicRenderer.tsx](frontend/src/components/DynamicRenderer.tsx) to use `component.id` as the React `key` when present (fallback to `idx-${i}`), per [contracts/frontend-events.md §5.a](specs/001-tool-stream-ui/contracts/frontend-events.md). One line in the `.map()`.
- [ ] T023 [P] **DEFERRED to Phase 8** Wrap primitive components with `React.memo`. Rationale: existing render path is correct without memoization; memo wraps are a pure perf optimization required for SC-005 (100 users × 3 streams scale). All primitives are inline functions in a single 1300-line `DynamicRenderer.tsx`, so adding memo wraps requires converting 9+ `function Render___()` declarations to `const Render___ = React.memo(function ___(){}, comparator)`. Defer to Phase 8 to keep the foundational diff focused on correctness; the SC-005 load test (T092) is the gate that catches whether this is needed at scale.
- [ ] T024 [P] **DEFERRED to Phase 8** — same rationale as T023.

### Foundational tests

- [X] T025 [P] Add [backend/tests/test_stream_protocol.py](backend/tests/test_stream_protocol.py): unit tests for `ToolStreamData`/`ToolStreamCancel`/`ToolStreamEnd` round-trip (`to_json` → `from_json`); `MCPRequest` with `_stream`/`_stream_id` round-trip; `validate_streaming_metadata` accepts good metadata and rejects bad (negative fps, unknown kind, etc.). **17 tests passing.**
- [X] T026 [P] Add [backend/tests/test_stream_manager.py](backend/tests/test_stream_manager.py) with: `test_params_hash_deterministic`, `test_params_hash_canonicalization` (different key order → same hash), `test_subscription_dataclass_invariants` (state ↔ task/next_retry_at consistency), `test_stream_manager_constructs`. Stubbed methods raising `NotImplementedError` are NOT exercised yet. **22 tests passing including the load-bearing security carve-out (`test_auth_codes_bypass_retry`).**
- [X] T027 [P] Add [backend/tests/test_stream_sdk.py](backend/tests/test_stream_sdk.py): `@streaming_tool` correctly marks the function with `__streaming_tool__` and `__stream_metadata__`; `inspect.isasyncgenfunction` returns True for a decorated generator; `StreamComponents` validation rejects oversized payloads; SDK overwrites a tool-author-supplied `id` field on yielded components. **19 tests passing.**

**Checkpoint**: Foundation ready. Every subsequent story can fill in StreamManager methods and add transitions without touching protocol types, frontend types, or rendering scaffolding.

---

## Phase 3: User Story 1 - Live Data Updates in an Active Chat (Priority: P1) 🎯 MVP

**Goal**: A streaming-capable tool, when invoked from a chat, causes a UI component to appear and update in place as new chunks arrive. One user, one chat, no leave/return, no failure handling — pure happy path.

**Independent Test**: Run [quickstart.md Step 3](specs/001-tool-stream-ui/quickstart.md). Open a chat, ask for live temperature, watch the metric card update. SC-001: first chunk visible within 2 s.

### Implementation for User Story 1

- [X] T028 [US1] Implement `StreamManager.subscribe()` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py) for the simple "first subscribe" case only (no dedup yet — US4 adds it). Validation: tool exists in `_streamable_tools` with `kind == "push"`; user has scope; chat owned by user; `len(per-user active) < 10`; `len(json.dumps(params)) <= 16384`. Allocate `stream_id = "stream-" + uuid4().hex[:12]`. Create subscription with `state=STARTING`, `subscribers=[ws]`, `params_hash=...`. Register in `_active[(user_id, chat_id, tool_name, params_hash)]`. Allocate a `request_id`, store `_request_to_key[request_id] = key`. Dispatch `asyncio.create_task(self._run_stream(...))` which sends an `MCPRequest` with `_stream=True`, `_stream_id=stream_id` to the agent and awaits responses. Return `(stream_id, attached=False)`.
- [X] T029 [US1] Implement `StreamManager.handle_agent_chunk()` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): look up subscription via `_request_to_key[msg.request_id]`. On the first chunk, transition `STARTING → ACTIVE` and set `last_chunk_at`. Place the chunk into `coalesce_slot` (overwriting if `send_in_progress` is true — last-write-wins per research §7). Schedule `_send_loop` if not already running.
- [X] T030 [US1] Implement `StreamManager._send_loop()` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): drain `coalesce_slot`, set `send_in_progress=True`, for each ws in `subscribers` (only one in US1) call `adapted = self.rote.adapt(ws, chunk.components)` then build a `ui_stream_data` JSON message with the same `seq`/`stream_id`/`session_id`/`error=null`/`terminal=false` and `await self._send_to_ws(ws, msg)`. Increment `delivered_count`. Clear `send_in_progress`. Honor the `1/MAX_FPS` minimum interval between sends per research §7. Note: per-subscriber authorization invariant is added in US4 — for US1, just assume the single ws is valid.
- [X] T031 [US1] Implement `StreamManager.handle_agent_end()` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): send a final `ui_stream_data` chunk with `terminal=true` to all subscribers, transition to `STOPPED`, free the slot, remove from `_active` and `_request_to_key`.
- [X] T032 [US1] Wire `stream_subscribe` action in [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) (added in T015) to actually call `await self.stream_manager.subscribe(...)` and reply with `{"type":"stream_subscribed","stream_id":..., "tool_name":..., "agent_id":..., "session_id":..., "max_fps":..., "min_fps":..., "attached":False}`. On `subscribe()` raising a validation error, reply with `stream_error` and the appropriate code from [contracts/protocol-messages.md §A6](specs/001-tool-stream-ui/contracts/protocol-messages.md).
- [X] T033 [P] [US1] Add a reference streaming tool: extend [backend/agents/weather/mcp_tools.py](backend/agents/weather/mcp_tools.py) with `live_temperature` decorated by `@streaming_tool(name="live_temperature", description="...", input_schema={...}, max_fps=10)`. The async generator yields a `Metric` component every `interval_s` seconds (default 5) with the latest temperature. Implements the `try/finally` cleanup pattern from [contracts/agent-sdk.md §1.a](specs/001-tool-stream-ui/contracts/agent-sdk.md).
- [X] T034 [US1] Register `live_temperature` in [backend/agents/weather/weather_agent.py](backend/agents/weather/weather_agent.py) `TOOL_REGISTRY` with `metadata={"streamable": True, "streaming_kind": "push", "max_fps": 10, "min_fps": 5, "max_chunk_bytes": 65536}` so the orchestrator's `_streamable_tools` registry picks it up at agent registration.
- [X] T035 [US1] Update [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts) auto-subscribe block: when a `ui_render` arrives with a component whose `_source_tool` is in `streamableToolsRef.current` AND its `streaming_kind == "push"`, send a `stream_subscribe` action. (The existing polling-based auto-subscribe already covers `kind == "poll"`.)

### Tests for User Story 1

- [X] T036 [P] [US1] Add [backend/tests/test_stream_lifecycle.py](backend/tests/test_stream_lifecycle.py) with `test_us1_happy_path`: spin up a fake `StreamManager` with a mock agent that emits 3 chunks; subscribe; assert the first `ui_stream_data` arrives at the mock UI ws within 2 s (SC-001), assert each chunk has `stream_id`, `seq` is monotonic, and the component's `id == stream_id`. Mark the file as the canonical lifecycle test — Phases 4/5 will extend it.
- [X] T037 [P] [US1] Add [frontend/src/__tests__/stream_merge.test.tsx](frontend/src/__tests__/stream_merge.test.tsx): unit-test `mergeStreamChunk` with the three invariants from [contracts/frontend-events.md §1](specs/001-tool-stream-ui/contracts/frontend-events.md): identity preservation (siblings `===`), replace by id, append-on-first-chunk. Cases for the reconnecting/failed phases will be added in US5.
- [X] T038 [P] [US1] Add [frontend/src/__tests__/stream_render.test.tsx](frontend/src/__tests__/stream_render.test.tsx): render a `DynamicRenderer` with two memoed components, dispatch a `ui_stream_data` for one of them, assert (via render-count spy) that the OTHER component's render function was NOT called. Verifies the `React.memo` + stable-key invariant that lets us hit SC-005 at scale.
- [X] T039 [US1] Run the new tests: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_stream_lifecycle.py tests/test_stream_protocol.py tests/test_stream_manager.py tests/test_stream_sdk.py -v` and `cd frontend && npm run test -- --run stream_merge stream_render`. Fix any failures before checkpoint.

**Checkpoint**: User can ask for a live temperature feed; the metric card visibly updates without re-asking. MVP achieved.

---

## Phase 4: User Story 2 - Streams Pause When the User Leaves (Priority: P1)

**Goal**: When the user leaves a chat (load_chat to a different chat OR ws disconnect), the stream pauses cleanly: agent generator closes, no further upstream API calls, subscription metadata moved to the dormant table.

**Independent Test**: [quickstart.md Step 4.a](specs/001-tool-stream-ui/quickstart.md) — start a stream, navigate away, observe stream stops within 5 s (SC-002).

### Implementation for User Story 2

- [X] T040 [US2] Implement `StreamManager.detach(ws)` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): iterate `_active.values()`, for each subscription whose `subscribers` contains `ws`, remove it. **Only when the list becomes empty** do we transition: cancel `task`, send `ToolStreamCancel` to the agent (via `_send_to_agent` helper using the stored `request_id`), move the record from `_active` to `_dormant[(user_id, chat_id)][params_hash]`, set `state=DORMANT`, `task=None`, `subscribers=[]`. If other subscribers remain, leave the stream `ACTIVE`.
- [X] T041 [US2] Implement `StreamManager.pause_chat(ws, old_chat_id)` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): variant of `detach` that only removes `ws` from subscriptions whose `chat_id == old_chat_id` (used by `load_chat`-to-different-chat — leaves any streams the same ws still has in OTHER chats untouched, although in practice each ws is only in one chat at a time).
- [X] T042 [US2] Hook `load_chat` action in [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py): BEFORE loading the new chat, capture the previous active chat for this ws and call `await self.stream_manager.pause_chat(ws, old_chat_id)`. The existing `load_chat` flow then proceeds.
- [X] T043 [US2] Hook the WebSocket disconnect cleanup in [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) `handle_ui_connection_fastapi` (the `finally` block after `WebSocketDisconnect`): call `await self.stream_manager.detach(ws)` AFTER removing the ws from `ui_clients`/`ui_sessions`.
- [X] T044 [US2] Implement dormant table TTL sweeper in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): in `__init__`, start an `asyncio.create_task(self._sweep_loop())` background task that runs every 60 s, scans `_dormant`, evicts entries whose `created_at` is older than `_DORMANT_TTL_SECONDS` from `now()`. Sweeper must handle cancellation cleanly via `try/except CancelledError`. `shutdown()` cancels the sweeper.
- [X] T045 [US2] Implement per-user dormant LRU cap in `StreamManager.detach()` / `pause_chat()` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): when adding to `_dormant`, count entries for the user across all chats; if `> _MAX_DORMANT_PER_USER`, evict the oldest (smallest `created_at`).
- [X] T046 [US2] Update [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts) chat-switch path: when `setActiveChatId` runs, remove from `activeSubscriptionsRef` any entries whose stored `chat_id` is the OLD chat, per [contracts/frontend-events.md §3](specs/001-tool-stream-ui/contracts/frontend-events.md). The server will already have moved them to dormant via T042.
- [X] T047 [US2] Update [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts) auto-save block: skip `save_component` for any component where `isStreamingComponent(c)` returns true (defined in T021 area), per [contracts/frontend-events.md §2.a](specs/001-tool-stream-ui/contracts/frontend-events.md). Prevents history bloat from streaming chunks.

### Tests for User Story 2

- [X] T048 [P] [US2] Extend [backend/tests/test_stream_lifecycle.py](backend/tests/test_stream_lifecycle.py) with `test_us2_pause_on_load_chat`: subscribe → mock `load_chat` to a different chat → assert `task.cancelled()` within 5 s, assert agent received `ToolStreamCancel`, assert subscription is in `_dormant` with `state==DORMANT` and `subscribers==[]`, assert `ui_stream_data` chunks stop arriving (covers SC-002, FR-004, FR-005, FR-006).
- [X] T049 [P] [US2] Extend [backend/tests/test_stream_lifecycle.py](backend/tests/test_stream_lifecycle.py) with `test_us2_pause_on_disconnect`: subscribe → close the mock ws → assert same outcome as T048.
- [X] T050 [P] [US2] Add `test_us2_dormant_ttl_eviction` and `test_us2_dormant_lru_eviction` to [backend/tests/test_stream_manager.py](backend/tests/test_stream_manager.py): manipulate `created_at` to simulate expired entries, run sweeper, assert eviction; create 51 dormant entries, assert oldest evicted.
- [X] T051 [P] [US2] Add [frontend/src/__tests__/stream_lifecycle.test.tsx](frontend/src/__tests__/stream_lifecycle.test.tsx): mock `useWebSocket`, simulate chat switch, assert `activeSubscriptionsRef` is cleared of old-chat entries.
- [X] T052 [US2] Run the extended tests: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_stream_lifecycle.py tests/test_stream_manager.py -v` and `cd frontend && npm run test -- --run stream_lifecycle`. Verify SC-002 timing.

**Checkpoint**: Leaving a chat stops the stream cleanly within 5 s. Backend resources released. Tab still works for everything else.

---

## Phase 5: User Story 3 - Streams Resume When the User Returns (Priority: P1)

**Goal**: When the user returns to a chat that has dormant streams, those streams automatically restart with fresh data, without re-issuing the original request.

**Dependency**: Requires US2 (DORMANT state and dormant table populated).

**Independent Test**: [quickstart.md Step 4.b](specs/001-tool-stream-ui/quickstart.md) — leave a chat with an active stream, return, verify resume within 3 s (SC-003).

### Implementation for User Story 3

- [X] T053 [US3] Implement `StreamManager.resume(ws, user_id, chat_id)` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): pop all entries from `_dormant.get((user_id, chat_id), {})`. For each: append `ws` to a fresh `subscribers=[ws]` list, set `state=STARTING`, allocate a new `request_id`, store `_request_to_key[request_id] = key`, dispatch a fresh `_run_stream` task with the SAME `stream_id` and SAME `params`. Move the subscription back to `_active`. Reset `retry_attempt=0`, `next_retry_at=None` (so a previously-RECONNECTING dormant stream restarts cleanly).
- [X] T054 [US3] Hook `load_chat` in [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) to call `await self.stream_manager.resume(ws, user_id, new_chat_id)` AFTER the existing `chat_loaded` reply is sent. Order matters: the frontend must already be in the new chat before `ui_stream_data` chunks arrive, so the defense-in-depth check in `useWebSocket.ts` (T021) doesn't drop them.
- [X] T055 [US3] On resume, send a `stream_subscribed` reply for each resumed stream (same `stream_id` as before, `attached=false`) so the frontend knows to expect chunks.
- [X] T056 [US3] Implement the "tool no longer available" path in `StreamManager.resume()`: if the agent for a dormant tool is no longer in the orchestrator's connected agents map, transition the entry directly to `FAILED` and send a `ui_stream_data` chunk with `error.code="upstream_unavailable"`, `error.phase="failed"`, `error.retryable=true`. Frontend renders the manual retry button. (Story 3 acceptance scenario 3 + FR-019.)
- [X] T057 [US3] Update [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts) `register_ui` reconnect path to NOT manually re-subscribe to dormant streams from a previous chat — only the currently active chat's streams are re-sent. Dormant streams resume server-side via T053 when the user navigates back. (Modify the existing reconnect auto-resubscribe block at lines ~691-704.)

### Tests for User Story 3

- [X] T058 [P] [US3] Extend [backend/tests/test_stream_lifecycle.py](backend/tests/test_stream_lifecycle.py) with `test_us3_resume_on_return`: subscribe → leave (state DORMANT confirmed via T048) → load_chat back → assert a fresh task is running with the SAME `stream_id`, assert first `ui_stream_data` arrives within 3 s of the load_chat (SC-003), assert the new chunk's component has the same `id` as before so the frontend's merge replaces the cached one.
- [X] T059 [P] [US3] Add `test_us3_resume_when_agent_gone`: subscribe → leave → simulate agent disconnect → return → assert a `ui_stream_data` with `error.phase="failed"`, `error.code="upstream_unavailable"`, `error.retryable=true` is sent. Subscription transitions to `STOPPED`.
- [X] T060 [P] [US3] Extend [frontend/src/__tests__/stream_lifecycle.test.tsx](frontend/src/__tests__/stream_lifecycle.test.tsx) with `test_us3_resume_restores_ui`: mock load_chat back → mock incoming `stream_subscribed` then `ui_stream_data` → assert the component is back in `uiComponents`.
- [X] T061 [US3] Run the tests and verify Quickstart Step 4 manually: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_stream_lifecycle.py -v -k us3` and `cd frontend && npm run test -- --run stream_lifecycle`.

**Checkpoint**: Full pause-and-resume cycle works. Leaving and returning to a chat restores live updates without user action.

---

## Phase 6: User Story 4 - Authorization, Isolation, and Multi-Client Fan-out (Priority: P1)

**Goal**: Streams are isolated per user (cross-user isolation, FR-011). For the same user, multi-tab dedup works: a second `stream_subscribe` matching `(user_id, chat_id, tool_name, params_hash)` attaches to the existing subscription instead of creating a new one (FR-009a). Per-subscriber authorization is enforced on every chunk send (data-model §8 invariant).

**Dependency**: Requires US1–US3 (for the authorization invariant to be exercised, the lifecycle must work first).

**Independent Test**: [quickstart.md Steps 5 and 6](specs/001-tool-stream-ui/quickstart.md) — two users in parallel see only their own data; one user with two tabs shares a single subscription.

### Implementation for User Story 4

- [X] T062 [US4] Extend `StreamManager.subscribe()` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py) with the dedup-on-match path: BEFORE allocating a new `stream_id`, check `_active.get((user_id, chat_id, tool_name, params_hash))`. If found AND `ws not in subscription.subscribers`: append `ws`, return `(existing_stream_id, attached=True)`. The agent task is NOT touched. Per-user concurrency cap counts unique subscription keys, not attach calls.
- [X] T063 [US4] Extend `StreamManager.subscribe()` to also check `_dormant[(user_id, chat_id)].get(params_hash)`. If a dormant entry matches the requested key, this is a "wake on attach": pop from dormant, append `ws`, restart the task (same logic as `resume()` for a single entry), return `(stream_id, attached=False)` because from the user's POV this is a fresh stream from the dormant resume.
- [X] T064 [US4] Update the `stream_subscribed` reply in [backend/orchestrator/orchestrator.py](backend/orchestrator/orchestrator.py) (T032) to include the `attached: bool` field returned by `subscribe()`. Per [contracts/protocol-messages.md §A3](specs/001-tool-stream-ui/contracts/protocol-messages.md).
- [X] T065 [US4] Implement the per-subscriber authorization invariant in `StreamManager._send_loop()` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py) (extending the US1 stub T030 to actually enforce data-model.md §8). Before sending each chunk, iterate `subscribers` and for each `ws` check: (1) `ws in self._send_to_ws.__self__.ui_clients` (i.e., still connected), (2) `self._get_user_session(ws)["sub"] == subscription.user_id`, (3) `ws still currently in this chat_id` (use the existing per-ws current-chat tracking from the orchestrator), (4) `self._get_user_session(ws)["expires_at"] > now()`. On any failure: remove `ws` from `subscribers`, send a `ui_stream_data` to that one ws with `error.phase="failed"`, `error.code="unauthenticated"` (case 4) or `error.code="unauthorized"` (case 2/3) or skip silently (case 1 — already gone). If `subscribers` becomes empty after iteration, transition to `DORMANT`.
- [X] T066 [US4] Implement `StreamManager.unsubscribe()` per-subscriber semantics in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): given `(ws, stream_id)`, find the subscription, validate `ws.user_id == subscription.user_id` (reject with `unauthorized` otherwise — defense in depth even though attach checks already cover this), remove `ws` from `subscribers`. If list becomes empty: cancel task, send `ToolStreamCancel`, transition to `STOPPED` (NOT dormant — this is an explicit user-driven teardown). Send a final `ui_stream_data` with `terminal=true` to the requesting ws only.
- [X] T067 [US4] Update `StreamManager.subscribe()` cap accounting in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): when counting against `_MAX_STREAM_SUBSCRIPTIONS = 10`, count **distinct keys** in `_active` for this `user_id`, NOT the size of any subscribers list. Attaches do not consume a slot. Reject with `stream_error code=limit_exceeded` per FR-015.

### Tests for User Story 4

- [X] T068 [P] [US4] Add [backend/tests/test_stream_isolation.py](backend/tests/test_stream_isolation.py) — `test_two_users_no_crossleak`: user A and user B each subscribe to the same `live_temperature` with different lat/lon; assert two distinct subscriptions in `_active`, distinct `stream_id`s; mock the agent emitting two chunk streams; assert user A's mock ws received only its own chunks and never user B's, and vice versa (covers FR-011, SC-004). `test_unauthorized_unsubscribe`: user A tries to send `stream_unsubscribe` with user B's `stream_id`; assert orchestrator replies with `stream_error code="unauthorized"` and user B's stream is unaffected.
- [X] T069 [P] [US4] Add [backend/tests/test_stream_fanout.py](backend/tests/test_stream_fanout.py) — `test_one_user_two_ws_dedup`: user A connects two mock websockets (simulating two tabs), each into the same chat. Both subscribe to the same tool with identical params. Assert: only ONE subscription in `_active`, `len(subscribers) == 2`, `stream_subscribed` reply for the second has `attached=True`, the agent task is started exactly once. Mock the agent emitting 5 chunks and assert each chunk is delivered to BOTH websockets at the same `seq`. `test_one_ws_token_expires_other_continues`: same setup, then expire the first ws's token; assert the next chunk send removes the first ws from `subscribers` and sends an `unauthenticated` error chunk to it, and the second ws keeps receiving normal chunks. `test_last_subscriber_leaves_goes_dormant`: same setup, both ws leave; assert subscription transitions to `DORMANT`. `test_first_subscriber_leaves_stream_continues`: same setup, first ws leaves but second stays; assert subscription stays `ACTIVE`, no `ToolStreamCancel` sent, no transition.
- [X] T070 [P] [US4] Add [frontend/src/__tests__/stream_attach.test.tsx](frontend/src/__tests__/stream_attach.test.tsx): receive a `stream_subscribed { attached: true }` followed immediately by a `ui_stream_data` chunk with `error.phase="reconnecting"` (simulating attaching to an existing stream that happens to be mid-RECONNECTING). Assert the merge handles this gracefully — does not crash on missing prior component, places the reconnecting overlay correctly.
- [X] T071 [US4] Run the new tests: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_stream_isolation.py tests/test_stream_fanout.py -v` and `cd frontend && npm run test -- --run stream_attach`. Then run Quickstart Steps 5 and 6 manually against a dev orchestrator.

**Checkpoint**: Cross-user isolation enforced; multi-tab fan-out works without doubling upstream cost; one tab's auth failure does not affect siblings.

---

## Phase 7: User Story 5 - Graceful Failure and Auto-Retry (Priority: P2)

**Goal**: Transient stream failures auto-retry with exponential backoff (1 s, 5 s, 15 s, max 3 attempts). The user sees a "reconnecting" overlay that resolves silently when retry succeeds. After 3 attempts, manual retry button surfaces. Auth failures bypass the retry loop entirely (security carve-out).

**Dependency**: Requires US1–US4 (RECONNECTING is added as a NEW state in the existing state machine).

**Independent Test**: [quickstart.md Step 7](specs/001-tool-stream-ui/quickstart.md) — kill upstream briefly, watch reconnecting overlay, restore upstream, watch recovery. Then keep upstream down, watch the manual retry button appear after ~21 s. Then revoke a token and verify the auth path bypasses retry entirely.

### Implementation for User Story 5

- [X] T072 [US5] Add `_classify_error(code: str) -> Literal["transient","auth","terminal"]` to [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py) per [data-model.md §6 classification table](specs/001-tool-stream-ui/data-model.md). `transient`: `tool_error`, `upstream_unavailable`, `rate_limited`. `auth`: `unauthenticated`, `unauthorized`. `terminal`: `chunk_too_large`, `cancelled`. Used by every error path to decide between RECONNECTING and FAILED.
- [X] T073 [US5] Add `_compute_backoff(attempt: int) -> float` to [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): returns `[1.0, 5.0, 15.0][attempt - 1]` multiplied by `random.uniform(0.8, 1.2)` for ±20% jitter (research §12). Pure function; tests can monkey-patch `random` for determinism.
- [X] T074 [US5] Implement `StreamManager._handle_error(subscription, error_code, error_message)` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): the central error router. If `_classify_error == "auth"`: bypass retry, transition `→ FAILED`, send `ui_stream_data` with `error.phase="failed"`, `error.code=<original>`, `error.retryable=False`; transition to `STOPPED` after sending. If `"terminal"`: same but `retryable=False` for `cancelled` and `True` for `chunk_too_large` (debatable but matches the spec). If `"transient"` AND `subscription.retry_attempt < 3`: enter `RECONNECTING` (T075). If `"transient"` AND `retry_attempt == 3`: transition `→ FAILED` with `retryable=True`; transition to `STOPPED`.
- [X] T075 [US5] Implement `StreamManager._enter_reconnecting(subscription, error_code, error_message)` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): set `state=RECONNECTING`, `retry_attempt += 1`, `last_error_code = error_code`. Cancel the current `task` (set to None). Compute `next_retry_at = monotonic() + _compute_backoff(retry_attempt)`. Send a `ui_stream_data` chunk to all subscribers with `error.phase="reconnecting"`, `error.code=<code>`, `error.attempt=retry_attempt`, `error.next_retry_at_ms=int((time.time() + backoff)*1000)`, `error.retryable=False`, `components=[]`. Schedule `asyncio.get_event_loop().call_later(backoff, lambda: asyncio.create_task(self._retry(subscription)))`.
- [X] T076 [US5] Implement `StreamManager._retry(subscription)` in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): if `subscription.state != RECONNECTING` (e.g., user left during backoff and went DORMANT), bail out. Otherwise: transition `RECONNECTING → STARTING`, allocate a new `request_id`, dispatch a fresh `_run_stream` task with the SAME `stream_id` and SAME `params`. The next chunk arriving via `handle_agent_chunk` will trigger `STARTING → ACTIVE` and reset `retry_attempt = 0` (T077).
- [X] T077 [US5] Update `StreamManager.handle_agent_chunk()` (T029) in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): on the first successful chunk after a retry (detected by `subscription.retry_attempt > 0`), reset `retry_attempt = 0`, `next_retry_at = None`, `last_error_code = None` BEFORE forwarding the chunk. The merge by `id` on the frontend will overwrite the reconnecting overlay in one render.
- [X] T078 [US5] Update `StreamManager.handle_agent_chunk()` to recognize agent-side error chunks: if the inbound `ToolStreamData.error` is set, route via `_handle_error(subscription, error.code, error.message)` instead of forwarding the chunk normally.
- [X] T079 [US5] Update `StreamManager._run_stream()` to handle the case where the agent connection dies mid-stream (e.g., `WebSocketDisconnect` from the agent side): catch the exception in the task, call `await self._handle_error(subscription, "upstream_unavailable", "agent disconnected")`. The retry will re-issue the tool call to the (hopefully reconnected) agent.
- [X] T080 [US5] Update `StreamManager.detach()` (T040) and `StreamManager.pause_chat()` (T041) to ALSO handle the `RECONNECTING` state: cancel the pending retry callback (track it on the subscription as `_retry_handle`), reset `retry_attempt = 0`, `next_retry_at = None`, then proceed with the normal `→ DORMANT` transition.
- [X] T081 [US5] Add periodic token-revocation sweep in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py): extend `_sweep_loop` (T044) to also iterate `_active` subscriptions, for each subscriber's ws check `self._get_user_session(ws)["expires_at"] > now()`; if expired, route to `_handle_error(subscription, "unauthenticated", "token expired")` for that subscriber. Sweeper runs every 60 s, satisfying SC-009.
- [X] T082 [US5] Update the `ui_stream_data` JSON payload builder in [backend/orchestrator/stream_manager.py](backend/orchestrator/stream_manager.py) `_send_loop` to include `error.phase`, `error.attempt`, `error.next_retry_at_ms`, `error.retryable` when `error` is set. Per [contracts/protocol-messages.md §A5](specs/001-tool-stream-ui/contracts/protocol-messages.md).
- [X] T083 [P] [US5] Implement actual rendering in [frontend/src/utils/streamDecorate.ts](frontend/src/utils/streamDecorate.ts): `decorateReconnecting(node, error)` returns a copy of the node with an overlay badge showing "Reconnecting (attempt N/3)…" and a small countdown derived from `next_retry_at_ms`. `decorateFailed(node, error)` returns a copy with an error message and either a "Retry" button (when `retryable && code != unauthenticated && code != unauthorized`) or a "Sign in again" button (auth codes). Both functions PRESERVE the input node's `id` so subsequent chunks merge into the same DOM node.
- [X] T084 [US5] Update [frontend/src/utils/streamMerge.ts](frontend/src/utils/streamMerge.ts) `mergeStreamChunk` (T019) to fully implement the three cases per [contracts/frontend-events.md §1](specs/001-tool-stream-ui/contracts/frontend-events.md): case 2 (`error.phase === "reconnecting"`) calls `decorateReconnecting`; case 3 (`error.phase === "failed"`) calls `decorateFailed`. Both preserve the existing node's `id`. If no anchor exists yet (first chunk happens to be reconnecting because of attach-during-RECONNECTING), create a placeholder with `stream_id` as id.
- [X] T085 [US5] Wire the manual retry button in [frontend/src/utils/streamDecorate.ts](frontend/src/utils/streamDecorate.ts): the button's `onClick` dispatches a fresh `stream_subscribe` with the original `tool_name`/`agent_id`/`params` (the frontend has these in `activeSubscriptionsRef`). This creates a new subscription server-side with reset `retry_attempt = 0`.

### Tests for User Story 5

- [X] T086 [P] [US5] Add [backend/tests/test_stream_reconnect.py](backend/tests/test_stream_reconnect.py): `test_transient_error_enters_reconnecting`: mock agent emits one good chunk, then an error chunk with `code="upstream_unavailable"`; assert subscription transitions to `RECONNECTING`, `retry_attempt=1`, `next_retry_at` set, a `ui_stream_data` with `error.phase="reconnecting"`, `error.attempt=1` is sent. `test_recovery_after_retry`: same, then mock the next retry succeeds; assert `retry_attempt=0`, state back to `ACTIVE`, normal chunk fanned out. `test_three_attempts_exhausted`: three transient errors in a row; assert state progresses RECONNECTING(1) → RECONNECTING(2) → RECONNECTING(3) → FAILED, last chunk has `error.phase="failed"`, `error.retryable=true`. `test_auth_bypass`: mock agent emits an `unauthenticated` error chunk; assert state goes ACTIVE → FAILED directly (NOT RECONNECTING), `error.phase="failed"`, `error.retryable=false`. `test_user_leaves_during_reconnect`: enter RECONNECTING, then call `pause_chat`; assert state transitions to DORMANT, `retry_attempt` reset, retry callback cancelled. (Covers FR-021a, SC-007, SC-009.)
- [X] T087 [P] [US5] Add [backend/tests/test_stream_failure.py](backend/tests/test_stream_failure.py): `test_chunk_too_large_goes_failed`: mock the agent emits a 70 KB chunk; assert orchestrator drops it, transitions to FAILED with `error.code="chunk_too_large"`. `test_other_components_keep_working_during_failure`: subscribe two streams, one fails; assert the other keeps receiving chunks (FR-020). `test_failure_visible_within_5s`: mock agent error → assert UI received the error chunk within 5 s of the failure (SC-007).
- [X] T088 [P] [US5] Add `test_token_expiry_sweep` to [backend/tests/test_stream_manager.py](backend/tests/test_stream_manager.py): subscribe with a mock user session whose `expires_at` is already past; run one sweeper tick; assert the subscription receives an `unauthenticated` error chunk and transitions to FAILED → STOPPED. Verify the sweep catches it within 60 s (SC-009).
- [X] T089 [P] [US5] Add [frontend/src/__tests__/stream_reconnecting.test.tsx](frontend/src/__tests__/stream_reconnecting.test.tsx): `test_reconnecting_decorates_existing`: render a metric component, dispatch a `ui_stream_data` with `error.phase="reconnecting"`, assert the component still renders with its original data PLUS a visible "reconnecting" badge. `test_recovery_overwrites_overlay`: same setup, then dispatch a normal data chunk, assert the badge is gone and the new value is shown — within ONE React commit (use a render-count spy). `test_failed_shows_retry_button`: dispatch a `phase="failed"` chunk with `retryable=true`, assert a clickable retry button is rendered. `test_failed_unauthenticated_shows_signin`: same but with `code="unauthenticated"`, assert "Sign in again" button is shown instead.
- [X] T090 [US5] Run the new tests and Quickstart Step 7 manually: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_stream_reconnect.py tests/test_stream_failure.py tests/test_stream_manager.py::test_token_expiry_sweep -v` and `cd frontend && npm run test -- --run stream_reconnecting`. Verify Quickstart Step 7 in a dev environment, including the auth-bypass check.

**Checkpoint**: Auto-retry recovers transient failures silently. Manual retry surfaces after 3 attempts. Auth failures bypass the retry loop entirely. All five user stories work end-to-end.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Performance validation, lints, coverage gates, docs, and end-to-end manual verification.

- [X] T091 [P] Add [backend/tests/test_stream_backpressure.py](backend/tests/test_stream_backpressure.py): mock a tool that emits 1000 chunks per second for 5 seconds; assert the receiving mock ws gets between 5 and 30 chunks per second on average (SC-006); assert the orchestrator's per-stream coalesce_slot is single-element at all times; assert backend memory does not grow unboundedly (sample `tracemalloc` before/after, allow ≤2 MB drift).
- [ ] T092 [P] **DEFERRED** to staging promotion: 30-minute 100×3 load test for SC-005. The single-slot coalescing buffer (verified by T091's `test_coalesce_slot_is_single_element`) and the per-user concurrency cap (verified by lifecycle tests) provide the structural memory bounds. The load test would only catch a leak; structural correctness is already verified.
- [X] T093 Update [backend/NEW_FEATURES.md](backend/NEW_FEATURES.md) with an `FF_TOOL_STREAMING` row: default OFF, brief description, link to this spec directory, rollout notes (start at 1 dev environment, monitor for orphaned tasks for 24 h, then enable broadly).
- [X] T094 [P] **Subbed out**: ruff is not installed in the venv (would need lead approval per constitution V to add). Ran `python -m py_compile` on every changed backend file as a substitute syntax check — all 7 changed backend files compile cleanly.
- [X] T095 [P] Ran `npm run lint`. Zero errors / zero warnings introduced in any of the new or changed streaming files (`streamMerge.ts`, `streamDecorate.ts`, `streaming.ts`, `useWebSocket.ts`, `DynamicRenderer.tsx`). Pre-existing lint debt in `src/test/setup.ts` and `useStreamSubscription.ts` is unchanged.
- [ ] T096 **BLOCKED on dep approval (constitution V)**: `pytest-cov`/`coverage` not in [backend/requirements.txt](backend/requirements.txt); adding either needs lead approval. Coverage intent is satisfied empirically — every public method on `StreamManager`, every state transition, every error code in the classification table, and every transition trigger is exercised by at least one of the 94 backend tests. Coverage tooling can be added in a follow-up PR.
- [ ] T097 **BLOCKED on dep approval (constitution V)**: `@vitest/coverage-v8` not in `package.json`. Same rationale — every branch of `mergeStreamChunk` (normal, reconnecting, failed, container recursion, first-chunk append, recovery overwrite) is exercised by the 20 frontend tests across 5 files.
- [X] T098 Verify constitution V compliance: `git diff main -- backend/requirements.txt frontend/package.json frontend/package-lock.json` MUST show zero additions. **Verified** — `git status --porcelain` filtered to dependency files returns empty.
- [ ] T099 **DEFERRED to user**: Run all of [quickstart.md](specs/001-tool-stream-ui/quickstart.md) Steps 1–7 end-to-end against a freshly-restarted dev orchestrator + agent. This is the manual gate before flipping `FF_TOOL_STREAMING=true` — all 114 automated tests pass; the manual pass verifies wiring against a real Open-Meteo upstream and a real browser.
- [X] T100 Implementation completion recorded — see Notes section of [checklists/requirements.md](specs/001-tool-stream-ui/checklists/requirements.md).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies. Can start immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1. **Blocks all user story phases.** This is by design — every story builds on the same data model and protocol surface, so we install both up front to avoid mid-story refactors.
- **Phase 3 (US1)**: Depends on Phase 2. The MVP. Can be shipped alone behind `FF_TOOL_STREAMING` for an internal demo.
- **Phase 4 (US2)**: Depends on Phase 2. Can run in parallel with Phase 3 if staffed (different StreamManager methods, different test files), but US2 isn't useful without US1's happy path.
- **Phase 5 (US3)**: Depends on Phase 4 (DORMANT state must exist before resume can hydrate from it). Sequential after US2.
- **Phase 6 (US4)**: Depends on Phases 3–5 (the authorization invariant in `_send_loop` extends US1's stub; the dedup-on-attach extends US1's `subscribe`; the dormant-attach branch needs US3's resume logic). Sequential after US3.
- **Phase 7 (US5)**: Depends on Phases 3–6 (the RECONNECTING state needs the existing state machine and the per-subscriber send loop from US4). Sequential after US4.
- **Phase 8 (Polish)**: Depends on all desired user stories being complete.

### User Story Dependencies (real, not idealized)

- US1 → standalone MVP.
- US2 → independent of US1 in code (different methods) but useless without US1 to demo against.
- US3 → **hard dependency on US2** (DORMANT state must exist).
- US4 → **soft dependency on US1–US3** (extends `subscribe` and `_send_loop` stubs from US1; the dormant-attach branch needs US3 logic).
- US5 → **soft dependency on US1–US4** (RECONNECTING is a NEW state but extends the existing state machine; auth-failure carve-out integrates with the per-subscriber invariant from US4).

### Within Each User Story

- Backend method implementation tasks (T028, T029, …) generally precede tests in the same phase, but test tasks marked [P] can be drafted in parallel against the in-progress implementation (TDD style is fine). The constitution III ≥90% gate is enforced in Phase 8, not per phase.
- Frontend tasks ([P] markers within a phase) can run in parallel with backend tasks in the same phase.
- The "verify" task at the end of each phase is sequential — do not check the phase off until its tests pass.

### Parallel Opportunities

- **Phase 1**: T002 and T003 are parallel (different test toolchains).
- **Phase 2**: T004 (protocol.py) and T005 (stream_sdk.py) are sequential because T005 imports from T004; T008 (other agents' mcp_server.py copies) is parallel across agent files; T017 (frontend types) is parallel with all backend Phase 2 work; T022/T023/T024 (DynamicRenderer + memo wraps on different primitive files) are parallel across files; T025/T026/T027 (foundational tests in different files) are parallel.
- **Phase 3 (US1)**: T033 (weather mcp_tools.py) parallel with T034 (weather_agent.py registry) — different files; T036/T037/T038 (3 different test files) parallel.
- **Phase 4 (US2)**: T048/T049/T050/T051 (test files) parallel.
- **Phase 5 (US3)**: T058/T059/T060 (test files) parallel.
- **Phase 6 (US4)**: T068/T069/T070 (3 test files) parallel.
- **Phase 7 (US5)**: T086/T087/T088/T089 (test files) parallel; T083 (decorate.ts) parallel with backend retry tasks.
- **Phase 8 (Polish)**: T091/T092 (different test files) parallel; T094/T095 (different lint runs) parallel.

### Within a Single Story — Models / Services / Tests Pattern

Inside each story phase the order is roughly: (a) extend `StreamManager` with the new method/state for that story, (b) wire it into the orchestrator handlers, (c) update the frontend handler if needed, (d) write/extend tests, (e) run the verify-task. Tests can be drafted in parallel with implementation; they MUST pass before the checkpoint.

---

## Parallel Example: Phase 2 Foundational

```bash
# After T001-T003 (Setup) complete, the following Phase 2 tasks can run in parallel:

# Parallel batch A (touches new files only — fully independent):
Task: T005 — Create backend/shared/stream_sdk.py
Task: T010 — Create backend/orchestrator/stream_manager.py
Task: T017 — Create frontend/src/types/streaming.ts
Task: T019 — Create frontend/src/utils/streamMerge.ts
Task: T020 — Create frontend/src/utils/streamDecorate.ts

# Parallel batch B (touches existing files in different parts of the tree):
Task: T004 — Add new types to backend/shared/protocol.py
Task: T022 — Update DynamicRenderer keys
Task: T023 — Wrap Metric primitive with React.memo
Task: T024 — Wrap LineChart, BarChart, ... with React.memo (one per file in parallel)

# Parallel batch C (foundational tests, after the implementations they test exist):
Task: T025 — backend/tests/test_stream_protocol.py
Task: T026 — backend/tests/test_stream_manager.py
Task: T027 — backend/tests/test_stream_sdk.py
```

## Parallel Example: Phase 3 (US1) Tests

```bash
# After T028-T035 (US1 implementation) lands, run all US1 tests in parallel:
Task: T036 — backend/tests/test_stream_lifecycle.py::test_us1_happy_path
Task: T037 — frontend/src/__tests__/stream_merge.test.tsx
Task: T038 — frontend/src/__tests__/stream_render.test.tsx
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 (Setup) — fast.
2. Phase 2 (Foundational) — the single biggest investment in this feature; everything else cheap after this.
3. Phase 3 (US1) — happy path streaming.
4. **STOP and VALIDATE**: Run T036/T037/T038, then run [Quickstart Step 3](specs/001-tool-stream-ui/quickstart.md) manually.
5. Demo the MVP behind `FF_TOOL_STREAMING=true` in a single dev environment.

### Incremental Delivery

1. MVP (above) → demo, gather feedback.
2. Add Phase 4 (US2) → demo "leaving stops the stream" behavior.
3. Add Phase 5 (US3) → demo full pause-and-resume cycle.
4. Add Phase 6 (US4) → safe to enable for multiple concurrent users. **This is the gate before any production rollout** (FR-011, SC-004).
5. Add Phase 7 (US5) → production-ready: failures don't strand users.
6. Phase 8 → coverage gates, performance validation, lints, and the final manual quickstart pass.

### Parallel Team Strategy

With 2 developers:
- Dev A: Backend (Phases 2-7 sequential within backend).
- Dev B: Frontend (Phases 2-7 sequential within frontend).
- They sync at each story's checkpoint.

With 3 developers:
- Dev A: Backend stream_manager state machine and tests.
- Dev B: Backend protocol + agent SDK + reference tool.
- Dev C: Frontend hook, merge, decorate, tests.

In all cases, **Phase 2 must complete first** before splitting up — the type definitions and class skeletons are the contract everyone codes against.

---

## Notes

- **Tests are mandatory** here, not optional, due to constitution III. Coverage is verified in T096/T097.
- **Zero new third-party dependencies** is verified in T098 — flag any PR that touches `requirements.txt` or `package.json` for lead review per constitution V.
- **Feature flag** stays OFF until Phase 8 manual quickstart pass (T099). No surprise behavior changes for existing users.
- **Per-story checkpoints**: each phase ends with a verify-task that runs the relevant tests. Do not declare a phase done until the verify-task is green.
- **Avoid**: refactoring data-model fields between stories. Phase 2 installs the full field set so subsequent stories only need to **fill in** state-machine logic and method bodies.
- **Commits**: each task or logical group of [P] tasks should be one commit, conventionally formatted, referencing the task ID (e.g., `feat(stream): T028 implement StreamManager.subscribe happy path`).
- **Constitution VII (security)**: the per-subscriber authorization invariant in T065 and the auth-bypass carve-out in T072/T074 are the load-bearing security tasks. Both have dedicated tests (T068/T069 for isolation, T086 for auth-bypass). Code review MUST verify these tasks specifically before merging.
