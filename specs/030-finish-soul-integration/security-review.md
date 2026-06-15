# Security Review — Offline-Grant Store (025 T057 / 030 FR-004)

**Subject**: `backend/orchestrator/offline_grant.py` and the scheduler execution path that consumes it.
**Constitution**: VII (Security), X (Production Readiness).
**Gate**: `FF_SCHEDULER_EXECUTION` MUST remain **off** until this review is signed off by a lead developer (sign-off block at the bottom). This document is the code-level analysis prepared *for* that sign-off; the sign-off itself is a human decision and is **PENDING**.

## Scope

Unattended scheduled jobs run under authority derived from a stored Keycloak `offline_access` refresh token. This review covers: encryption at rest, key management, lifetime cap, revocation, scope attenuation, token egress, and the failure modes of the execution path.

## What was reviewed

| Aspect | Finding | Evidence |
|---|---|---|
| Encryption at rest | Refresh tokens are Fernet-encrypted before storage; plaintext is never persisted. | `offline_grant.py` `capture()` encrypts via `_fernet().encrypt(...)`; column `refresh_token_enc`. |
| Fail-closed key | If `OFFLINE_GRANT_ENC_KEY` is unset, `capture()` raises rather than storing plaintext. | `OfflineGrantError` on missing key; documented in module docstring. |
| Lifetime cap | Hard 365-day expiry stamped at capture; `is_valid()` refuses expired grants. | `expires_at = now + OFFLINE_GRANT_MAX_DAYS * _DAY_MS`; `is_valid()` expiry check. |
| Revocation | Per-user revoke (`revoke_for_user`) flips `revoked_at`; `is_valid()` refuses revoked; logout revokes (028). | `revoke_for_user`; `is_valid()` revoked check. |
| Token egress | Refresh token is never returned by any API and never logged; only a fresh short-lived access token is minted per run and used in-process. | `mint_access_token()` returns only the access token; `offline_grant.minted` log carries grant_id/user_id only (030 FR-017). |
| Scope attenuation | Per run, authority = intersection(consented_scopes, user's CURRENT scopes); narrowing only. | `runner._intersect_scopes`; `tool_permissions.get_agent_scopes`. |
| Fail-safe execution | Missing/expired/revoked grant or refresh failure → run records `skipped_auth`, pauses the job, notifies; never runs with stale authority. | `runner.run_job` steps 1–2. |
| Fail-closed loop | The execution loop does not start unless `FF_SCHEDULER_EXECUTION` is on (030). | `orchestrator.py` scheduler startup gate. |

## Residual items the sign-off MUST cover before enabling the flag

1. **WS consent capture (030 T010/FR-003)** — the handshake that retrieves the live session's `offline_access` refresh token and calls `capture()` is **not yet wired** end-to-end. The store method `ScheduledJobStore.set_offline_grant()` exists to receive the grant id, but the secure path from a WebSocket session to its refresh token (the token lives in the HTTP `web_session` store, not in `ui_sessions`) must be designed and reviewed here. Until then, jobs have `offline_grant_id = NULL` and the runner refuses them (`skipped_auth`) — safe, but non-functional for unattended runs.
2. **Delegated-token threading (030 FR-006)** — `run_scheduled_turn()` currently executes under the user's *current* scopes (the enforced ceiling) rather than threading the minted delegated `access_token` and narrowing tool execution end-to-end to `allowed_scopes`. Confirm whether ceiling-only enforcement is acceptable for the first enablement, or require full delegated-token threading first.
3. **Key rotation / storage** — confirm `OFFLINE_GRANT_ENC_KEY` provisioning is runtime-only (never baked into the image) and document the rotation procedure.
4. **Keycloak realm** — confirm `offline_access` scope and Offline Session Max ≥ 365 days are configured (see `docs/keycloak-realm-settings.md`).

## Recommendation

The store itself is cryptographically sound and fail-safe. The dangerous capability (unattended execution under offline authority) is correctly gated off by default. Do **not** enable `FF_SCHEDULER_EXECUTION` in production until items 1–4 are resolved and signed off below.

## Lead-developer sign-off

- [ ] Reviewed by: __________________  Date: __________
- [ ] Items 1–4 resolved or explicitly accepted as residual risk.
- [ ] Authorization to set `FF_SCHEDULER_EXECUTION=true` in: ☐ staging ☐ production

> Status: **PENDING** — this is an AI-prepared code analysis, not a lead-developer sign-off. Until the boxes above are checked by a lead developer, the execution loop stays fail-closed.
