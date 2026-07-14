# Data Model: Delegated Agent Chaining

**Feature**: 056-delegated-agent-chaining | **Date**: 2026-07-13

This feature is a token/dispatch mechanism. Most of its "entities" are in-memory
authority objects and audit records, not new tables. The design principle
(FR-026, SC-003) is that the delegation chain must be reconstructable **from the
tamper-evident audit log alone** — so hop provenance rides the existing
hash-chained `audit_events` table rather than a side table that would not be
hash-chained.

## Entity overview

| Entity | Storage | New? |
|--------|---------|------|
| Delegation chain | in-memory token lineage (nested `act`) + audit records | No — 048 token shape |
| Child (chained) delegation token | in-memory JWT payload, orchestrator-minted | No — `mint_child_delegation` |
| Chained hop | in-memory dispatch + a paired audit record pair | No new table |
| Chain hop provenance record | `audit_events` (existing hash chain) | No new table; new `event_class` value |
| Machine principal | audit `auth_principal` string convention | No storage |
| Durable consent (offline grant) | `user_offline_grant` (existing) | No — capture path wired (D8) |
| Job → consent link | `scheduled_job.offline_grant_id` (existing) | No — column already present |
| Sub-task | in-memory `BackgroundTask` + `VirtualWebSocket` | No new table |
| Chain budget | in-memory per-turn object | No storage |
| Chained-attack scenario | eval-only benchmark case | No product storage |

## Authority objects (in-memory, no schema)

### Child (chained) delegation token — `mint_child_delegation` (delegation.py:515-567)

The decoded payload the mint produces and the enforcement/audit path consumes:

```text
{
  "sub":  <human principal>,                    # inherited from parent (delegation.py:554)
  "act":  {"sub": "agent:<callee>",             # this hop's actor
           "act": <parent's act chain>},        # nested, terminating at human sub (547-550)
  "scope": <space-joined attenuate_scopes(parent, requested)>,  # intersection only (543)
  "iss":  <parent iss>,                          # never widened (557)
  "aud":  <parent aud>,                          # never widened (556)
  "iat":  <now>,
  "exp":  <parent exp>,                          # capped at parent (552, 560)
  "delegation": true,
  "delegation_depth":     <parent depth + 1>,    # refused past max (533-541)
  "max_delegation_depth": <min(recorded, 3)>,    # DEFAULT_MAX_DELEGATION_DEPTH (delegation.py:416)
  "cnf":  {"jkt": <DPoP thumbprint>}             # carried from parent (565-566)
}
```

**Invariants** (already property-tested by 048's `test_recursive_delegation.py`,
14 tests; this feature must keep them green with the flag on):
- `child.scopes ⊆ parent.scopes` (monotonic attenuation).
- No scope/tool/audience/relaxed-flag the parent lacks (no escalation).
- `act` chain complete, terminating at the human `sub` (completeness).
- `depth = parent + 1`, refused beyond 3 at mint AND rejected at verify
  (`verify_delegation_chain`, delegation.py:591-592).
- `child.exp ≤ parent.exp` within 60 s skew (`_DELEGATION_CLOCK_SKEW_SECONDS`,
  delegation.py:425).

**056 wiring rule (D3)**: when `attenuate_scopes` returns `[]` AND the requested
set was non-empty, the orchestrator **refuses the hop** (does not dispatch the
empty-scope child) and audits the requested-vs-granted scope sets.

### Chain budget — in-memory per-turn (D9, FR-021)

```text
ChainBudget(turn_id, chat_id):
  max_depth        = DEFAULT_MAX_DELEGATION_DEPTH (3)   # cumulative, composes with delegation depth
  max_hops         = <small default, e.g. 12>           # total hops across the whole tree
  wall_clock_s     = <small default, tunable>           # ceiling for all nesting (D9 tunable note)
  spent_hops       = 0
  started_at       = <now>
```

Charged on each hop mint; exhaustion returns honest partial results + an audited
`budget_stop` (never runaway recursion). Distinct from — and composing with — the
existing per-turn `MAX_TURNS = 10` ReAct bound (orchestrator.py:3796).
Per-subtree budget is a slice of the turn budget handed to each sub-task (D10).

