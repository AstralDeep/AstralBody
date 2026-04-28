# Research: Tool Tips and Getting Started Tutorial

**Feature**: 005-tooltips-tutorial
**Date**: 2026-04-28
**Phase**: 0

## Scope

The spec was clarified in five questions on 2026-04-28; no `[NEEDS CLARIFICATION]` markers remain. Phase 0 research focuses on the architectural decisions those answers imply, plus a small number of implementation patterns where there is more than one reasonable path and the choice affects later design.

---

## Decision 1 — Tooltip authoring split (static UI vs. SDUI)

**Decision**: Frontend owns tooltip copy for static UI surfaces (sidebar, panels, modals) via a typed catalog (`frontend/src/components/onboarding/tooltipCatalog.ts`). Backend owns tooltip copy for server-driven (SDUI) components via a new optional `tooltip: Optional[str] = None` field on the base `Component` dataclass in `backend/shared/primitives.py`. The frontend `Tooltip` wrapper accepts text from either source.

**Rationale**: Matches the answer to Q1 and the existing project pattern. Static dashboard chrome rarely changes and benefits from typed, ESLint-checked catalog entries; SDUI components are authored per-payload by agents and orchestrator code, and per-payload copy is the only way for new agents to ship help text without a frontend release. Adding a single optional field on the base `Component` is additive and preserves backward compatibility with every existing consumer that does not yet emit a tooltip.

**Alternatives considered**:
- *Backend-only ownership*: Centralizes copy but forces every static-UI tooltip through the backend, adding latency and a deploy dependency for trivial sidebar tooltips.
- *Frontend-only ownership keyed by component type*: Cannot express per-instance variation that SDUI agents need, and forces a frontend update for every new component type.

---

## Decision 2 — Onboarding-state storage location

**Decision**: PostgreSQL, one row per user in a new `onboarding_state` table. Read on dashboard mount via a single REST GET; written via REST PUT after each step transition. No browser-local cache for v1.

**Rationale**: Q2 answer = backend-only. Matches feature 003's per-user-row pattern, gives consistent behavior across devices/browsers, and a single-row primary-key lookup is well under the 50 ms target. Keeping browser cache out of v1 avoids stale-state bugs when users sign in from a second device mid-tour.

**Alternatives considered**:
- *Browser local storage*: Per-device, lost on browser clear, contradicts the clarification answer.
- *Write-through cache (backend + browser)*: Adds invalidation complexity for negligible latency benefit; deferred until needed.

---

## Decision 3 — Tutorial step storage + admin editability

**Decision**: Two tables — `tutorial_step` (canonical content, current state) and `tutorial_step_revision` (append-only history of every edit, enough to satisfy FR-017's traceability requirement without rebuilding feature 003's hash chain). Steps are ordered by an integer `display_order` column. An `audience` column with values `user` or `admin` controls whether non-admin users see a given step. Soft-delete via `archived_at` rather than physical DELETE so revision history remains intact and FR-009 (skip steps with unavailable targets) does not race with deletes.

**Rationale**: Q4 answer = build a backend-stored, admin-editable surface. Splitting current vs. revision tables keeps the user-facing read path a single indexed query while still giving admins/support a full edit log. Soft-delete + revision history makes "who edited what when" answerable without reading the broader audit log.

**Alternatives considered**:
- *Single `tutorial_step` table with a JSON `history` column*: Smaller schema but harder to query and risks unbounded row growth.
- *Reuse the audit log as the only history*: The audit log records edits via FR-017 anyway, but it is a one-way append per the AU-9 hash chain — pulling structured "old vs. new" diffs out of it for the admin UI is awkward.

---

## Decision 4 — Admin role source

**Decision**: Reuse the existing Keycloak admin role check that gates the FeedbackAdminPanel today. New admin endpoints depend on a shared FastAPI dependency (e.g., `require_admin`) that pulls roles from the validated JWT. No new role taxonomy is introduced.

**Rationale**: Constitution Principle VII mandates Keycloak roles. Reusing the existing admin check keeps the security surface uniform with feature 004. In dev mode the existing mock auth user already has admin role for parity.

**Alternatives considered**:
- *Introduce a "tutorial_editor" role*: Finer-grained, but no current organizational need; defer until product asks for it.

---

## Decision 5 — Audit-log integration shape

**Decision**: Add four new `event_class` values to the existing audit recorder: `onboarding_started`, `onboarding_completed`, `onboarding_skipped`, `onboarding_replayed`. Plus one for admin edits: `tutorial_step_edited`. All events use the existing per-user hash-chain so no new audit infrastructure is created. Onboarding events carry the user's onboarding-state row id and current step id; edit events carry `step_id`, `revision_id`, and a structured diff summary (changed fields, not full bodies — full bodies live in `tutorial_step_revision`).

**Rationale**: FR-012 and FR-017 both require audit trails; feature 003 already provides exactly that. Recording structured diff *summaries* in the audit log (not full payloads) keeps audit rows small while preserving traceability — the canonical "what changed" lives in `tutorial_step_revision`.

