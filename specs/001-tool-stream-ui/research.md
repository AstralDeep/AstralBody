# Phase 0 Research: Real-Time Tool Streaming to UI

**Feature**: 001-tool-stream-ui
**Date**: 2026-04-09
**Status**: Complete — all NEEDS CLARIFICATION resolved

This document satisfies **FR-014** (formal evaluation of routing paths) and feeds **SC-008** (recorded architectural decision).

---

## 1. ROUTING DECISION (Primary)

**Question** (from spec, raised explicitly by user): Should stream data flow `MCP tool → agent → orchestrator → UI`, or directly `MCP tool → UI`, or some other path?

### Decision

**Stream data flows `tool → agent → orchestrator → UI`.** The orchestrator stays the only WebSocket the browser connects to. Each stream chunk traverses one extra in-process forwarding step at the orchestrator before being delivered to the browser.

### Rationale (security)

| Property | tool → agent → orchestrator → UI (chosen) | tool → UI direct (rejected) |
|---|---|---|
| **Authentication boundary** | Single. Existing `register_ui` → JWT/JWKS validation at the orchestrator. Stream inherits this. | N. Each agent process must verify Keycloak JWTs and refresh JWKS independently. Token validation logic duplicated 12× across agents. |
| **Token delegation (RFC 8693)** | Stays at orchestrator (`_get_delegation_token`). Agents only see attenuated tokens. | Each agent must perform its own token exchange OR the browser must send the raw user token to every agent — both unacceptable. |
| **Per-user authorization** | Orchestrator already maps `(websocket → user_id, roles, scopes)`. Stream subscribe checks happen against this same registry. | Each agent re-implements per-user scope enforcement. Bug in any one agent leaks data. |
| **Network attack surface** | One WSS endpoint (port 8001). Browser cannot reach agent ports. | Each streaming agent must expose a publicly reachable port (8003, 8004, …), each requiring TLS termination, CORS, rate limiting, DoS protection. **N× larger surface.** |
| **Stream identifier as capability** | Stream IDs are server-only routing keys. The browser identifies its session by JWT, not by stream ID. Guessing a stream ID gets you nothing. | Direct path tempts a "subscribe by stream URL" model where the URL becomes a bearer credential — the exact pattern OWASP A01:2021 (Broken Access Control) warns against. |
| **Cross-user isolation** | Orchestrator already maintains `ui_sessions[ws] = user_data`. Routing a chunk to "the websocket that owns request_id X" automatically isolates by user. | Requires every agent to authenticate every subscriber for every chunk, with no shared session registry. |
| **Logging / abuse investigation** | One log stream at the orchestrator records every stream lifecycle event keyed to `(user_id, chat_id, tool, agent)`. Existing observability hooks apply. | Logs scattered across agent processes; correlation across agents requires a separate aggregator. |
| **Token revocation latency** | Single point checks token validity on chunk send; revocation takes effect within one chunk. | Each agent independently caches/checks tokens, possibly with different TTLs. |
| **Constitution VII compliance** | Direct fit. | Requires changing the constitution to allow agents to act as primary auth boundary — out of scope for this feature. |

**Bottom line on security**: routing through the orchestrator preserves the single-trust-boundary model the project was designed around. The direct path would force every agent into the role of public-facing authenticated server, which is the largest source of bugs in microservice security.

### Rationale (performance)

- **Extra hop cost**: One in-process Python coroutine forwarding step per chunk. On the same host or same Docker network, this adds approximately one local memory copy and one event-loop scheduling slot — sub-millisecond. Compared to:
  - The browser's network RTT (typ. 5–80 ms over WAN, 1–5 ms over LAN),
  - The actual tool work producing the chunk (typically tens of ms minimum),
  - The ROTE adaptation pass (which must happen anyway, see §2),
  - The browser repaint cost (1–16 ms),
  the orchestrator hop is statistically invisible at the spec's target latencies (SC-001 = 2 s, SC-006 = 5–30 fps).
