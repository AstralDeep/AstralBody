# Feature Specification: Cross-Client Chrome & Settings Parity

**Feature Branch**: `042-cross-client-chrome-parity`
**Created**: 2026-07-01
**Status**: Draft
**Input**: User description: "In the Android client the settings page has repeated options that are already in the hamburger menu — remove them. Look at the website version of the system and modify the Windows and Android clients to match it exactly with all the same functionality. Consistency is key. Verify against the Android emulator via screenshots and live tests and by opening the Windows client and taking screenshots. Additionally make sure all GitHub CI actions complete successfully. Also, if needed, update the constitution for future clients (iOS, for example): the clients need to match across all clients, and the ROTE and orchestrator need to handle all of the generative UI with very little wrapping in the client."

## Overview

The web experience is the source of truth for the application's "chrome": a top bar (brand, connection status, an optional Pulse digest control, a Workspace Timeline control, and a Settings control) and a single grouped Settings menu (ACCOUNT, HELP, and an admin-only ADMIN TOOLS group, plus a red Sign out). Each menu item opens a settings "surface" (Agents & permissions, LLM settings, Personalization, Audit log, Theme, Take the tour, User guide, Tool quality, Tutorial admin).

Today the two native clients diverge from the web and from each other. The Android client shows a bespoke hamburger menu **and** a separate Settings page whose options duplicate the hamburger. The Windows client shows a flat row of top-bar buttons with no Settings menu at all, and is missing most surfaces. This feature makes every client present the same chrome and the same settings functionality, and establishes an architecture that prevents the clients from drifting apart again as new clients (e.g. a future iOS client) are added.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The same menu on every client (Priority: P1)

A person who uses the assistant on the web, on the Windows desktop app, and on the Android app sees the **same** top bar and the **same** Settings menu on all three: the same controls in the same order, the same menu groups (ACCOUNT, HELP, and — for admins — ADMIN TOOLS) with the same items in the same order, and a red "Sign out" at the bottom that actually signs them out. On Android, the previously duplicated Settings options are gone — there is now one place to find each thing, exactly as on the web.

**Why this priority**: This is the headline request ("consistency is key") and the concrete bug ("remove the repeated options"). It is the smallest slice that delivers the core value — one coherent, non-duplicated menu everywhere — and it is independently demonstrable by simply opening the three clients side by side. It also establishes the single source of truth that every later slice depends on.

**Independent Test**: Open the web, Windows, and Android clients as the same user; confirm the top-bar controls and the Settings menu groups/items/order are identical, that Android no longer shows any option twice, and that "Sign out" ends the session on each client.

**Acceptance Scenarios**:

1. **Given** a signed-in non-admin user, **When** they open the Settings menu on web, Windows, and Android, **Then** each shows exactly the ACCOUNT group (Agents & permissions, LLM settings, Personalization, Audit log, Theme) then the HELP group (Take the tour, User guide) then a red "Sign out", in that order, and shows no ADMIN TOOLS group.
2. **Given** the Android client, **When** the user looks for "Agents & permissions" or "Audit log", **Then** each appears in exactly one place in the menu and nowhere else (no separate duplicate Settings page).
3. **Given** any client, **When** the user selects "Sign out", **Then** their session is ended (not merely the window closed) and they are returned to the sign-in entry point.
4. **Given** the menu source of truth is changed on the server (e.g. an item is renamed or reordered), **When** each client next renders its menu, **Then** all clients reflect the change without a client code change.

---

### User Story 2 - Only admins see admin tools (Priority: P1)

An administrator sees an additional "ADMIN TOOLS" group (Tool quality, Tutorial admin) in the Settings menu on every client. A regular user never sees that group on any client, and cannot reach those admin surfaces even by other means.

**Why this priority**: Role-gating is a security property, not a cosmetic one; it must ship with the menu itself, not after. Getting it wrong on a native client would expose admin functionality. It is part of the same P1 menu slice.

**Independent Test**: Sign in as an admin and confirm ADMIN TOOLS appears on all three clients; sign in as a non-admin and confirm it is absent on all three and that a direct attempt to open an admin surface is refused.

**Acceptance Scenarios**:

1. **Given** an admin user, **When** they open Settings on web, Windows, or Android, **Then** an ADMIN TOOLS group with "Tool quality" and "Tutorial admin" is shown after HELP.
2. **Given** a non-admin user, **When** they open Settings on any client, **Then** no ADMIN TOOLS group and no admin items are shown.
3. **Given** a non-admin user, **When** an admin-only surface is requested by any client, **Then** the request is refused by the server and the refusal is recorded in the audit log.

