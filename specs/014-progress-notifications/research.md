# Phase 0 Research: In-Chat Progress Notifications & Persistent Step Trail

All Technical Context fields resolved without `NEEDS CLARIFICATION`. The four `/speckit-clarify` answers (recorded in [spec.md](./spec.md) → Clarifications) closed every spec-level ambiguity. This document records decisions specific to the implementation strategy and the alternatives considered.

---

## R1. Where to emit step lifecycle events on the backend

**Decision**: A new `ChatStepRecorder` class in `backend/orchestrator/chat_steps.py`, instantiated per active task and passed into the existing tool-execution path at three seams:

1. `Orchestrator.execute_tool_and_wait()` — start/complete/error per tool invocation.
2. `Coordinator` agent hand-off boundaries — start/complete per delegation.
3. The orchestrator's existing `chat_status` transition points (where `thinking`/`fixing`/`executing` are emitted today, ~25 sites) — start/complete per orchestrator phase.

**Rationale**: The orchestrator already emits `chat_status` transitions at these exact sites (see `orchestrator.py:947, 1011, 1438, 1840, 1911, 2186, 2215, 2243, 2374, 2498, 2537, 2547, 2568, 2585, 2605, 2618, 3152, 3164, 3170, 3327, 3337` and similar). Reusing those seams means we don't have to discover new instrumentation points; we add a sibling emitter at each. `execute_tool_and_wait` is the single fan-out point for every tool call, so wrapping it in a try/except/finally yields exact start/complete/error events without duplication.

**Alternatives considered**:

- **Generic AOP/interceptor wrapping every async method** — rejected. Too magical for the codebase's style; would over-instrument internal helpers and inflate event volume.
- **Polling `TaskManager` state** — rejected. State transitions there are coarse (PENDING/RUNNING/AWAITING_TOOL/etc.) and don't carry step-level identity, name, or args.

---

## R2. Wire format — extend `chat_status` vs. new event type

**Decision**: A **new** WebSocket message type `chat_step` for per-step lifecycle events. Keep `chat_status` for the rotating-word/loading state and extend it minimally with an optional `cosmic_word` field.

**Rationale**: `chat_status` is already a small, frequently emitted "current state of the turn" event consumed by `useWebSocket.ts` and wired into `ChatStatus` (status + message). Step entries are persistent records — semantically different from a transient status. Mixing them on the same channel would force every existing consumer of `chat_status` to filter step events. A separate type also allows a future step-history-only fetch endpoint without touching the status channel.

**Alternatives considered**:

- **Embed steps inside `chat_status`** — rejected (semantic mismatch + breaks existing consumers).
- **Use the `audit_append` channel** — rejected. Audit events already serve the security audit log (feature 003) with different retention and authorization; mixing would muddle both.

---

## R3. Persistence model — separate table vs. embed in `messages.content`

**Decision**: A new `chat_steps` table (one row per step entry) plus a `step_count` cache column on `messages`. Step entries are not embedded in the message JSON.

**Rationale**:

- Steps belong to a turn (which is bounded by a user message + assistant reply), but they are **not** the assistant message — they are siblings of it. Embedding them in the assistant's `content` JSON would require updating the assistant message every time a step finishes, and would force the frontend to scan all assistant messages to find step entries when rehydrating history.
- A dedicated table preserves natural ordering by `started_at`, allows efficient retrieval per chat, and lets us index the FK to `chat_id` (the existing query pattern) and a generated column for "is terminal" if needed.
- `step_count` on `messages` is purely a render-time optimization so the chat list endpoint doesn't have to join.
- This matches the project's pattern: feature 003 used a dedicated `audit_events` table; feature 002 used `chat_files`. Inline-blob embedding was used in feature 013 only for tiny per-user prefs (not for streamed records).

**Alternatives considered**:

- **Embed steps as components in `messages.content`** — rejected (above).
- **Append-only event log keyed by chat_id with a composite type column** — rejected. Conflates step records with audit/log records and reduces type safety.

---

## R4. PHI/HIPAA redaction — where it runs

**Decision**: A new `backend/shared/phi_redactor.py` module that exposes a single `redact(value, *, kind)` function. The recorder calls `redact(args, kind="args")` and `redact(result_summary, kind="result")` **before** the step is persisted **and before** the `chat_step` event is emitted on the WebSocket. The same redactor is used on the read path when serving steps from `GET /chats/{id}/steps` to provide defense-in-depth (in case a record was written before the redactor was installed or by a path that bypassed it).

