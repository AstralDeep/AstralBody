# Quickstart: Condensed Sidebar Settings Menu

**Feature**: 007-sidebar-settings-menu
**Audience**: Developer verifying the implementation locally; reviewer doing manual smoke before approving the PR.

This guide walks through a complete end-to-end verification on a fresh checkout of branch `007-sidebar-settings-menu` after `/speckit.tasks` and the implementation tasks are complete.

---

## Prerequisites

- Docker Desktop running (the AstralBody backend stack lives in containers).
- Node 20+ for the frontend dev server.
- A working clone of `AstralBody` on branch `007-sidebar-settings-menu`.

## 1. Start the backend stack

```bash
docker compose up -d
```

This brings up Postgres, Keycloak (or the mock-auth shim, depending on `.env`), the orchestrator (`astralbody` container, port 8001), and any agents.

Verify the orchestrator is up:

```bash
curl -s http://localhost:8001/health
# expect: {"status":"ok",...}
```

## 2. Start the frontend dev server

```bash
cd frontend
npm install   # only if dependencies changed
npm run dev
```

Visit `http://localhost:5173` (or whatever Vite reports). Sign in. With mock-auth (default for local dev), the user is `test_user` and is granted the `admin` role automatically — see `App.tsx:166-168`.

## 3. Smoke-test the Settings menu (all FRs)

### 3a — FR-001 / FR-002: Settings entry visible everywhere

1. Confirm a single **Settings** entry (gear icon) is visible in the expanded sidebar.
2. Click the desktop hamburger toggle (top-left of sidebar) to collapse the sidebar to the icon rail. Confirm the Settings gear is visible in the rail with a tooltip on hover.
3. Resize the browser to a narrow viewport (< 768 px, e.g., the responsive devtools mobile preset). The sidebar collapses into a mobile drawer. Open the drawer; confirm the Settings entry is visible inside.

### 3b — FR-003 / FR-004 / FR-005: Grouped menu contents (admin path)

Still signed in as the mock admin user:

1. Click **Settings**. The popover opens.
2. Confirm three section headings appear in this order: **Account**, **Help**, **Admin tools**.
3. Confirm:
   - **Account** lists: Audit log, LLM settings.
   - **Help** lists: Take the tour, User guide.
   - **Admin tools** lists: Tool quality, Tutorial admin.

### 3c — FR-005 / FR-006 / SC-003: Admin gating (non-admin path)

This requires a non-admin token. Two options:

**Option A** — temporarily edit the mock-auth role grant in `App.tsx:166-168` to remove the `admin` role from the dev user, restart the dev server, sign in.

**Option B** — point the dev server at a real Keycloak instance with a non-admin user.

Then:

1. Click Settings.
2. Confirm Account and Help sections render with their items.
3. Confirm the Admin tools section heading is **entirely absent** from the rendered DOM. Open the browser devtools Elements panel and search for "Admin tools" — there should be zero matches inside the menu container.

### 3d — FR-007 / FR-009: Item activation preserves URL deep-links

For each menu item:

1. Click the item.
2. Confirm the corresponding panel opens and the URL updates to the expected query parameter:
   - Audit log → `?audit=open`
   - LLM settings → `?llm=open`
   - Tool quality → `?feedback=open`
   - Tutorial admin → `?tutorial_admin=open`
   - User guide → `?user_guide=open`
   - Take the tour → no URL change (transient overlay).
3. Close the panel and verify the menu has dismissed.

Then directly visit `http://localhost:5173/?audit=open` (and each of the other deep-link URLs) without going through the menu. Each URL MUST open the corresponding panel directly (FR-009 / SC-002).

### 3e — FR-008: Dismissal

1. Open Settings.
2. Click outside the menu (e.g., on chat history). Menu closes; no panel opens.
3. Open Settings again.
4. Press Escape. Menu closes.
5. Open Settings again, click an item. Menu closes; panel opens.

### 3f — FR-012: Full WAI-ARIA keyboard navigation