## Chain hop provenance record (audit_events, existing hash chain)

Built by `delegation.delegation_chain_audit_record(parent, child, operation,
tool)` (delegation.py:642-667) and emitted through the normal `Recorder` path so
it is hash-chained (`chain_hmac`, audit/pii.py:150) and forward-verifiable
(`verify_chain`, audit/repository.py:365). Mapped onto the `AuditEventCreate`
schema (audit/schemas.py):

| audit_events field | Hop value | Source |
|--------------------|-----------|--------|
| `event_class` | `"delegation"` (**new tuple value**, schemas.py:30) | — |
| `action_type` | `delegation.hop.mint` / `delegation.hop.enforce` (paired) | FR-008 |
| `actor_user_id` | human authorizer (`child.sub`) | delegation.py:660 |
| `auth_principal` | acting agent (`child.act.sub`) | delegation.py:658 |
| `agent_id` | callee agent | dispatch |
| `correlation_id` | shared across the mint+enforce pair AND the turn's tool-call pair | FR-008, SC-003 |
| `inputs_meta` | `{parent_actor, delegation_depth, actor_chain, requested_scopes, granted_scopes}` (NO secret token bytes — FR-028) | delegation.py:659-666 |
| `outcome` | `in_progress` → `success`/`failure`(refused) | FR-005 |
| `outcome_detail` | refusal reason (e.g. `empty_intersection`, `depth_exceeded`, `revoked`) | FR-005/FR-006 |

**Reconstruction (FR-026, SC-003, closes 048 T018)**: a two-hop chain reads back
from `audit_events` by `correlation_id`, the `actor_chain` field on each record
reconstructing the full human→agent→sub-agent→tool path; `verify_chain` proves
tamper-evidence. This is the ONLY authority-trail storage — no side table.

**Adding `"delegation"` to `EVENT_CLASSES`** (audit/schemas.py:30-65) is a Python
constant edit validated by `AuditEventCreate._check_event_class`
(audit/schemas.py:115-119) — **not a database schema change**. No migration.

## Machine principal (audit convention, no storage — D13)

Machine-initiated turns are audited under `auth_principal = machine:<class>`
(`machine:scheduled_job`, `machine:parser_replay`, `machine:draft_self_test`) with
`actor_user_id = <owning human>` and `inputs_meta.consent_ref = <offline_grant_id>`.
Today `actor_principal_from_claims` returns `("legacy","legacy")` for a
claim-less machine turn (audit/hooks.py:38-39) and every helper drops
`legacy`-actor records (hooks.py:59-60, 105-106, 150, 250-251, 273-274, 317) — so
machine-turn tool calls are currently unaudited. The fix resolves the machine
principal from the turn context so records are recorded and attributed
(FR-014, SC-005). Cost attribution stays on the system LLM credential per 054
(`_llm_audit_principals` returns `("system","system")` for `websocket=None`,
orchestrator.py:4624-4640) — authority (human) and payment (system) are recorded
distinctly (FR-014, US2-AS5).

## Durable consent (offline grant) — existing table, wired

`user_offline_grant` already exists (offline_grant.py:76-83). This feature adds
the **first production caller** of `OfflineGrantStore.capture` (offline_grant.py:64)
at the consent-capture step (D8) and links the returned `grant_id` onto the job
via the existing `set_grant` (scheduler/store.py:71-74). **No schema change** —
`scheduled_job.offline_grant_id` is already present and today hardcoded `None`
(scheduling_chat.py:295, scheduler/api.py:120).

## Schema deltas & rollback (Constitution IX)

**Default: no new table, no schema migration.** The audit trail rides
`audit_events`; the machine principal is a string convention; consent linkage
reuses existing columns; the new event class is a Python constant.

**Conditional additive column (only if hop-reconstruction indexing proves
necessary during implementation)**: `audit_events.chain_root_correlation_id TEXT`
(nullable, indexed) to group a whole chain's records under one root id for fast
reconstruction queries. If added, it ships as a guarded idempotent `_init_db`
delta:

