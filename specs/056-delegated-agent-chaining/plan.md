# Implementation Plan: Delegated Agent Chaining

**Branch**: `056-delegated-agent-chaining` | **Date**: 2026-07-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/056-delegated-agent-chaining/spec.md`

**Framing source**: Thesis Direction A — "the first implemented, deployed,
evaluated system that binds attenuated, provenance-bearing agent delegation to a
persistent transport and to a self-extension loop, and measures its enforcement."
This feature is that integration made real (spec "Why now").

## Summary

Wire feature 048's tested-but-unwired recursive-delegation mechanism
(`orchestrator/delegation.py:400-668`, zero production call sites, 048 T014/T018
deferred) into the product so agents chain to peer agents and the orchestrator
stops being the sole planner — while preserving the DAF and RFC 8693 guarantees
end-to-end. Two orchestrator-mediated seams (a deterministic agent-runtime
callback and LLM-planned nested sub-turns) both re-enter the single-path gate
stack, minting a strictly-narrower child authority per hop
(`mint_child_delegation` -> `authorize_chained_tool_call`), with empty
intersections refused fail-closed and every hop emitting a paired provenance
record to the hash-chained audit (closing 048 T018). Machine-initiated turns
(scheduled runs, parser replay, draft self-tests) gain a shared consent-derived
root authority so they act in production, not just dev — captured explicitly,
narrowed to (consented AND current), attributed to a defined machine principal,
and shipped dark behind the pending offline-grant security-review gate. The
parallel dispatch path is brought to full gate parity with the single path (it
silently skips policy/taint/supervisor/HITL/delegation/concurrency today) so
chaining cannot amplify a weaker path. The dormant unattenuated peer-call path is
retired. The 047 benchmark gains chained-attack scenarios through the real
dispatch path. All decisions and their file:line evidence: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11 (backend, production image; local `.venv`
3.13). Backend-only mechanism — no client language work (see Constitution XII
note below).

**Primary Dependencies**: Existing only — the 048 recursive-delegation functions
in `orchestrator/delegation.py` (`mint_child_delegation`,
`verify_delegation_chain`, `authorize_chained_tool_call`, `attenuate_scopes`,
`delegation_chain_audit_record`), `DelegationService` (RFC 8693/DPoP,
`delegation.py:39`), the offline-grant store (`orchestrator/offline_grant.py`,
`cryptography`/Fernet), the scheduler + job runner (`backend/scheduler/`), the
`AgentRuntime` loopback bridge (`shared/agent_runtime.py`,
`shared/local_transport.py`), the hash-chained audit (`backend/audit/`,
`chain_hmac`/`verify_chain`), the tool permission/trust/security-flag stack
(`orchestrator/tool_permissions.py`, `tool_security.py`, `agent_trust.py`), the
MAS-defense scanner (`orchestrator/mas_defense.py`), the concurrency cap
(`orchestrator/concurrency_cap.py`), the VirtualWebSocket machine-turn substrate
(`orchestrator/async_tasks.py`), and the 047 benchmark harness
(`backend/security_benchmark/`, eval-only). `python-jose` (JWT), stdlib
`hmac`/`hashlib`/`json`/`base64` as 048 already uses. **Zero new third-party
runtime dependencies** (Constitution V, FR-027). Any benchmark corpus stays in
the eval-only manifest, isolation-guarded (Constitution V/XI carve-out).

**Storage**: PostgreSQL via `shared/database.py::_init_db()` idempotent guarded
startup migrations. Provenance hop records ride the existing `audit_events`
hash chain — **no new table** for the audit trail (FR-026 requires reconstruction
from the tamper-evident log). Possible additive deltas, each idempotent + guarded
with documented rollback: an optional `chain_hop` correlation column if hop
reconstruction needs an index beyond `correlation_id` (evaluated in data-model);
scheduler consent linkage reuses the existing `scheduled_job.offline_grant_id`
column (`scheduler/store.py:71-74`) — no schema change. The `EVENT_CLASSES` tuple
gains `"delegation"` (`audit/schemas.py:30` — a Python constant, not a schema
migration). Details + rollback: [data-model.md](data-model.md).

**Testing**: pytest inside the `astraldeep` container (both invocations:
`backend/tests` and module suites) against `postgres:17-alpine`; the 048 property
suite (`test_recursive_delegation.py`, 14 tests) + delegation (`test_delegation.py`,
11) + tool-permission (`test_tool_permissions.py`, 26) suites stay green
unchanged with the flag off (SC-009); new suites for the chaining seam, the
shared gate-authorizer parity contract, machine-turn authority, two-hop audit
reconstruction, budget/orphan bounds, peer-path retirement; benchmark chained
scenarios in `security_benchmark/tests`. `ruff check .` from repo root on
host/CI.

**Target Platform**: Linux server (Docker image). Backend + eval harness only.

**Project Type**: Server-driven multi-agent orchestrator (one backend; the wire
protocol and every client are consumers, unchanged here — see Constitution XII).

**Performance Goals**: A hop adds one pure-function child mint + one pure-function
verify (no user-token round trip — `authorize_chained_tool_call` re-derives from
the presented token, `delegation.py:621-639`); mid-session re-derivation is the
048 design point. Chain budget bounds cumulative depth (<=3), hop count, and wall
clock per turn (D9) so a decomposed turn terminates. Flag-off adds zero work
(byte-identical single-hop path).

**Constraints**: Flag off => byte-for-byte today's single-hop wire/token behavior
(FR-009, SC-009). Every refusal per-call and fail-closed, never
session-terminating, always audited without recording secret values (FR-028).
Explicit user opt-out and hard security-flag blocks always win over any chain,
trust baseline, or consent (FR-029). Empty scope intersection refuses (FR-005).
Machine-turn authority ships dark behind `FF_SCHEDULER_EXECUTION` until the T057
review is recorded (FR-016). No new runtime dependency (FR-027). The meta-tool
gate exemption stays structurally unavailable to real-agent hops (FR-003/FR-018).

**Scale/Scope**: ~7 backend modules touched (`delegation.py` call sites,
`orchestrator.py` dispatch/gate-authorizer/runtime-hop/machine-turn/audit,
`shared/agent_runtime.py`, `shared/base_agent.py` peer-path removal,
`scheduler/runner.py` + `run_scheduled_turn` token threading,
`attachment_autoparse.py` + `agentic_creation.py` machine-turn seam,
`mas_defense` hop enforcement wiring), `security_benchmark/` chained scenarios,
2 feature flags reused (no new product flags required; the seam rides
`FF_RECURSIVE_DELEGATION` and `FF_SCHEDULER_EXECUTION`), ~29 functional
requirements across 5 user stories.

## Constitution Check

*GATE: evaluated against Constitution v2.6.0 before Phase 0; re-checked after Phase 1.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Python backend | PASS | All work Python; no other backend language |
| II | SDUI architecture | PASS | No astralprims/primitive/renderer change; hop/sub-task progress rides EXISTING progress frames (FR-022, spec Assumption "Progress surfaces") — no new frame unless one proves unavoidable, then drift-guarded |
| III | 90% changed-code coverage | PLANNED | Every new path (child-mint wiring, gate-authorizer, runtime hop, machine-turn seam, consent capture, budget/orphan, peer retirement, audit hop record) ships unit + integration tests; CI diff-cover >=90% gate enforces |
| IV | Lint | PLANNED | `ruff check .` from repo root (matches ci.yml) |
| V | Zero new third-party deps | PASS | Reuses 048's JWT/DPoP/`cryptography` + existing modules; benchmark corpus (if any) stays eval-only + isolation-guarded (FR-027) |
| VI | Documentation | PLANNED | New public surfaces (runtime callback, gate authorizer, machine-turn seam, hop audit class) documented with docstrings; contracts/ documents the wire/audit deltas |
| VII | Security | PASS (core) | This feature IS the Principle VII recursive-delegation clause (v2.4.0) made real: four invariants preserved at every hop via 048's tested functions; child never outlives/exceeds/survives-revocation of parent; per-hop provenance to the hash chain; fail-closed flag default off. Meta-tool bypass structurally closed to real agents (FR-003). Machine root inherits the T057 review gate (FR-016). No new auth provider; Keycloak/RFC 8693 unchanged |
| VIII | UX via astralprims | PASS | No UI primitive change; honest per-call errors reuse existing `Alert` |
| IX | Idempotent migrations + rollback | PLANNED | No new table for the audit trail (rides `audit_events`); any additive column ships as a guarded `_init_db` delta with documented rollback (data-model.md); `EVENT_CLASSES` edit is a constant, not a migration |
| X | Production readiness / verify | PLANNED | Production-posture verification: scheduled run dispatches real-agent tools under consent (SC-004); no stubs; structured logs for every refusal/mint/quarantine/budget-stop |
| XI | CI gates | PLANNED | All 8 gates; the flag-off byte-equivalence run (existing 48 delegation+permission tests green) is SC-009; benchmark isolation guard stays green |
| XII | Cross-client consistency | PASS (N/A backend) | Backend-only token/dispatch mechanism; no wire-frame/primitive/chrome/theming change. Hop/sub-task progress reuses existing progress frames on every client with **no new native renderer** (spec Assumption "Progress surfaces"); if a new frame proves unavoidable it follows the drift-guard/manifest process and lands on all clients same-PR |
| XIII | Docs/research integrity | N/A | Product feature (the thesis docs — 046/049 — are separate tracks that cite this feature's artifacts, spec Assumptions) |

**Initial gate: PASS** — no violations to justify; Complexity Tracking empty.
**Post-Phase-1 re-check: PASS** — the design introduces no new project, no new
runtime dependency, no parallel definition, no client-visible protocol change;
the only new audit vocabulary is one `EVENT_CLASSES` value handled through the
existing constant, and every mechanism is a call site of already-merged code.

## Project Structure

### Documentation (this feature)

```text
specs/056-delegated-agent-chaining/
├── spec.md              # Feature specification (committed)
├── plan.md              # This file
├── research.md          # Phase 0 — 17 decisions with file:line evidence + alternatives
├── data-model.md        # Phase 1 — entities, audit-record shape, no-new-table rationale, rollback
├── quickstart.md        # Phase 1 — per-story live verification walkthrough
├── contracts/
│   ├── delegation-chaining.md      # runtime callback + hop lifecycle + gate-authorizer + child-mint contract
│   └── audit-and-machine-turn.md   # hop provenance record fields, machine principal, consent-capture, benchmark hooks
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── orchestrator/
│   ├── delegation.py               # 048 mechanism — CONSUMED, not modified (mint_child_delegation:515,
│   │                               #   verify_delegation_chain:570, authorize_chained_tool_call:621,
│   │                               #   delegation_chain_audit_record:642); a thin helper may be added to
│   │                               #   encode/sign the child compactly at the call site if needed
│   ├── orchestrator.py             # US3: extract _authorize_and_prepare shared gate stack from
│   │                               #   execute_single_tool (~5779-6062); route execute_parallel_tools
│   │                               #   (~6220-6304) through it; meta-tool parity (~5753-5777 vs 6261);
│   │                               # US1: child-mint at dispatch when a parent token is present
│   │                               #   (extend _get_delegation_token ~6798 / the token-inject site ~5977);
│   │                               #   authorize_chained_tool_call per hop; empty-intersection refusal;
│   │                               #   mediate AgentRuntime.call_agent_tool hops -> execute_single_tool;
│   │                               # US2: MachineTurnAuthority derivation; thread the minted token into
│   │                               #   run_scheduled_turn (~2923, token dropped at 2946-2949 today);
│   │                               #   machine principal in the audit path;
│   │                               # US4: ChainBudget per-turn object; sub-task spawn + digest return;
│   │                               #   orphan cancel; MAS scan enforcement on hop results (~3990-3996);
│   │                               #   provenance hop record emission to the audit chain
│   ├── chain_authority.py          # NEW — MachineTurnAuthority derivation + ChainBudget (small module,
│   │                               #   mirrors offline_grant.py / concurrency_cap.py one-purpose pattern)
│   ├── offline_grant.py            # CONSUMED — capture(:64) finally gets a production caller (D8);
│   │                               #   mint_access_token(:107)/is_valid(:97) unchanged
│   ├── mas_defense.py              # CONSUMED — scan_message(:101)/is_safe_message(:113); enforcement
│   │                               #   moves from log-only to quarantine on the hop path (D11)
│   ├── attachment_autoparse.py     # US2: auto_continue_after_go_live (:87) derives machine authority
│   ├── agentic_creation.py         # US2: _self_test_draft (:323) derives machine authority
│   └── scheduling_chat.py          # US2: schedule consent-capture step (offline_grant_id no longer
│                                   #   hardcoded None at :295)
├── shared/
│   ├── agent_runtime.py            # US1: add call_agent_tool (mediated hop request; today only
│   │                               #   start_long_running_job :45)
│   ├── base_agent.py               # US4: RETIRE call_peer_tool (:682) + peer transport/registry
│   │                               #   (connect_to_peer :653, _call_peer_via_ws/_a2a :726/:841)
│   ├── local_transport.py          # CONSUMED — LoopbackSocket routes the hop control frame back
│   └── feature_flags.py            # CONSUMED — recursive_delegation (:107), scheduler_execution (:47);
│                                   #   no new product flag required
├── scheduler/
│   ├── runner.py                   # US2: run_job (:88) hands the minted token to run_scheduled_turn
│   │                               #   via MachineTurnAuthority; _intersect_scopes (:29) reused
│   └── store.py                    # US2: set_grant (:71) linked from the consent-capture step
├── audit/
│   ├── schemas.py                  # add "delegation" to EVENT_CLASSES (:30) — a constant, not a migration
│   └── hooks.py                    # US2/US4: machine principal resolution (actor_principal_from_claims
│                                   #   :29 returns legacy today -> machine:<class>); hop provenance helper
├── security_benchmark/             # US5 (eval-only, isolation-guarded)
│   ├── adapters/                   # chained-attack scenarios (confused deputy, cross-hop escalation,
│   │                               #   depth violation, actor-chain forgery, chained-consent replay)
│   ├── adjudicator.py / envelope.py / report.py  # reuse the 4-outcome core + ablation columns
│   └── drivers/inprocess.py        # real dispatch path (047 T021 seam)
└── tests/                          # unit + integration + parity contract + flag-off equivalence
```

**Structure Decision**: No new project or package beyond one small backend module
(`chain_authority.py`) that follows the established one-purpose-store pattern
(`offline_grant.py`, `concurrency_cap.py`, `session_store.py`). Everything else is
a call site of already-merged 048 mechanism, a factoring of the existing single
path (`_authorize_and_prepare`), a thread-through of an already-minted token
(`run_scheduled_turn`), or a deletion (peer path). The eval-only benchmark
scenarios stay inside `security_benchmark/`, isolation-guarded.

## Implementation phasing (maps to /speckit-tasks)

1. **US3 dispatch-path parity** (prerequisite hardening — must land with/before
   US1 flag-on): extract `_authorize_and_prepare`; route the parallel path
   through it; meta-tool parity; shared gate-contract test across single/parallel.
   Ships independently as pure hardening; fixes the documented
   policy/taint/supervisor/HITL/delegation/concurrency skips. Also bounds the two
   pre-existing supervisor-gate test failures 048 flagged (spec Assumption).
2. **US1 chained authority** (`FF_RECURSIVE_DELEGATION`): `AgentRuntime.call_agent_tool`
   -> mediated hop -> `execute_single_tool` under `mint_child_delegation` +
   `authorize_chained_tool_call`; empty-intersection refusal; per-hop provenance
   record to the audit chain; two-hop reconstruction regression (closes 048 T018);
   flag-off byte-equivalence. The headline slice; independently shippable.
3. **US2 machine-turn authority** (dark behind `FF_SCHEDULER_EXECUTION`):
   `chain_authority.MachineTurnAuthority`; thread the minted token into
   `run_scheduled_turn`; extend to parser replay + self-tests at the one shared
   seam; consent-capture step; machine principal in audit. Ships dark; changes no
   runtime behavior until the T057 review is recorded.
4. **US4 planning decomposition** (`FF_RECURSIVE_DELEGATION`): `ChainBudget`;
   bounded isolated sub-tasks with child authority + per-subtree budget + digest
   return; orphan cancel; MAS scan enforcement on hop/digest payloads; retire the
   peer path with its regression test.
5. **US5 measurement** (eval-only): chained-attack benchmark scenarios through the
   real dispatch path; off-vs-on comparison report; ASR-no-regression bar.

Cross-cutting last: the flag-off byte-equivalence CI run (SC-009), observability
review (every refusal/mint/quarantine/budget-stop structured-logged), and the
per-story production-posture verification (quickstart.md).

## Complexity Tracking

*No Constitution Check violations — table intentionally empty.* The one new module
(`chain_authority.py`) is justified by FR-012's "one shared mechanism all
machine-turn classes inherit" and FR-021's global budget; inlining either into
`orchestrator.py` would scatter the machine-turn seam across three call sites (the
exact fragmentation FR-012 forbids).
