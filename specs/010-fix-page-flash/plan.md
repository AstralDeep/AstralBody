# Implementation Plan: Fix Page Flash from Repeated Background Fetches & Streaming Reconciliation

**Branch**: `010-fix-page-flash` | **Date**: 2026-05-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/010-fix-page-flash/spec.md`

## Summary

Eliminate visible UI flashes during page load, historical chat loading, and new query submission. Two distinct root causes are bundled in this fix:

1. **Redundant background fetches from globally mounted regions.** The admin-only `useFlaggedToolsCount` hook in `DashboardLayout` was tearing down and recreating its 60 s polling interval on every OIDC silent-token-refresh because the effect depended on the token identity. Each recreation fired an immediate `listFlaggedTools` call and a `setCount` even when the value was unchanged, which combined with framer-motion layout animations produced visible flashes. The audit must extend this remediation pattern to every other globally mounted region (FR-009, FR-012, FR-013).
2. **Streaming-reconciliation flashes in the chat shell and SDUI canvas.** Entry animations (`initial={{ opacity: 0, ... }}`) fired for every component on first paint, including ones restored from historical chats, causing the whole canvas/chat to fade in even when nothing was new. New components arriving via the SDUI stream must animate in without already-rendered components remounting (FR-006).

Technical approach: (a) replace token-keyed effect dependencies with ref-stable closures and gate all background fetches behind their consuming view (lazy fetch on menu open / view mount), removing automatic polling from globally mounted regions; (b) skip entry animations for components that exist at first mount (track `mountedRef` + an `initialIdsRef` set), so only post-mount additions animate; (c) hoist saved-theme application to a synchronous inline `<script>` in `index.html` to prevent FOUC during the React boot. Several of these changes are already in the working tree and need validation, completion of the audit, and regression tests.

## Technical Context

**Language/Version**: TypeScript 5.x (frontend), Python 3.11+ (backend — no backend code change expected for this feature)
**Primary Dependencies**: Vite + React 18, framer-motion, sonner, existing `fetchJson` helper in `frontend/src/api/feedback.ts`. No new dependencies.
**Storage**: N/A — feature is pure frontend behavior; no schema changes.
**Testing**: Vitest + React Testing Library (existing `frontend/src/components/**/__tests__/*.test.tsx` pattern), pytest for any backend touchpoints (none expected).
**Target Platform**: Modern desktop browsers (Chrome, Firefox, Safari, Edge — current evergreen versions). Mobile breakpoints already exercised in DashboardLayout.
**Project Type**: Web application (existing `backend/` + `frontend/` split).
**Performance Goals**: First stable paint of dashboard ≤ 2 s on broadband (SC-005); zero animated entries for already-present components on first paint; ≤ 1 background fetch per in-scope endpoint per session under normal use (SC-002).
**Constraints**: No new third-party libraries (Constitution V); no schema changes (Constitution IX not triggered); 90 % coverage on changed code (Constitution III); changes must be production-ready and exercised in a real browser before merge (Constitution X).
**Scale/Scope**: Audit covers the small set of globally mounted regions in `frontend/src/components/` (layout shell, header, sidebar, app-level providers in `frontend/src/main.tsx` / `App.tsx`). Estimated ≤ 6 components in scope based on existing structure.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Primary Language (Python backend) | No backend changes planned. | ✅ Pass |
| II. Frontend Framework (Vite + React + TS) | All changes in `.tsx` files via existing build. | ✅ Pass |
| III. Testing Standards (≥ 90 % coverage on changed code) | Plan includes Vitest unit tests for `useFlaggedToolsCount`, `SDUICanvas` mount-set behavior, `FloatingChatPanel` initial-message animation skip; integration test for the three primary scenarios (load, history, query). | ✅ Pass — gated on tests landing |
| IV. Code Quality (PEP 8 / ESLint) | No lint exceptions; existing ESLint config applies. | ✅ Pass |
| V. Dependency Management | Zero new dependencies. | ✅ Pass |
| VI. Documentation (JSDoc on TS exports) | New/updated hooks (`useFlaggedToolsCount`) and any extracted helpers must carry JSDoc explaining the dedup contract. | ✅ Pass — gated on docs landing |
| VII. Security (Keycloak, RFC 8693) | No auth surface change. Admin-only fetch still gated by `isAdmin` and server-side authz remains the source of truth. | ✅ Pass |
| VIII. User Experience (primitives, SDUI) | Fix preserves SDUI streaming (FR-011); only the entry-animation timing changes, not the component primitives or backend → frontend SDUI contract. | ✅ Pass |
| IX. Database Migrations | No schema change. | ✅ Pass (N/A) |
| X. Production Readiness | Plan requires real-browser validation across the three scenarios; no stubs/TODOs; observability (a single dev-mode `console.warn` if a globally mounted region issues a fetch is acceptable, no production logging needed for a frontend behavior fix). | ✅ Pass — gated on browser validation |

No violations. Complexity Tracking section omitted.

### Post-Phase-1 re-check (2026-05-01)

Phase 0/1 deliverables (`research.md`, `data-model.md`, `contracts/audit-checklist.md`, `quickstart.md`) reviewed against the same gates:

- The chosen dedup strategy (R1: lazy fetch on view-open + module-scoped session cache) introduces **no new dependencies** — gate V remains green.
- The audit checklist binds the feature to Constitution X (production readiness — real-browser validation across the three scenarios is mandatory before merge) and Constitution III (unit + component tests for the changed behaviors).
- The data model contains **no persisted entities** and no schema changes — gate IX remains N/A.
- No principle has shifted from green to yellow/red between the pre-Phase-0 check and now.

Gates re-confirmed: ✅ Pass. Ready for `/speckit.tasks`.

## Project Structure

### Documentation (this feature)

```text
specs/010-fix-page-flash/
├── plan.md              # This file
├── research.md          # Phase 0 output — chosen dedup strategy, audit method, animation reconciliation approach
├── data-model.md        # Phase 1 output — minimal: in-memory entities only (no persisted data)
├── quickstart.md        # Phase 1 output — manual smoke procedure for the three scenarios
├── contracts/
│   └── audit-checklist.md  # Phase 1 output — pattern-based audit checklist for globally mounted regions
└── tasks.md             # Phase 2 output — created by /speckit.tasks
```

### Source Code (repository root)

```text
backend/                                # Untouched by this feature
└── ...

frontend/
├── index.html                          # Modified — synchronous theme bootstrap script (anti-FOUC)
└── src/
    ├── components/
    │   ├── DashboardLayout.tsx         # Modified — useFlaggedToolsCount: ref-stable token, skip same-value setState, audit any other on-render fetches in this shell
    │   ├── SDUICanvas.tsx              # Modified — mountedRef + initialIdsRef to skip entry animations for components present at first paint
    │   ├── FloatingChatPanel.tsx       # Modified — same mountedRef pattern + initialMsgCountRef for chat messages
    │   ├── settings/SettingsMenu.tsx   # Possibly modified — if we move the lazy-fetch trigger into menu open
    │   └── feedback/FeedbackAdminPanel.tsx  # Untouched — already route-scoped (out of audit scope)
    ├── api/
    │   └── feedback.ts                 # Possibly modified — if a small session-cache wrapper is added
    └── App.tsx / main.tsx              # Audit only — confirm no on-render fetches in app-level providers
```

**Structure Decision**: Existing web-application layout (`backend/` + `frontend/`). All implementation work lives under `frontend/`. No new top-level directories. Test files colocated under `frontend/src/components/**/__tests__/` per repository convention.

## Complexity Tracking

> Constitution Check passed without violations; this section is intentionally empty.
