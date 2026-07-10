# Tasks: Recursive, Provenance-Bearing Delegation Chains

**Feature**: 048-recursive-delegation-chains | **Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)
Verified in the `astraldeep` container (Python 3.11). **Test-first**: red before impl, green after.

## Phase 1 — Enforcement property tests, FIRST and failing (US1, P1)

- [X] T001 `tests/test_recursive_delegation.py` — property-based (seeded stdlib `random`, 100–300 generated cases per invariant), against the intended API.
- [X] T002 Invariant tests: monotonic attenuation (T003), no-escalation incl. hostile requests (T004), actor-chain completeness + forged-link rejection (T005), depth-bound mint-refuse + verify-reject (T006).
- [X] T003 **Run red:** first execution → **10 failed** (`AttributeError: module 'orchestrator.delegation' has no attribute 'mint_child_delegation'`) — proves the tests exercise unbuilt behavior (SC-001).

## Phase 2 — Mint further-attenuated child tokens behind the flag (US2, P1)

- [X] T004 `attenuate_scopes()` — intersection policy (equal-or-narrower, never wider) (FR-002/FR-004).
- [X] T005 `mint_child_delegation()` — nested `act` (current-outermost, human `sub` terminus), depth = parent+1, `exp ≤ parent.exp`, DPoP `cnf` carried; raises `DelegationDepthExceeded` past max (FR-002/003/005/010).
- [X] T006 `verify_delegation_chain()` — depth bound, actor-chain completeness/termination, broken-link + expiry checks; fails closed (FR-003/005).
- [X] T007 `FF_RECURSIVE_DELEGATION` in `shared/feature_flags.py`, default **off**; `recursive_delegation_enabled()` gate (FR-009).
- [X] T008 **Run green:** property tests → **10 passed** (SC-001, SC-002).

## Phase 3 — Enforce the chain at dispatch over the persistent transport (US3, P1)

- [X] T009 `authorize_chained_tool_call()` — per-tool-call re-derivation: verify chain + `is_tool_in_scope`; per-call fail-closed denial (no socket teardown) (FR-006/007).
- [X] T010 Tests: in-scope chained call permitted; out-of-scope refused; over-depth/tampered refused; **mid-session re-derivation** (two tools, one token, no new user-token round trip) (US3-AS1..AS4).

## Phase 4 — Provenance records link every hop to the human (US4, P2)

- [X] T011 `delegation_chain_audit_record()` — emits acting agent, human authorizer, operation, scope/policy context, depth, tamper-evident timestamp; maps field-by-field onto the §2.5 HIPAA checklist (FR-008, SC-007). Appends to the existing `audit/pii.py` hash chain (tamper-evidence supplied by `chain_hmac`).
- [X] T012 Test: provenance record carries all HIPAA fields incl. `parent_actor` and `delegation_depth`.

## Phase 5 — Bind chains to fan-out & auto-created agents (US5, P3)

- [X] T013 Mint/enforce functions are the injection seam for sub-agent fan-out (035) and auto-created-agent promotion (027/035).
- [ ] T014 **[integration, flag-on]** Wire `mint_child_delegation` into the fan-out coordinator and the promotion rail, and `authorize_chained_tool_call` into the WS dispatch call-site, so each downstream principal acts under an attenuated child token. Seam + primitives + tests are in place; the live call-site wiring lands with the `FF_RECURSIVE_DELEGATION`-on integration (default-off means zero regression until then — FR-012 scoped to Story 5's P3).

## Phase 6 — Verification (real container)

- [X] T015 SC-001: property tests failed before impl, pass after (version-history-demonstrable via the red/green run logs).
- [X] T016 SC-004 (no regression): `test_delegation.py` (11) + `test_tool_permissions.py` (26) green with the change; the 2 `test_security_gates_wiring.py` *supervisor* failures reproduce on the **pristine pre-048** `delegation.py` → pre-existing, unrelated (isolated via truncation run).
- [X] T017 SC-006 (no new deps): only stdlib + existing `cryptography`/JWT primitives; `pip freeze` unchanged.
- [ ] T018 **[deferred]** SC-003 two-hop audit-chain reconstruction end-to-end against the live hash chain + SC-005 over a real WS session — land with the T014 flag-on integration (mechanism + records verified at unit level now).

## Dependencies

- Fed by: 045 (framing: defensible core), 046 (nested-`act`-over-transport rationale vs. re-implementing IBCT).
- Feeds: 047 (its escalation/confused-deputy cases exercise this at the system level), 049 (the mechanism an I-D would specify), Direction D (auto-created agents born under attenuated delegation), the HIPAA conformance case study.
- Constitution: V (no new deps), IX (idempotent migration if a schema delta is later needed), test-first (FR-001).

## Note on pre-existing failures (honesty)

`test_security_gates_wiring.py::test_supervisor_off_is_noop` and `::test_supervisor_allows_when_intent_present` fail on the current working tree **independently of this feature** (confirmed against the pristine pre-048 `delegation.py`). They concern the HITL *supervisor* gate, not delegation. Flagged for the owner; out of scope for 048.
