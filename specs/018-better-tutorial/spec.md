# Spec: Better Tutorial (US-17)

**Branch:** `017-better-tutorial`
**Parent:** US-17 | "As a user, I want a better tutorial that won't make me want to skip it as soon as I see it."
**Status:** In Progress

---

## Research Analysis

The assigned article *"Why Most Product Tours Get Skipped (and the One Pattern That Does Not)"* provides these key findings:

### The Problem
- **60-80% of users** dismiss product tours within 2-5 seconds of seeing the first step
- Why? Tours block users from **immediately testing whether the product meets their needs**
- Users come to "do the thing," not to read about how to do the thing

### Why Teams Build Bad Tours
1. **Perceived completeness** — "we shipped a tour" checkbox
2. **Demo appeal** — looks good in a demo but isn't useful
3. **Unmeasured metrics** — nobody tracks whether tours improve activation

### The Pattern That Works
- **Interactive walkthroughs that require actions** (not passive reading) perform best
- **Contextual tooltips** on first interaction (not a linear "next, next, next" tour)
- **Progressive disclosure** — don't explain everything upfront; reveal features as they become relevant
- **Immediate value** — the first step must show the user what they came for

---

## Current State Analysis

The existing tutorial system (`specs/005-tooltips-tutorial`) has:

### Strengths
- Full admin-editable tour with spotlights, step cards, and ARIA
- Backend persistence for user state (not_started/in_progress/completed/skipped)
- Resume-on-reload and replay functionality
- Works for both user and admin audiences

### Weaknesses (per US-17 objectives)
1. **Auto-launches aggressively** — any first-time sign-in gets the tour forced on them (no "not now" option)
2. **7 passive steps** — all steps are just text to read; none require user action (except "skip")
3. **Wall of text** — each step is a paragraph when it could be 1-2 lines
4. **No progress indicator on step 0** — users don't know it's a 7-step tour until they see "Step 1 of 7" on the first card

---

## Proposed Changes

### 1. "Not Now" Dismissal (High Impact)
Give users an escape hatch from the first step that isn't a hard "skip." Currently the only options are "Skip tour" (which permanently sets status=skipped) or powering through. We'll add:

- A prominent "Not now" button alongside "Start tour"
- "Not now" sets a 24-hour cooldown after which the tour prompts again
- Only after 2 "not now" dismissals does status permanently become "skipped"

### 2. Interactive Checkpoints (Medium Impact)
At least **half** of the tour steps should require the user to perform the action being described:

- **Step 2 (Chat):** User must type a word in the input field → check mark appears → can advance
- **Step 3 (Agents):** User must click the agents button to open the panel → auto-advances  
- **Step 4 (Enable agent):** User must toggle an agent on → auto-advances
- **Step 5 (Audit):** User must open the audit panel → auto-advances

Non-interactive steps (welcome, give-feedback, finish) remain read-only but are now shorter.

### 3. Rewritten Copy (Low Impact)
All step bodies cut to ≤2 short sentences. Titles stay the same for admin editing compatibility.

### 4. Visual Progress Bar (Low Impact)
Add a thin progress bar at the bottom of the step card showing `stepNumber / totalSteps`.

---

## Constitution Compliance

| Principle | Status |
|-----------|--------|
| I (HITECH/PHI) | ✅ No PHI data involved |
| II (Consent) | ✅ No consent changes |
| III (Tool Safety) | ✅ No tool changes |
| IV (Concurrency) | ✅ No concurrency changes |
| V (No New Dependencies) | ✅ Zero new npm/pip packages |
| VI (PII Redaction) | ✅ Frontend-only changes; any data sent to backend for state tracking already exists |
| VII (Audit) | ✅ No audit changes needed |
| VIII (Security) | ✅ UI-only changes |
| IX (No Raw SQL) | ✅ Using existing REST API |
| X (Testing) | ✅ Will add tests for interactive checkpoint logic |

---

## Implementation Plan

1. **`frontend/src/components/onboarding/OnboardingContext.tsx`** — add `dismissTemp()` for "Not now" with cooldown
2. **`frontend/src/components/onboarding/types.ts`** — add `dismissed_at` and `dismiss_count` to OnboardingState
3. **`frontend/src/components/onboarding/TutorialStep.tsx`** — add progress bar, "Not now" button on welcome step
4. **`frontend/src/components/onboarding/InteractiveCheckpoint.tsx`** (new) — component that wraps a step and detects user action
5. **`frontend/src/components/onboarding/TutorialOverlay.tsx`** — wire interactive checkpoints
6. **`backend/seeds/tutorial_steps_seed.sql`** — update step copy (idempotent, admin edits preserved)
7. **`backend/onboarding/schemas.py`** — optionally add dismissed_at/dismiss_count fields
8. **Tests** — update `OnboardingContext.test.tsx` and add interactive checkpoint tests

---

## Success Criteria

- [ ] Users can dismiss the tour with "Not now" (not forced skip)
- [ ] At least 3 of 7 steps are interactive (require user action)
- [ ] All step copy is ≤2 sentences
- [ ] Progress bar visible on every step
- [ ] Existing admin editing, replay, and tooltip systems still work
- [ ] Zero new npm/pip dependencies
- [ ] All existing tests pass