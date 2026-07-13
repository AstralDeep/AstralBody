# Contract: Audit Provenance, Machine-Turn Authority & Benchmark Hooks

**Feature**: 056-delegated-agent-chaining | **Date**: 2026-07-13

Backend-internal + eval-only contracts. No client-visible change.

## 1. Chain hop provenance record (US1, FR-008/FR-026, closes 048 T018)

Emitted through the existing `Recorder` so it is hash-chained (`chain_hmac`,
`audit/pii.py:150`) and forward-verifiable (`verify_chain`,
`audit/repository.py:365`). Built from `delegation.delegation_chain_audit_record`
(`delegation.py:642-667`).

**New audit vocabulary**: add `"delegation"` to `EVENT_CLASSES`
(`audit/schemas.py:30-65`) — a Python constant validated by
`_check_event_class` (`schemas.py:115-119`); **not a schema migration**.

**Paired records per hop** (mirrors the `tool.<name>.start`/`.end` pairing the
single path already emits, `audit/hooks.py:247-298`), sharing one
`correlation_id` with the turn's tool-call pair:

| action_type | when | outcome |
|-------------|------|---------|
| `delegation.hop.mint` | child minted (or refused pre-dispatch) | `in_progress` / `failure` (`empty_intersection`, `depth_exceeded`, `revoked`) |
| `delegation.hop.enforce` | `authorize_chained_tool_call` verdict | `success` / `failure` (`out_of_scope`, `tampered_chain`, `over_depth`, `expired`) |

`inputs_meta` carries `{parent_actor, acting_agent, human_authorizer,
delegation_depth, actor_chain, requested_scopes, granted_scopes}` — **never** the
token bytes (FR-028). `actor_user_id = human authorizer`, `auth_principal =
acting agent`, per `delegation_chain_audit_record` (delegation.py:658-660).

**Reconstruction (SC-003)**: reading `audit_events` filtered by `correlation_id`
recovers each hop's `actor_chain`, reconstructing human→agent→sub-agent→tool;
`verify_chain` proves tamper-evidence. Pinned as a regression test (closes 048
T018, which deferred exactly this end-to-end evidence, `048/tasks.md:40`).

## 2. Machine principal (US2, FR-014, SC-005)

Machine-initiated turns are attributed, not dropped:

- `auth_principal = machine:<class>` — one of `machine:scheduled_job`,
  `machine:parser_replay`, `machine:draft_self_test`.
