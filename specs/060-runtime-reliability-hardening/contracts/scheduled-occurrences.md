# Contract: Durable Scheduled Occurrences and Idempotent Effects

**Scope**: FR-006–FR-008; SC-002
**Authority**: PostgreSQL occurrence, claim, run, and effect-ledger rows. In-memory scheduler sets
are caches only and cannot establish ownership.

## 1. Occurrence identity

One intended execution is a `scheduled_occurrence`, distinct from its `scheduled_job` definition.
The first materialization allocates a UUID4 `occurrence_id`; retries and lease recovery retain it.
The database enforces `UNIQUE(job_id, scheduled_for)`, where `scheduled_for` is a PostgreSQL
`timestamptz` normalized to the schedule engine's declared precision. Database comparisons use that
value directly; API projections encode it as an RFC3339 UTC string with a `Z` suffix. A `job_run`
references exactly one occurrence and one attempt-scoped accepted operation.

Run-now uses the same model without rewriting the recurring cadence. The authenticated client
supplies a UUID4 `submission_id`; the materialized row stores it as nullable
`run_now_submission_id`, and a partial unique index on `(owner_user_id, run_now_submission_id)`
provides the owner-scoped retry boundary. The first accepted action allocates the occurrence UUID4
and a database-time `scheduled_for`; replaying that submission returns the same occurrence. Reusing
the submission for another job is `idempotency_conflict`. Automatic occurrences keep this field
null. Run-now requires an active, currently eligible job and never changes `scheduled_job.next_run_at`.

Required occurrence fields are:

- `occurrence_id`, `job_id`, `scheduled_for`, immutable `owner_user_id`, and nullable
  `run_now_submission_id`;
- `state`: exactly `pending`, `claimed`, `running`, `completed`, `failed`, `retryable`, or
  `cancelled`;
- `attempt_count`, `claim_generation`, nullable UUID `lease_token`, `lease_owner`, `lease_expires_at`;
- nullable `current_operation_id`, `first_eligible_at`, `started_at`, `terminal_at`, and
  `next_attempt_at`;
- safe `result_code` and `last_error_code` (no prompt/output/credential content).

`scheduled_for`, `first_eligible_at`, `lease_expires_at`, `started_at`, `terminal_at`, and
`next_attempt_at` are nullable/non-null PostgreSQL `timestamptz` values as their state permits; no
epoch-millisecond integer is a second canonical representation. Terminal states are `completed`,
`failed`, and `cancelled`. `retryable` returns to claim eligibility at `next_attempt_at` with the
same occurrence identity but a new attempt-scoped operation on its next claim. A handler that is
known to be ineligible is refused before schedule acceptance, so `skipped_ineligible` is a refusal
code, not an occurrence state.

## 2. Atomic materialization and claiming

For each due job, one database transaction:

1. locks the `scheduled_job` row;
2. computes the due `scheduled_for` from the locked definition;
3. inserts the occurrence with `ON CONFLICT (job_id, scheduled_for) DO NOTHING`;
4. advances `scheduled_job.next_run_at` past that exact occurrence; and
5. claims eligible occurrences in a bounded batch using `FOR UPDATE SKIP LOCKED`.

Claiming changes `pending`/eligible `retryable`/expired `claimed` or `running` to `claimed`,
increments `claim_generation`, writes a new UUID4 `lease_token`, and sets the lease owner/expiry in
the same transaction. Reclaiming an expired `claimed` or `running` row first terminalizes that
attempt's non-terminal operation as `retryable` with `claim_lost`; it never reuses a terminal
operation for the replacement attempt. Only after commit may the runner enqueue the linked
attempt-scoped operation.

