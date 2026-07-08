# Feature Specification: Native Android Client (SDUI Target)

**Feature Branch**: `041-android-sdui-client`
**Created**: 2026-06-30
**Status**: Complete
**Input**: User description: "Native Android client for AstralBody — a new ROTE/webrender SDUI target built in Kotlin + Jetpack Compose with NO web view. Renders the orchestrator's server-driven UI natively by consuming the same structured `components` wire the Windows client uses (ui_render / ui_upsert / ui_stream_data) over WebSocket, registering as an Android device (mobile/tablet) so output is device-adapted. Core deliverable is the SDUI-primitive → Compose mapping (the Android twin of the Windows renderer), with unknown types degrading to a labeled placeholder; consumes live push streaming (in place, seq-deduped, session-filtered, terminal-finalized); ONE responsive layout across phone/tablet/foldable; OIDC PKCE sign-in via the system browser with a dedicated public client + silent refresh (dev-token path for mock auth); native chrome surfaces driven by existing data actions/REST (agents, history, audit) — never the web HTML chrome; minimal additive server changes (auth allow-list + confirm an Android device profile); Gradle project with JVM unit tests for all pure logic + an Android CI job. Car/automotive, an on-device tools agent, offline mode, and push notifications are explicit non-goals for v1. Success = a phone AND tablet can authenticate, chat, manage agents, and render the full SDUI canvas (incl. streaming + audit viewer) natively, adapting to screen size, at parity with the Windows client's shipped surfaces."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sign in and converse on a phone (Priority: P1)

A person installs the AstralBody app on their Android phone, signs in securely with their existing organizational account, asks a question, and sees the assistant's reply rendered as native mobile UI (not a web page). This is the core loop and the minimum viable product.

**Why this priority**: Without secure sign-in and a chat round-trip that renders natively, there is no product. It is the smallest slice that delivers real value: mobile access to the assistant.

**Independent Test**: On a phone, complete sign-in, send a message, and confirm a native-rendered response appears — fully demonstrable with nothing else built.

**Acceptance Scenarios**:

1. **Given** a fresh install on a phone, **When** the user opens the app, **Then** they are guided through a secure organizational sign-in and land in a chat view.
2. **Given** a signed-in user, **When** they send a message, **Then** the assistant's response appears as native UI within the conversation, with no embedded web page anywhere.
3. **Given** an expired session, **When** the app next needs to act, **Then** it silently renews the session without forcing a re-login, up to a defined renewal limit.
4. **Given** a **debug** build pointed at a **mock-auth** test server, **When** real Keycloak login is not configured, **Then** a debug-only developer-token path allows sign-in for local testing (this path is absent from release builds).
5. **Given** an account without access, **When** sign-in completes, **Then** the user sees a clear "no access" message rather than a broken or blank screen.

---

### User Story 2 - Full rich-UI parity with live updates (Priority: P2)

The assistant's richer outputs — tables, cards, charts, metrics, lists, tabs, alerts, forms, code, timelines, and more — all render as native Android UI, and long-running/streaming results update in place as they arrive rather than appearing only when complete. Output types the app does not yet support degrade to a clearly labeled placeholder instead of breaking the screen.

**Why this priority**: This is what makes the assistant genuinely useful on mobile beyond plain text — the bulk of the "native SDUI" value. The MVP (US1) is viable without the full vocabulary, so it is the next slice.

**Independent Test**: Trigger responses that exercise each component type and a streaming tool; confirm each renders natively, streaming output updates progressively, and an unsupported type shows a placeholder.

**Acceptance Scenarios**:

1. **Given** a response containing a table / card / chart / metric / list / etc., **When** it is delivered, **Then** each component renders as its native Android equivalent.
2. **Given** a streaming response, **When** partial updates arrive, **Then** the on-screen content updates in place (no duplicate, no flicker) and finalizes when the stream completes.
3. **Given** out-of-order or already-seen streaming updates, **When** they arrive, **Then** stale/duplicate updates are ignored and the latest state is shown.
4. **Given** a component type the app does not yet support, **When** it is delivered, **Then** a labeled placeholder is shown and the rest of the screen renders normally.
5. **Given** a response addressed to a different conversation than the one in view, **When** it arrives, **Then** it does not disturb the current conversation.

---

### User Story 3 - Adapt fluidly across all screen sizes (Priority: P2)

The same app reflows for phones, tablets, and foldables: on large screens the conversation and the rich-output canvas sit side by side; on phones they stack and are navigable. Content never clips or requires horizontal scrolling at common sizes, and the layout responds to rotation, fold/unfold, and split-screen.

