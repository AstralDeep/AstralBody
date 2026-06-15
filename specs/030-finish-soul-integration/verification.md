# Verification Record — 030 Finish Soul Integration

## SC-009 — No new UI primitive types (FR-019)

All UI emitted by this feature uses **existing** astralprims primitives only:
`Alert`, `Text`, `Card`, `Button` (memory confirmations, onboarding confirmations,
schedule consent/notice). No new primitive classes were added to astralprims, and
no new renderer types were added to `webrender`. **Verified: 0 new primitive types.**

## SC-010 / FR-022 — No new third-party runtime libraries

`backend/requirements.txt` is unchanged by this feature. All new code imports only
modules already present (FastAPI, the astralprims package, stdlib `logging`/`uuid`,
the existing `personalization`/`scheduler`/`dreaming`/`audit` first-party modules,
the existing Fernet/Keycloak paths). **Verified: 0 new third-party dependencies.**

## Lint

`ruff check .` from the repo root is the CI gate (Constitution IV/XI); run before PR.

## Tests added (FR-015)

| File | Covers |
|---|---|
| `orchestrator/tests/test_memory_chat.py` | memory meta-tool (US2/T014) |
| `orchestrator/tests/test_onboarding_submit.py` | onboarding submit interpretation (US3/T024) |
| `orchestrator/tests/test_knowledge_guard.py` | retired-agent index guard (US6/T037) |
| `scheduler/tests/test_execution_gate.py` | fail-closed flag defaults (US1/T008) |
| `scheduler/tests/test_runner_dreaming.py` | dreaming sweep routing (US4/T027) |
| `dreaming/tests/test_dreaming_scheduling.py` | per-user job ensure/remove + set_offline_grant (US4/T028-29, T011) |
| `personalization/tests/test_profile_memory_skills_api.py` | profile/memory/skills/personalize REST contracts (T013/T024/T033/T014) |

## Local run

Run via the root `.venv` + docker postgres with `ASTRAL_ENV=development` (see quickstart.md).
Changed-code coverage gate (`diff-cover` ≥90%) is the merge bar (Constitution III) — run on the PR.

## Residual / human-gated (not auto-completable)

- **T009 / FR-004** — lead-developer **security sign-off** of the offline-grant store (this AI prepared the analysis in `security-review.md`; the sign-off is a human decision). `FF_SCHEDULER_EXECUTION` stays OFF until signed.
- **T010 / FR-003** — the WS offline-grant **consent-capture handshake** (secure session→refresh-token retrieval) is part of the T057-gated path; `set_offline_grant` store method is in place to receive the grant id.
- **T039** — staging end-to-end validation (needs a live staging stack).
- **T040** — CI green on the PR (runs on push).
