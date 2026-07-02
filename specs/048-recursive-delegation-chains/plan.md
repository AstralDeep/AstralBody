# Implementation Plan: Recursive, Provenance-Bearing Delegation Chains Over Persistent Transport

**Branch**: `048-recursive-delegation-chains` | **Date**: 2026-07-02 | **Spec**: [spec.md](spec.md)
**Framing source**: [`docs/thesis/thesis-statement-memo.md`](../../docs/thesis/thesis-statement-memo.md) (Direction A — the defensible core). Design informed by the AIP differential ([`docs/thesis/related-work/daf-vs-aip.md`](../../docs/thesis/related-work/daf-vs-aip.md), spec 046).

## Summary

Extend the single-hop RFC 8693 exchange in `orchestrator/delegation.py` to mint and verify **nested-`act` child delegation tokens** behind `FF_RECURSIVE_DELEGATION` (default **off**, fail-closed), enforcing four invariants — monotonic scope attenuation, no privilege escalation, actor-chain completeness, depth-bounding — with per-tool-call enforcement over the persistent transport and per-hop provenance records for the hash-chained audit. **Enforcement property tests are written first and fail (red) before implementation** (Constitution test-first). **No new third-party runtime dependency** (Constitution V): chained tokens use the JWT/DPoP/`cryptography` primitives already present.

## Technical Context

**Language/Version**: Python 3.11 (backend image; verified in the `astralbody` container).
**Primary Dependencies**: existing only — `cryptography` (EC/DPoP), stdlib `hmac`/`hashlib`/`json`/`base64` already used by `delegation.py`; the hash-chained audit (`audit/pii.py::chain_hmac`, `repository.py::verify_chain`); `shared/feature_flags.py`. Property generation uses stdlib `random` — **no `hypothesis` dependency added**.
**Storage**: no schema change anticipated. Delegation-chain records ride the existing `audit_events` chain; if a column is ever needed it ships as an idempotent `_init_db` delta (Constitution IX). None required for this build.
**Testing**: `backend/tests/test_recursive_delegation.py` — property-based (generated scope sets + chain shapes), runs without a DB/Keycloak (mock-mode tokens).
**Design choice (from spec 046)**: nested RFC 8693 `act` claims, **not** a Biscuit/Datalog token — keeps the contribution a transport-and-deployment story within current deps; provenance rides the existing audit chain rather than in-token policy blocks.
**Constraints**: flag off ⇒ byte-for-byte single-hop (no regression, FR-009/FR-014); every fault fails closed; denials are per-call (never a socket teardown).

## Constitution Check

- **Test-first ordering (FR-001)**: PASS — 10 property tests authored first, **failed red** (AttributeError on the unbuilt API), pass green after implementation. Demonstrable from the run log.
- **V (no new runtime deps)**: PASS — reuses existing JWT/DPoP/`cryptography`; property generators are stdlib.
- **IX (idempotent migration)**: PASS — no schema delta in this build; documented path if one is later needed.
- **Fail-closed default**: PASS — `FF_RECURSIVE_DELEGATION` default off; flag-off path is the unchanged single-hop code.
- **No regression (FR-014)**: PASS — existing `test_delegation.py` (11) + `test_tool_permissions.py` (26) green; the two `test_security_gates_wiring.py` *supervisor* failures were isolated to the **pristine pre-048 tree** (reproduce without any 048 change) — pre-existing, unrelated to delegation.
- **Cross-client parity**: N/A for this build — backend-only token mechanism; no wire-frame/primitive/UI change, so web/Windows/Android clients are unaffected. New audit fields are server-side. (If the flag is later turned on and surfaces delegation depth in a client-visible frame, that becomes a parity item; not in this build.)

Gate result: **PASS**.

## Project Structure

```
backend/orchestrator/delegation.py     # + recursive section (mechanism + invariants + enforcement)
backend/shared/feature_flags.py        # + FF_RECURSIVE_DELEGATION (default off)
backend/tests/test_recursive_delegation.py   # property tests (written first)
```

New public surface in `delegation.py` (all additive, after the existing `DelegationService`):
`recursive_delegation_enabled()`, `attenuate_scopes()`, `actor_chain()`, `mint_child_delegation()`,
`verify_delegation_chain()`, `authorize_chained_tool_call()`, `delegation_chain_audit_record()`,
constants `DEFAULT_MAX_DELEGATION_DEPTH`/`DELEGATION_DEPTH_CLAIM`/`MAX_DEPTH_CLAIM`,
exceptions `RecursiveDelegationError`/`DelegationDepthExceeded`.

## Phased Approach (as executed)

**Phase 0 — Study substrate.** Read the single-hop `exchange_token_for_agent` / `_create_mock_delegation_token` (`act = {sub: agent:<id>}`, DPoP `cnf.jkt`) and the audit hash chain.

**Phase 1 — Property tests first (US1).** Encode the four invariants against the intended API; run → **red** (API absent).

**Phase 2 — Mechanism (US2).** `attenuate_scopes` (intersection), `mint_child_delegation` (nested `act`, depth+1, exp-cap, DPoP carried), `verify_delegation_chain` (depth, chain completeness, expiry, human root). Run → **green**.

**Phase 3 — Dispatch enforcement (US3).** `authorize_chained_tool_call` — per-tool-call re-derivation reusing `is_tool_in_scope`; denials per-call, fail-closed. Tested incl. mid-session re-derivation.

**Phase 4 — Provenance (US4).** `delegation_chain_audit_record` maps a hop onto the §2.5 HIPAA field checklist for append to the hash chain.

**Phase 5 — Flag + integration seam (US5).** `FF_RECURSIVE_DELEGATION` in the registry; the mint/enforce functions are the seam the sub-agent fan-out (035) and auto-created-agent promotion (027/035) call — wiring lands with the flag-on integration.

**Phase 6 — Verify (real container).** Red→green; no regression.

## Evidence (verified in the `astralbody` container, Python 3.11)

- **Test-first**: first run of `test_recursive_delegation.py` → **10 failed** (`AttributeError: … has no attribute 'mint_child_delegation'`). After implementation → **10 passed**, then **14 passed** with the US3 enforcement tests.
- **Combined**: `test_recursive_delegation.py` + `test_delegation.py` → **25 passed**.
- **No regression**: existing delegation (11) + tool-permissions (26) green; the 2 supervisor failures reproduce on the pristine pre-048 `delegation.py` → pre-existing, not caused here.

## Complexity Tracking

No deviations. Nested-`act`-over-JWT was chosen specifically to avoid a new token-format dependency (the alternative, a Biscuit/Datalog chained token, would add a runtime dep and shift the contribution to a competing format — rejected per spec 046).
