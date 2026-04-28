# Quickstart: Tool Tips and Getting Started Tutorial

**Feature**: 005-tooltips-tutorial
**Date**: 2026-04-28
**Audience**: Developer wiring up the feature locally OR reviewer validating the end-to-end flow.

This walkthrough exercises every user-visible behavior in the spec end-to-end. It assumes the feature is implemented per [plan.md](plan.md) and [data-model.md](data-model.md).

## Prerequisites

- Repo at branch `005-tooltips-tutorial`.
- Backend dependencies already installed (this feature adds none).
- PostgreSQL running and reachable from the backend (existing setup).
- Frontend dev server able to start.

## 0. One-time setup

1. Apply schema additions: start the backend; `Database._init_db()` will create `onboarding_state`, `tutorial_step`, and `tutorial_step_revision` (idempotent).
2. Seed initial step content from `backend/seeds/tutorial_steps_seed.sql` (idempotent `INSERT … ON CONFLICT (slug) DO NOTHING`).

   ```bash
   docker exec astralbody bash -c "psql -U astralbody -f /app/backend/seeds/tutorial_steps_seed.sql"
   ```

3. Start the system:

   ```bash
   cd backend && .venv/Scripts/python.exe start.py
   ```

   Then start the frontend dev server in a second terminal.

## 1. First-run tutorial (User Story 1)

1. Sign in as a fresh user (one with no `onboarding_state` row). In dev with the mock-auth `test_user`:

   ```bash
   docker exec astralbody bash -c "psql -U astralbody -c \"DELETE FROM onboarding_state WHERE user_id='test_user';\""
   ```

2. Open the dashboard. Within 2 seconds the `TutorialOverlay` should appear, anchored to the first step's target.
3. Click **Next** through each step. Confirm the highlight moves to each new target. (Acceptance Scenario 2)
4. Refresh the browser mid-tour. The overlay should reappear on the same step or the next un-seen step. (Acceptance Scenario 5, FR-013)
5. Verify the row was created:

   ```bash
   docker exec astralbody bash -c "psql -U astralbody -c \"SELECT user_id, status, last_step_id FROM onboarding_state WHERE user_id='test_user';\""
   ```

   `status` should be `in_progress`.

6. Click **Next** on the final step. Confirm the overlay closes and the row's `status` flips to `completed` with `completed_at` populated.
7. Sign out and sign back in. The tutorial does **not** auto-launch. (Acceptance Scenario 4, SC-006)

## 2. Skip mid-tour

1. Reset state, sign in fresh.
2. On any step click **Skip tour** (or press `Escape`).
3. Confirm the overlay closes, the row's `status` is `skipped`, `skipped_at` is set, and the next sign-in does not auto-launch. (Acceptance Scenario 3, FR-001)

## 3. Replay (User Story 3)

1. From a state where status is `completed` or `skipped`, click the sidebar's **Take the tour** entry.
2. The tutorial overlay launches at step 1 immediately.
3. Skip again.
4. Verify the row's `status` did **not** revert to `in_progress` and that `completed_at` / `skipped_at` are unchanged — replay is transient.
5. Verify an `onboarding_replayed` audit event was recorded:

   ```bash
   docker exec astralbody bash -c "psql -U astralbody -c \"SELECT event_class, recorded_at FROM audit_events WHERE user_id='test_user' AND event_class='onboarding_replayed' ORDER BY recorded_at DESC LIMIT 1;\""
   ```

## 4. Tooltips on static UI (User Story 2)

1. Hover the **Audit log** sidebar entry for ≥500 ms. A tooltip with help text appears within 500 ms of hover. (SC-004, AC 1)
2. Tab to a sidebar entry via keyboard. Tooltip appears at the same position. (AC 2)
3. Move the cursor away. Tooltip closes within 200 ms. (AC 3)
4. Hover an interactive control with no entry in `tooltipCatalog.ts`. **No** tooltip frame appears. (AC 5, FR-008)
5. Press `Escape` while a tooltip is visible. It closes immediately. (AC 4)

## 5. Tooltips on SDUI components

1. From a chat session, trigger an action that returns a server-rendered component whose backend code sets `Component(tooltip="...")` on a button or card.
2. Hover the rendered button. The tooltip text from the backend payload is shown. (FR-014)
3. Repeat with a component whose backend code does **not** set `tooltip`. No frame appears. (FR-008)

## 6. Admin step editing (User Story for FR-015 → FR-018)

1. Sign in as an admin user.
2. Open the **Tutorial admin** sidebar entry (visible only to admins).
3. Click an existing step. Edit the title and body. Save.
4. Refresh and reopen the panel — the change persists.
5. Verify a `tutorial_step_revision` row was written:

   ```bash
   docker exec astralbody bash -c "psql -U astralbody -c \"SELECT id, step_id, change_kind, edited_at FROM tutorial_step_revision ORDER BY edited_at DESC LIMIT 1;\""
   ```

6. Verify a `tutorial_step_edited` audit event was recorded with `changed_fields = ['title','body']`.
7. As a non-admin user, attempt to call `GET /api/admin/tutorial/steps` directly. Returns `403`. (FR-018)
8. As any user, replay the tutorial. The updated copy appears immediately — no redeploy. (FR-016)

## 7. Admin step archiving

1. As an admin, archive a step.
2. As a non-admin, replay the tutorial. The archived step is not shown.
3. As an admin, view the step list with `?include_archived=true`. The archived step is still listed with `archived_at` set.
4. Restore the step. It reappears for non-admin users on next replay.

## 8. Per-user isolation

1. As user A, hit `GET /api/onboarding/state`. Capture the response.
2. Modify the request to include `?user_id=test_admin`. Confirm `400 Bad Request`. (Mirrors feature 003 policy)
3. As user A, attempt `PUT /api/onboarding/state` with a `last_step_id` that points to an `audience='admin'` step. Returns `400`. (Contract validation)

## 9. Backend tests

```bash
docker exec astralbody bash -c "cd /app/backend && python -m pytest onboarding/tests/ -q"
```

Expected: all tests pass; coverage on `backend/onboarding/` ≥ 90% (Constitution Principle III).

## 10. Frontend tests

```bash
cd frontend && npm run test -- onboarding
```

Expected: all Vitest cases in `frontend/src/components/onboarding/__tests__/` pass.

## 11. Accessibility smoke check

- Tab through the tutorial overlay end-to-end without using the mouse.
- Run a screen reader (NVDA / VoiceOver) on a single step — title and body must be announced.
- Confirm focus is trapped inside the overlay while it is open and returned to the previously-focused element on close.