- **Fan-out**: A streaming tool with one subscriber has fan-out of 1 in either model. With multiple subscribers (a single user with two open tabs, say), the orchestrator-mediated path can de-duplicate at the orchestrator if needed. The direct path forces every fan-out edge to be re-encrypted and re-sent over the wire. **The orchestrator path scales better**, not worse.
- **Backpressure**: The orchestrator already owns the user's WebSocket and knows whether the send buffer is draining. It can apply per-stream coalescing (drop intermediate updates, last-write-wins) at exactly the right place. A direct-from-agent design has no shared knowledge of the browser send buffer and either over-sends (causing buffer bloat) or requires a side-channel between agent and browser to learn buffer state.
- **Connection count**: Browser holds 1 socket regardless of streaming, vs. up to N additional sockets with direct streaming (one per active streaming agent). The 1-socket model also survives reverse-proxy / load-balancer setups that limit per-client connections.

**Bottom line on performance**: the extra hop is free at human-perceptible latencies, and the orchestrator-mediated model gives us one place to implement coalescing/backpressure correctly.

### Alternatives considered

1. **Direct `tool → UI` over a new WSS port per agent.** Rejected for the security reasons above. Performance gain would be one in-process forwarding step (negligible).
2. **Direct `tool → UI` over Server-Sent Events from each agent.** Same authentication problems as #1, plus SSE is one-way (the resume-on-return signal can't flow back to the agent without a side channel). Rejected.
3. **Server-Sent Events from the orchestrator alongside the existing WebSocket.** Two transports for the same trust boundary doubles client complexity (`useWebSocket` + an SSE hook) for no benefit. The existing WebSocket already supports server-push and is already authenticated. Rejected.
4. **gRPC bidirectional streaming through a sidecar in front of agents.** Adds a new protocol, a new dependency (`grpcio`, `grpcio-tools`), and a new transport for the browser (gRPC-Web), all of which would violate constitution V (no new deps without approval) and add operational complexity. Rejected.
5. **Polling: orchestrator periodically calls the tool and forwards the result.** This is what `stream_subscribe` currently does. It works for "refresh this chart every 30 s" but breaks the spec's "real-time" requirement (SC-001 = 2 s first update) for tools whose data sources are themselves event-driven (e.g., a file watcher, an inbox push, a subscription feed). Kept as a **fallback** for tools that don't opt into the new push model, but not the primary path.
6. **Publish/subscribe via Redis or NATS.** Would let agents publish without holding a connection to the orchestrator, but introduces a new infra dependency, a new failure mode (broker outage), and a new auth surface (broker ACLs). The project already has direct agent↔orchestrator WebSockets — there is no scaling reason today to add a broker. Rejected on YAGNI + constitution V.

### Recorded for SC-008

The decision above, with this rationale, satisfies SC-008 ("The architectural decision on stream routing is recorded as a written decision with explicit security and performance reasoning before any production rollout"). The PR introducing this feature must reference this section.

---

## 2. STREAM PRODUCTION MODEL ON THE AGENT SIDE

**Question**: How does a tool function actually emit a sequence of values?

### Decision

Tools opt in by becoming **async generators**. The agent's `MCPServer.process_request` checks whether the tool function is `inspect.isasyncgenfunction(...)` and, if so, iterates it, sending one `ToolStreamData` message per yielded item, then a final `ToolStreamEnd`. Existing synchronous and `async def` tools are unchanged.

A small helper module [backend/shared/stream_sdk.py](../../backend/shared/stream_sdk.py) provides:

- A `@streaming_tool` decorator that just marks the function and ensures it returns an async generator. Sugar over `inspect.isasyncgenfunction`.
- A `StreamCtx` object yielded as an extra parameter, exposing `emit(component_dict, *, raw=None)` for the cases where async-generator yield is awkward (e.g., a tool that wants to wrap a callback-based upstream library). Internally `emit` puts the chunk on an `asyncio.Queue` that the surrounding generator drains.

### Rationale

- **Native to Python.** Async generators are stdlib, no new dependency.
- **Backwards compatible.** A tool author who writes a normal `async def` returning a dict still works. The detection in `process_request` is one `if isasyncgenfunction(fn)` branch.
- **Cancellation is free.** Closing the async generator (`agen.aclose()`) propagates `GeneratorExit`, which lets tool authors clean up upstream subscriptions in a `finally` block. The orchestrator's pause-on-leave just calls `agen.aclose()` on the agent side — see §3.
- **Familiar idiom.** Same pattern used by FastAPI streaming responses, by `httpx`'s streaming, etc.