---

### User Story 3 - Settings open as native screens on every client (Priority: P2)

When the user selects any Settings item, the corresponding surface opens as a native screen with full functionality — not an embedded web page and not a "not available in this app" placeholder. Agents & permissions, LLM settings, Personalization, Audit log, Theme, Take the tour, and User guide all work natively on Windows and Android, matching what the web offers. The presentation is generated by the server and adapted to the device, so the clients hold only minimal wrapping and cannot drift from the web's functionality.

**Why this priority**: This is "all the same functionality." It is larger than the menu structure and depends on it (US1), so it follows as the next slice. Each surface is independently demonstrable, so the group can land surface by surface.

**Independent Test**: On Windows and Android, open each settings item in turn and confirm the surface renders natively and performs its core action (e.g. toggle an agent, change an LLM setting, page the audit log, apply a theme preset, start the tour), with no web view and no placeholder.

**Acceptance Scenarios**:

1. **Given** any settings item, **When** the user opens it on Windows or Android, **Then** the surface renders as native UI with the same fields/actions available on the web.
2. **Given** the "Agents & permissions" surface, **When** the user enables an agent or changes a tool permission on a native client, **Then** the change is applied and reflected, exactly as on the web.
3. **Given** the "Audit log" surface, **When** the user filters and pages on a native client, **Then** only the user's own entries are shown, matching the web behavior.
4. **Given** a surface the server has updated (new field, changed copy), **When** a native client opens it, **Then** the change appears without a native client code change.
5. **Given** a native client that does not yet recognize a specific piece of a surface, **When** that surface is opened, **Then** the unrecognized piece degrades to a clearly labeled placeholder and the rest of the surface still works.

---

### User Story 4 - Theme, Timeline, and Pulse behave identically (Priority: P3)

The remaining top-bar and dropdown behaviors match across clients: the Theme surface offers the same color presets and, once chosen, the theme is applied and remembered on that client and reflected on the others on next load; the Workspace Timeline control opens the same history-of-canvas view; and the optional Pulse digest control appears (and only appears) under the same condition on every client.

**Why this priority**: These complete exact parity but are not required for the core "one consistent, functional menu" value, so they are the final polish slice. Each is independently demonstrable.

**Independent Test**: Change the theme preset on one client and confirm it applies there and is honored on the others; open Workspace Timeline on each client; toggle the Pulse condition and confirm the control appears/disappears consistently on all clients.

**Acceptance Scenarios**:

1. **Given** the Theme surface, **When** the user selects a preset on any client, **Then** the new colors apply immediately on that client and are persisted to the user's preferences.
2. **Given** a persisted theme preference, **When** the user opens a different client, **Then** that client honors the saved preset.
3. **Given** the Workspace Timeline control, **When** the user activates it on any client, **Then** the read-only canvas history for the active conversation opens, with a way to return to the live canvas.
4. **Given** the Pulse digest capability is enabled server-side, **When** any client renders its top bar, **Then** the Pulse control appears; **and** when it is disabled, the control appears on no client.

---

### Edge Cases

- **Non-admin escalation attempt**: a crafted request from any client to open an admin-only surface must be refused server-side and audited, regardless of what the client shows.
- **Menu changes while a client is open**: renaming/reordering/adding a menu item on the server is reflected on each client's next menu render without a client update.
- **Unknown menu item or surface on an older client**: a client that receives a menu item whose surface it doesn't recognize still renders the item and, on selection, shows a graceful "coming to this client" state rather than crashing or blanking.
- **Connectivity loss while a surface is open**: the client shows a clear disconnected state and recovers without losing the user's place in the menu.
- **Sign out semantics**: "Sign out" must terminate the session (server-side where the web does), not merely close a window or clear a local token silently.
- **Small screens**: on a narrow phone, the top bar and menu remain usable (controls may collapse to icons) without hiding any item or changing its meaning.
- **Theme persistence conflict**: if two clients change the theme, the most recent change wins and is honored on next load by all clients.

## Requirements *(mandatory)*

### Functional Requirements

**Menu model (single source of truth)**

