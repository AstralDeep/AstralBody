# Implementation Plan: Real-Time Tool Streaming to UI

**Branch**: `001-tool-stream-ui` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-tool-stream-ui/spec.md`
**Revised**: 2026-04-09 — incorporating spec Clarifications session (FR-009a multi-client fan-out, FR-021a automatic retry with backoff, FR-012 60s revocation bound, FR-015 explicit caps, FR-006 explicit "tab focus is not a leave signal"). See [research.md §11 and §12](research.md) for the new design decisions.

## Summary

Enable agent tools to push a continuous stream of updates into a specific UI component inside the user's currently active chat session. Streams must stop when the user leaves the session (closes the view, switches chats, disconnects), resume automatically when the user returns, never leak across users or chats, and degrade gracefully on failure.

**Technical approach** (justification in [research.md](research.md)):

- **Routing path**: `tool → agent → orchestrator → UI`. The orchestrator stays the only WebSocket the browser talks to; the trust boundary, ROTE adaptation, RFC 8693 token delegation, per-user resource accounting, and observability all already live there. A direct `tool → UI` path would require duplicating Keycloak/JWT validation, CORS/WSS termination, and rate-limiting in every agent process, expand attack surface to N agent ports, and bypass the existing `register_ui` session model. The performance cost of the extra hop (one in-process forwarding step per chunk on the same host or container network) is well below the human-perceptible latency budget set in the spec (SC-001 = 2 s) and is dominated by network round-trip to the browser, not by the orchestrator.
- **Stream production model**: Tool functions opt in by becoming async generators (or by using a `StreamCtx.emit(...)` helper for cases where async generators are awkward). The agent's `MCPServer` request loop detects streaming tools and, instead of returning a single `MCPResponse`, sends a sequence of new `ToolStreamData` messages tagged with the originating `request_id`. Existing single-response tools are untouched.
- **Stream forwarding model**: The orchestrator already forwards `ToolProgress` notifications to the originating UI socket via `pending_ui_sockets[request_id]`. We extend the same routing table to forward `ToolStreamData` chunks. Each chunk is run through ROTE adaptation (same as `send_ui_render` today) before being **fanned out** to every websocket subscribed to that stream (see "Multi-client fan-out" below) as a `ui_stream_data` message.
- **Per-component in-place updates**: Streaming components carry a stable `id` (the `Component.id` field that already exists in [primitives.py](../../backend/shared/primitives.py) but is unused). The frontend's `DynamicRenderer` keys components by `id`, and `useWebSocket` merges incoming `ui_stream_data` chunks into the existing `uiComponents` tree by id rather than replacing the whole tree. This avoids remounting unrelated components when one streaming tile updates.
- **Session lifecycle**: The orchestrator's existing stream registry (`_stream_subs`, `_stream_tasks`) is rekeyed from `(ws_id, tool_name)` to `(user_id, chat_id, params_hash)` so streams are scoped to a chat AND deduplicated per user — this fixes a latent cross-chat leak we found during exploration **and** satisfies FR-009a (multi-client fan-out). On the **last** subscriber leaving the chat (`load_chat` or disconnect), the stream is paused (cancelled task, retained subscription metadata in a per-user dormant table). When **any** subscriber returns to a chat with dormant streams, those streams are resumed, which re-invokes the tool to fetch fresh data (no backfill of missed values, per A-007).
- **Multi-client fan-out** (FR-009a, new): A `StreamSubscription` is keyed by `(user_id, chat_id, tool_name, params_hash)` and holds a `subscribers: list[WebSocket]` of every client session the user has loaded into that chat. The agent runs the streaming tool exactly once; each emitted chunk is ROTE-adapted once and then sent to every websocket in `subscribers`. A second `stream_subscribe` matching the same key from a different tab attaches its websocket to the existing subscription instead of allocating a new one — this keeps a multi-tab user under the per-user concurrency cap (10) and avoids paying for upstream API calls twice. See [research.md §11](research.md).
- **Automatic retry on transient failure** (FR-021a, new): A new `RECONNECTING` state sits between `ACTIVE` and `FAILED`. On a transient stream error (tool exception, upstream unreachable, network blip — but **not** auth/authorization failures), the orchestrator retries with exponential backoff (1 s, 5 s, 15 s; max 3 attempts) and emits a `ui_stream_data` chunk with `error.phase == "reconnecting"` so the frontend renders a distinct "reconnecting" state. On the first successful chunk after retry, the state returns to `ACTIVE` and a normal data chunk overwrites the reconnecting state. After the 3rd backoff exhausts, the state transitions to `FAILED` with `error.phase == "failed"` and `retryable: true`, surfacing the manual retry button. See [research.md §12](research.md).
- **Backpressure**: Each chunk goes through a per-stream coalescing buffer with a configurable target rate (default 10 fps, clamped 5–30 fps per SC-006). If a chunk arrives while the previous one is still being sent, the older payload is dropped (last-write-wins) — never queued. Per-user concurrent stream cap is **10 active + 50 dormant**, uniform across all roles (FR-015).
- **Auth + isolation**: Streams inherit the existing JWT/Keycloak validation done at `register_ui`. The orchestrator already records `ui_sessions[ws] = {sub, _raw_token, ...}`; every chunk is delivered using the websocket, never a stream-id, so an external party guessing a stream id cannot subscribe. Tools that need upstream credentials still go through `_get_delegation_token` (RFC 8693) per chunk batch, not per individual chunk, with a refresh check. **Auth revocation latency**: bounded at 60 seconds via a periodic Keycloak introspection sweep (FR-012, SC-009). Auth failures bypass the auto-retry path entirely and go straight to the re-authentication state.
- **No new third-party dependencies** (constitution principle V). The implementation reuses `asyncio`, `fastapi`, the existing custom `MCPServer`/`MCPRequest`/`MCPResponse` types, and React 18 hooks.

## Technical Context

**Language/Version**:
- Backend: Python 3.11+ (`backend/.venv/Scripts/python.exe`)
- Frontend: TypeScript 5.x on React 18 with Vite 5

**Primary Dependencies** (all already in the project — none added):
- Backend: FastAPI + Uvicorn (WebSocket server), Pydantic dataclasses (existing message types in [protocol.py](../../backend/shared/protocol.py)), `asyncio` (stream tasks, queues, coalescing), the custom `MCPServer`/`MCPRequest`/`MCPResponse` framing in `backend/agents/*/mcp_server.py`, the existing ROTE middleware in [backend/rote/](../../backend/rote/), the existing delegation client used by `_get_delegation_token` in [orchestrator.py](../../backend/orchestrator/orchestrator.py).
- Frontend: React 18 (`useState`, `useRef`, `useReducer`, `useMemo`), the existing `useWebSocket` hook ([frontend/src/hooks/useWebSocket.ts](../../frontend/src/hooks/useWebSocket.ts)), `DynamicRenderer` ([frontend/src/components/DynamicRenderer.tsx](../../frontend/src/components/DynamicRenderer.tsx)), the existing component catalog ([frontend/src/catalog.ts](../../frontend/src/catalog.ts)).

**Storage**:
- SQLite history DB (existing) — used **only** to remember which streams should be resumed in a chat (subscription metadata: `tool_name`, `agent_id`, `params_hash`, `component_id`). Stream **payloads are never persisted** (per A-007 — no backfill).
- In-memory orchestrator state — `_stream_tasks`, `_stream_subs`, plus a new `_stream_dormant` map keyed by `(user_id, chat_id)` for streams the user can return to.

**Testing**:
- Backend: pytest + `pytest-asyncio` (already used in [backend/tests/test_progress_integration.py](../../backend/tests/test_progress_integration.py), [backend/tests/test_progress_system.py](../../backend/tests/test_progress_system.py)). Coverage measured with `coverage.py` per constitution principle III.
- Frontend: Vitest + React Testing Library (already used in [frontend/src/__tests__/sdui_rendering.test.tsx](../../frontend/src/__tests__/sdui_rendering.test.tsx)).

**Target Platform**:
- Backend: Linux server (Docker) and Windows dev box. Existing: orchestrator at `ws://localhost:8001/ws`, agents at 8003+.
- Frontend: Modern evergreen browser (Chromium, Firefox, Safari) — same target as today.

**Project Type**: Web application (existing backend + frontend split). No new top-level project introduced.

**Performance Goals** (from spec Success Criteria):
- First update visible within 2 s of stream start (SC-001).
- Backend work attributable to abandoned streams ceases within 5 s (SC-002).
- Resume on return within 3 s (SC-003).
- 100 concurrent users × 3 streams sustained for 30 minutes without unbounded memory growth (SC-005).
- UI update cadence between 5 fps and 30 fps when source rate exceeds it (SC-006).
- Failure visible within 5 s (SC-007).

**Constraints**:
- MUST reuse the single existing browser WebSocket (`ws://…/ws`). No new ports exposed to the browser.
- MUST inherit existing Keycloak JWT validation; no separate auth path for streams (constitution VII).
- MUST NOT add third-party dependencies without lead approval (constitution V) — design verifies this is unnecessary.
- MUST integrate with ROTE adaptation: streaming chunks pass through `Rote.adapt(websocket, components)` before send, same as `send_ui_render`.
- MUST NOT break the existing single-response tool path or the existing `stream_subscribe` polling path. Both keep working unchanged.
- Per-stream backend memory bounded by a single coalescing slot (last-write-wins) — not a queue.
- Per-user concurrent streams bounded by `_MAX_STREAM_SUBSCRIPTIONS` (currently 10).

**Scale/Scope**:
- ~12 existing agents in [backend/agents/](../../backend/agents/), of which a small handful (e.g. `weather`, `etf_tracker_1`, `email_tracker`) are plausible early adopters of streaming.
- 100 concurrent authenticated users target.
- ~3 active streams per user typical, 10 maximum.
- Bounded chat session lifetime: streams die with the chat, no infinite-lifetime cron tasks.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Primary Language (Python) | PASS | All backend additions are Python 3.11. |
| II | Frontend Framework (Vite + React + TS) | PASS | All frontend additions are `.ts`/`.tsx`. No JS, no other bundler. |
| III | Testing Standards (≥90% coverage) | PASS (gated) | Phase 2 tasks will include unit + integration tests for: orchestrator stream registry, chat-scoped lifecycle, ROTE-on-stream, frontend `ui_stream_data` merge, useWebSocket session-switch behavior. Coverage measured on changed code only. |
| IV | Code Quality (PEP 8 / ESLint) | PASS | Existing tooling (`ruff` for backend, ESLint for frontend) applies unchanged. |
| V | Dependency Management (no new libs without approval) | PASS | Plan deliberately uses only existing libraries. Verified during research. If a future implementer wants to add e.g. `aiostream` or a reactive library, they MUST get lead approval and document it in the PR. |
| VI | Documentation (docstrings + JSDoc + `/docs`) | PASS (gated) | New protocol message types (`ToolStreamStart`, `ToolStreamData`, `ToolStreamEnd`, `ToolStreamError`, `ui_stream_data`, `stream_subscribe`/`stream_unsubscribe` extensions) MUST have docstrings. New REST surface (none planned — see research) would auto-appear in `/docs` if added. New TypeScript exports MUST have JSDoc. |
| VII | Security (Keycloak + RFC 8693) | PASS | Architectural choice of routing through the orchestrator is **driven by** this principle. Streams inherit `register_ui` JWT validation, RFC 8693 token exchange continues to happen at the orchestrator, no agent port is exposed to browsers, no stream-id is a capability token. See research.md §1 for the threat model. |
| VIII | UX (primitives + dynamic generation) | PASS | No new primitive components introduced. Streaming reuses existing primitives (`Card`, `Table`, `LineChart`, `Metric`, etc.) and only adds a stable `id` field that the frontend uses as a React key. The pre-existing `Component.id` field in [primitives.py](../../backend/shared/primitives.py) is finally put to use; no schema migration. |

**Result (Phase 0 gate)**: All gates PASS. No entries in Complexity Tracking required.

**Re-check after Phase 1 design**: Re-evaluated against [research.md](research.md), [data-model.md](data-model.md), [contracts/protocol-messages.md](contracts/protocol-messages.md), [contracts/agent-sdk.md](contracts/agent-sdk.md), [contracts/frontend-events.md](contracts/frontend-events.md), and [quickstart.md](quickstart.md).

| # | Principle | Post-design status | Verified by |
|---|-----------|--------------------|-------------|
| I | Python backend | PASS | data-model §1-§8, agent-sdk.md, protocol-messages.md §B all Python; no other languages introduced. |
| II | Vite + React + TS | PASS | frontend-events.md uses only TypeScript and React 18 hooks; no JS, no new bundler. |
| III | Tests ≥90% | PASS (gated for /speckit.tasks) | plan.md Project Structure lists 6 backend + 3 frontend test files covering every FR group and SC. |
| IV | PEP 8 / ESLint | PASS | No new tooling, no exceptions requested. |
| V | No new third-party deps | **PASS — verified** | Stdlib-only on backend (asyncio, dataclasses, inspect, json, hashlib, uuid); React 18 only on frontend. Confirmed in research §1.4, §2 (no `aiostream`/`grpcio`), §6 (no `RxPY`). |
| VI | Documentation | PASS (gated) | Three contracts files + quickstart delivered. JSDoc obligation called out in frontend-events.md §7. Python docstring obligation implied by constitution and reinforced in plan. `/docs` surface unaffected (no new REST). |
| VII | Security (Keycloak + RFC 8693) | **PASS — load-bearing** | The entire routing decision (research §1) is justified by this principle. data-model §8 codifies the per-chunk auth invariant; research §8 covers revocation. RFC 8693 path stays in `_get_delegation_token`. |
| VIII | UX (primitives + dynamic generation) | PASS | data-model §1-§8 introduces no new primitive types. Activates the dormant `Component.id` field that was already in primitives.py and catalog.ts. |

**Result (Phase 1 gate)**: All gates still PASS. No new violations introduced by the design. Complexity Tracking remains empty.

**Re-check after Clarifications session (2026-04-09)**: Re-evaluated against the spec changes from `/speckit.clarify` (FR-006 backgrounded-tab policy, FR-009a multi-client fan-out, FR-012 60s revocation bound, FR-015 explicit caps, FR-019 reconnecting state, FR-021a auto-retry, SC-009 revocation SC). Two design changes were merged into [research.md §11 and §12](research.md), [data-model.md §3 and §6](data-model.md), and [contracts/protocol-messages.md §A4-A5](contracts/protocol-messages.md). No new principle violations: the fan-out is one extra `for ws in subscribers` loop in the existing send path; the auto-retry is a new state in the existing state machine; both are pure stdlib (`asyncio`) with no new dependencies. Constitution V (no new deps) **still verified**. Constitution VII (security) is reinforced — auth failures explicitly bypass the auto-retry path so a revoked token cannot be silently reconnected against. Complexity Tracking remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-tool-stream-ui/
├── plan.md                     # This file
├── research.md                 # Phase 0: routing decision + alternatives
├── data-model.md               # Phase 1: entities and state transitions
├── quickstart.md               # Phase 1: developer guide for adding a streaming tool
├── contracts/                  # Phase 1: WS protocol additions + agent SDK contract
│   ├── protocol-messages.md
│   ├── agent-sdk.md
│   └── frontend-events.md
├── checklists/
│   └── requirements.md         # Spec quality checklist (already created)
└── tasks.md                    # Phase 2 — created by /speckit.tasks (NOT this command)
```

### Source Code (repository root)

This feature modifies the **existing** backend + frontend layout. No new top-level directories.

```text
backend/
├── orchestrator/
│   ├── orchestrator.py         # MODIFIED — extend stream registry, add ToolStreamData
│   │                           #            forwarding, rekey to (user_id, chat_id, stream_id),
│   │                           #            wire load_chat / disconnect to pause-and-dormant.
│   ├── stream_manager.py       # NEW — extracted stream lifecycle owner; orchestrator delegates
│   │                           #       _stream_tasks/_stream_subs/_stream_dormant operations here.
│   │                           #       Keeps orchestrator.py from growing past its already-large size.
│   └── api.py                  # UNCHANGED (no new REST surface required — see research.md §4)
├── shared/
│   ├── protocol.py             # MODIFIED — add ToolStreamStart/Data/End/Error message classes;
│   │                           #            extend RegisterUI? NO — already has session_id.
│   ├── primitives.py           # UNCHANGED — uses existing Component.id field
│   ├── stream_sdk.py           # NEW — tiny helper exposed to agents: @streaming_tool decorator,
│   │                           #       StreamCtx.emit(component_dict), backwards compatible with
│   │                           #       existing one-shot tools.
│   └── feature_flags.py        # MODIFIED — add FF_TOOL_STREAMING flag (default OFF for rollout)
├── agents/
│   └── <agent>/mcp_server.py   # MODIFIED — request loop checks if tool is async-generator-
│   │                           #            decorated and routes accordingly. Common base lives
│   │                           #            in shared/, agents inherit. Single-response tools
│   │                           #            are unaffected.
│   └── weather/                # REFERENCE IMPLEMENTATION — convert one weather tool to streaming
│       └── mcp_tools.py        #   as the canonical example used in tests + quickstart.md
├── rote/
│   └── adapter.py              # UNCHANGED — adapter is stateless, called per chunk by stream_manager
└── tests/
    ├── test_stream_manager.py  # NEW — unit: registry, dormant table, chat-scope, cap enforcement
    ├── test_stream_protocol.py # NEW — unit: ToolStreamData round-trip, request_id correlation
    ├── test_stream_lifecycle.py# NEW — integration: subscribe → leave → return → resume
    ├── test_stream_isolation.py# NEW — integration: two-user concurrent, no cross-leak
    ├── test_stream_backpressure.py # NEW — integration: high-rate source coalesces to ≤30 fps
    ├── test_stream_failure.py  # NEW — integration: tool error → ui_stream_data with error state
    ├── test_stream_fanout.py   # NEW (FR-009a) — integration: one user, two ws, one subscription, both receive; one ws's token expires while the other continues
    └── test_stream_reconnect.py# NEW (FR-021a) — integration: transient failure → RECONNECTING with backoff → recovery; 3-attempt exhaustion → FAILED; auth failure bypasses RECONNECTING

frontend/
├── src/
│   ├── hooks/
│   │   └── useWebSocket.ts     # MODIFIED — handle ui_stream_data; merge by component.id;
│   │                           #            scope activeSubscriptionsRef to chat_id;
│   │                           #            on load_chat, unsubscribe stale, subscribe new;
│   │                           #            on disconnect, mark dormant; on reconnect, resume.
│   ├── components/
│   │   └── DynamicRenderer.tsx # MODIFIED — use component.id as React key; React.memo wrapper
│   │                           #            on streaming-eligible components so only the
│   │                           #            updated subtree re-renders.
│   ├── catalog.ts              # UNCHANGED — id field is already in every primitive's Zod schema
│   ├── contexts/               # POSSIBLY MODIFIED — if there's a ChatContext, extend it with
│   │                           # active stream metadata; otherwise add nothing.
│   └── __tests__/
│       ├── stream_merge.test.tsx       # NEW — useWebSocket merges chunks by id (covers normal, reconnecting, failed cases)
│       ├── stream_lifecycle.test.tsx   # NEW — chat switch unsubscribes; return resumes
│       ├── stream_render.test.tsx      # NEW — DynamicRenderer doesn't remount on chunk
│       ├── stream_reconnecting.test.tsx# NEW (FR-021a) — reconnecting overlay decorates without removing; recovery overwrites in one render; failed shows retry button
│       └── stream_attach.test.tsx      # NEW (FR-009a) — stream_subscribed { attached: true } handles reconnecting-state-on-attach
```

**Structure Decision**: Use the **existing** backend/frontend split. No new top-level project. The only new backend file outside `tests/` is [backend/orchestrator/stream_manager.py](../../backend/orchestrator/stream_manager.py), which is extracted from the orchestrator solely to keep `orchestrator.py` (already 1800+ lines) from growing further — it is not a new architectural layer. The only new frontend artifact is a set of tests; no new components and no new directories. Streaming reuses the existing single browser WebSocket and the existing primitives catalog.

## Complexity Tracking

> No constitution violations. Section intentionally empty.
