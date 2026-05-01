# Audit Checklist — Globally Mounted Regions (Frontend)

**Feature**: 010-fix-page-flash
**Date**: 2026-05-01
**Type**: Pattern-based audit contract (not an API contract)

This is the contract the implementer is held to for FR-009, FR-012, and FR-013. The deliverable for this contract is a completed checklist (this file, with each item resolved) committed alongside the code change.

## Definition

A **globally mounted region** is a component that renders on every authenticated route regardless of the active view. Concretely, in this codebase, that means any component:

- mounted as an ancestor of the active-view conditional in `frontend/src/App.tsx` / `frontend/src/main.tsx`, **or**
- mounted as part of the persistent layout shell that does not unmount when the user switches between dashboard, history, settings, or other in-app views.

Route-scoped panels (e.g., `FeedbackAdminPanel`) are **out of scope** even if they currently issue background fetches, because they only mount when the user opens that route.

## Audit requirements

For each component in the audit set below, the auditor MUST:

1. Open the file and read every `useEffect` / `useLayoutEffect` / module-top-level statement.
2. Identify any call that issues a network fetch — direct `fetch(...)`, `axios.*`, or any project API helper (e.g., `listFlaggedTools`, `loadAgents`, `fetchHistory`, etc.).
3. Decide which category each fetch falls into:
   - **(a) Already conformant** — fires only on explicit user action, view-open, or via the new `BackgroundFetchCache.getOrFetch` helper with no `refresh: true`. ✅
   - **(b) Non-conformant** — fires on render, on token-identity change, on a polling interval, or on every route change. ❌ Must be remediated.
   - **(c) Excluded** — server-driven UI (SDUI) component streams pushed from the backend (FR-011) and explicit user-initiated mutations. Document the exclusion.
4. For each ❌, apply the chosen remediation pattern (see below) and record the resolution.

## Remediation patterns

- **R-A: Move to consuming view.** Delete the fetch from the global region; let the view that consumes the data fetch when it mounts (e.g., move flagged-tools count fetch out of `DashboardLayout` and into the `SettingsMenu` open handler or the `FeedbackAdminPanel` mount).
- **R-B: Wrap in `BackgroundFetchCache.getOrFetch`.** When a fetch genuinely belongs in the layout (e.g., user profile shown in the header), wrap it in the session-cache helper so it fires once per session and is reused on remount.
- **R-C: Refactor to ref-stable dependency.** When the fetch is correctly placed but its `useEffect` dependency array contains an identity-unstable value (token, options object), refactor to refs so the effect runs once per logical lifecycle, not per silent refresh.

## Audit set (this codebase)

> Auditor: tick each box only after applying the audit requirements above. If a component is not in the actual rendered tree above the route boundary, mark it "Out of scope" and note why.

### Layout shell

- [x] `frontend/src/App.tsx` — top-level routing/layout. Reviewed every `useEffect`. The only network-touching effect is the WebSocket lifecycle inside `useWebSocket(WS_URL, auth.user?.access_token)`, which is the SDUI / chat transport (FR-011 exclusion). No on-render HTTP fetches. ✅ Conformant.
- [x] `frontend/src/main.tsx` — provider tree. No HTTP fetches on render; just providers and the React root. ✅ Conformant.
- [x] `frontend/src/components/DashboardLayout.tsx` — main shell with sidebar, header. Previously fired `useFlaggedToolsCount` with a `setInterval` polling the admin flagged-tools endpoint every 60s, with the access token on its `useEffect` deps; silent OIDC refresh re-fired the effect and produced rapid-fire calls + visible flashes. **Remediated (R-A + R-B).** Hook extracted to its own module ([useFlaggedToolsCount.ts](../../../frontend/src/components/useFlaggedToolsCount.ts)), polling removed entirely, fetch routed through `backgroundFetchCache` (key `admin-feedback-flagged?limit=100`), token held in a ref written from a deps-`[token]` effect (not during render). The badge picks up fresh data via an explicit refresh call when admin opens the FeedbackAdminPanel. ✅ Conformant.
- [x] `frontend/src/components/settings/SettingsMenu.tsx` — persistent menu trigger. Pure UI, no fetches. ✅ Conformant.

### App-level providers (audit each that wraps the route boundary)

- [x] **ThemeContext / ThemeProvider** ([ThemeContext.tsx](../../../frontend/src/contexts/ThemeContext.tsx)) — pure localStorage reads + a CustomEvent listener for server-pushed preferences. No network fetch. ✅ Conformant.
- [x] **OnboardingProvider** ([OnboardingContext.tsx](../../../frontend/src/components/onboarding/OnboardingContext.tsx)) — globally mounted around the entire authenticated shell. **Found non-conformant.** `useOnboardingState` and `OnboardingContext` BOTH had token-keyed `useEffect`s that called `refresh()` on every silent OIDC token refresh. Each refresh ran `setLoading(true)` → `setState(body)` → `setLoading(false)`, propagated via React Context, and re-rendered the entire app subtree. **Remediated (R-C + R-B).** Token now held in a ref. Initial-load gated by `firstLoadDoneRef` so the fetch fires exactly once on the first non-empty token observed. Both the GET and the explicit-refresh paths route through `backgroundFetchCache` (key `onboarding-state`); `update()` invalidates the cache so subsequent reads see fresh state. The duplicate effect in `OnboardingContext` was deleted entirely. ✅ Conformant after fix.
- [x] **TooltipProvider** — pure context; no fetches. ✅ Conformant.
- [x] **FeedbackProvider** ([FeedbackContext.tsx](../../../frontend/src/components/feedback/FeedbackContext.tsx)) — pure context (token, ws, isAdmin); no fetches. ✅ Conformant.
- [x] **AgentPermissionProvider** — context-only; consumers fetch on user action (modal open). Out of scope (route-scoped consumption) but verified no on-render fetches. ✅ Conformant.
- [x] **OIDC `useSmartAuth`** — token refresh is intentional and excluded; the audit confirms no application-data fetches piggyback on token-identity changes after the remediations above. ✅ Conformant.
- [x] **`useWebSocket`** — the SDUI / chat transport is FR-011 excluded; verified the hook does not issue eager HTTP fetches on socket open. ✅ Conformant (excluded).

