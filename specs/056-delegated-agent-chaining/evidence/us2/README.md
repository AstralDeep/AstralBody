# US2 evidence — background work acts with real, revocable consent (T030)

Recorded 2026-07-14 in the `astraldeep` container under **production
delegation posture** (`DELEGATION_REQUIRED=true`) with the review-gated
`FF_SCHEDULER_EXECUTION=1` for the duration of the run. Real `JobRunner`, real
`OfflineGrantStore` (a real encrypted `user_offline_grant` row), real
`ScheduledJobStore`, real orchestrator dispatch, real `audit_events`.

Only two things are stubbed, both pure network transports unavailable on this
box: the Keycloak refresh exchange inside `mint_access_token`, and the RFC 8693
token exchange. Every step that this feature actually builds — consent
validation, revocation re-check at derivation, scope intersection, threading
the root into the turn, delegated dispatch, machine-principal audit,
skip/pause/notify — is the real code path.

## What the run proves (`live-verify-output.txt`)

1. **A machine turn now acts delegated in production** (SC-004). The scheduled
   run derives a fresh root from the job's durable consent; the turn's RFC 8693
   exchange consumes that **consent-derived subject token**; the real-agent
   tool dispatches carrying a delegation token. Before this feature the turn
   had no session token at all and production posture refused every real-agent
   dispatch fail-closed — scheduled jobs were development-mode-only.
2. **Machine-principal attribution** (FR-014, SC-005). Both tool-call rows
   carry `auth_principal = machine:scheduled_job`, `actor_user_id = <the owning
   human>`, and `inputs_meta.consent_ref = <the grant id>`. They used to be
   recorded as `legacy` and therefore **dropped entirely**. Cost stays on the
   SYSTEM LLM credential (054) — who paid and who authorized are recorded
   distinctly and never blur.
3. **Revocation stops it, and says so once** (SC-004). After
   `revoke_for_user`, three consecutive firings each dispatch **zero** tools,
   record `skipped_auth`, pause the job — and the user receives **exactly one**
   actionable notification, not one per firing.

## Ship-dark posture (FR-016)

`FF_SCHEDULER_EXECUTION` remains **default off** in the committed code; the
flag was set only inside this verification process. The offline-grant security
review (025 T057 / 030 FR-004/FR-005) is inherited, not bypassed:
`tests/test_scheduler_execution_gate.py` pins that the execution loop is
flag-gated, that `chain_authority` contains no flag bypass, and that consent
capture (which is safe to ship on) is independent of it.

## Test suites backing this

`tests/test_machine_turn_authority.py` (derivation, narrowing to consented ∩
current, fail-closed skips, one-notification collapse, delegated dispatch when
bound vs. refused when unbound, machine-root chains attenuate),
`tests/test_machine_turn_classes.py` (all three classes — scheduled run, parser
replay, draft self-test — derive at the ONE shared seam),
`tests/test_consent_capture.py` (explicit capture on approval only; the card
names scopes + 365-day durability + revocation path; nothing captured
implicitly), `tests/test_chain_authority.py`, `tests/test_machine_principal.py`,
`tests/test_scheduler_execution_gate.py`.

Full container suite: **3712 passed, 3 skipped**.
