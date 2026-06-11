# T042 — Real-browser gate (evidence)

**Date**: 2026-06-10 | **Verdict**: PASSED-WITH-NOTES
**Environment**: rebuilt `astralbody` container (py3.11) from the 028 working tree on `:8001`,
PostgreSQL 17 (`astralbody-postgres`), LLM `google/gemma-4-31B-it` via
`api-llm-factory.ai.uky.edu`. Headless Chromium (Playwright 1.60); WS frames captured.
Scripts: `backend/tmp/e2e/t042_*.py`; per-phase machine reports (`*-report.json`),
screenshots, and the fail-closed boot log in this directory.

## Part A — auth

### A5 Production fail-closed — PASS (`a5-fail-closed-boot.log`)
- `.env` with `USE_MOCK_AUTH=true` and **`ASTRAL_ENV` unset** (production is the default):
  orchestrator logs `CRITICAL — REFUSING TO START: USE_MOCK_AUTH is enabled but ASTRAL_ENV is
  not 'development'…` (SystemExit 78) and **nothing is served on :8001** (curl: connection refused).
- After `ASTRAL_ENV=development`: clean boot, shell `HTTP 200` (dev passthrough unchanged —
  mock-mode control run of the gate script confirmed the shell served directly).

### A1 Sign-in gate, real-auth mode — PASS (`a1-report.json`, `a1-keycloak-login.png`)
Run with `USE_MOCK_AUTH=false` (no credentials needed for the chain):
- `GET /?chat=test` → **302** `Location: /auth/login?next=%2F%3Fchat%3Dtest`, **empty body**
  (zero app markup pre-auth, FR-001/FR-002).
- `/auth/login` → **307** to `iam.ai.uky.edu` `…/protocol/openid-connect/auth` with
  **PKCE** (`code_challenge`), `state`, and `offline_access` in scope.
- Open-redirect guard: `next=https://evil.example/phish` never reaches the authorize URL.
- Headless browser starting at `/` lands on the realm's login page (screenshot).

### A2/A3/A4 — environment-constrained, compensated by unit tests
Silent refresh against a live realm, restart-survival of a real session, and Keycloak-side
revocation verification require realm credentials/admin access not available to this
headless run. Compensated (Constitution III) by `test_session_store_refresh.py`
(refresh rotation, anchor immutability, hard-cap, restart survival via a fresh store
instance, refresh-failure → session dead + audit) and `test_logout_revocation.py`
(revoke order, offline-tolerant queue retry, 025 offline-grant revocation, user-switch).
Run these once against the real realm when operator access is available.

## Part B — workspace

### B1 Accumulate + LLM in-place refresh — PASS (`b1-report.json`, `b1-*.png`)
Fresh chat `2249c123`: process-table turn (14 s) → `au_cpu-info-card` + `wc_d1bc549d36abb56e`;
chart turn (16 s) → `au_chart-card` **added, table survives** (no canvas wipe).
"Refresh the process table … do not touch the chart" → **2 `ui_upsert` ops, both targeting
`au_cpu-info-card`**; table's `component_id` stable, **chart DOM node untouched**
(pre-tagged attribute survived ⇒ morph, not re-render), no new component created.

### B2′ Deterministic component_action — PASS (`ca-report.json`, `b2-refresh-*.png`)
NocoDB (the only paginated-table producer) is unreachable here, so the deterministic trigger
was the renderer's own `.astral-action` button markup injected into the live table component's
scope; the click then flowed through the **real client delegated handler** (component_id +
chat_id auto-injection) and the **real server pipeline** (resolve → permission → execute →
upsert → snapshot → fan-out). Result: `ui_upsert` in **0.5 s targeting only that component**;
the other two components' DOM untouched. `table_paginate`→`component_action` routing itself is
unit-proven (`test_component_action.py`).

### B3 Re-hydration — PASS (`b3-rehydrated.png`, `b3-transcript.png`)
Reload of `?chat=e492428c`: all 3 components restored, **0 tool re-runs** (no `chat_step`
frames), 11 transcript bubbles with **0 empty bubbles**, component-bearing messages render
server-supplied `html` (tables visible in the transcript).

### B4 Read-only timeline — PASS (`b4-*.png`)
5 snapshots listed (one per turn + per component action). Viewing one: historical canvas +
warning banner "…— read-only", topbar status `Viewing workspace history (read-only)`.
Canvas actions inert (`Read-only history view — go back to live to interact.`); server-side
refusal + `workspace.action_denied(timeline_readonly)` is unit-proven. While in history,
a second tab's refresh produced `Live workspace updated — use "Back to live" to see it.`
**Back to live** restored the current 3-component state and cleared the mode.

### B5 Multi-device fan-out — PASS (`b5-second-tab.png`)
Second context (480×900 mobile UA, same chat): full workspace on load; the desktop tab's
component refresh arrived as `ui_upsert` on the mobile socket in **0.3 s** (≪ 2 s bound).

### B6 Permission denial — PASS (`b6-report.json`, `b6-denied.png`)
`live_system_metrics` (general-1) disabled for `test_user` via its per-kind
`tool_overrides` row → refresh click: denial Alert **"Action not permitted: This tool is
disabled in your permissions."** in chat, component unchanged, and exactly one new
`workspace.action_denied` audit row (`outcome=failure`). Prior permission state restored.

## Notes / follow-ups (non-blocking)

1. First B1 attempt timed out waiting for turns — transient LLM-factory queue latency
   (turns >4 min); rerun completed in 14–50 s/turn. No product defect.
2. The LLM echoes raw component JSON into an "Analysis" chat bubble alongside the rendered
   card (visible in `b1-refresh-inplace.png`, right panel) — pre-existing model-behavior
   cosmetic, not a 028 regression.
3. B2 pagination buttons could not be exercised literally (no NocoDB); covered by the
   injected-trigger run above plus `test_component_action.py` pagination-alias tests.
4. Mock auth makes every browser session `test_user`/admin, so non-admin DOM-absence and
   the literal signed-out screen remain unit-proven only (as in 027).