- **FR-001**: The system MUST expose a single server-owned description of the chrome — the ordered top-bar controls and the grouped, ordered Settings menu items (each with a stable key, display label, target surface, and any parameters), including which groups/items are admin-only and which controls are conditional (e.g. the Pulse control) — that every client consumes to render its chrome.
- **FR-002**: All clients (web, Windows, Android, and any future client) MUST render their top bar and Settings menu from this one description, so that a change to it is reflected on every client with no client-side code change.
- **FR-003**: The Settings menu MUST present the groups and items in the exact order defined by the source of truth: ACCOUNT (Agents & permissions, LLM settings, Personalization, Audit log, Theme), HELP (Take the tour, User guide), ADMIN TOOLS for admins only (Tool quality, Tutorial admin), and a visually distinct (red) "Sign out" at the very bottom.
- **FR-004**: The top bar MUST present its controls in the exact order defined by the source of truth: brand, connection status, the conditional Pulse control, the Workspace Timeline control, and the Settings control.

**Consistency & de-duplication**

- **FR-005**: The Android client MUST remove the separate Settings page options that duplicate menu entries; each destination MUST be reachable from exactly one place in the chrome, matching the web.
- **FR-006**: The Windows client MUST present the Settings menu (a grouped dropdown from the Settings control) rather than a flat row of top-bar buttons, relocating existing destinations (e.g. Agents, Audit) into the menu to match the web.
- **FR-007**: Item labels, grouping, and ordering MUST be identical across clients; no client may add, rename, reorder, or omit an item relative to the source of truth.

**Role-gating**

- **FR-008**: The ADMIN TOOLS group and its items MUST be shown only to users with the administrator role, on every client.
- **FR-009**: Opening any admin-only surface MUST be authorized on the server against the user's verified role, independently of what any client displays; unauthorized requests MUST be refused and audited.

**Native settings surfaces**

- **FR-010**: Every Settings item MUST open its surface as native UI on every client — never an embedded web page — with the same functionality available on the web.
- **FR-011**: The presentation of each settings surface MUST be generated by the server and adapted to the requesting device/client, so that native clients hold only minimal, generic wrapping and cannot diverge from the web's functionality.
- **FR-012**: Native clients MUST reuse their existing native rendering of server-driven UI to display settings surfaces (no separate, surface-specific native implementations that could drift).
- **FR-013**: When a native client encounters an element of a surface it does not yet support, it MUST show a clearly labeled placeholder for that element and continue rendering the rest of the surface.
- **FR-014**: Interactions within a surface (e.g. toggling an agent, saving a setting, paging the audit log, choosing a theme preset, advancing the tour) MUST post back to the server and take effect, matching the web outcome and audit behavior.

**Theme, Timeline, Pulse, Sign out**

- **FR-015**: The Theme surface MUST offer the same color presets on every client; selecting a preset MUST apply it immediately on that client and persist it to the user's preferences so other clients honor it on next load. There MUST NOT be a separate top-bar light/dark toggle on any client (Theme lives in the menu, matching the web).
- **FR-016**: The Workspace Timeline control MUST open the read-only canvas-history view for the active conversation on every client, with a way to return to the live canvas.
- **FR-017**: The conditional Pulse control MUST appear on a client's top bar when, and only when, the server indicates the capability is enabled, uniformly across clients.
- **FR-018**: "Sign out" MUST end the user's session (server-side session termination equivalent to the web), on every client, and return the user to the sign-in entry point.

**Change management & quality**

- **FR-019**: The feature MUST NOT require a separate parallel definition of the menu per client; adding a future client MUST be achievable by having it consume the same menu description and the same server-driven surfaces.
- **FR-020**: Any schema or stored-preference change introduced MUST be applied by the project's automatic, guarded, idempotent startup-migration mechanism, with a documented rollback.
- **FR-021**: The feature MUST introduce no new third-party runtime dependency on any client or on the server unless explicitly approved and documented.
- **FR-022**: Device-independent client logic (parsing the menu description, applying role-gating, mapping the description to native controls, and mapping server-driven surface descriptions to native UI) MUST be covered by automated tests that run without a device or emulator.
- **FR-023**: The web, Windows, and Android clients MUST each be exercised against the running system as part of accepting this feature (web in a real browser, Windows launched and screenshotted, Android on an emulator with screenshots and live interaction), and the automated verification pipeline for the affected areas MUST pass.

### Key Entities *(include if feature involves data)*