### Alternatives considered

- **Callback-based API** (`tool.on_data = lambda x: ...`). Rejected — callbacks compose poorly with `await`, and the `StreamCtx` helper covers callback-style upstream APIs anyway.
- **Reactive streams library** (e.g., `RxPY`, `aiostream`). Rejected — new dependency (constitution V), unfamiliar to most contributors, async generators do everything we need.
- **MCP SDK streaming** (`notifications/progress`). The project does **not** use the official MCP SDK; the `MCPServer` class in [backend/agents/*/mcp_server.py](../../backend/agents/) is a project-local custom implementation. Adopting the official SDK is out of scope for this feature.

---

## 3. SESSION LIFECYCLE: STOP, DORMANT, RESUME

**Question**: How does the system know the user has "left" the session, and how does it persist enough to resume?

### Decision

Three lifecycle events drive a stream's state:

| Event | Source | Action |
|---|---|---|
| **Subscribe** | `ui_event` action `stream_subscribe` (also auto-fired by frontend on `ui_render` for streamable components, exactly as today) | Allocate `stream_id`, validate user permissions + cap, create async task that drains the agent's stream, send `stream_subscribed` confirmation. |
| **Leave** | One of: `load_chat` to a different chat_id (frontend already sends this); WebSocket disconnect (FastAPI fires `WebSocketDisconnect`); explicit `stream_unsubscribe`. | Cancel the orchestrator-side draining task, call `agen.aclose()` on the agent side via a new `ToolStreamCancel` request, **move the subscription metadata to the dormant table** keyed by `(user_id, chat_id)`. Do not delete it. |
| **Return** | `load_chat` to a chat_id that has dormant streams. | For each dormant entry, re-issue the subscribe with the same `tool_name`/`agent_id`/`params`/`component_id`. Tool restarts cleanly; UI sees a fresh first chunk within 3 s (SC-003). |

The dormant table is **in-memory only**, with a hard cap per user (e.g., 50 dormant subscriptions) and a TTL (e.g., 1 hour). Surviving an orchestrator restart is **not** a goal — on restart the user re-loads the page, the frontend re-sends `register_ui` + `load_chat`, and any streams the frontend remembers as active are re-subscribed via the existing reconnect path in [useWebSocket.ts](../../frontend/src/hooks/useWebSocket.ts) lines ~691-704. This avoids a database migration and persistent stream state, both of which are out of scope for the spec (A-007).

### Rationale

- **Chat-scoped, not websocket-scoped.** During exploration we found that the existing `_stream_subs` is keyed `(ws_id, tool_name)`, not `(ws_id, chat_id, tool_name)` — meaning streams can leak across chats today. Rekeying to `(user_id, chat_id, stream_id)` fixes this latent bug as a side effect of the new feature.
- **Use existing leave signal.** The frontend already sends `load_chat` whenever the active chat changes. We don't need a new "I left" message.
- **No backfill complexity.** Per A-007, on resume we show fresh data, not missed history. This means dormant state is just `{tool_name, agent_id, params, component_id}`, not "the last N values seen."
- **TTL bounds memory.** A user who opens 1000 chats, each with 3 streams, then leaves them all dormant, cannot grow the dormant table without bound. The TTL + per-user cap together provide the bound demanded by FR-015.

### Alternatives considered

- **Persist dormant subscriptions in SQLite.** Rejected — adds a migration, persistent state to manage on rollback, and the existing reconnect-via-frontend-state path already handles the "page refresh" case adequately.
- **Treat any disconnect as a hard stop, no resume.** Rejected — fails User Story 3.
- **Use the existing `_stream_tasks` keying without rekeying.** Rejected — leaks across chats, fails User Story 4, and would propagate the bug.

---

## 4. NEW REST SURFACE? NO.

**Question**: Does this feature need any new REST endpoints?

### Decision

**No.** All control flow goes over the existing WebSocket as `ui_event` actions: `stream_subscribe`, `stream_unsubscribe` (already exist; we extend them), and `stream_status` (new, for diagnostics). The `/docs` Swagger UI mandated by constitution VI is already populated by the existing FastAPI app and gains nothing from this feature.

### Rationale

- The browser is already on a WebSocket. Forcing it to mix REST + WS for the same lifecycle would worsen, not improve, the integration.
- A REST `GET /streams/active` for ops/debug was considered. Deferred — can be added later if real operational need emerges, with lead approval per any new endpoint.

---

## 5. ROTE INTERACTION

**Question**: ROTE adapts every `ui_render` per device profile. Should streaming chunks bypass it, share state with it, or pass through it?

### Decision

**Streaming chunks pass through ROTE adaptation, on the same code path as `send_ui_render` today.** Specifically, the new `_send_stream_chunk(websocket, chunk)` helper in `stream_manager.py` calls `self.rote.adapt(websocket, chunk.components)` before wrapping in a `ui_stream_data` message and sending.

### Rationale

- **Per-device fidelity.** A streaming line chart that arrives as a chart for a browser user must arrive as a degraded metric card for a watch user, exactly as static `ui_render`s do today. Bypassing ROTE would create two parallel rendering pipelines and a UX inconsistency.
- **Adapter is stateless per call.** [backend/rote/adapter.py](../../backend/rote/adapter.py) takes `(components, profile)` and returns adapted components. There's no per-stream state to keep coherent. The cost is one adapter pass per chunk — well within the 5–30 fps budget for any reasonable component count.
- **Caching** — ROTE already caches the per-websocket device profile (`_profiles[ws]`) so we don't re-fetch capabilities per chunk. The `_last_components` cache in ROTE is **not** updated by streaming chunks (we pass `update_cache=False` in a new keyword arg) because re-adapting on viewport change should re-fetch from the live stream, not replay a stale chunk.

### Alternatives considered

- **Bypass ROTE for streams**, send raw components. Rejected — breaks UX consistency on non-browser devices (SC criteria are device-agnostic).
- **Apply ROTE only on the first chunk and reuse the result.** Rejected — components in subsequent chunks may have different content (different chart series, different table rows) and need independent adaptation decisions.

---

## 6. PER-COMPONENT-ID UPDATES IN THE FRONTEND

**Question**: Today the frontend replaces the entire `uiComponents` state on every `ui_render`. Streaming would cause unrelated components to re-mount on every chunk. How do we update only the streaming component?

### Decision

The orchestrator includes a stable `id` on every component participating in a stream (assigned at subscribe time, e.g. `stream_<uuid>`). The frontend's `useWebSocket` handler for the **new** `ui_stream_data` message merges the chunk into `uiComponents` by walking the tree and replacing the component whose `id` matches. Other components are untouched.

`DynamicRenderer` is updated to:
1. Use `component.id` (when present) as the React `key`, so React's reconciliation does not unmount unchanged siblings.
2. Wrap streaming-eligible primitives in `React.memo` keyed on the JSON-stringified component, so a sibling streaming a chunk does not cause this component's render to re-execute.

### Rationale

- **Already supported by the data model.** The `Component.id: Optional[str]` field exists in [backend/shared/primitives.py](../../backend/shared/primitives.py) but is currently unused by the backend. The Zod schemas in [frontend/src/catalog.ts](../../frontend/src/catalog.ts) all permit an optional `id`. We are activating dormant infrastructure, not adding a new field.
- **Pure additive change.** Non-streaming components keep getting re-rendered by `ui_render` exactly as they do today; we're only changing what happens when an `ui_stream_data` message arrives.
- **No virtual-DOM diff bottleneck.** With `React.memo` and stable keys, the cost of a single chunk is one component subtree re-render — independent of how many other components are on the canvas.

### Alternatives considered

- **State management library** (Redux Toolkit / Zustand). Rejected — would be a new dep (constitution V) and the merge logic is small enough to live in `useWebSocket`.
- **Replace `uiComponents` wholesale on each chunk** but rely on memoization to avoid expensive re-renders. Rejected — still causes React reconciliation traversal of every component on every chunk, which violates SC-005 at scale (100 users × 3 streams × 30 fps = 9000 reconciliations/sec).

---

## 7. BACKPRESSURE / COALESCING

**Question**: SC-006 says the visible refresh rate must be 5–30 fps even when the source rate is higher. How is that enforced and where?

### Decision

Each stream has a single-slot **coalescing buffer** at the orchestrator: a `latest_chunk` reference plus a `send_in_progress` flag. When the agent emits a chunk:

1. If no send is in progress, schedule the send immediately.
2. If a send is in progress, replace `latest_chunk` with the new chunk (overwriting any previous queued value). The previous queued chunk is **dropped**, not queued.

After each successful send, if `latest_chunk` is non-null, schedule another send. A periodic timer caps the minimum interval between two consecutive sends to `1/MAX_FPS` (default `1/30` = 33 ms), ensuring SC-006's upper bound. A separate watchdog ensures the gap between sends never exceeds `1/MIN_FPS` (default `1/5` = 200 ms) **when the source has data** — if the source is silent, the watchdog does not fire.

### Rationale

- **No queue, no memory bloat.** The buffer is one slot. A pathological tool emitting 1 million chunks/second consumes O(1) backend memory per stream.
- **Last-write-wins semantics match streaming UX.** A live stock ticker should show the latest price, not a 30-second backlog of stale prices.
- **Correctness under WebSocket back-pressure.** `send_in_progress` is set true when `await ws.send_text(...)` begins and cleared when it returns. If the browser is slow, `send_in_progress` stays true; chunks pile up into the single slot and only the latest survives.

### Alternatives considered

- **Bounded queue.** Rejected — no UX benefit over single-slot, and complicates "drop policy" code.
- **Sliding-window aggregation** (e.g., average the last N values before sending). Rejected — would require per-component knowledge to know how to aggregate (sum? average? last? per-field?). Out of scope; if a tool wants aggregation, it implements aggregation in the tool function itself.

---

## 8. AUTH REVOCATION MID-STREAM

**Question**: SC-002 / FR-012 require streams to stop on auth invalidation. How is this detected without paying a JWT validation cost on every chunk?

### Decision

The orchestrator validates the JWT once at `register_ui` and stores `user_data["_raw_token"]` plus `expires_at` in `ui_sessions[ws]`. The stream manager's send loop checks `expires_at < now()` cheaply on each send. If expired:

1. Refresh attempt: existing delegation client offers a refresh path; if it succeeds, update `_raw_token` and continue.
2. If refresh fails or token has been revoked (Keycloak `/.well-known/openid-configuration` introspection on a periodic background job, **not** per-chunk), the stream is stopped and a `ui_stream_data` chunk with error state `unauthenticated` is sent. The browser shows the re-auth prompt.

### Rationale

- **No per-chunk JWT cost.** Cheap timestamp comparison only.
- **Bounded staleness.** Worst case: the stream continues for one introspection-job interval (e.g., 60 s) after revocation. Acceptable for the spec's threat model; any tighter bound requires per-chunk introspection which is expensive at 30 fps.
- **Reuses existing delegation client** rather than introducing a new revocation path.

### Alternatives considered

- **JWKS check on every chunk.** Rejected — far too expensive at high fps.
- **Push-based revocation from Keycloak** (back-channel). Rejected — not configured in the project's deployment, would require ops change.

---

## 9. FEATURE FLAG / ROLLOUT

**Question**: How do we ship this without disrupting the existing system?

### Decision

Add `FF_TOOL_STREAMING` to [backend/shared/feature_flags.py](../../backend/shared/feature_flags.py), default `False`. When false:

- Tool decorator `@streaming_tool` is still importable (no import errors) but the agent's request loop falls back to executing the generator to completion and returning a single concatenated `MCPResponse`.
- Orchestrator does not register the new `ui_stream_data` message handler on the frontend (it sends `ui_render` instead).
- Frontend's new `ui_stream_data` handler is a no-op when the message never arrives.

When true, the new path is active. The flag can be flipped per-environment and rolled back instantly without code changes.

### Rationale

- **Constitution principle V** requires lead approval for any change with broad impact. A feature flag lets the change ship dark, get reviewed, and roll out gradually.
- **Existing project pattern.** [backend/shared/feature_flags.py](../../backend/shared/feature_flags.py) already hosts `FF_PROGRESS_STREAMING`, `FF_LIVE_STREAMING`, etc. — we follow the convention, not invent it.

---

## 10. WHAT ABOUT THE EXISTING `stream_subscribe` POLLING PATH?

**Question**: There's already a `stream_subscribe` action that periodically re-runs a tool. Does this feature replace it?

### Decision

**No.** The existing polling path (orchestrator.py lines ~2672-2823) stays untouched and is the right answer for tools whose data is naturally polled (e.g., "refresh this chart every 30 seconds against a non-streaming HTTP API"). The new push path is for tools whose data is naturally event-driven (file watchers, message queues, OS notifications, long-running jobs reporting progress).

A tool author chooses by:
- Writing an `async def` that returns once → polled by `stream_subscribe` if the tool declares itself streamable in metadata.
- Writing an `async generator` decorated with `@streaming_tool` → pushed via the new `ToolStreamData` path.

Both routes deliver to the same `ui_stream_data` frontend message, so the UI behavior is identical and the user can't tell the difference. The only difference is whether the orchestrator drives the cadence or the tool does.

### Rationale

- **YAGNI on deprecation.** Removing the polling path adds risk to existing streamable tools (e.g. `weather`) for no UX benefit.
- **One UI path.** Both routes converge on `ui_stream_data` at the frontend, so the merge-by-id and React.memo work covers both.

---

## 11. MULTI-CLIENT FAN-OUT (added 2026-04-09 from spec Clarifications)

**Question** (raised by spec FR-009a after `/speckit.clarify` Q2): When the same user has the same chat open in multiple client sessions (e.g. two browser tabs), should each session get its own upstream subscription, or should the orchestrator deduplicate to one and fan the chunks out?

### Decision

**Deduplicate.** A `StreamSubscription` is keyed by `(user_id, chat_id, tool_name, params_hash)`. It holds a `subscribers: list[WebSocket]` field listing every websocket of that user that has loaded that chat and asked for that tool with those params. When a new `stream_subscribe` arrives whose key matches an existing subscription, the orchestrator simply appends the new websocket to the subscribers list and returns the existing `stream_id` in the `stream_subscribed` confirmation. The agent-side tool runs **exactly once**. Each emitted chunk is ROTE-adapted **once per device profile** (still per-websocket because two tabs may be different device classes) and then sent to every websocket in the list.

**Lifecycle changes from this**:

- **Subscribe**: if a matching subscription exists, attach this websocket and return immediately. Do NOT count it against the per-user concurrency cap a second time.
- **Unsubscribe / leave**: remove the websocket from the list. **Only when the list becomes empty** does the subscription transition to `DORMANT` and the agent-side generator close. As long as at least one tab of the same user is still loaded into the chat, the stream stays `ACTIVE`.
- **Per-user cap**: counts unique `(user_id, chat_id, tool_name, params_hash)` tuples in `_active`, not websockets. A user with 3 tabs of the same chat each running 4 tools = 4 active subscriptions, not 12.

### Rationale (security)

- **Same trust boundary.** All subscribers in the list are by construction the **same user** (the orchestrator only attaches a websocket whose `ui_sessions[ws]["sub"]` equals the subscription's `user_id`). FR-011 cross-user isolation is unaffected.
- **Authorization re-check on attach.** Each new tab attaching to an existing subscription independently passes the FR-010 authorization check (chat ownership, scope, cap). Sharing the upstream tool invocation does not bypass per-tab authorization at attach time.
- **Authorization re-check on send.** The per-chunk authorization invariant in [data-model.md §8](data-model.md) iterates the subscribers list and validates each websocket independently before send (websocket still in `ui_clients`, token not expired, etc.). A websocket whose token expires mid-stream is removed from the list and gets a re-auth chunk; the other tabs continue receiving updates.
- **No stream-id-as-bearer-token risk.** Stream IDs remain server-internal. The browser never uses them to subscribe; it uses `(tool_name, params)` and the orchestrator does the lookup.

### Rationale (performance & cost)

- **Halves the cost of paid upstream APIs** for users who keep two tabs open (a common pattern when comparing data side-by-side). The weather, market-data, and inbox-watch tools are all paid per-call upstream.
- **One ROTE pass amortized**: actually still one per device profile (because two tabs may differ), but at most one per *distinct profile*, not one per websocket. In the common case (both tabs are the same browser) it's literally one ROTE call shared between sends.
- **One agent-side generator** instead of N. The generator's memory and event loop slots are O(1) in the number of subscribers.
- **Coalescing buffer is shared** across subscribers — the single-slot last-write-wins from §7 still applies, just with the send loop iterating multiple websockets per slot turn.

### Alternatives considered

- **Independent subscriptions per websocket** (the original Phase 0 design). Rejected after Q2 — burns paid upstream API calls and exhausts the per-user cap fast (5 tabs × 2 streams = cap reached).
- **One winner, others go static.** Rejected — silent staleness in non-winner tabs is confusing UX.
- **One winner with handoff to next tab on close.** Rejected — adds complexity (election protocol, race on close), and has no advantage over the simpler "all subscribers receive" model.

### Edge cases

- **First tab leaves, second tab still viewing**: subscription stays `ACTIVE`, first websocket removed from subscribers list, agent generator keeps running, second tab keeps receiving chunks. No state transition.
- **Both tabs leave at once**: subscribers list empties → transition to `DORMANT` exactly as the single-tab case did before.
- **Tab returns to a chat where another tab already has the stream active**: new tab's `stream_subscribe` matches the existing key, attaches, and immediately starts receiving the next chunk. UI shows fresh data within one chunk interval (well within SC-001's 2 s budget — usually faster, since the stream is already running).
- **Two tabs with different `params`** (e.g. different lat/lon): different `params_hash`, different subscriptions, both count against the cap. Correct — they ARE different streams.
- **Authorization downgrade for one tab only** (rare but possible mid-stream): only that tab gets the re-auth chunk and is removed from subscribers; the others continue.

---

## 12. AUTOMATIC RETRY ON TRANSIENT FAILURE (added 2026-04-09 from spec Clarifications)

**Question** (raised by spec FR-021a after `/speckit.clarify` Q5): On a transient stream failure (brief upstream blip, network hiccup, tool exception), should the system retry automatically before showing an error, or surface every failure to the user immediately?

### Decision

**Automatic retry with capped exponential backoff, then surface manually.** The `StreamSubscription` state machine adds a `RECONNECTING` state between `ACTIVE` and `FAILED`. On a transient stream error from the agent (`ToolStreamData` with `error.code` in the transient set, OR a chunk-send IO error, OR the agent connection dropping mid-stream):

1. The orchestrator transitions the subscription `ACTIVE → RECONNECTING`, sets `retry_attempt = 1`, `next_retry_at = now() + 1s`.
2. It immediately fans out a `ui_stream_data` chunk to all subscribers with `error.phase == "reconnecting"`, `error.code == <original code>`, `error.attempt == 1/3`, `error.next_retry_at_ms == <epoch>`. The frontend renders a distinct "reconnecting" visual state on the existing component (preserving its `id`).
3. After 1 s, the orchestrator re-issues the underlying tool call (same `stream_id`, same params, same agent — exactly the resume path used by `DORMANT → STARTING`).
4. **On the first successful chunk after retry**: transition `RECONNECTING → ACTIVE`, fan out the chunk normally (which overwrites the reconnecting state in the UI's merge-by-id).
5. **On a second failure**: bump `retry_attempt` to 2, schedule next retry at `now() + 5s`, fan out another reconnecting chunk with `attempt == 2/3`.
6. **On a third failure**: bump to 3, schedule at `now() + 15s`.
7. **On a fourth failure (i.e., 3 retries exhausted)**: transition `RECONNECTING → FAILED`, fan out a `ui_stream_data` chunk with `error.phase == "failed"`, `error.retryable == true`. The frontend renders the manual retry button. The user clicking retry re-issues `stream_subscribe` from scratch, which starts a fresh subscription (resets `retry_attempt`).

**Auth failures bypass the retry loop entirely.** If the error code is `unauthenticated` or `unauthorized`, the orchestrator goes directly `ACTIVE → FAILED` with `error.phase == "failed"`, `error.retryable == false`, and the frontend shows the re-authentication state instead of a retry button. Auto-retrying after a token revocation would be a security regression.

**Failure code classification**:

| `error.code` | Auto-retry? | Reason |
|---|---|---|
| `tool_error` | Yes | Could be a transient bug or a flaky upstream the tool doesn't catch internally. |
| `upstream_unavailable` | Yes | Network blip / 503 / DNS hiccup. |
| `rate_limited` | Yes (with respect for `retry_after` if present) | Backoff naturally helps. |
| `chunk_too_large` | **No** | Deterministic — same chunk will be too large on retry. Surface immediately. |
| `cancelled` | **No** | Explicit cancellation isn't a failure to retry. |
| `unauthenticated` | **No** | Security: never auto-recover from a revoked token. |
| `unauthorized` | **No** | Security: scope changes are not transient. |

### Rationale

- **Matches industry pattern.** EventSource/SSE clients auto-reconnect with backoff. gRPC clients have built-in retry policies. Users have come to expect "spinner that says reconnecting" rather than "broken component that needs a click."
- **Hides real-world flakiness.** A 1-second upstream blip would otherwise force the user to click retry. With this policy the user briefly sees "reconnecting" and then the stream resumes; total user-visible disruption ≈ 1 second.
- **Bounded worst case.** 1 + 5 + 15 = 21 s of total backoff before the manual-retry state appears. SC-007 was extended to 25 s to cover this plus jitter.
- **Reuses the resume path.** Internally, a retry is just a `DORMANT-like → STARTING` transition with the same `stream_id`, same params, same agent. No new code path on the agent side; the agent doesn't even know the difference between a fresh subscribe and a retry.
- **Security-preserving.** The classification table above explicitly carves out auth failures so the auto-retry can never be used to grind through revoked tokens.

### Alternatives considered

- **User-initiated only** (Q5 option A). Rejected — user must click for every blip.
- **Fixed retries (3 attempts, 5 s apart)** (Q5 option B). Rejected — 5 s is too long for the common 1 s blip and too short for a 30 s outage. Exponential is strictly better.
- **Always automatic, never give up** (Q5 option D). Rejected — a stream pinned in "reconnecting" forever is indistinguishable from a broken stream. The user needs an escape hatch.
- **Auto-retry auth failures with a refresh-token attempt first.** Considered. Rejected — token refresh already happens in `_get_delegation_token` per chunk batch; if it fails there, the token is genuinely dead and should not be retried. Adding a second refresh layer here would create a confusing feedback loop with the existing `expires_at` check from §8.

### Edge cases

- **User leaves chat during RECONNECTING**: same as leaving during ACTIVE. Subscription transitions to `DORMANT`, retry timer cancelled, `retry_attempt` reset. On return, the stream starts fresh.
- **User unsubscribes during RECONNECTING**: cancel timer, transition to `STOPPED`.
- **Multi-tab fan-out interaction**: all subscribers receive the same reconnecting chunks. When the retry succeeds, all subscribers see the recovery simultaneously. If one tab leaves during reconnect, it just drops out of the subscribers list; the retry loop continues for the others.
- **Backoff jitter**: each backoff interval gets ±20% jitter to avoid thundering-herd on a recovering upstream.

---

## Open questions resolved

| Originally vague | Resolution |
|---|---|
| Which routing path? | §1: tool → agent → orchestrator → UI. |
| Push or pull from tool? | §2: opt-in async generator (push). Existing pull path stays for tools that prefer it. §10. |
| How to know user "left"? | §3: existing `load_chat` + WebSocket disconnect. No new client signal. |
| How to resume? | §3: in-memory dormant table keyed by `(user_id, chat_id)`. |
| Need new REST? | §4: no. |
| Bypass ROTE? | §5: no, route through it (cached profile). |
| Per-component-id update mechanism? | §6: activate the unused `Component.id` field; merge by id in the frontend. |
| Backpressure policy? | §7: single-slot coalescing buffer, last-write-wins, 5–30 fps clamp. |
| Auth revocation? | §8: cheap timestamp + background introspection job, 60 s upper bound (FR-012, SC-009). |
| Rollout safety? | §9: `FF_TOOL_STREAMING` flag, default off. |
| Multi-client fan-out (FR-009a)? | §11: deduplicate by `(user_id, chat_id, tool_name, params_hash)`, fan out to a shared subscribers list. Counts as one against the per-user cap. |
| Auto-retry on transient failure (FR-021a)? | §12: new RECONNECTING state, 1s/5s/15s exponential backoff with jitter, then manual retry. Auth failures bypass entirely. |

**No NEEDS CLARIFICATION markers remain. Ready for Phase 1.**
