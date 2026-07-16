# Contract: Canonical Operation and Agent Lifecycle Status

**Scope**: FR-032, FR-043, FR-047, FR-054–FR-057; SC-011, SC-016, SC-022
**Authority**: server operation/runtime state. A client creates a distinct local-only `submitting`
projection for immediate feedback, but cannot claim durable `accepted` or invent a server terminal
result.

## 1. `operation_status` frame

```json
{
  "type": "operation_status",
  "operation_id": "3558c68b-a02e-4529-9cf8-5ba95bcc7951",
  "action": "chrome_llm_save",
  "surface": "llm_settings",
  "chat_id": null,
  "connection_generation": "dbe2670f-04ce-40c8-ab08-615500571f90",
  "request_generation": "b1876d0c-7401-47fa-8c78-8cdedba692a8",
  "sequence": 2,
  "state": "validating",
  "phase": "validating_credentials",
  "label": "Checking your provider credentials…",
  "terminal": false,
  "retryable": false,
  "error": null,
  "retry_after_ms": null,
  "updated_at": "2026-07-15T18:41:00Z"
}
```

All fields are required; nullable values are explicit JSON null. IDs are full UUIDs. `action` and
`phase` are stable snake-case machine values; `label` is safe user-facing text. `sequence` is a
non-negative 64-bit integer increasing within an operation. A repeated sequence and any lower
sequence are ignored.

Canonical states and derived flags are:

| State | Terminal | Retryable | Meaning |
|---|---:|---:|---|
| `accepted` | false | false | server confirms the operation is durably accepted/queued |
| `validating` | false | false | checking normalized input or provider response |
| `persisting` | false | false | committing accepted state |
| `running` | false | false | other active execution |
| `completed` | true | false | committed success |
| `failed` | true | false | corrective/non-retryable failure for this input |
| `cancelled` | true | false | user, disconnect, supersession, or shutdown cancelled |
| `retryable` | true | true | attempt ended; a new attempt may be submitted |

The only valid flags are those in the table. `error` is null for non-terminal and completed states;
for `failed`, `cancelled`, or `retryable` it is
`{"code":"<stable_code>","message":"<safe corrective text>"}`. `retry_after_ms` is non-null only
when state is `retryable` and the service knows a delay.

Stable shared codes are: `invalid_input`, `validation_failed`, `provider_unavailable`,
`network_unavailable`, `deadline_exceeded`, `capacity_exceeded`, `queue_wait_expired`,
`registration_timeout`, `disconnected`, `cancelled_by_user`, `operation_failed`, `conflict`,
`incompatible_runtime`, `agent_offline`, and `stale_generation`. More specific internal diagnostics
map to one of these before crossing the UI wire.

## 2. Ordering and terminal ownership

The initiating client creates UUID4 `submission_id` and `request_generation`, records a local-only
`submitting` projection immediately, and includes both on the `ui_event`. `submitting` has no
`operation_id`, is not an `operation_status` wire frame, is not included in the canonical server
state table, and never counts as accepted work. It may use the action/surface/chat/generations and a
safe “Submitting…” label solely to render immediate feedback.

The server treats `submission_id` as the owner-scoped retry identity. After durable admission, the
server allocates `operation_id` and returns/emits the first canonical `operation_status` with state
`accepted`. Its `sequence` is the durable operation `state_revision` (normally zero at acceptance),
and every later status sequence is the corresponding increasing revision. Repeating the same
submission resolves the same accepted operation. An admission refusal is correlated by
`submission_id` and terminalizes only the local submission projection as failed/retryable; it does
not fabricate an `operation_id` or an `operation_status` terminal.

The durable operation coordinator compare-and-sets the first terminal state. Exactly one server
terminal can be emitted; duplicate or late terminal attempts are suppressed. Clients retain the
highest sequence and first terminal. A late `completed` after `failed`, `cancelled`, or `retryable`
is a no-op even if it has a larger sequence. Retrying after a definitive server terminal/refusal
creates a new submission and request generation. Retrying transport while acceptance is unknown
reuses the same submission ID so it cannot create a second operation.

Chat-scoped statuses obey the conversation generation checks. Surface-only statuses require the
current connection/request generation but have `chat_id: null`. Reconnect obtains the retained
operation projection while the operation record remains within its retention window.

## 3. Timing and presentation

- The initiating control visibly acknowledges activation within **250 ms**. This is local and does
  not wait for socket, provider, database, or server round trip; its state is `submitting`, never
  `accepted`.
- If any operation remains active at one second, its current phase label is visible. All operations
  longer than two seconds therefore meet FR-043's status deadline.
- Only the duplicate initiating control is disabled during single-flight work. Navigation, focus,
  scrolling, window/scene resizing, and unrelated controls stay responsive and acknowledge within
  250 ms.
- Status is exposed as an accessible live region/status role without stealing focus. Controls retain
  stable name, role, enabled/busy state, and keyboard/focus order.
- Every progress sequence ends in exactly one terminal state. Removing a spinner without a terminal
  label is invalid.

## 4. Apple first-login LLM Save specialization

`chrome_llm_save` uses this exact phase path:

```text
accepted → validating/validating_credentials → persisting/saving_credentials → completed
```

Allowed terminal mappings:

- invalid provider/key response → `failed`, code `validation_failed`, fields remain editable;
- provider/network unavailable → `retryable`, code `provider_unavailable` or
  `network_unavailable`, fields remain editable;
