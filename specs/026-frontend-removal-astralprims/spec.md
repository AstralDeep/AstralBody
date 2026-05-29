# Feature Specification: FastAPI-Delivered UI & `astralprims` Primitive Package

**Feature Branch**: `026-frontend-removal-astralprims`  
**Created**: 2026-05-29  
**Status**: Draft  
**Input**: User description: "I want to remove the current react frontend and replace it with fastAPI on the backend. I also want to remove the defined primitves that are currently in the backend and use a new python package called \"astralprims\" to manage the primitives being pushed to the frontend"

## Overview

Today the product is a **server-driven UI (SDUI)**: the backend builds UI as primitive objects (defined in `backend/shared/primitives.py`), serializes them to JSON, streams them to a separate React single-page application, and the React app maps each primitive type to a hand-written React component for display.

This feature replaces that arrangement. The standalone React frontend is removed. The backend delivers server-driven UI via FastAPI: a new, dedicated Python package named **`astralprims`** owns the **definition** of every UI primitive and its serializable structured representation, the **orchestrator renders** those primitives into the client-appropriate format, and the existing **ROTE** layer **adapts** that rendering to the connecting device/client so each receives the format it expects. For this feature, the only client target that must work is the **web** (HTML/CSS/JS delivered by the backend); the design must, however, anticipate additional client targets in the future (e.g., a Windows desktop app, native phone OS, native watch OS), each of which will expect a different delivered format.

The behavior users see — chat with agents, server-generated rich UI, charts, audio, file upload/download, paginated tables, streaming progress, tutorials, audit/feedback panels, login — must be preserved at **full parity** with the current product.

## Clarifications

### Session 2026-05-29

- Q: When the system renders agent/user-supplied text into web HTML, how must untrusted content be handled to prevent injection/XSS? → A: Escape by default — all primitive text content is HTML-escaped by default; raw HTML is only permitted via a narrowly-scoped, explicit opt-in (e.g., a dedicated markdown/code primitive routed through a sanitizer).
- Q: Should astralprims expose a stable structured (e.g., JSON) representation of a UI response as an intermediate, separate from per-target rendered markup? → A: Yes — astralprims keeps a serializable structured primitive tree as the canonical form; each renderer transforms that tree into a target's output, and programmatic/non-web consumers can read the structured form directly (preserving today's JSON contract).
- Q: Reconcile rendering ownership with Constitution v2.0.1 (spec previously said astralprims renders). → A: Aligned to the constitution — `astralprims` **defines** primitives + the structured representation only; the **orchestrator** renders them into the client-appropriate format; **ROTE** adapts that rendering per device. All "astralprims renders / renderer within astralprims" wording was corrected accordingly.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Web user keeps the full experience after the re-architecture (Priority: P1)

A returning web user opens the product in their browser, signs in, chats with an agent, and sees the same rich, interactive responses they saw before — cards, tables, charts, alerts, buttons, file upload/download, audio, and live streaming progress — now delivered directly by the backend instead of by a separate React app.

**Why this priority**: This is the whole point of the feature. If the web experience is not preserved at parity, the re-architecture is a regression regardless of any internal cleanliness gained. It is the minimum shippable slice.

**Independent Test**: With the React build removed and the backend serving the web UI, run through the primary chat flow end-to-end in a browser and confirm every primitive type and every interactive surface renders and behaves as it did before.

**Acceptance Scenarios**:

1. **Given** a signed-in web user, **When** they send a message that produces a multi-primitive response (e.g., a card containing text, a table, and a chart), **Then** the full response renders correctly in the browser with the same visual structure and styling as the prior React app.
2. **Given** an agent that streams a long-running response, **When** the response is produced incrementally, **Then** the user sees streaming/progress updates appear live, in order, without a full-page reload.
3. **Given** a primitive that requires interaction (button, file upload, parameter form, color picker, pagination control), **When** the user interacts with it, **Then** the action is sent back to the backend and the resulting UI update is delivered and displayed.
4. **Given** the application is loaded, **When** an audit, feedback, tutorial, or settings surface is opened, **Then** it works equivalently to the prior React implementation.

---

