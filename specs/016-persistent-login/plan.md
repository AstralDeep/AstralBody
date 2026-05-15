# Implementation Plan: Persistent Login Across App Restarts (Web + Flutter Wrapper)

**Branch**: `016-persistent-login` (planned; current branch: `main`) | **Date**: 2026-05-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/016-persistent-login/spec.md`

## Summary

Make AstralBody users stay signed in across full browser/app restarts for up to 365 days from their most recent interactive login, on both the React web frontend and the Flutter WebView wrapper, **without changing the login flow itself**. The user explicitly asked to "respect the current login method, just extend the credential storing" — the entire feature reduces to (a) switching `react-oidc-context`'s token store from `sessionStorage` to `localStorage` (which the Flutter WebView already persists across launches), (b) enforcing a client-side 365-day hard-max ceiling, (c) wiring three new audit `action_type` values into the existing `event_class="auth"` bucket, and (d) configuring Keycloak's offline-session lifespan to match.

No new third-party libraries. No new database tables. No new UI primitives. No backend route changes outside one audit-recording site. Flutter side requires zero Dart code change — its WebView already preserves localStorage across cold launches by default on both iOS and Android.

## Technical Context

**Language/Version**: Python 3.11+ (backend); TypeScript 5.x on Vite + React 18 (frontend); Dart / Flutter (passthrough — no changes required this feature)
**Primary Dependencies**: Backend — FastAPI, `python-jose` (already used for JWT JWKS validation), `psycopg2`, the existing `audit` module. Frontend — `react-oidc-context@^3.3.0` and its transitive `oidc-client-ts@^3.4.1` (both already installed). The `WebStorageStateStore` we need is exported from `oidc-client-ts`. **No new third-party libraries** (Constitution V).
**Storage**: PostgreSQL — **no schema changes**. The `audit_events.event_class` column has no CHECK constraint (Python-side `EVENT_CLASSES` tuple is the only validator), and we are not adding a class anyway, only three new dotted `action_type` values. Client-side credential persistence: browser `localStorage` (same physical mechanism on web and inside the Flutter WebView).
**Testing**: Backend — `pytest`. Frontend — `vitest` + `@testing-library/react` (already used by features 003/006/007). Add fakeable storage and `react-oidc-context` mocks to assert silent-resume and 365-day-cap behavior.
**Target Platform**: Evergreen browsers (Chrome / Firefox / Safari / Edge); iOS 15+ (WKWebView via `webview_flutter`); Android 9+ (Android WebView via `webview_flutter`).
**Project Type**: Web application (Python backend + React frontend) consumed by a Flutter WebView wrapper.
**Performance Goals**: SC-001 — dashboard within 2 s of cold launch on a returning user. SC-004 — silent-resume launch ≤ fresh-login cold-start + 500 ms median.
**Constraints**: Constitution V (no new third-party libs without lead approval), Constitution IX (auto migrations — N/A here; no schema change), Constitution X (production readiness — golden + edge cases tested; no stubs).
**Scale/Scope**: Five files changed in the frontend, two files changed in the backend, one Keycloak realm setting tuned, zero Flutter changes. Estimated total LOC delta: ~250 frontend, ~50 backend, ~150 test code, plus this plan's docs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I — Primary Language (Python backend) | PASS | Backend changes are Python only. |
| II — Frontend Framework (Vite + React + TS) | PASS | Frontend changes are `.ts`/`.tsx`. |
| III — Testing Standards (≥ 90 % coverage) | PASS | Plan includes unit + integration tests for the new auth-persistence module and the new audit `action_type` recording sites. Existing 90 % gate applies to changed code. |
| IV — Code Quality (ruff / ESLint) | PASS | Existing tooling applies; no exemptions requested. |
| V — Dependency Management (no new deps w/o lead approval) | PASS | No new packages added. `WebStorageStateStore` is in `oidc-client-ts` which is already transitively installed (declared as a sibling of `react-oidc-context` in `frontend/package.json`). |
| VI — Documentation (docstrings / JSDoc) | PASS | New exported helpers get JSDoc; new Python helper gets a Google-style docstring. |
| VII — Security (Keycloak IAM, no alt auth providers) | PASS | Login flow unchanged — still Keycloak OIDC with PKCE via `react-oidc-context`. We are switching *only* the token *store*, not the provider. No new auth method, no alternative IdP, no token-handling logic moved server-side. |
| VIII — User Experience (predefined primitives) | PASS | No new UI primitives. FR-012 was explicitly resolved as "no new chrome UI". |
| IX — Database Migrations | PASS — N/A | No schema changes. Adding new `action_type` values requires no DDL because `event_class` is the only validated column and we are not modifying it. |
| X — Production Readiness | PASS | Plan covers golden path + edge cases (offline, revoked, expired, hard-max, storage-write-failure, user-switch). No stubs, no debug-only code. Observability satisfied by the three new `action_type` recordings. |

**Initial gate result**: PASS. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/016-persistent-login/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── oidc-storage.md      # contract: localStorage layout + key naming
│   ├── audit-actions.md     # contract: three new auth.* action_type values
│   └── ws-register-flag.md  # contract: register_ui message gains resumed:boolean
├── checklists/
│   └── requirements.md  # Existing — produced by /speckit-specify
└── tasks.md             # /speckit-tasks output (not produced by this command)
```

