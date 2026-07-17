# Contract: Runtime Operations and Admission

**Scope**: FR-001–FR-005, FR-008, FR-024; SC-001, SC-011, SC-019
**Authority**: `backend/orchestrator/work_admission.py` is the only admission and accepted-operation
state authority. Existing task managers expose compatibility views over it; they do not allocate
independent identities or capacity.

## 1. Identities and ownership

The server allocates a full UUID4 `operation_id`. An operation is **accepted** only after the
coordinator has durably created its operation record and returned either `queued` or `running`.
Client submission IDs are retry identities, not operation IDs. Admission refusals are not accepted
operations and never receive a synthetic operation identity or success state.

The durable accepted-operation record has exactly these contract fields; API and status projections
may omit internal fence values only where this contract explicitly says so, but implementations do
not introduce competing aliases such as `kind`, `owner_kind`, or `owner_id`:

| Field | Type and contract |
|---|---|
| `operation_id` | UUID4 primary identity; server allocated, never shortened or reused |
| `operation_kind` | bounded snake-case subsystem code such as `connection_frame`, `background_chat`, `scheduled_occurrence`, `agent_generation`, `maintenance`, or `llm_credential_save` |
| `admission_class` | `interactive`, `background`, `scheduled`, `maintenance`, or `system` |
| `owner_scope` | `connection`, `user`, `schedule`, `maintenance`, or `system` |
| `owner_user_id` | authenticated user identifier when user/schedule owned; otherwise null |
| `connection_scope_id` | server-issued UUID for connection-owned work; otherwise nullable subscriber/origin scope |
| `chat_id` | owner-validated chat identity when chat scoped; otherwise null |
| `parent_operation_id` | prior/parent accepted operation UUID when applicable; otherwise null |
| `idempotency_namespace`, `idempotency_key` | nullable together; the non-null pair is unique within owner scope |
| `normalized_input_digest` | lowercase SHA-256 of normalized non-secret work identity when an idempotency pair is present; otherwise null |
| `connection_generation`, `request_generation` | UUID wire generations when client scoped; otherwise null |
| `execution_generation` | non-negative BIGINT; `0` means never selected, the first worker selection sets `1`, every reselection increments it, and a started operation retains its final value after terminalization |
| `execution_lease_token` | internal fresh server-issued UUID for the selected worker; non-null only while `running` and cleared on terminalization |
| `state` | exactly `queued`, `running`, `completed`, `failed`, `cancelled`, or `retryable` |
| `phase_code` | nullable safe bounded snake-case phase; never message data or credentials |
| `terminal_code`, `safe_summary`, `retry_after_ms` | terminal outcome fields; null while non-terminal and never raw input/output |
| `state_revision` | non-negative 64-bit integer incremented by each accepted state/phase transition |
| `accepted_at`, `queue_deadline_at`, `started_at`, `terminal_at`, `updated_at`, `cancel_requested_at`, `purge_after` | PostgreSQL `timestamptz`, nullable only where the lifecycle has not reached the corresponding event |

`connection` ownership means disconnect cancels the work. `user` and `system` ownership means the
work may continue after one viewer disconnects. Code must choose ownership before admission; it may
not detach connection-owned work after a disconnect has begun.

Authenticated REST reconciliation is available only for operations admitted as `user` or
`schedule` owned. Possession of an operation or submission UUID never grants access to a
connection-owned record, because a connection scope is neither a durable principal nor a bearer
credential. A client action that must reconcile after reconnect (for example, credential Save) is
therefore admitted as user-owned from the outset and may retain `connection_scope_id` only as
origin/subscriber metadata. Ephemeral connection-owned frames terminate with their socket and use
their scoped wire terminal while connected; they are never reclassified after admission.

When a non-null idempotency pair already exists, submission returns the original operation and does
not execute again. A key reused with a different operation kind, owner, or normalized input digest
is refused with `idempotency_conflict`. Timestamps use database time; wire projections encode them
as RFC3339 UTC strings with a `Z` suffix.

## 2. Admission result

The coordinator returns exactly one of these typed results:

```json
{
  "accepted": true,
  "operation_id": "41a35019-5904-4931-bdbd-cba5d94fb9be",
  "state": "queued",
  "state_revision": 0,
  "queue_position": 3,
  "queue_deadline_at": "2026-07-15T18:41:05Z"
}
```

```json
{
  "accepted": false,
  "code": "capacity_exceeded",
  "retryable": true,
  "retry_after_ms": 1000
}
```