1. Tab through the page until the Settings trigger is focused (visible focus ring).
2. Press Enter (or Space) → menu opens, first item receives focus.
3. Press ArrowDown → focus moves to the second item.
4. Press End → focus jumps to the last item.
5. Press Home → focus jumps back to the first item.
6. Press Tab → focus stays within menu items (trap), moves to next item.
7. Press Shift+Tab → focus moves backwards within items.
8. Press Enter on a focused item → corresponding panel opens; menu closes; focus returns to the Settings trigger (visible focus ring back on the trigger).
9. Open menu again; press Escape → menu closes; focus returns to the trigger.

Inspect ARIA attributes via devtools:
- Trigger: `aria-haspopup="menu"`, `aria-expanded="true"` when open / `"false"` when closed, `aria-controls` referencing the menu id.
- Menu container: `role="menu"`.
- Items: `role="menuitem"`.

### 3g — FR-010 / SC-005: Tutorial integration

1. Click **Settings → Take the tour** to replay the tutorial from step 1.
2. Step through the tour with the Next button.
3. When a step's target is one of the moved items (e.g., "Audit log"), confirm:
   - The Settings menu opens automatically (you did not click it).
   - The target item is highlighted by the tutorial spotlight.
4. Click Next. Confirm the menu auto-closes when the next step's target is outside the menu (e.g., chat input, agent panel).
5. Confirm the tutorial completes end-to-end with no broken / un-highlighted steps.

### 3h — FR-014: Missing-callback omission

This requires temporarily editing `App.tsx` to pass `onOpenAuditLog={undefined}` to `DashboardLayout`. Then:

1. Reload, open Settings.
2. Confirm the Audit log item is **absent** from the Account section (not greyed-out, not visible at all).
3. Pass *all four* user-scope callbacks (`onOpenAuditLog`, `onOpenLlmSettings`, `onReplayTutorial`, `onOpenUserGuide`) as `undefined` and confirm the Account and Help section headings disappear too.
4. Restore `App.tsx`.

### 3i — FR-015: Server-side authz boundary preserved

This is a non-visual check. With a non-admin token:

1. Even though the Admin tools section is hidden client-side, attempt to hit one of the admin REST endpoints directly with the non-admin's JWT:

   ```bash
   curl -s -H "Authorization: Bearer <non-admin-token>" \
     http://localhost:8001/api/feedback/admin/flagged
   # expect: 403 Forbidden (or 401)
   ```

2. Confirm the existing server-side role check rejects the request — proving menu visibility is *not* the security boundary.

## 4. Run the test suite

From the repo root:

```bash
cd frontend && npm test -- --run
```

Confirm:
- New file `frontend/src/components/settings/__tests__/SettingsMenu.test.tsx` runs all 14 cases listed in `research.md` § Decision 6 and passes.
- Existing `DashboardLayout` tests (if present) pass after their assertions are updated to expect the consolidated Settings entry.
- Existing `OnboardingContext` tests pass after the `currentStepTargetKey` field is added (no behavioral change to existing assertions).
- Coverage on `frontend/src/components/settings/` is ≥ 90% (Constitution Principle III).

## 5. Visual regression spot-check

Take a screenshot of the sidebar in each of the three viewport modes (expanded, collapsed icon rail, mobile drawer) and compare to a screenshot of `main`. Expect:
- Expanded sidebar: 6 fewer button rows, replaced by one Settings row.
- Collapsed icon rail: 4 fewer icons (Audit log + Tool quality + the new ones), replaced by one Settings gear.
- Mobile drawer: same as expanded but inside the drawer.

## 6. Cleanup

If you tested option A from § 3c (edited the mock-auth admin grant) or § 3h (nulled out callbacks), revert those edits before committing.

---

## Acceptance gate

This feature is ready to merge when:

- All 9 sub-checks under § 3 pass on a real device.
- Test suite passes (§ 4).
- Visual regression matches expectation (§ 5).
- The PR includes screenshots of the three viewport modes.
- Code review verifies Constitution principles I (N/A), II ✓, III ✓, IV ✓, V ✓ (no new deps), VI ✓, VII ✓ (FR-015 explicit), VIII ✓.
