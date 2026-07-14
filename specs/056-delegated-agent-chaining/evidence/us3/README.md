# US3 evidence — dispatch-path parity (T012)

Recorded 2026-07-14 against the `astraldeep` container (real Orchestrator,
real Postgres, merged 056 branch at the Phase-3 checkpoint).

## Files

- `live-verify-output.txt` — `us3_live_verify.py` run inside the container
  under explicit production delegation posture (`DELEGATION_REQUIRED=true`):
  1. **Fail-closed parity**: with no session token, the single path and the
     parallel batch refuse with byte-identical
     "delegated authorization … unavailable" errors (the parallel path
     previously dispatched UNSCOPED with no refusal at all).
  2. **Token parity**: with the exchange available, every call in a parallel
     batch now carries its own `_delegation_token` (verified per-call).
  3. **Meta-tool parity**: `__scheduler__` / `__memory__` meta-tools dispatch
     correctly from a parallel batch (previously only `__orchestrator__`
     worked; the others dead-ended in the no-agent error).
- `parity-suite-output.txt` — in-container run of
  `tests/test_dispatch_parity.py` (all 8 gates driven down both paths with
  identical refusals + equivalent audit rows; SC-006),
  `tests/test_hop_concurrency_accounting.py` (FR-019 dual-slot charging), and
  `tests/test_security_gates_wiring.py` (the two 048-flagged supervisor tests
  pass after the parity refactor — T011). 27 passed.

## Notes

- The 048-flagged "two pre-existing supervisor-gate failures" no longer
  reproduce on this branch: `backend/tests/conftest.py` (added post-048)
  strips ambient `FF_HITL_HIGHRISK`/gate env vars that caused them. T011 is
  satisfied by the green run recorded here; no supervisor-gate bug was
  exposed by the T007 refactor.
- Full backend suite after the refactor: **3650 passed, 3 skipped** (zero
  regressions; the only test change was binding the new
  `_release_hop_cap_slot` surface into `test_long_running_job_progress.py`'s
  orchestrator stand-in fixture).