- `actor_user_id = <owning human user_id>`.
- `inputs_meta.consent_ref = <offline_grant_id>` (the run's authorizing consent).
- Cost/authority split: the paying LLM credential is the admin SYSTEM record
  (054; `_llm_audit_principals` → `("system","system")` for `websocket=None`,
  `orchestrator.py:4624-4640`), while the *authority* principal names the human —
  the two never blur (FR-014, US2-AS5).

**Fix required**: `actor_principal_from_claims` returns `("legacy","legacy")`
when claims are absent (`audit/hooks.py:38-39`), and every helper skips recording
on `legacy` (`hooks.py:59-60,105-106,150,250-251,273-274,317`) — so machine-turn
tool calls are unaudited today. Resolve the machine principal from the
VirtualWebSocket turn context (a per-turn attribute set by
`MachineTurnAuthority`, §3) before the `legacy` fallback, so machine-turn records
are recorded and attributed. Interactive turns are unchanged.

## 3. MachineTurnAuthority derivation seam (US2, FR-012/FR-013/FR-015)

`backend/orchestrator/chain_authority.py` — one shared derivation all
machine-turn classes call:

```python
async def derive(self, *, user_id, agent_id, consented_scopes,
                 grant_id, turn_class) -> MachineAuthority | AuthoritySkip:
    """Fresh per-run root authority for a machine turn. Returns either a
    MachineAuthority(access_token, allowed_scopes, principal) or an
    AuthoritySkip(reason) that the caller records + notifies. Fail-closed:
    missing/revoked/expired consent or an empty (consented ∩ current) set ⇒
    AuthoritySkip (no real-agent dispatch)."""
```

Steps (reusing existing pieces):
1. `OfflineGrantStore.is_valid(grant_id)` (`offline_grant.py:97-105`) — revoked/
   expired ⇒ `AuthoritySkip` (FR-013).
2. `OfflineGrantStore.mint_access_token(grant_id)` (`offline_grant.py:107`) —
   fresh token per run; Keycloak-side revocation ⇒ `AuthoritySkip`.
3. `_intersect_scopes(consented, current)` (`scheduler/runner.py:29-31`) narrowed
   to the user's CURRENT grants — never wider than either (FR-012).
4. Return the root; the turn threads it into `handle_chat_message`, so real-agent
   dispatch runs delegated in production and any further hop mints children off it
   (FR-015, one authority model / two roots).

**Consumers** (the three machine-turn classes at one seam):
- Scheduled runs: `scheduler/runner.py:run_job` (`:88`) → `run_scheduled_turn`
  (`orchestrator.py:2923`), which today **drops** the minted token
  (`orchestrator.py:2946-2949`, `:2980`). Thread the root through.
- Parser replay: `attachment_autoparse.auto_continue_after_go_live`
  (`attachment_autoparse.py:87-146`).
- Draft self-tests: `agentic_creation._self_test_draft`
  (`agentic_creation.py:323-350`).

**Flag gate**: the scheduler class stays dark behind `FF_SCHEDULER_EXECUTION`
(default off, `feature_flags.py:47`; loop gated at `orchestrator.py:8765-8787`)
until the offline-grant security review (025 T057 / 030 FR-004/FR-005) is
recorded — inherited, not bypassed (FR-016, SC-004 gated on the review).

**Authority-skip notification** (FR-013): a skip records the outcome (existing
`skipped_auth` in `scheduler/runner.py:105-112`) and notifies the user via
`notify_user` (`orchestrator.py:3010`); repeated skips for one paused job collapse
into a single actionable notification, not one per firing (spec Edge Case
"Notification fatigue").

## 4. Consent capture (US2, FR-011, D8)

An explicit, scoped, durable capture step wherever machine authority is created:
- Scheduling consent card (`schedule_decision` ui_event via `scheduling_chat`,
  `orchestrator.py:5758-5764`) — records the granted scopes, the durable
  (365-day-capped) nature, and the revocation path, then calls the existing but
  **currently-uncalled** `OfflineGrantStore.capture(user_id, refresh_token,
  agent_id)` (`offline_grant.py:64`) using the session refresh token
  (`session_store.py:207`), and links `grant_id` via `set_grant`
  (`scheduler/store.py:71-74`). Today `offline_grant_id` is hardcoded `None`
  (`scheduling_chat.py:295`, `scheduler/api.py:120`).
- No durable consent is created implicitly (FR-011): capture happens only at this
  explicit confirmation step.

## 5. Machine-turn audit event classes

Machine-turn tool dispatch uses the existing `agent_tool_call` pair (now
recorded, not dropped, §2). Scheduled-run lifecycle keeps the existing
`schedule` class (`audit/schemas.py:58`). Chain hops from a machine turn use the
new `delegation` class (§1). No other new classes.

## 6. Benchmark chained-attack scenarios (US5, FR-024/FR-025/FR-026, eval-only)

Extend `backend/security_benchmark/` (eval-only, isolation-guarded — Constitution
V/XI carve-out; product runtime gains zero dependency):

- New scenarios in the adapter/adjudicator core (`adapters/base.py`,
  `adjudicator.py`): **confused deputy** (agent A steers a hop to exceed A's
  authority), **cross-hop scope escalation** (child requests a superset),
  **depth-bound violation** (hop past depth 3), **actor-chain forgery** (tampered
  `act`), **chained-consent replay** (reuse a revoked machine grant). Each maps to
  the named defense layer expected to block it (`envelope.py` `LAYER_FOR_OBJECTIVE`).
- Executed through the **real dispatch path** via `drivers/inprocess.py` (the 047
  T021 seam, `047/tasks.md:49`), not the synthetic driver — so a block is genuine
  gate enforcement (FR-024).
- **Off-vs-on comparison** (FR-025, SC-008): a run with `FF_RECURSIVE_DELEGATION`
  off then on, reporting per-scenario outcomes + overall ASR, acceptance bar
  `ASR(on) ≤ ASR(off)`. Each blocked chained attack is attributed to a named layer
  (delegation attenuation, depth bound, actor-chain verify, MAS scan, permission
  gate).
- Reuses the existing report/ablation core (`report.py`, `envelope.py`); the
  isolation guard (`isolation_check.py`) stays green (no product module imports
  the harness).

## 7. Observability (Constitution X)

Structured logs (with agent/chat/correlation context) for every: child mint,
hop refusal (with reason code), empty-intersection refusal, MAS quarantine,
budget stop, orphan cancel, machine-turn authority derive/skip, and consent
capture. No secret token material in any log line (FR-028).
