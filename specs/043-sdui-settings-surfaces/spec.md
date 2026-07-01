# Feature Specification: Native SDUI Settings Surfaces

**Feature Branch**: `043-sdui-settings-surfaces`
**Created**: 2026-07-01
**Status**: Draft
**Input**: User description: "Add pages to all the settings pages that are currently blank and say 'This settings screen is coming to the app soon.' All of these pages already exist in the web client interface and just need to be ported over to the Windows and Android clients."

## Overview

Feature 042 made the Windows and Android clients render the same Settings menu as the web from one server-owned model. But five of those menu items open a placeholder on the native clients — *"This settings screen is coming to the app soon"* — because their screens exist only as server-rendered **HTML** chrome, which the native clients (no web view) cannot display. This feature ports those screens to the native clients by delivering each settings surface as **server-driven UI (SDUI)**: the orchestrator composes the surface from `astralprims` primitives, ROTE adapts it to the device, and each client renders it with the **same component renderer it already uses for the chat canvas**. No new per-client, per-surface UI is hand-built, so the surfaces stay identical across clients and cannot drift (Constitution II/XII).

The five surfaces to port are **LLM settings, Personalization, Theme, Take the tour, and User guide**. (Agents & permissions and Audit log already have native screens; Tool quality and Tutorial admin are admin-only and, per feature 042, remain **web-only** — out of scope here.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Settings surfaces open natively instead of a placeholder (Priority: P1)

A person on the Windows or Android app opens a Settings item (e.g. LLM settings, Theme, User guide) and sees the real screen — the same fields, controls, and information the web shows — rendered as native UI. No item shows the "coming soon" placeholder, and there is no embedded web page anywhere.

**Why this priority**: This is the whole point of the feature and the direct user request ("add the pages"). It is the smallest slice that removes every placeholder and delivers the settings functionality on the native clients. It is independently demonstrable per surface.

**Independent Test**: On Windows and on Android, open each of the five settings items in turn and confirm a working native surface renders (not a placeholder, not a web view) with the same content the web shows.

**Acceptance Scenarios**:

1. **Given** the Settings menu on a native client, **When** the user opens "Theme" / "User guide" / "LLM settings" / "Personalization" / "Take the tour", **Then** the corresponding surface renders as native UI with the same fields/sections/controls as the web.
2. **Given** any ported surface, **When** it is displayed, **Then** there is no "coming soon" placeholder and no embedded web page.
3. **Given** a surface the server later changes (new field, changed copy), **When** a native client re-opens it, **Then** the change appears with no native client code change.
4. **Given** a native client that does not recognize one element of a surface, **When** that surface opens, **Then** that element degrades to a clearly labeled placeholder and the rest of the surface still renders and works.

---

### User Story 2 - Surface actions take effect natively (Priority: P1)

Interacting with a ported surface actually does something: choosing a theme preset, saving an LLM setting, editing a personalization/memory item, toggling a skill, or advancing the tour posts back to the server and takes effect, exactly as on the web (same server actions, same audit trail).

**Why this priority**: A read-only surface is half the value; the settings must be *usable*. It rides on US1's delivery mechanism, so it is the same slice for each surface. It is independently testable per action.

**Independent Test**: On each native client, perform the primary action of each surface (apply a theme preset, save/clear an LLM setting, edit a memory item, toggle a skill, advance the tour) and confirm it takes effect and is reflected/audited as on the web.

**Acceptance Scenarios**:

1. **Given** the Theme surface on a native client, **When** the user selects a preset, **Then** it is saved to their preferences (and honored on next load) exactly as the web's preset action does.
2. **Given** the LLM settings surface, **When** the user saves or clears a setting, **Then** the change is applied server-side and reflected on re-open.
3. **Given** the Personalization surface, **When** the user edits/deletes a memory item or toggles a skill/job, **Then** the change is applied and reflected, matching the web.
4. **Given** any surface action, **When** it runs, **Then** it passes through the same permission/audit gates as the web (no privileged client bypass).

---

### User Story 3 - Theme changes actually restyle the native app (Priority: P2)

When the user picks a theme preset in the (now native) Theme surface, the app's own colors change to match — not just a saved preference, but the live appearance of the native client — and other clients honor the saved theme on next load.

**Why this priority**: Applying the theme to the native chrome is a distinct, larger step than rendering the Theme surface (US1) and saving the preset (US2); the surface is useful before the app restyles, so this follows.

**Independent Test**: Pick a preset on a native client and confirm the app's background/surface/accent colors update live; open another client and confirm it loads with the saved preset.

**Acceptance Scenarios**:

1. **Given** the Theme surface on a native client, **When** a preset is chosen, **Then** the client's own theme (background, surface, primary/accent, text) updates to that preset immediately.
2. **Given** a saved theme preference, **When** the user opens a different client, **Then** it renders with that preset from first paint.

---

### Edge Cases

- **Unknown surface / unknown component**: an older client that receives a surface (or a component within it) it doesn't understand shows a labeled placeholder for the unknown part, never a blank or crashed screen.
- **Large or slow surface**: a data-heavy surface (long audit-style lists, many memory items) renders without freezing the UI.
- **Action failure**: a failed surface action (network drop, server refusal) surfaces a clear, in-surface error and leaves the client usable — it does not blank the surface.
- **Admin-only surfaces**: Tool quality and Tutorial admin remain web-only; if a native client somehow requests them, the server refuses (unchanged from feature 042).
- **Web unchanged**: porting a surface to SDUI must not change how that surface looks or behaves on the web.

## Requirements *(mandatory)*

### Functional Requirements

**Delivery mechanism**

- **FR-001**: The system MUST deliver a settings surface to a native client as structured, device-adapted UI (SDUI) composed from the shared UI primitive vocabulary — never as an HTML page and never as a placeholder.
- **FR-002**: Native clients MUST render a delivered surface using their existing server-driven-UI renderer (the same one used for the chat canvas), with no separate hand-built implementation per surface per client.
- **FR-003**: The presentation of each surface MUST be generated once on the server and adapted per device, so the surface is identical in content/behavior across web, Windows, and Android and cannot drift (Constitution II/XII).
- **FR-004**: Opening a settings item on a native client MUST show its surface within a short, interactive time; the web surface behavior MUST be unchanged by the port.

**The five surfaces**

- **FR-005**: The **Theme** surface MUST render natively (presets + any color controls) and apply/save a chosen preset.
- **FR-006**: The **User guide** surface MUST render natively (its sections/navigation and content).
- **FR-007**: The **LLM settings** surface MUST render natively and support its actions (view models, test, save, clear).
- **FR-008**: The **Personalization** surface MUST render natively and support its actions (profile, memory add/edit/delete, skill toggles, scheduled-job controls, dreaming controls) as the web offers.
- **FR-009**: The **Take the tour** surface MUST work natively (start/advance/complete the guided tour, or its native-appropriate equivalent).
- **FR-010**: Every ported item MUST replace its current "coming soon" placeholder on both native clients.

**Actions & correctness**

- **FR-011**: Interactions within a surface MUST post back to the server and take effect using the same server actions the web uses, with the same permission and audit behavior (no client-side privilege bypass).
- **FR-012**: A surface action's result (save confirmation, updated values, validation/error) MUST be reflected in the surface, matching the web outcome.

**Theme application (P2)**

- **FR-013**: Selecting a theme preset on a native client MUST update that client's own visual theme live, and the saved preset MUST be honored by every client on next load.

**Quality & scope**

- **FR-014**: When a client cannot render a specific component of a surface, it MUST degrade that component to a labeled placeholder and continue rendering the rest (graceful degradation).
- **FR-015**: Admin-only surfaces (Tool quality, Tutorial admin) are explicitly **out of scope** and remain web-only (feature 042); this feature MUST NOT expose them on native clients.
- **FR-016**: The feature MUST introduce no new third-party runtime dependency on the server or either native client unless explicitly approved and documented.
- **FR-017**: Any schema/stored-preference change MUST ship via the project's automatic, guarded, idempotent startup-migration mechanism with a documented rollback.
- **FR-018**: Device-independent logic (composing a surface's primitives; mapping a delivered surface to native UI; the action round-trip shaping) MUST be covered by automated tests that run without a device/emulator.
- **FR-019**: Each ported surface MUST be exercised against the running system on every affected client target (web in a browser, Windows launched, Android on an emulator) before it is considered done (Constitution X/XII).

### Key Entities *(include if feature involves data)*

- **Settings surface (SDUI)**: a server-generated, device-adapted screen for one menu item (Theme, User guide, LLM settings, Personalization, Take the tour), composed from the shared primitive vocabulary so any client renders it natively.
- **Surface component**: one node of a surface (text, card, table, list, input, toggle, button, color control, tabs, …) — the existing SDUI wire vocabulary the clients already render; no new client contract is introduced.
- **Surface action**: an interaction within a surface (apply preset, save/clear setting, edit/delete memory, toggle skill, advance tour) that posts back to the server via the existing action channel and hits the same permission/audit gates.
- **Theme preset**: a named set of color values that both saves to the user's preferences and (P2) restyles the native client.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On both native clients, 100% of the five in-scope settings items open a working native surface — **zero** "coming soon" placeholders and **zero** embedded web pages remain for them.
- **SC-002**: A reviewer comparing each surface across web, Windows, and Android finds the same content and controls on all three (verified per surface with screenshots).
- **SC-003**: The primary action of each surface (apply theme preset, save/clear LLM setting, edit a memory item, toggle a skill, advance the tour) succeeds on both native clients and is reflected/audited exactly as on the web.
- **SC-004**: Choosing a theme preset on a native client restyles that client live, and a second client opens with the saved preset (verified across all three clients).
- **SC-005**: Changing a surface's server-side composition (add a field/section) is reflected on all clients on next open with no client code change (demonstrated once).
- **SC-006**: The web presentation and behavior of every ported surface are unchanged (verified by comparison before/after).
- **SC-007**: All required CI gates pass (backend pipeline gates; Android build/lint/test/coverage gates), and device-independent logic meets the project's coverage bar.

## Assumptions

- **Feature 042 is the baseline**: the server-owned menu model, the `chrome_menu` delivery, and the native clients' existing SDUI renderers are in place and reused. This feature adds the *surface* delivery on top of the menu.
- **The web surfaces are the source of truth**: LLM settings, Personalization, Theme, Take the tour, and User guide already exist as server-rendered chrome surfaces (`webrender/chrome/surfaces/*.py`) with working server actions; this feature re-expresses their presentation as SDUI without changing their underlying data actions.
- **SDUI over a web view**: native clients render surfaces from the shared primitive vocabulary via their existing renderers; a web view is explicitly not used (both native clients are web-view-free by design).
- **Admin surfaces stay web-only**: Tool quality and Tutorial admin are not ported (feature 042 decision); they remain available only on the web.
- **Delivery contract is additive**: surfaces are delivered to native clients over an additive frame (the native equivalent of the web's HTML modal), and web delivery is unchanged; converted surfaces may render from the same primitive composition for all targets so there is a single source per surface.
- **Theme application is native work**: mapping theme presets to each client's own theme tokens (Compose color scheme on Android, Qt palette on Windows) is expected and scheduled as P2, after the surfaces render and save.
- **Incremental, independently-shippable delivery**: surfaces land one at a time (simplest first — Theme/User guide — then LLM settings, Personalization, Take the tour); each is production-ready and verified on every affected client before the next.
- **No new runtime dependencies** are expected on the server or either native client; any exception requires explicit approval and documentation.
