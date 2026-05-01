# Phase 0 Research — Fix Page Flash

**Feature**: 010-fix-page-flash
**Date**: 2026-05-01

This document resolves the open technical questions implied by the spec and Technical Context. Each entry follows: Decision / Rationale / Alternatives considered.

---

## R1. Dedup strategy for "once per session per endpoint"

**Decision**: Remove automatic polling from globally mounted regions entirely. Replace with **lazy fetch on view-open**: the consuming UI surface (e.g., the open SettingsMenu, the FeedbackAdminPanel route) triggers the fetch when it becomes visible. A small per-endpoint session cache (a module-scoped `Map<endpointKey, Promise<T>>` keyed by URL + sanitized query) coalesces duplicate concurrent calls and serves a previously fetched response within the same session unless the caller passes an explicit `refresh: true` flag.

**Rationale**:
- Matches the user's clarification answer literally: "Once per session per endpoint; refreshed only on explicit user action or view open."
- Eliminates the root cause of the flash (token-keyed effect re-creation can no longer trigger an immediate fetch on silent token refresh, because there is no effect mounted in the global region anymore).
- Keeps the badge-count UX: when the admin opens the settings menu, the count is fetched once for the session; subsequent opens reuse the cached value; opening the FeedbackAdminPanel itself (an explicit action) refreshes.
- Module-scoped cache is the simplest implementation that satisfies the contract without introducing a new library.

**Alternatives considered**:
- *Keep the 60 s polling but harden the dependency array.* The current working-tree fix does this. It reduces flash frequency but does not satisfy "once per session per endpoint" — every 60 s a new request still fires from a globally mounted region, in violation of FR-008/FR-009. Rejected.
- *Adopt TanStack Query.* Solves dedup, caching, and stale-while-revalidate elegantly, but introduces a new dependency that requires lead-developer approval (Constitution V) and meaningfully widens the change set. Rejected for this scope; can be revisited later if more endpoints need this behavior.
- *Move the fetch into a context provider that is lazy-mounted.* Adds indirection without solving the audit problem (the provider would itself be globally mounted). Rejected.

---

## R2. Identifying globally mounted regions for the audit

**Decision**: Define the audit set programmatically as the set of components rendered above (i.e., as ancestors of) the route boundary in the React tree. In this codebase, that boundary is whatever component conditionally renders by route in `App.tsx` / `main.tsx` (likely a `<Router>` / `<Routes>` block or a single-page conditional). Everything mounted **outside** that boundary that does not unmount when the active view changes is in scope. The audit checklist (see [contracts/audit-checklist.md](./contracts/audit-checklist.md)) lists the concrete components for this codebase.

**Rationale**:
- Aligns with the spec clarification ("rendered on every authenticated route regardless of which view the user is on").
- Concrete: an auditor can grep `useEffect` calls in those files for `fetch(`, `axios`, or any of the existing API helpers (`listFlaggedTools`, `loadAgents`, `getMessages`, etc.) and treat each hit as a candidate.
- Excludes route-scoped panels like `FeedbackAdminPanel` (mounts only when the admin opens that route), preventing scope creep.

**Alternatives considered**:
- *Audit every component in `frontend/src/components/`.* Way too broad — most of the codebase is route- or surface-scoped. Rejected.
- *Use React DevTools to inspect the live tree during runtime.* Useful for spot-checking but not reproducible in CI or PR review. Used as a supplementary technique, not the primary audit method.

---

## R3. Animation reconciliation — distinguishing "present at first paint" from "added after first paint"

**Decision**: Each animating list region holds two refs:

- `mountedRef: useRef(false)` — flipped to `true` inside a mount-only `useEffect(() => { ... }, [])`.
- `initialIdsRef: useRef(new Set<string>())` (or `initialMsgCountRef: useRef(0)` for ordered streams without IDs) — captured inside the same mount-only effect from the props at first render.

For each `<motion.*>` element, the `initial` prop becomes a conditional:

```tsx
initial={initialIdsRef.current.has(id) ? false : { opacity: 0, y: 20, scale: 0.95 }}
```

Components present at first paint render with `initial={false}`, which framer-motion treats as "no entry animation — start at the animate state." Components added later still get the soft fade-in.

**Rationale**:
- This is the standard, documented framer-motion idiom for the "skip enter on first mount, animate later" pattern. No new dependency; uses primitives already in the project.
- Satisfies FR-006 literally: existing components do not remount, re-key, or flash; only newly arriving components animate.
- Matches the working-tree fixes already drafted in `SDUICanvas.tsx` and `FloatingChatPanel.tsx` — research confirms those drafts are on the correct path; remaining task is verifying they cover all `<motion.*>` usages in those files and adding tests.

**Alternatives considered**:
- *Use `<AnimatePresence initial={false}>`* — affects exit animations and only suppresses the **first** child's enter; doesn't solve the case where many children all re-mount on first paint. Rejected.
- *Disable all entry animations.* Simple but regresses the polished feel of new arrivals. Rejected — user complaint is about flashes, not animations themselves.

---

## R4. Theme/FOUC during initial paint

**Decision**: Keep the synchronous inline `<script>` already drafted in `frontend/index.html` that reads `localStorage['astral-theme']` and applies the CSS variables before React boots. Set a non-white default body background (`#0F1221`) inline so the very first paint is dark even when no saved theme exists.

**Rationale**:
- Eliminates the white-flash that occurs between HTML parse and the first React render applying the theme — the most user-visible part of the "page load flash."
- Pure HTML/inline JS, no React lifecycle dependency, runs before any module load.
- Wrapped in `try/catch` so a corrupt `localStorage` entry cannot break the boot.

**Alternatives considered**:
- *Move theme application into a top-level `useLayoutEffect`.* Still runs after React mount, so a brief unstyled paint can still occur. Rejected.
- *Server-render theme variables.* Vite + React in this project is client-only; adding SSR for one cosmetic concern is disproportionate. Rejected.

---

## R5. Test strategy for "no flash"

**Decision**: A combination of three test layers:

1. **Unit (Vitest + RTL)** — for `useFlaggedToolsCount`: assert that token identity changes do not re-trigger fetch and that same-value responses do not cause `setCount`.
2. **Component (Vitest + RTL with `framer-motion` test mode)** — for `SDUICanvas` and `FloatingChatPanel`: render with N initial items, assert `initial={false}` is passed to those `<motion.*>` elements; render again after a streamed addition, assert the new element receives the fade-in `initial` object.
3. **Manual smoke (browser, see [quickstart.md](./quickstart.md))** — exercise the three primary scenarios in a real browser; record DevTools Network panel and assert ≤ 1 request per in-scope endpoint per session and zero visible flashes.

**Rationale**:
- "Flash" is fundamentally a perceptual property — fully automating it requires a visual-regression harness the project does not currently have. The unit + component tests pin the structural conditions that cause flashes; the manual smoke verifies the user-visible outcome.
- Aligns with Constitution X (real-browser validation required) and Constitution III (90 % coverage on changed code is achievable via the unit + component layers).

**Alternatives considered**:
- *Add Playwright + a visual-regression service.* Worth doing eventually, but exceeds this feature's scope and introduces new tooling/dependencies. Out of scope for now.

---

## Open items

None. All NEEDS CLARIFICATION items were resolved during `/speckit.clarify`. No new ones surfaced in research.