**Rationale**: Spec FR-009b mandates that PHI not appear in either rendered or persisted entries. Putting redaction at the boundary closest to write (and again at the read boundary) is the standard pattern for compliance — it gives us two independent enforcement points so a bug in one cannot leak data through the other. Keeping the redactor in `backend/shared/` lets future features (audit, exports) reuse the same logic without duplication.

**Implementation approach (no new dependencies)**: Pattern-based redaction over JSON — masks any field whose key matches a HIPAA identifier list (name, DOB, SSN, MRN, address line, phone, email, IP, account number, certificate, vehicle, device id, biometric, photo URL, full date < year, plus the 18 HIPAA Safe Harbor identifiers) and any string value matching DOB/SSN/phone/MRN regex shapes. Strings exceeding the truncation threshold are first redacted, then truncated. Redactor is pure-Python, dependency-free.

**Alternatives considered**:

- **Use a third-party PHI library (e.g., presidio)** — rejected by Constitution V (no new dependencies without lead-developer approval). The pattern-based approach is sufficient for the truncated-summary contract per FR-009a (we are not running clinical NLP over full bodies, only redacting recognizable identifiers from short summaries).
- **Run redaction only on persistence** — rejected. The WebSocket path would then briefly transmit raw payloads; FR-009b requires both rendered and persisted entries to be PHI-free.

---

## R5. Truncation policy

**Decision**: Uniform truncation across step types: arguments truncated to 512 characters of the JSON-stringified form, result summary truncated to 512 characters. If truncation occurs, the rendered entry shows an explicit `…` ellipsis and a `truncated: true` flag in the wire payload. Binary or non-JSON-serializable values render as `<binary:N bytes>`.

**Rationale**: 512 characters is roughly two terminal lines of context — enough for a human to recognize what was searched and what came back without bloating chat history. The existing `ProgressDetails.tsx` renders similarly sized snippets. A single threshold (rather than a per-step-type threshold) satisfies FR-009a's "applied consistently across all step types" requirement and keeps testing tractable.

**Alternatives considered**:

- **Per-step-type thresholds** — rejected (violates FR-009a).
- **No truncation, rely only on UI clipping** — rejected. Persistence would still hold the full payload, breaching the FR-009a "full raw inputs and full raw results MUST NOT be persisted" guarantee.

---

## R6. Cancellation semantics — best-effort abort, result discard

**Decision**: When a `cancel_task` message arrives (already handled at `orchestrator.py:947`):

1. The active `Task` transitions to `CANCELLED` via the existing state machine.
2. The recorder iterates currently-in-progress step entries, marks each `cancelled`, and emits a `chat_step` lifecycle event (`status: "cancelled"`).
3. The event loop's task wrapping the in-flight tool call is cancelled with `task.cancel()`, which raises `asyncio.CancelledError` inside `_execute_via_websocket` / `_execute_via_a2a` (a path the code already handles at `orchestrator.py:4003`).
4. For network requests already issued to a remote agent, the orchestrator does NOT block waiting for them — but if a response arrives later, it is dropped on the floor by checking the recorder's per-step terminal flag before integrating the result into the assistant reply.

**Rationale**: Matches Q4 clarification (best-effort abort + discard). Reuses the existing `asyncio.CancelledError` plumbing rather than introducing cancellation tokens. The terminal-flag check is a five-line guard at the seams that already integrate tool results.

**Alternatives considered**:

- **Hard abort (Q4 option C)** — rejected by user choice; would require every downstream (A2A, sub-agents) to wire a cancellation token.
- **Mark-only (Q4 option A)** — rejected by user choice; wastes external API quota.

---

## R7. Frontend rotating-word implementation