### Source Code (repository root)

```text
backend/
├── audit/
│   └── schemas.py           # MODIFY: no changes — auth.* actions live under existing "auth" class
├── orchestrator/
│   ├── orchestrator.py      # MODIFY: on ws register, record auth.session_resumed OR auth.login_interactive based on register_ui.resumed flag
│   └── ws_handlers (inline) # MODIFY: parse `resumed: bool` from RegisterUI
└── shared/
    └── protocol.py          # MODIFY: extend RegisterUI dataclass with optional `resumed: bool = False`

frontend/
└── src/
    ├── main.tsx             # MODIFY: wire userStore = WebStorageStateStore({ store: localStorage }) into oidcConfig
    ├── auth/                # NEW directory
    │   ├── persistentLogin.ts        # NEW: 365-day hard-cap enforcement + user-switch revocation + register_ui.resumed flag emission
    │   ├── revocationQueue.ts        # NEW: offline-tolerant best-effort signout/revoke retry queue (sessionStorage-backed)
    │   └── __tests__/
    │       ├── persistentLogin.test.tsx
    │       └── revocationQueue.test.tsx
    ├── App.tsx              # MODIFY: call persistentLogin.checkHardMaxOrSignOut() in the auth gate before mounting <Shell>; record initial_login_at on fresh interactive logins; wire register_ui.resumed in useWebSocket call site
    └── hooks/
        └── useWebSocket.ts  # MODIFY: include `resumed: boolean` in the register_ui payload from persistentLogin state

flutter-passthrough/        # NO CHANGES this feature
└── lib/
    ├── main.dart            # unchanged
    └── webview_screen.dart  # unchanged — WebView already persists localStorage by default

# Keycloak (operator config, not code)
# - SSO Session Idle: ≥ 365 days (or use offline_access — already in scope)
# - Offline Session Idle: ≥ 365 days
# - Offline Session Max: ≥ 365 days (or 0 = unlimited; the client enforces 365)
# - Client Access Token Lifespan: 5–15 min (unchanged from current, drives FR-004 propagation cadence)
```

**Structure Decision**: Web application (backend + frontend); reuse existing modules. The only new top-level directory is `frontend/src/auth/` for the small persistence helper. Flutter is untouched. The feature is intentionally *thin* — most of the heavy lifting is delegated to `oidc-client-ts`'s built-in `WebStorageStateStore` + `automaticSilentRenew`, which AstralBody already uses in `sessionStorage` mode today.

## Complexity Tracking

No constitution violations. Table omitted.

---

## Phase 0 — Outline & Research

See **[research.md](research.md)** for the consolidated findings. Highlights:

