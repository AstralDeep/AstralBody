# Quickstart — Manual Smoke for Fix Page Flash

**Feature**: 010-fix-page-flash
**Audience**: Implementer / reviewer validating the fix in a real browser before merge (Constitution X).

## Setup

1. Pull `010-fix-page-flash`, install deps, and start the full stack:

   ```powershell
   docker compose up --build
   ```

2. Open the app in Chrome (or Firefox) at the configured dev URL.
3. Open DevTools → Network panel. Set "Preserve log" ON and filter to "Fetch/XHR".
4. Have a **non-admin** account and an **admin** account ready. Log in as admin first; you'll switch later.

## Scenario 1 — Initial page load (FR-001, SC-001, SC-002)

1. Sign out fully (clear session) and refresh.
2. Sign in. Watch the dashboard appear.

**Pass criteria**:
- ✅ No white flash between the HTML loading and the themed UI rendering (the inline theme bootstrap script in `index.html` should kick in).
- ✅ Sidebar, header, and dashboard shell render and hold steady — no fade-in re-running, no remount.
- ✅ DevTools Network panel: at most **one** request to `/api/admin/feedback/quality/flagged?limit=100` for the entire session (or zero, if the SettingsMenu has not been opened yet under the chosen remediation).
- ✅ Total ≤ 1 request per in-scope endpoint per session.

## Scenario 2 — Loading a historical chat (FR-002, SC-001, SC-002)

1. With at least one historical chat present, click into one in the sidebar.
2. Watch the chat content area populate.

**Pass criteria**:
- ✅ Only the message content area updates. Sidebar, header, dashboard shell, and chat shell do not flash or re-mount.
- ✅ Messages and SDUI components that are part of the loaded history appear **without** a fade-in animation (they are "present at first paint" of the chat view).
- ✅ DevTools Network panel: zero new requests to in-scope background endpoints.

## Scenario 3 — Submitting a new query (FR-003, FR-006, SC-001, SC-002)

1. In an open conversation, send a new message.
2. Watch the response stream in.

**Pass criteria**:
- ✅ The chat shell and all surrounding layout regions do not flash or remount.
- ✅ As new SDUI components arrive in the canvas, **only the new components** animate in. Existing components stay put — no global fade.
- ✅ DevTools Network panel: zero additional requests to in-scope background endpoints during the streaming response.

## Scenario 4 — Token silent refresh (FR-008, SC-002)

1. Stay signed in as admin and leave the dashboard idle for the duration required to trigger an OIDC silent token refresh (typically 5–15 min depending on token TTL).
2. Without taking any action, watch the network panel and the UI.

**Pass criteria**:
- ✅ When the silent refresh fires, no in-scope background endpoint is re-requested as a side effect.
- ✅ The UI does not flash.

## Scenario 5 — Non-admin user (FR-005)

1. Sign out, sign back in as a non-admin user.
2. Repeat Scenarios 1–3.

**Pass criteria**:
- ✅ Zero requests to `/api/admin/feedback/quality/flagged*` in the entire session.
- ✅ All other flash criteria from Scenarios 1–3 still pass for non-admins.

## Scenario 6 — Explicit refresh path (FR-004, FR-008)

1. As admin, open SettingsMenu → click into "Tool quality" / open `FeedbackAdminPanel`.
2. Watch the network panel.

**Pass criteria**:
- ✅ Exactly one request to the flagged-tools endpoint fires when the panel opens (this is an explicit "view-open" trigger).
- ✅ Closing and re-opening the panel within the same session may either reuse the cached value (no new request) or refetch on each open — either is acceptable; consistency with the chosen remediation is what matters. Document which behavior the implementation chose.

## Scenario 7 — Long session, no flash regression

1. Stay signed in and active for 10 minutes, alternating between sending queries, switching chats, and idling.

**Pass criteria**:
- ✅ Cumulative request count to any in-scope endpoint stays at "1 per session + N explicit user actions". Compare to the baseline before the fix where dozens of calls per minute were observed.
- ✅ No visible flash or flicker observed at any point.

## Reporting

Capture a HAR export from the Network panel covering scenarios 1, 3, and 7, and attach it to the PR. Include a short note in the PR body confirming each scenario passed and listing any divergences from the chosen remediation strategy.