**Why this priority**: "All screen sizes" is a headline goal and tablets/foldables are a primary target, but a phone-only MVP (US1) still delivers value — so adaptivity is the next slice rather than a blocker.

**Independent Test**: Run the same build on a phone, a tablet, and a foldable (or a resizable window); confirm the layout adapts (side-by-side vs stacked) and stays usable with no clipped or overflowing content.

**Acceptance Scenarios**:

1. **Given** a tablet or wide window, **When** the user views a conversation with rich output, **Then** the conversation and the canvas are shown side by side.
2. **Given** a phone or narrow window, **When** the same content is shown, **Then** the layout stacks and remains navigable without horizontal scrolling.
3. **Given** a rotation, fold/unfold, or split-screen resize, **When** it occurs, **Then** the layout re-adapts without losing the current conversation or scroll position.

---

### User Story 4 - Manage agents, history, and audit natively (Priority: P3)

Users can manage which agents/tools are enabled and their permissions, browse and reopen past conversations, and review their own audit log — all as native screens matching the surfaces already shipped on the desktop client, driven by the same underlying data.

**Why this priority**: Important for parity and trust, but the assistant is usable (US1–US3) before these management surfaces land, so they can follow.

**Independent Test**: From the app, enable/disable an agent and adjust a permission, reopen a past conversation, and page through the personal audit log with filters — each demonstrable on its own.

**Acceptance Scenarios**:

1. **Given** the agents screen, **When** the user enables an agent or changes a tool permission, **Then** the change is applied, reflected in the UI, and audited server-side.
2. **Given** the history screen, **When** the user selects a past conversation, **Then** it reopens with its messages and rich output.
3. **Given** the audit screen, **When** the user filters by category/outcome/keyword or pages further, **Then** matching entries are shown, scoped to the user only.

---

### Edge Cases