### User Story 2 - All UI primitives are defined by `astralprims` (Priority: P1)

An agent author (or backend developer) builds an agent response using UI primitives. They import and use primitives from the new `astralprims` package, which defines each primitive (its data shape, validation, and serializable structured representation). The orchestrator renders those primitives for the connected client. The old `backend/shared/primitives.py` definitions no longer exist and nothing in the product depends on them.

**Why this priority**: Moving primitive definitions into the dedicated `astralprims` package is the second explicit goal of the request and is a prerequisite for the multi-client future. Parity for web (Story 1) depends on `astralprims` covering every current primitive type and on the orchestrator rendering each one.

**Independent Test**: Confirm `backend/shared/primitives.py` is removed, that every agent and orchestrator code path that previously produced UI now uses `astralprims`, and that `astralprims` exposes every primitive type the product currently supports.

**Acceptance Scenarios**:

1. **Given** the codebase after the change, **When** searching for the old primitives module and its symbols, **Then** there are no remaining references to it anywhere in the product.
2. **Given** the `astralprims` package, **When** enumerating the primitive types it supports, **Then** the set is at least the full current catalog (container, text, button, input, param_picker, card, table, list, alert, progress, metric, code, image, grid, tabs, divider, collapsible, bar/line/pie/plotly charts, color_picker, theme_apply, file_upload, file_download, audio).
3. **Given** any agent in the system, **When** it produces a UI response, **Then** that response is constructed entirely from `astralprims` primitives.

---

### User Story 3 - Backend delivers the format the client expects (Priority: P2)

The orchestrator detects what kind of client is connected, selects the matching renderer, and ROTE adapts the result to the device — so each client receives UI in the format it can display. For this feature, a web client receives web markup (HTML/CSS/JS). The mechanism is built so that a future non-web client (desktop, phone, watch) can connect and receive its own appropriate format without redesigning the primitive layer.