The default claim lease is **15 seconds** and is configurable as
`scheduled_claim_lease_seconds` (5–60). A dedicated claim lease-keeper starts immediately after the
claim transaction commits and renews the same `(lease_token, claim_generation)` throughout both the
`claimed`/operation-queued interval and the `running` interval, at least once per one third of the
configured lease. Renewal is independent of admission selection and handler execution. Before the
queued-to-running transition, the runner renews and rechecks the claim in the same transaction that
records the run. If renewal loses its compare-and-set, the queued attempt operation terminalizes
`retryable` with `claim_lost`, never starts, and publishes no effect. Recovery may reclaim only after
database time is at or beyond `lease_expires_at`. Every renewal, start, result, retry, and completion
compare-and-sets both `lease_token` and `claim_generation`; a stale claimant gets
`stale_occurrence_claim` and may not publish an effect.

The occurrence lease does not replace the accepted operation's execution lease. As soon as the
attempt operation is selected, a second keeper renews its coordinator fence at least once per one
quarter of the configured operation-slot lease through start, handler execution, effect commit, and
terminalization. Loss of either keeper cancels the handler immediately and forbids publication; a
current occurrence whose operation lease is lost becomes retryable with a bounded safe code, while
a stale occurrence claimant leaves recovery to the authoritative newer claim.

The scheduler feature flag remains fail-closed/default-off. Pausing or deleting a job prevents new
materialization. In one linearizable store transition it terminalizes every accepted attempt for a
pending/retryable/claimed-but-not-running occurrence with `cancelled_job_paused` or
`cancelled_job_deleted`, releases its admission capacity, and marks that occurrence `cancelled`.
An occurrence already durably `running` wins the race and is not interrupted by definition-only
pause/delete. Terminal history is never erased, and resume never resurrects a cancelled occurrence.
The ordinary claim candidate query rechecks that the owning job is still active.

Authenticated `POST /api/schedule/{job_id}/run-now` requires the client submission UUID and returns
the safe occurrence identity/state with HTTP 202 and `Cache-Control: no-store`; owner mismatch and
unknown job share non-disclosing not-found behavior. The Chrome surface embeds one UUID per rendered
Run-now action, so double activation/retry reuses it while a later rerender represents a new explicit
action. With unattended scheduling disabled, neither REST nor Chrome may materialize an occurrence.

## 3. Dispatch and retry

After a claim commits, the runner allocates the next `attempt_number` and creates or idempotently
resolves the accepted operation for that attempt with:

```json
{
  "operation_kind": "scheduled_occurrence",
  "admission_class": "scheduled",
  "owner_scope": "schedule",
  "idempotency_namespace": "scheduled_occurrence_attempt",
  "idempotency_key": "<occurrence_id>:<attempt_number>",
  "occurrence_id": "<occurrence_id>",
  "attempt_number": 2,
  "parent_operation_id": "<prior-attempt-operation-id-or-null>"
}
```

The operation cannot start unless the claim fence still matches. Transition to `running` creates or
resolves exactly one `job_run` for `(occurrence_id, attempt_number)`, with that attempt's unique
`operation_id`, BIGINT execution generation, and UUID execution lease token. Repeating enqueue before
that attempt terminalizes resolves the same operation. Once the operation is `completed`, `failed`,
`cancelled`, or `retryable`, it is
immutable and is never used for another attempt. A crash after attempt allocation therefore reuses
the operation for that same attempt; lease recovery that begins a later attempt creates a new
operation while preserving `occurrence_id`.

Retry policy is captured from the job when the occurrence is materialized. A retryable handler
failure moves the occurrence to `retryable`, clears the claim, and stores bounded `next_attempt_at`;
the next claim increments `attempt_count` and creates its new operation. A non-retryable failure or
exhausted policy becomes `failed`. The final recovery test must reach `completed` or an explicit
terminal failure within 60 seconds after the last injected recovery event.

## 4. Eligibility and effect contract

A scheduled handler declares before schedule acceptance:

```text
supports_unattended = true
idempotency_boundary = astraldeep_transaction | downstream_idempotency_key
effect_kinds = [stable, reviewed names]
```

Missing support is refused as `handler_not_idempotent`; the job remains ineligible for unattended
execution and the limitation is shown before user acceptance. A handler may not claim best-effort
deduplication.