- **Chrome description (menu model)**: the server-owned, role-aware definition of the top-bar controls and the grouped Settings menu — the single source of truth every client renders. Attributes: ordered top-bar controls (with conditional flags), ordered groups, ordered items (stable key, label, target surface, parameters, admin-only flag).
- **Menu group**: a labeled, ordered collection of menu items (ACCOUNT, HELP, ADMIN TOOLS), possibly admin-gated.
- **Menu item**: one selectable entry — stable key, display label, the surface it opens, and any parameters.
- **Top-bar control**: one control in the top bar (brand, status, Pulse, Timeline, Settings), each with placement and an optional visibility condition.
- **Settings surface**: a server-generated, device-adapted screen for one menu item (e.g. Agents & permissions), composed of the shared UI vocabulary so any client can render it natively.
- **Client/device target**: a consumer of the chrome and surfaces (web, Windows, Android, future iOS), reporting its form factor so output is adapted appropriately.
- **Role**: the user's authorization level (administrator vs regular user) that determines which groups/items/surfaces are visible and permitted.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reviewer comparing the web, Windows, and Android Settings menus side by side finds the same groups, the same items, and the same order on all three, with zero duplicated entries — verified by screenshots of each client.
- **SC-002**: On Android, every destination reachable from the chrome is reachable from exactly one place (no option appears twice) — the original duplication is gone.
- **SC-003**: 100% of the Settings items (Agents & permissions, LLM settings, Personalization, Audit log, Theme, Take the tour, User guide, and the two admin items for admins) open a working native surface on both native clients, with zero "not available in this app" placeholders for the whole surface and zero embedded web pages.
- **SC-004**: An administrator sees the ADMIN TOOLS group on all three clients and a non-administrator sees it on none; a non-admin's direct attempt to open an admin surface is refused and audited — verified on each client.
- **SC-005**: Changing the menu's source of truth (rename/reorder/add one item) is reflected on all three clients on next render with no client code change — demonstrated once end to end.
- **SC-006**: Selecting a theme preset on one client applies it there and is honored by the other clients on next load — demonstrated across all three.
- **SC-007**: "Sign out" ends the session on each client (the user must re-authenticate to return), verified on all three.
- **SC-008**: All required continuous-integration checks for the affected areas pass on the change (backend pipeline gates and the Android build/lint/test/coverage gates), and device-independent client logic meets the project's coverage bar.

## Assumptions

- **Source of truth is the current web chrome**: the exact groups, items, order, labels, admin-gating, red Sign out, and the "Theme is a menu surface, not a top-bar toggle" behavior are taken from the web as it exists today. The screenshot's "sun" control is the (feature-flag-gated) Pulse digest control, not a theme toggle; matching the web means reproducing the Pulse control's gated behavior, not adding a theme toggle.
- **Full functional parity now**: all settings surfaces — including those not yet present on the native clients (LLM settings, Personalization, Theme, Take the tour, User guide, Tool quality, Tutorial admin) — are in scope for this feature, delivered so they render natively on both native clients.
- **Server-driven surfaces (thin clients)**: settings surfaces are composed from the shared UI vocabulary, generated by the server, and adapted per device, so native clients reuse their existing server-driven-UI rendering rather than hand-building each surface. This is the mechanism that makes "match exactly" durable and keeps client wrapping minimal.
- **Reuse existing capabilities**: the underlying data actions/endpoints behind each surface already exist (agents, permissions, audit, LLM config, personalization, theme presets, tour, guide, admin tools); this feature is about presenting them consistently, not reinventing them.
- **Auth and roles are existing**: the administrator role and the sign-in/sign-out mechanisms already exist and are reused; role-gating uses the existing verified-role source.
- **No new runtime dependencies** are expected on the server or either native client; any exception requires explicit approval and documentation.
- **Verification environment**: the web can be exercised in a real browser and the Windows client can be launched locally for screenshots; the Android app is verified on an emulator where the platform SDK is available, otherwise via the automated build/test pipeline and on-demand instrumented UI tests. The device-independent logic is covered by tests that run without an emulator so the feature is verifiable in CI regardless.
- **Companion constitution amendment**: a separate amendment establishes cross-client UI consistency as a durable rule (all present and future clients must match) and requires the server + adaptation layer to own generative UI with only minimal client wrapping. This feature is expected to comply with that amendment.
- **Independent, incremental delivery**: the priorities (P1 menu structure + role-gating + sign out, P2 native surfaces, P3 theme/timeline/pulse polish) are each independently shippable and production-ready; a slice is not considered done until it is exercised against the running clients and its CI gates pass.