**Why this priority**: The multi-client capability is the strategic reason for separating primitive definitions (`astralprims`) from rendering (the orchestrator's render layer). It is P2 because only the web target must function for this feature to ship, but the seam must exist now so future targets are additive, not a rewrite.

**Independent Test**: Connect as a web client and confirm web markup is delivered; confirm the format-selection seam exists and is exercised (even if only one renderer — web — is implemented), such that adding a second renderer requires no change to primitive definitions or agent code.

**Acceptance Scenarios**:

1. **Given** a web client connects, **When** the backend produces a UI response, **Then** the client receives it as web-displayable markup and renders it.
2. **Given** the rendering layer, **When** a new (future) client target is added, **Then** only a new renderer is required — primitive definitions and agent-side code remain unchanged.
3. **Given** a client whose target format is unknown or unsupported, **When** it connects, **Then** the system handles it predictably (defined fallback or clear refusal) rather than failing silently.

---

### Edge Cases

- **In-flight sessions during cutover**: How are users with an open session affected when the React app is removed and the backend-delivered UI takes over? (Assumption: a clean cutover; no requirement to support a live React client and the new web delivery simultaneously.)
- **Unknown/old clients**: A cached old React bundle or an unrecognized client connects after cutover — the system must not serve a broken half-state; it directs the client to reload the current backend-delivered UI.
- **Primitive not yet renderable for a target**: A primitive type that a future renderer does not yet support — the renderer degrades gracefully (e.g., a readable placeholder) rather than crashing the whole response.
- **Interactive round-trips under streaming**: A user interacts with a primitive (e.g., pagination) while a stream is still updating the same area — updates must remain consistent and ordered.
- **Large/binary primitives**: Audio and file download primitives that carry or reference binary data must continue to work when rendered and delivered by the backend.
- **Authentication/session**: Login and persistent-login behavior must continue to work without the React auth module that previously managed it client-side.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST remove the standalone React frontend as a separate application; the product MUST no longer require a separate React/SPA build to be served to web users.
- **FR-002**: The backend MUST deliver complete, ready-to-display server-driven UI to connected clients via FastAPI, with the ROTE layer adapting that UI to the connecting device/client.
- **FR-003**: A new Python package named `astralprims` MUST own the definition of all UI primitives (their data shape, defaults, and validation), replacing `backend/shared/primitives.py`.
- **FR-004**: The **orchestrator** MUST render `astralprims` primitives into the format expected by the connected client. Primitive definitions live in `astralprims`; rendering lives in the orchestrator's render layer (per Constitution Principle II, v2.0.1).
- **FR-005**: For this feature (the web-specific case of FR-004), the orchestrator's render layer MUST render `astralprims` primitives to **web** output (HTML/CSS/JS) that a browser can display, including the interactive behaviors users have today.
- **FR-006**: `astralprims` MUST support, at minimum, the full set of primitive types currently in use, so that web parity is achievable: container, text, button, input, param_picker, card, table (including pagination and tool re-invocation context), list, alert, progress, metric, code, image, grid, tabs, divider, collapsible, bar/line/pie/plotly charts, color_picker, theme_apply, file_upload, file_download, and audio.
- **FR-007**: All agents and orchestrator code paths that previously produced UI via `shared.primitives` MUST be updated to produce UI via `astralprims`, with no remaining references to the old module.
- **FR-008**: The system MUST preserve **full feature parity** for every existing user-facing surface, including: agent chat, server-generated rich responses, streaming/progress updates, charts, audio playback, file upload and download, paginated tables, parameter forms, theming/color application, tutorials/tooltips, audit log, feedback, and settings.
- **FR-009**: The system MUST continue to support user authentication and the existing persistent-login behavior without relying on the removed React client-side auth module.
- **FR-010**: The orchestrator MUST select the renderer matching the connected client target, and the ROTE layer MUST adapt that rendering to the connecting device; for this feature only the web renderer must be implemented, but the target-selection mechanism MUST be in place. (Renderer selection is an orchestrator responsibility; ROTE's responsibility is per-device adaptation — per Constitution Principle II, v2.0.1.)
- **FR-011**: The rendering architecture MUST be extensible so that adding a future client target (e.g., Windows desktop, native phone, native watch) requires adding a renderer only — without changing primitive definitions or agent-side response code.
- **FR-012**: Interactive primitives MUST continue to round-trip user actions back to the backend and receive resulting UI updates, preserving today's action/payload behavior (e.g., buttons, forms, pagination, file upload, theme apply).
- **FR-013**: The system MUST handle an unknown or unsupported client target predictably (defined fallback or clear, non-silent refusal).
- **FR-014**: The system MUST degrade gracefully when a renderer does not support a given primitive (readable placeholder rather than failing the entire response).
- **FR-015**: The change MUST NOT alter agent capabilities, available tools, permissions/scopes, or audit obligations; it is a delivery/rendering re-architecture, not a behavioral one for agents.
- **FR-016**: Existing automated coverage for UI/rendering behavior MUST be migrated or replaced so that web parity is verifiable after the React test suite is removed.
- **FR-017**: When rendering primitives to web HTML, the orchestrator's web render layer MUST HTML-escape all agent- and user-supplied text content by default. Raw/unescaped HTML MUST only be emitted through a narrowly-scoped, explicit opt-in (e.g., a dedicated markdown/code primitive) whose content is passed through a sanitizer; no primitive may inject unescaped untrusted content into the page by default.
- **FR-018**: `astralprims` MUST expose a stable, serializable structured representation (a primitive tree) of every UI response as the canonical intermediate form. The orchestrator's renderers MUST transform this structured form into their target output, and the structured form MUST remain readable directly by programmatic/non-web consumers (preserving the existing JSON wire contract for clients that consume primitives rather than rendered markup).

### Key Entities *(include if data involved)*

- **UI Primitive**: A single unit of UI (e.g., text, card, table, chart, audio, button). Has a type, content/data fields, optional styling, and — for interactive primitives — an action and payload. **Defined** by `astralprims`; **rendered** by the orchestrator.
- **UI Response**: An ordered collection of primitives produced by an agent/orchestrator in reply to a user action. Its canonical form is a serializable structured primitive tree (the intermediate representation); renderers transform that tree into per-target output, delivered as one renderable unit (including incremental/streamed updates).
- **Structured Representation (Primitive Tree)**: The stable, serializable intermediate form of a UI Response that all renderers consume and that programmatic/non-web consumers may read directly. Preserves the existing JSON wire contract.
- **Client Target**: The kind of connected client and the delivery format it expects (web for this feature; desktop/phone/watch anticipated). Drives which orchestrator renderer is used against the structured representation, with ROTE adapting per device.
- **Renderer**: A component within the **orchestrator's render layer** that transforms the structured representation into a specific client target's format. The web renderer is required now; additional renderers are additive.
- **`astralprims` Package**: The new Python package that owns primitive **definitions** and their serializable **structured representation**, replacing `backend/shared/primitives.py`. (Rendering moves to the orchestrator's render layer, which replaces the prior React rendering registry.)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of primitive types currently in use are defined by `astralprims` and rendered correctly by the orchestrator for the web target.
- **SC-002**: A web user can complete every primary task they could before (sign in, chat, view all primitive types, interact, upload/download files, play audio, page through tables) with no loss of capability — verified by an end-to-end parity pass covering every user-facing surface.
- **SC-003**: Zero references to the removed `backend/shared/primitives.py` (and its symbols) remain anywhere in the product after the change.
- **SC-004**: The product serves the web UI without building or shipping a separate React/SPA application.
- **SC-005**: Adding a hypothetical second client renderer requires changes only within the orchestrator's render layer — no edits to `astralprims` primitive definitions or to any agent's response-building code (demonstrated by design/seam, validated via a stub or documented extension point); the new renderer consumes the same structured representation as the web renderer.
- **SC-006**: All previously passing user-facing behaviors remain passing under the new delivery path (no parity regressions in the migrated/replaced test coverage).
- **SC-007**: Streaming responses render incrementally on the web with no full-page reload, matching prior responsiveness.
- **SC-008**: Untrusted text content rendered to the web is HTML-escaped by default — a primitive carrying markup/script in its text fields renders that content inertly (no script execution, no injected elements) unless routed through the explicit, sanitized opt-in path.

## Assumptions

- **Web-only for this feature**: Only the web client target must be implemented now. Desktop/phone/watch targets are explicitly future work; the requirement here is that the architecture does not preclude them.
- **Clean cutover**: There is no requirement to run the old React app and the new backend-delivered web UI simultaneously for the same users; the React app is removed as part of this feature.
- **Client announces its target**: The connected client communicates (or is detectable as) its target type so the backend can select the correct format; for the web this is the browser connection. Exact negotiation mechanism is an implementation detail to be settled in planning.
- **ROTE adapts rendering to the device**: The existing ROTE module continues to coordinate agent responses and is the layer that adapts the orchestrator-rendered SDUI to the connecting device/client target; ROTE's responsibilities are extended, not replaced. This matches Constitution Principle II (v2.0.1): astralprims defines, the orchestrator renders, ROTE adapts.
- **Parity baseline is the current catalog**: "Full parity" is measured against the primitive set and surfaces present in the current product at the time of this spec.
- **Existing backend stack continues**: FastAPI, websockets/streaming, authentication (Keycloak/OIDC + persistent login), agent/tool/permission systems, audit, and the database remain in place; this feature changes how UI is defined and delivered, not those subsystems.
- **`astralprims` packaging**: `astralprims` is introduced as a distinct first-party package owned by the project, installed via `pip install astralprims`. Per Constitution Principle V, a first-party project package is not a third-party dependency; its introduction need only be documented in the PR, not approved as a new external library.
- **Accessibility/localization out of scope**: This feature introduces no new accessibility or localization requirements. The web renderer SHOULD NOT regress existing semantics (e.g., keep the same element semantics the prior React output had), but a dedicated a11y/i18n parity bar is explicitly deferred to a follow-up.

## Dependencies

- The existing ROTE orchestration layer (`backend/rote/`), which adapts the orchestrator-rendered UI to the connecting device.
- The existing FastAPI/websocket/streaming infrastructure used to push responses to clients.
- The existing authentication and persistent-login behavior, which must be preserved without the React auth module.
- The complete inventory of current primitive types and user-facing surfaces, which defines the parity target.