- whole-attempt ten-second bound → `retryable`, code `deadline_exceeded`;
- user cancels/signs out → `cancelled`.

The server owns one **10-second** outer deadline covering validation, persistence, unlock, and the
durable terminal transition. Terminal delivery is replayable/queryable and is not assumed merely
because a socket send was attempted. Provider probing has an **8-second maximum** so later phases
have budget. Completion is valid only after credentials are durably persisted and the first-login
gate is unlocked. On `completed`, the app advances to the next server-owned page; on an active
connection in release trials this occurs within five seconds at least 95% of the time. At the owned
deadline the server atomically terminalizes the operation `retryable/deadline_exceeded` and clears
its execution lease token. A provider success carrying the prior BIGINT execution generation and
UUID token afterward cannot persist, unlock, navigate, or replace that terminal.

Independently, iOS and macOS start a monotonic **10-second client watchdog** at Save activation. It
runs across socket loss, app background/foreground, and scene/window changes. If no authoritative
server terminal has arrived when it fires, the client stops the loading indicator, leaves the form
editable, and displays a safe retryable “Unable to confirm; reconnecting” result keyed by the same
submission/operation. This watchdog result is a local connectivity projection, not a fabricated
server terminal, so it cannot suppress the first durable server result.

When connectivity is available, the client reconciles a reconnectable operation—which the server
admitted as user-owned before execution—with `GET /api/operations/{operation_id}`. If disconnection
occurred before the accepted response exposed an operation ID, it resolves the same user-owned
submission through
`GET /api/operation-submissions/{submission_id}`; the response is either the original accepted
operation projection or its definitive admission refusal. Reconnect and explicit retry-status reuse
the original submission identity until reconciliation proves that attempt terminal. A reconciled
`completed` advances once; a reconciled `failed`, `cancelled`, or `retryable` keeps the fields
editable. Thus a lost status frame cannot leave Apple loading past ten seconds or cause duplicate
credential writes.

Pressing Save twice while submitting/active or awaiting reconciliation reuses/focuses the same
submission status and submits no second operation.
Background/foreground and window/scene changes do not detach the task from the model. No frame or
log includes the credential value.

Connection-owned operations are intentionally excluded from these REST queries: they terminate on
disconnect and a connection UUID is not an authentication principal. Operation/submission UUID
possession never substitutes for the authenticated user-owner check.

## 5. `agent_lifecycle` frame

```json
{
  "type": "agent_lifecycle",
  "agent_id": "ua-dice-4f3c2a",
  "revision_id": "2e9bca16-898b-4f51-8549-eaa81d97dc23",
  "runtime_instance_id": "91a03450-f0fc-4c32-a61c-085e7779d74a",
  "lifecycle_generation": 14,
  "state_revision": 3,
  "state": "online",
  "reason_code": null,
  "label": "Online",
  "updated_at": "2026-07-15T18:41:00Z"
}
```

All fields are required and nullable fields are explicit null. States are exactly `starting`,
`online`, `updating`, `failed`, and `offline`. `revision_id` may be null only before a revision is
selected or after confirmed deletion; `runtime_instance_id` may be null for offline/failed without
an instance. `lifecycle_generation` identifies the authoritative host/revision generation;
`state_revision` increases for every state change within it.

Clients compare `(lifecycle_generation, state_revision)` lexicographically and ignore an equal/lower
pair. A higher generation replaces all prior state even if its state revision is lower. The service
derives this projection only from the current durable runtime fence:

- delivery/start accepted → `starting`;
- current candidate preparation while old revision remains available → `updating`;
- current child registered/live **and** durably selected/promoted as invocable → `online`;
- current attempt terminally failed with actionable reason → `failed`;
- host/child loss, explicit stop, deletion, or no selected runtime → `offline`.

Stable reason codes are the non-sensitive runtime codes in
[personal-agent-runtime.md](personal-agent-runtime.md). `agent_lifecycle` is added to the shared UI
manifest and handled by every client. Legacy `agent_offline` may be emitted during a bounded
compatibility period but never overrides a newer canonical lifecycle pair.

## 6. Rendering and parity

The server-owned authoring/status surface maps states to existing shared palette roles and
astralprims; clients do not define a different lifecycle vocabulary or color meaning. A client that
cannot render the full status component shows the same label as a labeled fallback. Push handling
updates the visible authoring surface within two seconds without a full list reload.

## 7. Required contract tests

- State/flag/error validation; monotonic sequence; duplicated/reordered phases; first-terminal wins;
  reconnect replay/GET reconciliation; old connection/request rejection; and proof that local
  `submitting` never appears as server `accepted` before durable admission.
- All operations over two seconds show a phase by the deadline and end exactly once.
- Thirty first-login trials on each Apple platform for valid, invalid, slow, unavailable, timeout,
  duplicate Save, disconnection before/after admission, lost terminal frame, backgrounding, focus,
  navigation, and window/scene changes; the local watchdog always exits loading by ten seconds,
  durable GET reconciliation converges without duplicate persistence, and all SC-016 timing and
  responsiveness bounds hold. This evidence is non-waivable for the Apple rejection-remediation
  release.
- Twenty lifecycle sequences across every supported client cover all five states, stale generations,
  same-generation state ordering, and fallback accessibility; convergence occurs within two seconds.