Initial refusal `code` is one of:

- `capacity_exceeded`: the configured queue is full;
- `registration_required` or `registration_timeout`: a connection cannot create work;
- `idempotency_conflict`: the retry identity describes different work;
- `connection_closing`: admission began after connection drain started;
- `service_draining`: the deployment is shutting down.

All are retryable except `idempotency_conflict` and `registration_required`. A refusal increments
non-sensitive admission counters, but must not be represented as an accepted operation record. By
contrast, a queued item whose finite deadline later expires was already accepted: its durable
operation terminalizes as `retryable` with `terminal_code: queue_wait_expired`.

For a client submission, acceptance or refusal is retained under its owner-scoped `submission_id`
for the same default 24-hour reconciliation window. This is a safe admission-result record, not an
accepted operation. Repeating or querying that identity returns the original result and cannot turn
a refusal into acceptance without a new submission ID.

## 3. Capacity and queue rules

Capacity is reserved atomically before an operation changes to `running`. That transition increments
the operation's BIGINT `execution_generation` and allocates a fresh UUID4 `execution_lease_token`.
Any permitted worker reselection rotates the token and increments the generation before new code
runs; neither fence value is copied to another execution. Capacity is released exactly once on a
terminal transition. A `finally` block alone is not the authority: terminal compare-and-set in the
coordinator is. Active count must never exceed the configured pool ceiling, including during
cancellation and worker failure.

The initial release profile uses these defaults; operators may lower or raise them within existing
configuration policy:

| `system_config` field | Default | Meaning |
|---|---:|---|
| `work_active_limit` | 20 | concurrent interactive/foreground operations |
| `work_queue_limit` | 100 | finite foreground queue item limit |
| `work_queue_max_wait_ms` | 5000 | maximum foreground queue residence |
| `background_active_limit` | 5 | concurrent background operations |
| `background_queue_limit` | 100 | finite background queue item limit |
| `background_queue_max_wait_ms` | 30000 | maximum background queue residence |
| `operation_retention_seconds` | 86400 | terminal record retention (24 hours) |

The deployment may define separate scheduled and maintenance pool sizes, but all pools are allocated
by the same coordinator and reported together. Queue ordering is FIFO by durable `accepted_at` and
then `operation_id`; cancellation/control work bypasses queues so a saturated pool cannot prevent
drain. A queued item whose deadline expires is terminalized `retryable` without entering user code.

## 4. Connection contract

On socket acceptance the server creates one `connection_scope_id`, a tracked task set, a bounded
pre-registration FIFO, and one FIFO mutation lane.

1. A structurally valid registration frame must complete within **5 seconds** of socket acceptance.
2. Before registration, at most `registration_queue_limit` frames (default 16) may wait. Registration,
   cancellation, ping/pong, and close are parsed as control frames; type detection never uses a
   substring search.
3. A non-control pre-registration frame is not submitted to the operation coordinator until
   registration succeeds. Overflow closes the connection with an explicit
   `registration_queue_full` result.
4. Registration timeout terminalizes every queued frame as `registration_timeout`, cancels every
   waiter, and closes the connection. No waiter may remain on an event that can no longer fire.
5. State-changing frames run through the connection's FIFO mutation lane. Because the existing
   application router reads shared live connection state rather than a per-frame immutable
   snapshot, admitted reads and mutations form an ordered reader/writer lane: consecutive reads may
   run concurrently, a mutation waits for every earlier read and mutation, and every later read
   waits for that mutation. Parsed cancellation/ping/pong/close controls remain outside this data
   lane. Duplicate retries use their idempotency pair.
6. Disconnect atomically marks the scope closing, refuses new admission, terminalizes queued work,
   requests cancellation of connection-owned running work, and awaits the tracked set. At **5
   seconds** it force-terminalizes any remainder as `cancelled` with
   `disconnect_drain_timeout`, clears its execution lease token in the same compare-and-set,
   cancels/joins the tracked wrapper, and leaves no registered waiter or task.

Disconnect does not cancel accepted user/system-owned background work; it only removes that
connection as a status subscriber.

## 5. Operation state machine

```text
submit ──► queued ──► running ──► completed
           │          ├──► failed
           │          ├──► cancelled
           │          └──► retryable
           ├──► cancelled
           └──► retryable
```