Every AstralDeep-controlled visible effect uses the canonical `effect_ledger` row unique on
`(occurrence_id, effect_kind, effect_key)`. Its state is exactly `reserved`, `published`, or
`failed`. Every reservation/publication/failure mutation compare-and-sets `occurrence_id`,
`claim_generation`, `lease_token`, the attempt's `operation_id`, that operation's BIGINT
`execution_generation`, and its UUID `execution_lease_token`. If the attempt operation is no longer
`running`, either execution fence differs/has been cleared, or the occurrence claim is stale, the
effect mutation is a no-op and returns `stale_occurrence_claim`; terminalized work cannot publish a
late effect.

- Database-owned chat/history, notification, state, and audit effects insert the target row and mark
  the ledger `published` in one transaction after locking and rechecking both fences, using
  `INSERT ... ON CONFLICT` on the occurrence key.
- A supported downstream effect passes `occurrence_id` (or a deterministic derivative) as the
  downstream idempotency key and records the returned stable receipt before acknowledging success.
- If a crash occurs after the visible effect but before acknowledgement, recovery reads the ledger
  or downstream receipt and marks completion without re-emitting.
- A `published` ledger key is immutable. A different payload digest for the same key fails terminally
  as `effect_idempotency_conflict`.
- `reserved` moves to `published` only after the atomic effect/receipt boundary. It moves to `failed`
  with a safe code only after reconciliation proves no visible effect occurred. A later valid
  attempt may move `failed` back to `reserved` only with the same payload digest and both fresh
  claim/operation fences; an ambiguous downstream outcome is never blindly retried.

No email, webhook, or other external path becomes eligible merely because this ledger exists; a
real atomic/idempotent downstream boundary is required.

## 5. Wire/API projections

Recent run projections add full `occurrence_id`, the attempt's `operation_id`, `attempt_number`,
canonical occurrence `state`, RFC3339 UTC timestamps, and safe result code. They do not expose lease
tokens/owners, execution generations, or raw failure/output content. Notifications and progress
carry the same `occurrence_id` and attempt number so retries are visibly one occurrence with distinct
attempts, not duplicate occurrences.

Stable non-sensitive result codes include:

- `handler_not_idempotent`, `claim_lost`, `lease_expired`, `operation_lease_lost`,
  `effect_idempotency_conflict`;
- `cancelled_job_paused`, `cancelled_job_deleted`;
- existing normalized authentication/handler outcomes, without changing their security behavior.

`claim_lost`/`lease_expired` from a stale worker do not terminalize the current occurrence; they
terminate only that worker's operation attempt.

## 6. Observability

Report materialized, claimed, running, retrying, recovered, terminal, cancelled, and ineligible
counts; claim age/lease lag; duplicate materialization suppression; stale-claim rejection; effect
reservation/publication/deduplication/conflict; and oldest eligible occurrence age. Labels contain
job type/effect kind/result code, never instruction, output, owner, token, or target-chat content.

## 7. Required contract tests

- 10,000 trials combining repeated polls, two scheduler instances, slow work, lease renewal, process
  death before/after claim, expiry recovery, and acknowledgement loss; at most one visible effect.
- Transaction fault injection after every materialize/advance/claim/run/effect/completion boundary.
- A stale token/generation cannot renew, publish, complete, retry, or cancel a newer claim.
- Same occurrence identity across all retries, one distinct accepted operation and one `job_run` per
  attempt, and no reuse of a terminal operation by a later attempt.
- Same-key/same-digest effect replay is a no-op; same-key/different-digest is terminal conflict.
- Unsupported handler is refused before unattended schedule acceptance with an actionable reason.
- Multi-instance PostgreSQL tests use real database transactions; mocks alone do not satisfy this
  contract.
- A saturated scheduled pool keeps one claim queued for longer than two complete 15-second lease
  periods while its independent lease-keeper renews; a second instance cannot reclaim it, and the
  eventual attempt produces at most one effect. Killing the owner stops renewal and permits the same
  occurrence with a new attempt only after database expiry.