```sql
ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS chain_root_correlation_id TEXT;
CREATE INDEX IF NOT EXISTS idx_audit_chain_root
    ON audit_events (chain_root_correlation_id) WHERE chain_root_correlation_id IS NOT NULL;
```

- **Guard/idempotency**: `ADD COLUMN IF NOT EXISTS` + `CREATE INDEX IF NOT
  EXISTS`; re-boot is a no-op. Bump `SCHEMA_REVISION` per the 052 `schema_meta`
  fast-path convention (`054.001` → `056.001`, database.py:15) only if a column
  is added.
- **Rollback**: additive and nullable; consumed only by 056 reconstruction
  queries. `DROP INDEX IF EXISTS idx_audit_chain_root; ALTER TABLE audit_events
  DROP COLUMN IF EXISTS chain_root_correlation_id;` after disabling
  `FF_RECURSIVE_DELEGATION`. No backfill; the hash-chain columns are untouched
  (the column is NOT part of the canonical row hashed by `chain_hmac`, so adding
  it cannot invalidate existing chains — verify_chain's `row_for_chain`
  explicitly enumerates the hashed fields, audit/repository.py:386-403, and this
  column is not among them).
- **Representative-dataset evidence** (Constitution IX): boot against a dump
  containing existing `audit_events` rows; confirm `verify_chain` still returns
  `None` (chain intact) after the additive column, and that reconstruction reads
  work; second boot no-ops.

Because reconstruction is already possible from `correlation_id` +
`actor_chain` on each record, the **preferred plan is to ship zero schema
change** and add the column only if a query-performance need is demonstrated in
implementation — recorded here so the option is guarded and rollback-documented
in advance.

## State transitions

### One hop
```
parent authority present at dispatch
  → mint_child_delegation (depth+1, scopes ∩, exp ≤)      [refuse if empty ∩ / over depth]
  → authorize_chained_tool_call (verify chain + tool in scope)   [refuse per-call, fail-closed]
  → full gate stack via _authorize_and_prepare (D5)        [refuse if any gate denies]
  → execute + paired audit (tool.start/end + delegation.hop.mint/enforce)
  → MAS scan of the result (D11)                           [quarantine + audit if flagged]
  → result/digest returned to requester
```

### Machine turn
```
due job / parser go-live / self-test
  → MachineTurnAuthority.derive(user, agent, consented_scopes)
      load grant → is_valid? (revoked/expired → skip_auth + notify, collapsed)
      → mint_access_token (fresh) → intersect(consented, current)   [empty → skip_auth]
  → root subject-token threaded into handle_chat_message
  → real-agent dispatch runs delegated; any hop mints children off the root (D2)
  → audited under machine:<class> + owning human
```

### Sub-task (US4)
```
planner decomposes
  → spawn BackgroundTask/VirtualWebSocket with child authority + per-subtree budget slice
  → run isolated; produce a bounded provenance-tagged digest
  → MAS scan digest (D11) → return to parent   [parent ended/budget out → cancel + audit + discard]
```

## Validation rules (from spec FRs)

- Empty scope intersection refuses (FR-005) — never a silent empty-scope token.
- Child never outlives/exceeds/survives-revocation of parent (FR-002, FR-006,
  FR-010) — enforced by `mint_child_delegation` + `verify_delegation_chain` +
  derivation-time revocation re-check (D17.3).
- One agent's credentials never forwarded to another (FR-008) — credentials are
  injected per-(user, callee) at the dispatch site (orchestrator.py:5920-5925),
  never carried on the token; the child token carries scope claims only.
- Explicit opt-out / hard security-flag block always win (FR-029) — they are the
  `is_tool_allowed` / security-flag gates the hop re-enters (D1), independent of
  any trust baseline or consent.
- No secret token bytes in any audit record (FR-028) — the hop record carries
  actor/scope/depth metadata only (delegation.py:656-666), never the JWT.
- Flag off ⇒ byte-identical single-hop behavior (FR-009, SC-009) — the 048
  suites + the 11 delegation + 26 permission tests pass unchanged.
