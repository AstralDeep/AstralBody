# Phase 1 Data Model: Real-Time Tool Streaming to UI

**Feature**: 001-tool-stream-ui
**Date**: 2026-04-09 *(revised after `/speckit.clarify` session — adds multi-client fan-out per FR-009a and the RECONNECTING state per FR-021a)*

This document defines the runtime entities, their fields, relationships, validation rules, and state transitions. **No database schema is added** — all state is in-memory in the orchestrator process. The only existing data structure that this feature modifies is the `Component` dataclass in [backend/shared/primitives.py](../../backend/shared/primitives.py), which already has the necessary `id` field — we only start populating it.

---

## Entity Map (overview)

```text
┌──────────────────┐  1   *  ┌──────────────────┐  1   *  ┌──────────────────┐
│   UserSession    │────────▶│   ChatSession    │────────▶│ StreamSubscription│
│ (websocket-bound)│         │ (chat_id-bound)  │         │ (per stream)      │
└──────────────────┘         └──────────────────┘         └──────────────────┘
                                      │                            │
                                      │                            │ produces
                                      │                            ▼
                                      │                  ┌──────────────────┐
                                      │                  │   StreamChunk    │
                                      │                  │  (per emission)  │
                                      │                  └──────────────────┘
                                      │
                                      │ holds dormant entries when not active
                                      ▼
                              ┌──────────────────┐
                              │ DormantStreamRef │
                              │ (resumable spec) │
                              └──────────────────┘
```

---

## 1. `UserSession` (existing — no changes)

**Defined**: in-memory in `Orchestrator.ui_sessions: Dict[WebSocket, dict]` (already exists).

**Source of truth**: [backend/orchestrator/orchestrator.py](../../backend/orchestrator/orchestrator.py) lines 78–87, populated by `register_ui` handler.

**Fields used by this feature** (no new fields):

| Field | Type | Source | Purpose |
|---|---|---|---|
| `sub` | `str` | JWT claim | The Keycloak user_id. Used to scope streams. |
| `_raw_token` | `str` | JWT raw form | Used for RFC 8693 delegation per chunk batch. |
| `expires_at` | `int` (epoch sec) | JWT `exp` claim | Cheap revocation check on each chunk send. |
| `roles` | `list[str]` | `realm_access.roles` | Authorization for `stream_subscribe`. |

**Validation**: existing — `register_ui` handler verifies JWT signature against JWKS (production) or accepts mock JWT (dev).

**Lifecycle**: created on `register_ui`, destroyed on WebSocket disconnect. The stream manager subscribes to disconnect to drive the "leave" lifecycle event.

---

## 2. `ChatSession` (existing — no changes)

**Defined**: in the SQLite history database, accessed via `self.history.get_chat(chat_id, user_id=...)`.

**Fields used by this feature**: only `chat_id` and `user_id`. The stream manager uses `(user_id, chat_id)` as the dormant-table key. No new columns added.

**Validation**: existing — `chat_id` must belong to the authenticated user; this check already happens in `handle_chat_message` and `load_chat` handlers.