Only the coordinator may perform a transition. Terminal states are immutable. A second terminal
attempt is logged as `duplicate_terminal_suppressed` and cannot overwrite the first outcome.
Cancellation is idempotent: cancelling a terminal operation returns that terminal record; cancelling
queued/running work requests cooperative cancellation and still guarantees one terminal state.

Every worker progress update, result, artifact publication, database mutation, and visible effect
commit carries `(operation_id, execution_generation, execution_lease_token)`. Immediately before
commit, the shared coordinator gate locks/rechecks that the operation is still `running` with that
exact BIGINT generation and UUID token. Database-owned state/effects and the fence check commit in
one transaction. Filesystem publication uses a generation-specific staged artifact and rechecks the
complete fence before its atomic replace. External effects may use only an approved durable outbox
or downstream idempotency/reconciliation boundary whose dispatch also rechecks the complete fence;
direct unfenced emission is invalid. Terminalizing an operation clears its lease token atomically,
so a worker that survives cancellation or resumes after the five-second disconnect bound can
perform cleanup but cannot publish, mutate current state, or report late success.

`operation_status` is the user-facing projection described in
[operation-and-lifecycle-status.md](operation-and-lifecycle-status.md): durable `queued` projects
as `accepted`, durable `running` projects its current phase, and terminal states project one-to-one.

## 6. Query and retention

`GET /api/operations/{operation_id}` returns the authenticated caller's safe user/schedule-owned
operation projection. Unknown, expired, connection-owned, and non-visible identities use the same
non-disclosing not-found behavior; UUID possession alone never confers visibility. Its fields are
exactly `operation_id`, `operation_kind`, `admission_class`, `owner_scope`, `chat_id`,
`parent_operation_id`, `connection_generation`, `request_generation`, `state`, `phase_code`,
`terminal_code`, `safe_summary`, `retry_after_ms`, `state_revision`, `accepted_at`,
`queue_deadline_at`, `started_at`, `terminal_at`, `updated_at`, and `purge_after`; nullable values are
explicit JSON null. It never exposes owner identifiers, idempotency keys/digests,
`execution_generation`, `execution_lease_token`, message, prompt, credential, provider response, or
deployment secret.

`GET /api/operation-submissions/{submission_id}` returns exactly one retained owner-visible result:
`{"accepted":true,"operation":<safe-operation-projection>}` or
`{"accepted":false,"code":"<safe-code>","retryable":<bool>,"retry_after_ms":<int-or-null>}`.
Unknown, expired, and non-visible submission identities use the same non-disclosing not-found
behavior. This endpoint is the durable reconciliation path when a client loses the admission reply
before learning `operation_id`; it stores/exposes no submitted payload or normalized digest.

Terminal records default to 24-hour retention. Cleanup claims rows in bounded batches and removes
each record no later than one hour after `purge_after`. Cleanup itself is admitted as maintenance
work and cannot block interactive acknowledgement beyond FR-024.

## 7. Observability

Expose counters/gauges or equivalent structured diagnostics for:

- active and queued count by operation kind, configured limits, and oldest queued/running age;
- accepted, refused by code, queue-expired, cancelled, failed, retryable, and completed totals;
- duplicate submission and duplicate terminal suppression;
- registration queue overflow/timeout and disconnect drain duration/remainder;
- retention purge count/lag.

Labels may contain operation kind, scheduled job type, reviewed effect kind, phase, result code, and
deployment instance only. They must not contain user identifiers, chat text, agent source, URLs with
credentials, or operation payloads.
The production-neutral bridge in this feature is authenticated
`GET /api/runtime-reliability/metrics`; it refreshes the configured admission-class gauges off the
event loop and returns only `{name, value, labels}` samples from that reviewed vocabulary with
`Cache-Control: no-store`.

## 8. Required contract tests

- 1,000-frame saturation/disconnect test: ceiling never exceeded, one terminal per accepted item,
  and zero tracked connection tasks after five seconds.
- Queue FIFO, full refusal, finite wait expiry, cancellation-before-start, cancellation-while-running,
  duplicate retry, duplicate terminal, worker exception, and shutdown-drain tests.
- Forced terminalization races every database, filesystem, outbox, result, and progress commit;
  stale execution generations/tokens produce zero visible late effects or state mutation.
- Registration success at the boundary, timeout, flood, malformed type, disconnect-during-register,
  and reconnect-while-old-scope-drains tests.
- Retention at 24 hours and purge-by-25-hours test with no payload leakage in query/metrics/logs.
- Maintenance/process contention test proving interactive p95 ≤ 2 seconds and max ≤ 5 seconds.