- **Connectivity loss mid-session**: the app shows a clear disconnected state and recovers (reconnect + re-authenticate) with no lost input and no duplicate sends.
- **Session renewal limit reached**: the user is prompted to sign in again rather than getting stuck.
- **Web-only surface pushed by the server**: the app acknowledges it gracefully (no crash, no blank screen) because it renders native screens, not embedded web.
- **Very large outputs** (long tables, long transcripts): render without freezing the UI (virtualized/paged).
- **Privacy / data minimization**: content the server withholds for a given device is not requested or shown.
- **Car/automotive environment**: out of scope for v1 — the app targets phone/tablet/foldable (see Assumptions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app MUST authenticate users with their existing organizational identity via the platform's secure native sign-in pattern (system browser), and MUST silently renew the session until a defined limit, after which it prompts re-sign-in.
- **FR-002**: Authentication MUST be **real Keycloak** in all shipped builds — there is no mock/dev auth in the product. Any developer-token shortcut, if present, MUST be gated to debug builds against a mock-auth server and MUST NOT exist in release builds.
- **FR-003**: The app MUST connect to the orchestrator and register as a device target, declaring its form factor (phone/tablet) and screen characteristics so the server adapts output to the device.
- **FR-004**: The app MUST render the assistant's structured UI outputs as native Android UI — never an embedded web page — for the established component vocabulary (text, card, container, grid, hero, badge, metric, key-value, timeline, rating, alert, button, input, parameter picker, file upload, file download, code, divider, progress, list, table, tabs, collapsible, bar/line/pie charts, chat history, skeleton/loading).
- **FR-005**: When the app receives a component type it does not support, it MUST display a clearly labeled placeholder and continue rendering the rest of the screen.
- **FR-006**: The app MUST apply in-place updates to already-rendered output (replace/update/remove an individual component) without re-rendering or duplicating the whole screen.
- **FR-007**: The app MUST consume live streaming output and update the corresponding on-screen content in place as partial frames arrive, finalizing when the stream ends; it MUST ignore stale or duplicate frames (out-of-order or already-seen) and MUST NOT apply frames addressed to a different conversation.
- **FR-008**: The app MUST let users send messages and interact with rendered controls (buttons, forms, pickers), posting those interactions back to the orchestrator.
- **FR-009**: The app MUST present a single adaptive layout that reflows across phone, tablet, and foldable (side-by-side conversation + canvas on large screens; stacked/navigable on small), and MUST re-adapt to rotation, fold/unfold, and split-screen without losing conversation state.
- **FR-010**: The app MUST provide native screens for managing agents and tool permissions, browsing/reopening conversation history, and reviewing the user's own audit log, each driven by the orchestrator's existing data actions/endpoints (not web HTML).
- **FR-011**: The audit screen MUST show only the user's own entries, support filtering (category, outcome, keyword) and incremental paging, and never expose another user's data.
- **FR-012**: The app MUST clearly indicate connection state and MUST recover from disconnection (reconnect and re-authenticate) without duplicate sends or lost typed input.
- **FR-013**: The app MUST gracefully acknowledge any server-pushed web-only chrome/HTML surface without crashing or blanking, since it renders native screens.
- **FR-014**: The app MUST honor server-side data minimization for the device profile — it must not request or display content the server withholds for that device.
- **FR-015**: The feature MUST require only minimal, additive server changes — registering the new client's identity in the auth allow-list and ensuring a phone/tablet device profile exists in the adaptation layer — and MUST reuse the existing message/streaming protocol and existing data endpoints with no new wire protocol.
- **FR-016**: All device-independent logic (protocol decoding, the structured-output → native-UI mapping, the streaming-update rules, and data-shaping for the management screens) MUST be covered by automated tests that run without a device/emulator, and the build MUST be verifiable in continuous integration.

### Key Entities *(include if feature involves data)*

- **Rendered Component**: one unit of assistant output — a typed structured node with attributes and optional children — mapped to a native UI element and identified so it can be updated in place.
- **Conversation**: an ordered exchange of user/assistant turns plus the current rich-output canvas; reopenable from history.
- **Agent / Tool Permission**: an available capability and the user's enable/permission state for it.
- **Audit Entry**: a record of an action in the user's own log (time, category, action, outcome, description); filterable and paged.
- **Device Profile**: the form factor and screen characteristics the app reports so output is adapted appropriately.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user on a phone can sign in and receive their first natively-rendered response in under 2 minutes from first launch.
- **SC-002**: 100% of the established component vocabulary renders as native UI; any unsupported type shows a labeled placeholder — zero blank or broken screens caused by unknown types.
- **SC-003**: Streaming responses update on screen within about 1 second of the server emitting an update, with no duplicate or out-of-order content visible.
- **SC-004**: The same build runs on phone, tablet (≥ 7"), and foldable form factors with the layout adapting (side-by-side vs stacked) and no clipped content or horizontal scrolling at common sizes and orientations.
- **SC-005**: Every surface the desktop client currently ships (chat, rich canvas, agents & permissions, history, audit log) is available natively on Android at functional parity.
- **SC-006**: After a connection drop, the app reconnects and restores a usable session automatically in the common case, with no duplicate sends and no lost typed input.
- **SC-007**: The user's audit view never shows another user's data (verified), and respects device-level data minimization.
- **SC-008**: Device-independent logic is covered by automated tests that pass in CI without an emulator, and a build artifact is produced by CI on every change.

## Assumptions

- **Car/automotive out of scope (v1)**: Android Auto and Android Automotive OS are a distinct UI paradigm with driver-distraction constraints and templated/automotive surfaces; they will be specced separately. v1 targets phones, tablets, and foldables — covering "all screen sizes" in the handheld/large-screen family.
- **On-device tools agent is a follow-on**: a client-hosted capability for share/notifications/clipboard/location (the Android analog of the desktop tools agent), gated by permissions, privacy filtering, and audit, is out of v1.
- **Reuse, don't extend, the protocol**: the existing message/streaming protocol and existing data endpoints are reused unchanged; the only server-side changes are additive — an auth allow-list entry for the new client, and confirming/defining a phone/tablet device profile in the adaptation layer.
- **Parity is scoped to shipped desktop surfaces**: chat, rich canvas, agents/permissions, history, and audit. The remaining settings surfaces (LLM, personalization, theme, attachments, drafts) are a documented roadmap, each following the same native-screen pattern.
- **Real authentication is mandated**: the implementation authenticates via real Keycloak OIDC (Authorization-Code + PKCE) — no reliance on mock/dev auth for the product. It uses the dedicated **`astral-mobile`** public client, **already provisioned and added to `KEYCLOAK_ALLOWED_AZP`** by the operator. Because `astral-mobile` was cloned from the desktop client (loopback redirect), its Valid Redirect URIs must include an Android **custom-scheme/app-link** redirect (e.g. `com.personalailabs.astraldeep:/oauth2redirect`) — Android cannot use a loopback redirect.
- **Distribution**: v1 produces an internal/sideloadable build artifact; store distribution and release signing are later concerns.
- **Out of scope (v1)**: offline use and push notifications.
- **Verification loop**: the primary engineering environment cannot build or run the mobile app directly, so automated unit tests for device-independent logic plus a CI build are the verification backbone, with on-device/emulator checks performed where the platform SDK is available.