1. **`react-oidc-context` storage swap mechanics**: confirmed that providing `userStore: new WebStorageStateStore({ store: window.localStorage })` in `oidcConfig` is the documented one-line change to persist tokens across browser sessions. `automaticSilentRenew: true` (already set) continues to work because the renewer reads its current state from whatever store is configured.

2. **`webview_flutter` localStorage persistence**: verified by reading the [`webview_flutter` plugin documentation](https://pub.dev/packages/webview_flutter) plus the iOS/Android implementation classes (`WKWebView` default `WKWebsiteDataStore.default()`; Android `WebView` with `setDomStorageEnabled(true)` which is the package default). Cookies + localStorage persist across cold launches as long as the OS retains app data. The current `webview_screen.dart` does not clear storage, so no Dart change is required.

3. **Keycloak offline-session timing**: the `offline_access` scope is already requested in `main.tsx`. The realm's *Offline Session Idle* and *Offline Session Max* settings cap how long an offline refresh token remains valid server-side. The plan sets both ≥ 365 days; combined with the client-side hard-max check (FR-013), the *operative* lifetime is exactly 365 days from the most recent interactive login.

4. **`oidc-client-ts` clock-skew default**: `clockSkewInSeconds: 300` (5 minutes) — matches FR-010 exactly without any code change.

5. **Offline-tolerant revocation queue**: `oidc-client-ts` does not retry `revokeTokens()` or `signoutRedirect()` on network failure. We implement a small `revocationQueue` module that pushes pending revoke calls into `sessionStorage` (NOT localStorage — we don't want the queue to outlive the tab if it never gets flushed) and drains on the next online opportunity. ~50 LOC.

6. **Distinguishing interactive vs silent at audit time**: the cleanest signal is whether the OIDC `onSigninCallback` ran on this page load. If yes → interactive. If `auth.isAuthenticated` becomes true *without* the callback firing → silent resume. We surface this as a boolean `resumed` field on the `register_ui` WS message, and the orchestrator records the matching `action_type`.

All Phase-0 NEEDS-CLARIFICATION items are resolved before Phase 1.

## Phase 1 — Design & Contracts

### Data model

See **[data-model.md](data-model.md)**. Key changes:

- **Stored Credential** entity gains a concrete shape in browser `localStorage` under two namespaces:
  - The `oidc-client-ts` user record at key `oidc.user:<authority>:<client_id>` (created and managed by the OIDC library; we do not write to it directly).
  - A small AstralBody-owned record at key `astralbody.persistentLogin.v1` holding `{ initial_login_at: ISO8601, last_user_sub: string, deployment_origin: string }`. This is the **365-day clock anchor** (FR-013) and the **user-switch detection key** (FR-008).
- No database schema change. No new table. No new column.

### Contracts

See **[contracts/](contracts/)**:

- **[oidc-storage.md](contracts/oidc-storage.md)** — exact localStorage keys we create/read, payload shapes, versioning rule (the trailing `.v1` allows future-incompatible changes without corrupting old installs — FR-008's "force a single re-login on migration" handles it).
- **[audit-actions.md](contracts/audit-actions.md)** — the three new `action_type` values (`auth.login_interactive`, `auth.session_resumed`, `auth.session_resume_failed`) recorded under the existing `event_class="auth"` bucket; example payloads.
- **[ws-register-flag.md](contracts/ws-register-flag.md)** — the new optional `resumed: boolean` field on the WS `register_ui` message; default `false` so existing clients are unaffected.

### Quickstart

See **[quickstart.md](quickstart.md)** for the smallest end-to-end smoke test: sign in, close browser, reopen, verify dashboard renders without login.

### Agent context update

The `<!-- SPECKIT START -->` block in `CLAUDE.md` is updated to add `specs/016-persistent-login/plan.md` to the plan list (handled at the end of this command).

## Re-evaluation: Constitution Check (post-Phase-1)

All gates remain PASS. The Phase-1 design does not introduce new dependencies, primitives, or schema; it adds one small frontend helper module (`frontend/src/auth/`) and surface-level edits to four existing files. Observability obligations (Principle X) are satisfied by the three new `auth.*` recordings.

**Final gate result**: PASS. Ready for `/speckit-tasks`.