### Header / sidebar pieces

- [x] **Sidebar agent list** — reads `agents` from the WebSocket-backed state already in the parent; no HTTP fetch. ✅ Conformant.
- [x] **Header connection-status indicator** — consumes `isConnected` from WebSocket state; passive. ✅ Conformant.
- [x] **`<Toaster>` (sonner)** — passive UI. ✅ Conformant.

### Route-scoped panels (out of audit scope)

For completeness — these mount only on user action (panel-open) and are therefore **out of audit scope** per the spec's "globally mounted region" definition:

- `AuditLogPanel` — opens via menu / `?audit=open`.
- `LlmSettingsPanel` — opens via menu / `?llm=open`.
- `FeedbackAdminPanel` — opens via menu / `?feedback=open`. (Now invokes a session-cache refresh of the flagged-tools count when opened.)
- `TutorialAdminPanel` — opens via menu / `?tutorial_admin=open`.
- `UserGuidePanel` — opens via menu / `?guide=open`.
- `TutorialOverlay` — visibility gated by `OnboardingContext.visible`.

Background fetches inside these panels (e.g., `FeedbackAdminPanel.tsx:115` calling `listFlaggedTools(token)` on mount) are conformant with the spec because they fire on view-open, which is an explicit user action (FR-008).

## Audit completion record

- **Date of audit**: 2026-05-01
- **Auditor**: Claude Opus 4.7 (1M context), under user-supervised `/speckit.implement`.
- **Components found non-conformant**:
  1. `frontend/src/components/DashboardLayout.tsx :: useFlaggedToolsCount` — 60 s `setInterval` polling AND `useEffect` keyed on the OIDC access token.
  2. `frontend/src/components/onboarding/useOnboardingState.ts` — `useEffect` keyed on `accessToken` calling `refresh()` on every silent token rotation.
  3. `frontend/src/components/onboarding/OnboardingContext.tsx` — duplicate `useEffect` keyed on `accessToken` calling the same `refreshState()` a second time.
- **Remediations applied**:
  - Extracted `useFlaggedToolsCount` into [frontend/src/components/useFlaggedToolsCount.ts](../../../frontend/src/components/useFlaggedToolsCount.ts). Removed `setInterval`. Routed the fetch through [frontend/src/lib/backgroundFetchCache.ts](../../../frontend/src/lib/backgroundFetchCache.ts) under key `admin-feedback-flagged?limit=100`. Token held in a ref written from a token-deps effect. Hook now exposes `refresh()` which `DashboardLayout` invokes when admin opens `FeedbackAdminPanel` (an explicit user action).
  - Refactored `useOnboardingState`: token in a ref, initial fetch gated by `firstLoadDoneRef`, GET routed through `backgroundFetchCache` under key `onboarding-state`; mutation path (`update`) invalidates the cache so the next read is fresh.
  - Deleted the duplicate token-keyed effect in `OnboardingContext`.
- **Components remaining non-conformant**: None.
- **Test coverage of the new contract**:
  - [frontend/src/lib/__tests__/backgroundFetchCache.test.ts](../../../frontend/src/lib/__tests__/backgroundFetchCache.test.ts) — 9 tests, all pass.
  - [frontend/src/components/__tests__/useFlaggedToolsCount.test.tsx](../../../frontend/src/components/__tests__/useFlaggedToolsCount.test.tsx) — 8 tests pin the contract: no polling, no fetch on token-identity change, no setState on unchanged value, refresh() invalidates and refetches, remount within session does NOT refetch.
  - [frontend/src/components/__tests__/SDUICanvas.flash.test.tsx](../../../frontend/src/components/__tests__/SDUICanvas.flash.test.tsx) — 5 tests pin first-paint and streaming-reconciliation behavior.
  - [frontend/src/components/__tests__/FloatingChatPanel.flash.test.tsx](../../../frontend/src/components/__tests__/FloatingChatPanel.flash.test.tsx) — 4 tests pin first-paint silence and post-mount streaming animation.
  - Pre-existing tests: `OnboardingContext.test.tsx` (7) still passes against the refactored hook.
  - Total: 146 / 146 tests pass after this feature.

## Acceptance for this contract

The audit is accepted when:

1. Every box above is ticked or marked "Out of scope" with a one-line reason.
2. The "Audit completion record" section is filled in.
3. Smoke testing per [quickstart.md](../quickstart.md) shows zero flashes and ≤ 1 request per in-scope endpoint per session in DevTools Network panel.