**Decision**: A self-contained `<CosmicProgressIndicator>` component that runs an internal `setInterval` (cleared on unmount and on `chatStatus.status` reaching `done`/`idle`), pulling words from a 55-element constant array exported from `chatStepWords.ts`. Word selection: random, with a tiny anti-stutter rule that never picks the same word twice in a row. Cadence: 1.2 seconds (within SC-002's 1×/sec floor and 3 sec ceiling). Transitions: `framer-motion` fade at 200 ms (already used elsewhere in the codebase, e.g., `ChatInterface.tsx:677`).

**Rationale**: The list is a single source of truth (`chatStepWords.ts`) so backend tests don't need a duplicate list — the backend never reads it. Random selection with no-immediate-repeat is the pattern Claude's UI uses and avoids visual stutter. 1.2 sec is fast enough to feel alive and slow enough to read.

**Alternatives considered**:

- **CSS-only crossfade with hand-rolled animation** — rejected. `framer-motion` is already in the bundle for `ChatInterface`; extra animation state would just inflate code.
- **Server-driven word selection** — rejected. Adds zero value (no a/b testability planned), increases WebSocket traffic, and creates network-jitter sensitivity that breaks SC-002.

---

## R8. Frontend collapse-state persistence

**Decision**: `useStepCollapseState(stepId, status)` hook backed by `sessionStorage` under a single key `astral.chat_step_collapse.v1`. Hook reads on mount, persists on toggle, and applies the status-dependent default when the entry has no stored override (FR-016: success → collapsed, error/cancelled → expanded, in-progress → expanded). `sessionStorage` is per-tab and dies with the tab/window — matching FR-019's "scoped to local browser session" exactly.

**Rationale**: `sessionStorage` is the literal browser primitive for "this session." `localStorage` would over-persist (FR-019 explicitly says collapse state need not survive logout/device move). A single JSON object under one key keeps the storage footprint compact and avoids per-id key pollution. The hook is a thin layer (~30 lines) reusing the project's existing functional-state pattern.

**Alternatives considered**:

- **`localStorage`** — rejected (over-persists per FR-019).
- **Backend per-user preferences (table `user_preferences` à la feature 013)** — rejected (over-persists; introduces unnecessary network round-trips on collapse/expand; FR-019 explicitly scopes this to the local session).
- **In-memory React state only** — rejected (loses state across page reloads, violating FR-018).

---

## R9. Live-vs.-history rehydration

**Decision**: Three paths share the same rendering:

- **Live**: `useWebSocket` accumulates `chat_step` events into a per-chat `chatSteps` map keyed by `(chat_id, step_id)`.
- **Initial chat load**: `GET /chats/{id}/steps` returns all step rows for that chat (already-redacted), feeding the same `chatSteps` map.
- **Resume after disconnect**: On reconnect, `useWebSocket`'s existing rehydrate path also calls `GET /chats/{id}/steps`, then any `chat_step` events newer than the latest `started_at` reconcile via the same key. Any step row that was `in_progress` at disconnect time and is older than 30 seconds is treated as `interrupted` for rendering (covers the connection-drop edge case).

**Rationale**: One state shape, three feeders. Reuses the existing `useWebSocket` rehydrate machinery instead of building a parallel one. The 30-second cutoff matches the existing tool timeout default in `execute_tool_and_wait` (`timeout: float = 30.0`).

**Alternatives considered**:

- **Re-derive steps from `chat_status` history** — rejected; status is transient and not persisted.
- **Stream historical steps via WebSocket on reconnect** — rejected; one-shot REST is simpler and already matches the chat-loaded pattern.

---

## R10. Migration strategy

**Decision**: Extend `Database._init_schema()` in `backend/shared/database.py` with idempotent `CREATE TABLE IF NOT EXISTS chat_steps (...)` and a guarded `ALTER TABLE messages ADD COLUMN step_count INTEGER DEFAULT 0` using the existing `_column_exists` helper (used elsewhere in `database.py:117–131`). No standalone migration file — matches the established project pattern (feature 013 used the same approach for `chats.agent_id`).

**Rationale**: Constitution IX requires automatic, idempotent migrations executed on startup. The existing `_init_schema` flow IS that mechanism in this project. Adding to it keeps the schema defined in one place and stays consistent with prior features.

**Alternatives considered**:

- **Standalone Alembic migration file** — rejected. The project does not use Alembic on this DB layer (no `alembic.ini`); introducing it for one feature would be over-engineering.

---

## Open questions deferred to implementation

None block planning. Two items previously deferred during clarification can be revisited during `/speckit-tasks` or post-merge:

- Whether step entries appear in chat exports/shares beyond the FR-009b PHI guarantee — depends on the existing chat-export pipeline (out of scope here; will inherit whatever that pipeline does, with redacted content already in place).
- Specific PHI detection regex tuning — owned by `backend/shared/phi_redactor.py` and refinable in place without touching this feature's contracts.