**Alternatives considered**:
- *Stuff full step bodies into the audit row*: Bloats audit storage; revision table is the right home for full content.
- *Skip the audit hookup*: Violates FR-012 / FR-017 directly.

---

## Decision 6 — Accessibility & touch-device approach

**Decision**: Use semantic HTML and ARIA from the start — `role="dialog"` and `aria-labelledby`/`aria-describedby` on the tutorial overlay, focus-trap inside the overlay, ESC and visible "Skip" / "Close" controls; tooltip wrapper renders an `aria-describedby` link from target → tooltip body and is reachable via `:focus-visible`. On touch devices (detected via the existing ROTE device-capabilities pipeline already in `useWebSocket.ts`), tooltips switch from hover to long-press and the `Tooltip` wrapper exposes a small tappable info icon as a fallback affordance. No new third-party a11y library — built directly with ARIA + native focus management.

**Rationale**: FR-010 / FR-011 / SC-007 are explicit. Reusing the existing ROTE device-capability detection avoids a redundant feature-detection layer. Hand-rolled focus trap is small (~30 lines) and skipping a library keeps Constitution Principle V satisfied.

**Alternatives considered**:
- *react-joyride / shepherd.js*: Both add a dependency and inflate bundle size; both require Constitution Principle V (lead-developer approval). Defer until empirical reason to adopt.
- *react-tooltip*: Same dependency concern; trivial to roll our own with ARIA.

---

## Decision 7 — Resume-on-reload semantics (FR-013)

**Decision**: Onboarding state stores `last_step_id` (FK into `tutorial_step.id`). On dashboard mount, the frontend fetches both the user's onboarding state and the user-applicable step list; if state is `in_progress` it auto-resumes at the first step whose `display_order` is ≥ the recorded step. If `last_step_id` no longer resolves (because the step was archived since the user paused), it falls back to the next step in order.

**Rationale**: FR-013 requires reload to resume rather than restart. Anchoring on step id (not array index) means admin re-ordering or archival of steps does not corrupt resume.

**Alternatives considered**:
- *Store last-completed array index*: Breaks if admins reorder or archive steps.

---

## Decision 8 — Replay does not reset onboarding state to `not_started`

**Decision**: When the user activates the replay affordance, the frontend launches the overlay at step 1 *without* mutating the user's onboarding state row. A `tutorial_replayed` audit event is recorded (FR-012) but the row's `status` stays at whatever it was (`completed` or `skipped`). This way replay does not re-trigger auto-launch on next sign-in (User Story 3 AC 2).

**Rationale**: FR-005 says replay must work "regardless of their onboarding state"; SC-006 requires duplicate auto-launches to be 0%. Treating replay as a transient action — not a state mutation — satisfies both.

**Alternatives considered**:
- *Reset state to `in_progress` on replay*: Would violate SC-006 unless we re-mark `completed` again on close, which is needless write churn.

---

## Decision 9 — Tutorial step copy update propagation (FR-016)

**Decision**: No client-side cache of step copy beyond the React component tree. The frontend fetches `/api/tutorial/steps` on each tutorial launch (auto or replay), so admin edits become visible to subsequent launches without redeploy. SDUI-component tooltips are read from the live payload and likewise pick up backend changes immediately.

**Rationale**: FR-016 explicitly forbids redeploy-gated updates. The step list is small (~10–20 rows); a fresh fetch per launch costs almost nothing and avoids a stale-cache class of bug.

**Alternatives considered**:
- *Cache step list in localStorage*: Saves one small request per session; not worth the staleness risk for the admin-editable surface.

---

## Decision 10 — Mounting the TutorialOverlay

**Decision**: Mount `TutorialOverlay` once at the root of `DashboardLayout`. It listens to `OnboardingContext` for activation; otherwise it renders `null`. The "Take the tour" affordance is a sidebar button (under the existing "Audit log" / "Agents" sidebar) that dispatches a `replay()` action through the context. Admin users see one extra sidebar entry for the `TutorialAdminPanel` (parallel to `FeedbackAdminPanel`). For tooltip wrapping: extend `DynamicRenderer.tsx` so any rendered SDUI component with a non-empty `tooltip` field is wrapped in a `<Tooltip text={…}>`. Static-UI elements opt in by importing `tooltipCatalog` directly.

**Rationale**: Matches existing `DashboardLayout` overlay/modal pattern from features 003 and 004 (AuditLogPanel, FeedbackAdminPanel). Single-mount avoids multiple overlay z-index conflicts. Extending `DynamicRenderer` is the natural single chokepoint for SDUI tooltips.

**Alternatives considered**:
- *Per-page TutorialOverlay mounts*: Causes duplicate state and complicates resume.
- *Backend-pushed tutorial activation message via WebSocket*: Unnecessary; client knows when to start based on its own state.