**Lifecycle**: orthogonal to streams. A chat outliving its streams is normal (the user sent a message, didn't subscribe to anything). A stream cannot outlive its chat (cleanup on chat deletion is **out of scope** for this feature — chat deletion is rare and the orchestrator restart will clean any orphaned streams).

---

## 3. `StreamSubscription` (NEW)

**Defined**: in-memory in `StreamManager._active: Dict[StreamKey, StreamSubscription]`.

**Identity** *(revised: keyed by `params_hash`, not `stream_id`, so multiple subscribe requests from the same user for the same `(chat, tool, params)` resolve to the same subscription — FR-009a fan-out)*:

```python
StreamKey = tuple[str, str, str, str]  # (user_id, chat_id, tool_name, params_hash)
```

**Fields**:

| Field | Type | Required | Description | Validation |
|---|---|---|---|---|
| `stream_id` | `str` | yes | Server-assigned UUID. Opaque to the client. Used as `Component.id` for the rendered component. Stable across the subscription's lifetime, including across `RECONNECTING` retries. | Generated server-side; never trusted from client. |
| `user_id` | `str` | yes | Owner. From `UserSession.sub`. | MUST equal current websocket's `user_id` on every operation. |
| `chat_id` | `str` | yes | Chat the stream belongs to. | MUST be a chat owned by `user_id`. Verified at subscribe. |
| `tool_name` | `str` | yes | Tool identifier. | MUST be in the registered streamable tools list (existing `_streamable_tools`). |
| `agent_id` | `str` | yes | Which agent provides the tool. | Derived from streamable tools registry. |
| `params` | `dict` | yes | Tool input arguments at subscribe time. Used unchanged on resume. | Schema validated against the tool's MCP input schema (existing validation). Size cap: 16 KB. |
| `params_hash` | `str` | derived | SHA-256 of canonical JSON of `params`, first 16 hex chars. **Part of the subscription key** — a second subscribe with the same hash from any of the user's clients attaches to the existing subscription. | — |
| `component_id` | `str` | derived | Equals `stream_id`. The id frontend uses to merge chunks. | — |
| `subscribers` | `list[WebSocket]` | yes | **NEW (FR-009a)**. The set of websockets — all owned by `user_id` — currently subscribed to this stream. The list grows when another tab attaches and shrinks as tabs leave. The subscription is alive (non-DORMANT) iff this list is non-empty. | Each entry MUST have `ui_sessions[ws]["sub"] == user_id`. Duplicate-add is idempotent. |
| `created_at` | `float` | yes | Monotonic time of subscribe. | — |
| `last_chunk_at` | `Optional[float]` | no | Monotonic time of last chunk delivered to UI. None until first chunk. | — |
| `state` | `StreamState` enum | yes | One of `STARTING`, `ACTIVE`, `RECONNECTING`, `DORMANT`, `STOPPED`, `FAILED`. | See state transitions below. |
| `state_reason` | `Optional[str]` | no | Human-readable reason for `RECONNECTING`/`STOPPED`/`FAILED`. | — |
| `retry_attempt` | `int` | yes | **NEW (FR-021a)**. 0 while `ACTIVE`. Set to 1, 2, 3 when entering `RECONNECTING` for each backoff. Reset to 0 on successful chunk after retry. | 0 ≤ retry_attempt ≤ 3. |
| `next_retry_at` | `Optional[float]` | no | **NEW (FR-021a)**. Monotonic time of the next scheduled retry attempt. None unless `state == RECONNECTING`. | — |
| `last_error_code` | `Optional[str]` | no | **NEW (FR-021a)**. Last error code observed; used to populate `error.code` on the reconnecting/failed chunk. | — |
| `task` | `Optional[asyncio.Task]` | no | The orchestrator-side draining task. None when not active. | — |
| `coalesce_slot` | `Optional[StreamChunk]` | no | The single-slot coalescing buffer (see research §7). | Size capped indirectly by chunk size cap. |
| `send_in_progress` | `bool` | yes | True while at least one of the per-subscriber `ws.send_text(...)` calls is in flight. | — |
| `delivered_count` | `int` | yes | Number of chunks delivered to the UI (post-coalescing), counted **per subscriber-send**. A chunk fanned out to 3 subscribers increments by 3. | Monotonic. For observability. |
| `dropped_count` | `int` | yes | Number of chunks dropped due to coalescing. | Monotonic. For observability. |

**Cardinality** *(revised for fan-out)*:

- One `UserSession` (i.e., one websocket) may appear in **many** `StreamSubscription.subscribers` lists — once for each `(chat, tool, params)` it has subscribed to.
- One `(user_id, chat_id, tool_name, params_hash)` tuple maps to **exactly one** `StreamSubscription` in either `_active` or `_dormant`. Per FR-009a, a duplicate subscribe attaches the new websocket to the existing entry instead of allocating a second one.
- The per-user concurrency cap (`_MAX_STREAM_SUBSCRIPTIONS = 10`, FR-015) counts **distinct subscription keys** for the user, not websockets. A user with 3 tabs each subscribing to the same 4 streams = 4 against the cap, not 12.

**Validation rules**:

1. `user_id` MUST match the websocket's authenticated user on every subscribe / attach (FR-011).
2. `chat_id` MUST exist and belong to `user_id` (existing chat ownership check).
3. `tool_name` MUST be present in `_streamable_tools` and the user MUST have the required scope per `_get_delegation_token` (FR-010).
4. Distinct active subscription keys per user MUST be ≤ `_MAX_STREAM_SUBSCRIPTIONS` (10). Attaching a new websocket to an existing subscription does NOT count.
5. `params` size MUST be ≤ 16 KB after JSON serialization.
6. `subscribers` list MUST be non-empty whenever `state ∈ {STARTING, ACTIVE, RECONNECTING}`. Becoming empty triggers `→ DORMANT`.

### State transitions *(revised: adds RECONNECTING state per FR-021a)*

```text
                  subscribe (or attach to existing)
                 ──────────────────────────────────►
   ┌──────────┐               ┌──────────┐ first chunk      ┌──────────┐
   │ (none)   │  validate ok  │ STARTING │─────────────────►│  ACTIVE  │◄────┐
   └──────────┘──────────────►└──────────┘                  └────┬─────┘     │
                                   │                             │           │ first
                                   │ tool error                  │           │ successful
                                   │ before any chunk            │           │ chunk after
                                   ▼                             │           │ retry
                              ┌──────────┐                       │           │
                              │  FAILED  │                       │           │
                              └──────────┘                       │       ┌───┴───────────┐
                                                                 │       │ RECONNECTING  │
                                                                 │       │ (1s, 5s, 15s) │
                                                                 │       └───┬───────────┘
                                                                 │           │
                                                                 │           │ 3 attempts
                                                                 │           │ exhausted
                                                                 │           ▼
                                                                 │      ┌──────────┐
                                                                 │      │  FAILED  │
                                                                 │      └──────────┘
                                                                 │
                                                                 │ subscribers list empties
                                                                 │  (last tab leaves)
                                                                 ▼
                                                            ┌──────────┐
                                                            │ DORMANT  │
                                                            └────┬─────┘
                                                                 │
                                                                 │ a subscriber returns
                                                                 ▼
                                                            ┌──────────┐
                                                            │ STARTING │  (new task, fresh data)
                                                            └────┬─────┘
                                                                 │
                                                                 │ explicit unsubscribe (last)
                                                                 │ OR TTL expiry
                                                                 │ OR token revoked
                                                                 ▼
                                                            ┌──────────┐
                                                            │ STOPPED  │  (terminal)
                                                            └──────────┘

  ACTIVE → RECONNECTING happens on any TRANSIENT error (tool_error, upstream_unavailable,
  rate_limited, or chunk-send IO error). Auth failures (unauthenticated, unauthorized)
  go directly ACTIVE → FAILED — they bypass the retry loop entirely (research §12).
```

| Transition | Trigger | Side effects |
|---|---|---|
| `(none) → STARTING` | `stream_subscribe` action received, validated, AND no existing subscription matches `(user_id, chat_id, tool_name, params_hash)` | Allocate `stream_id`, append the requesting websocket to `subscribers`, register in `_active`, create `asyncio.Task` that opens the agent-side generator. |
| `(attach)` (no transition) | `stream_subscribe` arrives with a key that matches an existing `_active` subscription | Append the websocket to `subscribers`, send `stream_subscribed` confirmation immediately with the existing `stream_id`. The agent-side task is NOT touched. The next chunk fans out to the new subscriber. |
| `STARTING → ACTIVE` | First `ToolStreamData` arrives from agent | Set `last_chunk_at`. Fan out first `ui_stream_data` chunk to all subscribers (within SC-001 = 2 s budget). |
| `STARTING → FAILED` | Tool raises before first chunk, or agent unreachable, AND error code is in the non-retryable set (auth, chunk_too_large, cancelled) | Send `ui_stream_data` with `error.phase == "failed"` to all subscribers. Move to `STOPPED` after sending. |
| `STARTING → RECONNECTING` | Tool raises before first chunk with a transient code | Same as `ACTIVE → RECONNECTING` below, with `retry_attempt = 1`. |
| `ACTIVE → RECONNECTING` (FR-021a) | Transient error mid-stream (`tool_error`, `upstream_unavailable`, `rate_limited`, chunk-send IOError, or agent disconnect) AND `retry_attempt < 3` | Set `state = RECONNECTING`, `retry_attempt += 1`, `next_retry_at = now() + backoff(retry_attempt)` where backoff is 1/5/15 s with ±20% jitter (research §12). Cancel current `task`. Fan out a `ui_stream_data` chunk to all subscribers with `error.phase == "reconnecting"`, `error.code == <last>`, `error.attempt == retry_attempt`, `error.next_retry_at_ms`. |
| `RECONNECTING → STARTING` | Backoff timer fires | Create new `task` with same `stream_id`, same `params`, same `agent_id`. (Internally identical to the `DORMANT → STARTING` resume path.) |
| `RECONNECTING → ACTIVE` | First successful chunk arrives after retry | Reset `retry_attempt = 0`, `next_retry_at = None`, `last_error_code = None`. Fan out the chunk normally — its merge by `id` overwrites the reconnecting state in every subscriber's UI. |
| `RECONNECTING → FAILED` | Retry produces another transient error AND `retry_attempt == 3` (3 attempts exhausted) | Fan out `ui_stream_data` with `error.phase == "failed"`, `error.retryable == true`. Move to `STOPPED` after sending. The user clicking retry re-issues `stream_subscribe`, which starts a fresh subscription. |
| `RECONNECTING → DORMANT` | Subscribers list empties during a retry window | Cancel backoff timer, drop `retry_attempt` and `next_retry_at`, move to `_dormant`. On return, starts fresh (resets retry counter). |
| `ACTIVE → FAILED` (auth path) | Mid-stream error code is `unauthenticated` or `unauthorized` | **Bypasses RECONNECTING entirely** (security — never auto-retry a revoked token). Fan out `ui_stream_data` with `error.phase == "failed"`, `error.code == "unauthenticated"`, `error.retryable == false`. Frontend renders re-authentication state. Move to `STOPPED`. |
| `ACTIVE → DORMANT` | The **last** websocket in `subscribers` leaves the chat (`load_chat` to a different `chat_id` for that ws, `ws_disconnect`, or explicit `stream_unsubscribe` from that ws) | If the subscribers list still has entries after the removal, **no transition occurs** — the stream stays `ACTIVE` for the remaining tabs. Only when `len(subscribers) == 0` do we cancel `task`, send `ToolStreamCancel`, and move the record from `_active` to `_dormant[(user_id, chat_id)]`. |
| `DORMANT → STARTING` | A `stream_subscribe` (or auto-subscribe on `load_chat` return) arrives matching the dormant key | Pop from `_dormant`, append the requesting websocket to a fresh `subscribers` list, create new `task`, re-issue subscribe to agent with original `params` and same `stream_id`. UI sees fresh first chunk. |
| `ACTIVE → STOPPED` | Last subscriber sent `stream_unsubscribe`, OR token-introspection sweep finds the user's token revoked, OR `_MAX_STREAM_SUBSCRIPTIONS` exceeded by a higher-priority subscribe (LRU eviction) | Cancel task, free slot, send `ui_stream_data` with `terminal: true` to all remaining subscribers. |
| `DORMANT → STOPPED` | TTL expires (default 1 hour), OR `_MAX_DORMANT_PER_USER` (50, FR-015) exceeded (LRU evicts oldest dormant) | Free slot. UI is not notified (the user isn't viewing the chat). On their return, the stream is simply absent — they may re-trigger it via the original chat action. |

**Invariants** *(revised)*:

- A stream is in **at most one** of `_active`, `_dormant`. Never both.
- `STARTING`, `ACTIVE`, `RECONNECTING` MUST have a non-empty `subscribers` list.
- `STARTING` and `ACTIVE` MUST have a non-None `task`. `RECONNECTING` has `task = None` (it's between attempts) but has a non-None `next_retry_at`.
- `DORMANT`, `STOPPED`, and `FAILED` MUST have `task = None` AND `next_retry_at = None`.
- `retry_attempt == 0` whenever `state == ACTIVE`. `retry_attempt > 0` only in `RECONNECTING` or in the moment between `RECONNECTING → STARTING` and the first successful chunk.
- Auth failures (`unauthenticated`, `unauthorized`) MUST NEVER cause an `ACTIVE → RECONNECTING` transition. They go straight to `FAILED` — verified by a unit test.
- `delivered_count` and `dropped_count` are monotonically non-decreasing.
- For any websocket `ws` in any subscription's `subscribers`: `ui_sessions[ws]["sub"] == subscription.user_id`. Cross-user attachment is forbidden.

---

## 4. `DormantStreamRef` (NEW)

**Defined**: in-memory in `StreamManager._dormant: Dict[tuple[str, str], dict[str, StreamSubscription]]`.

**Outer key**: `(user_id, chat_id)`.
**Inner key**: `params_hash` (the same field that, combined with the outer key and `tool_name`, forms the active-table `StreamKey`).
**Inner value**: A `StreamSubscription` with `state == DORMANT` and `subscribers == []`. It is *the same dataclass*; we don't introduce a separate type. The dormant table is just a different residence. On `DORMANT → STARTING`, the dormant entry is popped, the returning websocket is appended to a fresh `subscribers` list, and the subscription moves back to `_active`.

**Caps**:

- Per `(user_id, chat_id)`: no explicit cap (dominated by per-user cap).
- Per `user_id` (across all dormant chats): `_MAX_DORMANT_PER_USER` (default 50, configurable).
- TTL: `_DORMANT_TTL_SECONDS` (default 3600). Background sweeper task in `StreamManager` removes expired entries.

**Why a separate residence**: keeping dormant subscriptions out of `_active` makes the active-cap accounting clean (`len(_active per user) <= 10`) and lets the per-chat resume scan be O(1) rather than scanning all subscriptions for matches.

---

## 5. `StreamChunk` (NEW)

**Defined**: a transient dataclass passed from agent → orchestrator → frontend. Not persisted.

**Wire form**: see [contracts/protocol-messages.md](contracts/protocol-messages.md). This section is the in-memory representation.

**Fields**:

| Field | Type | Required | Description |
|---|---|---|---|
| `stream_id` | `str` | yes | Identifies the subscription this chunk belongs to. MUST equal the `id` of the component(s) in the chunk (or one of them, in container cases). |
| `seq` | `int` | yes | Monotonically increasing per-stream sequence number, assigned by the **agent**. The orchestrator uses it for logging and for the coalescing buffer to detect "newer arrived during send." |
| `components` | `list[Component]` | yes | The UI components to merge into the existing render. May be a single primitive (most common) or a small subtree. Total serialized size MUST be ≤ 64 KB. |
| `raw` | `Optional[Any]` | no | Optional raw data the tool wants to make available to the frontend (e.g. for charting). Counted against the 64 KB cap. |
| `error` | `Optional[StreamError]` | no | Set when this chunk is an error notification. Mutually exclusive with `components` of new data. |
| `terminal` | `bool` | no | True when this chunk is the last for the stream (e.g., the tool completed naturally). Default false. |

**Validation**:

- `stream_id` MUST be an `_active` stream owned by the websocket the chunk is being delivered on.
- Total size cap (64 KB) — chunks exceeding this are dropped at the orchestrator and a `FAILED` transition is triggered with reason `chunk_too_large`. Prevents memory blow-up from a runaway tool.
- `seq` MUST be > the last `seq` seen for this stream. Out-of-order chunks are dropped (last-write-wins still applies in the coalescing slot).

---

## 6. `StreamError` (NEW, embedded in StreamChunk)

*Revised for FR-021a: adds `phase`, `attempt`, `next_retry_at_ms` so the frontend can distinguish "we're trying" from "we gave up".*

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | `str` enum | yes | One of: `tool_error`, `unauthenticated`, `unauthorized`, `rate_limited`, `upstream_unavailable`, `chunk_too_large`, `cancelled`. |
| `message` | `str` | yes | Human-readable, safe to display in the UI. MUST NOT contain stack traces or internal paths. |
| `phase` | `"reconnecting" \| "failed"` | yes | **NEW**. `"reconnecting"` = the orchestrator is in the FR-021a backoff loop and the stream may recover automatically. `"failed"` = terminal; the user must take action (retry button or re-authenticate). |
| `retryable` | `bool` | yes | Whether the user retry button (FR-021) should be enabled. Always `false` when `phase == "reconnecting"` (the system is already retrying). Always `false` when `code ∈ {unauthenticated, unauthorized, chunk_too_large, cancelled}`. Always `true` when `phase == "failed"` and the cause is transient. |
| `attempt` | `Optional[int]` | when `phase == "reconnecting"` | Current retry attempt (1, 2, or 3). Allows the UI to show "Reconnecting (attempt 2/3)…". |
| `next_retry_at_ms` | `Optional[int]` | when `phase == "reconnecting"` | Wall-clock epoch milliseconds of the next retry attempt. Allows the UI to render a countdown if it wants. |

**Classification table** (which codes get auto-retried):

| `code` | `phase` produced on first error | Auto-retry? | Notes |
|---|---|---|---|
| `tool_error` | `reconnecting` | yes | Could be a flaky upstream. |
| `upstream_unavailable` | `reconnecting` | yes | Network blip / 503 / DNS hiccup. |
| `rate_limited` | `reconnecting` | yes (with jitter) | Backoff naturally helps. |
| `chunk_too_large` | `failed` | **no** | Deterministic — same chunk will be too large on retry. |
| `cancelled` | `failed` | **no** | Explicit cancellation isn't a failure. |
| `unauthenticated` | `failed` | **no** | Security: never auto-recover from a revoked token. |
| `unauthorized` | `failed` | **no** | Security: scope changes are not transient. |

This table is the runtime enforcement of the security carve-out in research §12.

---

## 7. `StreamableToolMetadata` (existing — extended)

**Defined**: registered at agent startup via the existing `RegisterAgent` flow. Stored in `Orchestrator._streamable_tools: Dict[str, dict]` (already exists per orchestrator exploration).

**Existing fields**: `agent_id`, `default_interval`, `min_interval`, `max_interval` (used by the polling-based `stream_subscribe` path; left untouched).

**New fields** (additive — old tools without them keep working as polled streams):

| Field | Type | Default | Description |
|---|---|---|---|
| `kind` | `"poll" \| "push"` | `"poll"` | `"poll"` = orchestrator drives cadence (existing); `"push"` = tool is an async generator and produces chunks itself. |
| `max_chunk_bytes` | `int` | 65536 | Per-stream override of the default 64 KB cap. |
| `max_fps` | `int` | 30 | Per-stream override of the default coalescing upper bound. |
| `min_fps` | `int` | 5 | Per-stream override of the default coalescing lower bound. |

**Validation**: `kind` MUST be one of the two literals. `max_fps` and `min_fps` MUST satisfy `1 <= min_fps <= max_fps <= 60`.

---

## 8. Relationships and authorization model

**Authorization invariant** *(revised: applies per-subscriber for fan-out)*: For any `StreamChunk` being fanned out from a `StreamSubscription` `s`, the orchestrator iterates `s.subscribers` and for each websocket `ws` in the list, all of the following MUST be true before sending to that specific `ws`:

1. `ws` is in `Orchestrator.ui_clients` and `ui_sessions[ws]` is populated.
2. `ui_sessions[ws]["sub"] == s.user_id` (defense in depth — the subscriber should never have been added otherwise, but we re-check at send time).
3. The websocket is currently loaded into `s.chat_id` (i.e., the user hasn't switched this particular tab to a different chat since attaching). If it has, the websocket is removed from `s.subscribers` and the send to **this** ws is skipped — the other subscribers still receive the chunk.
4. `ui_sessions[ws]["expires_at"] > now()`. If expired, this websocket is removed from `s.subscribers` AND a single `ui_stream_data` chunk with `error.phase == "failed"`, `error.code == "unauthenticated"` is sent to this websocket only. The other subscribers continue receiving normal chunks.

If after iterating, `s.subscribers` is empty, the subscription transitions to `DORMANT` (the same path as a clean leave).

This invariant is the runtime enforcement of FR-010, FR-011, FR-012, and **FR-009a (fan-out isolation)**. It is exercised by `test_stream_isolation.py` (cross-user) and a new `test_stream_fanout.py` (intra-user multi-tab, including the case where one tab's token expires while the other continues).

---

## 9. What is **not** in this data model

- **No persistent storage of streams.** Dormant state is in-memory; orchestrator restart loses it. Acceptable per research §3.
- **No persistent storage of chunks.** Per A-007, no backfill on resume.
- **No new database tables, no migrations.**
- **No user-facing entity** (the user only sees a UI component; they have no concept of "subscription" — that's an implementation detail).
- **No new field on the existing `Component` dataclass.** The `id` field is already there; we just start populating it.
- **No cross-user fan-out.** FR-009a only deduplicates within a single `user_id`. Two different users running the same tool with the same params get two independent subscriptions. Sharing a stream across users is explicitly out of scope (spec.md "Out of Scope").
- **No retry of auth failures.** Per the §6 classification table and research §12, `unauthenticated`/`unauthorized` skip the `RECONNECTING` state entirely. Any test that exercises auth-failure paths must verify this property.
