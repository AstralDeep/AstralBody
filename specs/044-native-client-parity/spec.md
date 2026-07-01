# Feature Specification: Cross-Client Native Parity Review & Remediation

**Feature Branch**: `044-native-client-parity`
**Created**: 2026-07-01
**Status**: Draft
**Input**: User description: "Cross-client code review and remediation for the two new native clients: audit the Windows desktop client (windows-client/) and the native Android SDUI client (android-client/) against the web client (backend/webrender served shell) for feature parity, correctness, and usability, then apply revisions to close every gap found. Scope: (1) consistency of the WS + REST protocol handling across all three clients (chat, streaming, ui_render/ui_upsert, chrome_render, attachments, auth/session lifecycle); (2) server-driven UI component rendering fidelity — every astralprims primitive type pushed by the backend must render correctly and usably on each client per its ROTE device profile; (3) native client-side UI/chrome quality and usability (layout, input affordances, settings surfaces, error states); (4) feature completeness — anything the web client can do that the native clients claim to support must actually work end to end. Deliverable: a reviewed, revised codebase where Windows and Android clients are verified consistent with the web client, with defects fixed and verification evidence captured."

## Overview

AstralBody now ships three user-facing clients: the server-rendered web shell, a native Windows
desktop client, and a native Android client. All three consume the same server-driven UI
contract — the server owns *what* is shown; each client owns *how* it is shown for its device.
Features 041–043 brought the native clients up quickly, and a baseline audit (see
[baseline-findings.md](baseline-findings.md)) shows the three clients have drifted: some server
messages are silently ignored on native, some interactions work on one client but not another,
several shipped-in-name features (settings actions, theme restyle, attachments on desktop) are
incomplete, and the recorded verification evidence cannot attest that the native UIs are usable
(desktop screenshots render all text as unreadable placeholder glyphs).

This feature is a systematic review-and-fix pass: build the authoritative parity matrix
(server contract × three clients), close every gap in scope, and capture verification evidence
that a user on any client gets a dependable, equivalent experience.

## Clarifications

### Session 2026-07-01

- Q: Which big-ticket missing features should this feature BUILD vs. defer? → A: **All of
  them** — Windows attachments, live theme restyle on both natives, Android server-driven
  top-bar controls, table pagination on both natives, *and every other identified functional
  gap*. The default disposition for any gap is build-to-parity; only deliberate, documented
  channel decisions (admin tools, guided tour, HTML-only chrome, audio/generative media)
  remain web-only with graceful degradation.
- Q: May remediation change the backend when the server contract is the root cause? → A:
  **Full-stack fixes** — fix wherever the root cause lives, including the backend and the web
  client's rendering, provided wire changes stay additive/backward-compatible and all
  existing gates stay green.
- Q: Required verification depth? → A: **Live end-to-end on all three clients** — the real
  Windows app on the development machine, the Android emulator, and the web browser against
  the dev backend — with legible captured evidence, plus new automated protocol/render guards
  running in CI.
- Q: Are the unreadable (tofu) desktop verification screenshots a live defect or a capture
  artifact? → A: **Unknown — investigate both** the client's font handling and the screenshot
  capture pipeline, and fix the true cause.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The daily chat loop is dependable on every client (Priority: P1)

A researcher uses AstralBody interchangeably from the browser, their Windows desktop, and their
Android phone. On any client, they send a message, watch progress while agents work, see the
answer and rich components arrive, and trust the client to tell them when something goes wrong —
a failed request, a dropped connection, an expired session. Signing out actually signs them out
everywhere the server is concerned.

**Why this priority**: This is the product's core loop. Today, server error messages are
invisible on both native clients, the Windows client never recovers from a dropped connection,
several progress signals are ignored, and sign-out on both native clients leaves the server
session alive. These are correctness and security defects, not polish.

**Independent Test**: Can be fully tested by running one scripted conversation on each client
while injecting failures (server error reply, socket drop, expired token, sign-out) and
confirming each client shows the expected state and recovers.

**Acceptance Scenarios**:

1. **Given** an active conversation on any of the three clients, **When** the server replies
   with an error message for the user's request, **Then** the client presents the error visibly
   (not a silent no-op or a permanently "thinking" state).
2. **Given** a connected native client, **When** the connection drops (network blip, server
   restart), **Then** the client shows its connection state, reconnects automatically with
   backoff, and resumes the session without user action once the server is reachable.
3. **Given** an expired access token, **When** the server demands re-authentication, **Then**
   the client silently refreshes and reconnects when it holds a valid refresh credential, and
   otherwise returns the user to an explicit sign-in step — never a dead session.
4. **Given** a user who signs out on any client, **Then** the server-side session/refresh
   credential is revoked such that the old token can no longer be used, matching the web
   client's logout semantics.
5. **Given** a long-running agent turn, **When** the server emits progress signals
   (acknowledgement, status changes, step trail, tool progress, async task completion),
   **Then** each client reflects progress equivalently for the signals it supports, and the
   turn always terminates in a visible done/failed state.
6. **Given** any server-pushed message type a client does not support, **Then** the client
   ignores it deliberately (logged, documented in the parity matrix) — never an unlogged
   silent drop, and never a crash.

---

### User Story 2 - Every component the server sends looks right on my device (Priority: P1)

A user's agents produce rich output — tables, charts, dashboards, forms, files, streamed
updates. Whatever the server decides to push, the user sees a correct, legible, usable
rendering on their client: components that their client declared support for render natively
and correctly; anything else is substituted by the server before it arrives; interactive
components (buttons, forms, inputs, file pickers, downloads) actually round-trip.

**Why this priority**: Rendering fidelity is the whole premise of the server-driven UI
architecture. The audit found per-type gaps (no table pagination on either native client,
inert theme/color components, name mismatches, markdown constructs missing on Android),
and the current desktop verification screenshots show unreadable text — so fidelity is
unproven today.

**Independent Test**: Can be fully tested by pushing a canonical gallery covering every
primitive type (and every interactive variant) to each client and verifying rendering and
round-trip behavior against the parity matrix, with legible screenshot evidence per client.

**Acceptance Scenarios**:

1. **Given** the canonical component gallery, **When** it is delivered to each client under
   that client's declared capabilities, **Then** every component renders correctly and legibly
   with no placeholder leaking for a type the client declared it supports.
2. **Given** a component type a native client does not support, **When** an agent emits it,
   **Then** the server substitutes a supported equivalent before delivery, and the client-side
   labeled placeholder appears only as a last-resort safety net.
3. **Given** interactive components (button, input, form with multiple submit actions, file
   upload, file download), **When** the user operates them on any client, **Then** the
   resulting action reaches the server and the visible outcome matches the web client's.
4. **Given** a table larger than one screen, **When** it is delivered to a native client,
   **Then** the user can access all rows (pagination or equivalent), matching web behavior.
5. **Given** a multi-turn conversation with in-place component updates and live streams,
   **Then** the final canvas state on each client matches the server's intent — later
   full-canvas renders must not lose components that keyed updates added earlier.
6. **Given** assistant text containing the supported markdown constructs (headings, emphasis,
   inline/fenced code, lists, links), **Then** each client renders them equivalently.

---

### User Story 3 - Settings I can actually use from any client (Priority: P2)

A user opens the settings menu on any client and sees the same server-owned menu (minus
deliberately web-only entries). Every entry they can see opens something functional: the
settings surfaces (Theme, User guide, LLM settings, Personalization) load, their controls
work, and Save/Test/Load actions round-trip with visible success or failure. Nothing dead-ends
in an infinite loading state or a broken placeholder.

**Why this priority**: The settings-surface hosts shipped in 043, but the action round-trips
and failure states were never completed or verified: on Android the top-bar portion of the
server menu model is decoded but never rendered (pulse digest, workspace timeline, connection
status), a surface that never arrives leaves an infinite skeleton, and action failures give no
feedback on either native client.

**Independent Test**: Can be fully tested by walking the entire server-sent menu on each
client, opening every entry, exercising every surface action (including a forced failure),
and confirming visible outcomes.

**Acceptance Scenarios**:

1. **Given** the server-owned menu model, **When** each client renders its chrome, **Then**
   the menu contents, grouping, ordering, role gating, and sign-out affordance match the model
   on all three clients, and native clients render the model's top-bar controls they are
   committed to support.
2. **Given** any settings surface opened on a native client, **When** the surface content
   arrives, **Then** it renders natively; **When** it does not arrive within a bounded time,
   **Then** the user sees a retry affordance — never an indefinite skeleton.
3. **Given** a settings surface with Load/Test/Save actions, **When** the user submits, **Then**
   success and failure are both visibly confirmed on the surface, on all clients that show it.
4. **Given** a deliberately web-only capability (admin tools, guided tour, HTML-only chrome),
   **When** a native user could encounter it, **Then** it is either absent from their menu or
   presents an explicit "available on the web app" notice — never a broken or empty surface.

---

### User Story 4 - Attachments work from my desktop too (Priority: P2)

A user who received attachment support in chat on web and Android can do the same from the
Windows desktop client: pick files, see staged chips with parser status, send them with a
message, and have agents read them — the same end-to-end flow the other clients already have.

**Why this priority**: Windows is the only client with no attachment affordance at all (the
wire format already supports it). This is the largest single feature-parity hole, but it is
independent of the correctness work in US1–US3. Confirmed in scope to build (Clarifications,
2026-07-01), alongside theme restyle, Android top-bar controls, and table pagination.

**Independent Test**: Can be fully tested by attaching supported and unsupported file types on
Windows, sending them, and comparing the full lifecycle (chips, parser status notes, agent
reading the file, re-loading the chat) against the Android and web behavior.

**Acceptance Scenarios**:

1. **Given** the Windows composer, **When** the user stages files, **Then** they see chips with
   filename and parser status (ready / preparing / pending approval / unavailable) equivalent
   to Android's, can remove chips, and the sent message carries the attachments.
2. **Given** an attachment whose format has no parser yet, **Then** the Windows user sees the
   same status escalation story as web/Android (preparing → pending admin approval →
   unavailable), not a silent failure.
3. **Given** a previously uploaded file, **When** the user reopens the chat, **Then** the turn
   shows its attachments consistently across all three clients.

---

### User Story 5 - My workspace follows my theme choice (Priority: P3)

A user picks a theme preset on the Theme settings surface and the client visibly restyles —
on every client that offers the surface, not just the web shell.

**Why this priority**: The Theme surface renders on both native clients today, but applying a
preset does nothing (the apply component is a no-op on both) — a visible broken promise,
though cosmetic relative to P1/P2.

**Independent Test**: Select each preset on each client; confirm the app restyles immediately
and the choice persists across restart via the user's server-stored preference.

**Acceptance Scenarios**:

1. **Given** the Theme surface on any client, **When** the user applies a preset, **Then** the
   client's chrome and canvas restyle immediately and the choice survives restart.
2. **Given** a client that cannot restyle some element natively, **Then** the surface says so
   rather than silently ignoring the action.

---

### User Story 6 - Evidence I can trust, docs that tell the truth (Priority: P3)

A maintainer (or thesis committee member) reviewing this research application can open the
feature's verification bundle and see legible, current evidence that all three clients behave
consistently: a parity matrix, per-client screenshots with readable text, automated guards
that fail when a client and the server drift, and specs/docs whose recorded status matches
reality.

**Why this priority**: Today the desktop verification screenshots render all text as
placeholder boxes, feature 042's task list is entirely unchecked despite having shipped,
feature 043's verification tasks are open, and the project instructions misdescribe the
Windows client's UI technology. Trustworthy evidence is what makes the parity claim durable.

**Independent Test**: Regenerate the evidence bundle from scratch on a clean checkout and
confirm every artifact is legible, current, and matched by a passing automated guard.

**Acceptance Scenarios**:

1. **Given** the verification bundle, **Then** it contains a complete parity matrix (server
   message types × clients; component types × clients) with a disposition for every cell.
2. **Given** the captured screenshots, **Then** all text is legible (the placeholder-glyph
   capture defect is fixed) on every client's captures.
3. **Given** the automated test suites, **Then** a newly added server message type or
   component type that a native client does not classify causes a test failure (drift guard),
   and the existing per-client suites pass.
4. **Given** the specs and project docs, **Then** recorded feature status (041/042/043 task
   lists, client READMEs, known-issue lists, project instructions) matches the shipped
   reality after this feature.

---

### Edge Cases

- Server introduces a brand-new message type or component type: native clients must degrade
  per their documented policy (logged ignore / labeled placeholder) and the drift guards must
  flag the gap at build time — never a crash or unlogged drop.
- A settings surface's content frame never arrives (server restart mid-open): bounded wait,
  visible retry; reopening must not wedge the client.
- Socket drops mid-stream (live-updating component): stream state must resolve (resume or
  visible interruption), not freeze as if still live.
- Token refresh fails while offline: client must distinguish "offline, will retry" from
  "signed out, needs interactive login".
- Sign-out while the revocation endpoint is unreachable: local session is still cleared;
  behavior documented (queued/best-effort revocation) consistent with the web client's
  offline-tolerant revocation posture.
- Attachment upload succeeds but the chat message is never sent (user closes app): staged
  uploads must not corrupt later sessions; re-open behaves cleanly.
- A table/list far exceeding a phone screen: content remains reachable and the UI responsive.
- Fonts/glyphs unavailable in the capture or runtime environment (the current desktop
  screenshot defect): UI text must render legibly on supported platforms, and the capture
  pipeline must produce legible evidence.
- Rapid re-renders (adaptive designer re-arranging the canvas) racing keyed upserts: final
  state must match the server's last instruction on every client.
- A user with only the base role (no admin): native menus and surfaces never expose
  admin-gated entries; server keeps enforcing regardless of client rendering.

## Requirements *(mandatory)*

### Functional Requirements

**Parity matrix & protocol completeness**

- **FR-001**: The feature MUST produce an authoritative parity matrix covering (a) every
  message type the server can push to a UI client and (b) every component type in the server's
  published vocabulary, with a per-client disposition for each entry: natively rendered /
  native equivalent / server-substituted / gracefully degraded / deliberately ignored
  (documented + logged). No cell may remain "silently dropped".
- **FR-002**: Both native clients MUST visibly surface server error replies tied to a user
  action, and MUST log (not drop) any unrecognized inbound message with its type name.
- **FR-003**: Both native clients MUST automatically reconnect after connection loss with
  bounded backoff, show current connection state to the user, and re-establish their session
  (re-registration, agent discovery, history) without user action. Outbound messages composed
  while disconnected MUST either queue-and-flush or fail visibly — never vanish.
- **FR-004**: On session expiry, both native clients MUST attempt silent refresh and
  reconnect; when refresh is impossible (no/invalid refresh credential), they MUST return the
  user to an explicit sign-in affordance. No configuration may leave the user in a dead
  session with only a status caption.
- **FR-005**: Sign-out on both native clients MUST revoke the server-side session (refresh
  credential/end-session), clear local credentials, and return to the signed-out state —
  equivalent to the web client's logout semantics, including its offline-tolerant posture.
- **FR-006**: Both native clients MUST reflect the chat progress contract consistently:
  message acknowledgement, status transitions (including async task hand-off and completion),
  and a guaranteed terminal state for every turn. Progress signals a client deliberately does
  not visualize MUST be classified as such in the parity matrix.
- **FR-007**: Historical-conversation viewing MUST be consistent: loading a prior chat
  re-hydrates transcript and components on all clients, and the read-only-history state is
  honored (mutating affordances disabled) wherever a client offers a history/timeline view.

**Rendering fidelity & interactivity**

- **FR-008**: Every component type a native client advertises as supported MUST render
  correctly, legibly, and usably on that client, verified via a canonical gallery covering
  all vocabulary types and their key variants (empty, long, malformed inputs included).
- **FR-009**: Component types a native client does not advertise MUST be substituted
  server-side before delivery; the client-side labeled placeholder MUST remain as a safety
  net and MUST never appear for an advertised type in verification runs.
- **FR-010**: Interactive components MUST round-trip end to end on both native clients:
  buttons (action + payload), single inputs, multi-field forms including multi-action
  submits and write-only secret fields, file selection, and authenticated file download
  with visible completion/failure.
- **FR-011**: Large tables MUST remain fully accessible on native clients with behavior
  consistent with the web client (paging or an equivalent affordance), using the existing
  server-side pagination contract.
- **FR-012**: Native markdown rendering MUST cover the agreed construct set — at minimum
  headings, bold/italic, inline and fenced code, ordered/unordered lists, and links — and
  the same text MUST NOT render as raw markup on one client and formatted on another.
- **FR-013**: Canvas state MUST converge identically across clients for the same server
  instructions: full renders, keyed in-place updates, removals, and live stream frames
  (including out-of-order/duplicate frame protection). The known Android defect where a full
  render can discard earlier keyed components MUST be fixed.
- **FR-014**: Each client MUST continue to declare its true renderable vocabulary at
  registration, and automated drift guards MUST fail when the server vocabulary and a
  client's declared set fall out of sync (including type-name mismatches).

**Chrome, settings surfaces & navigation**

- **FR-015**: All three clients MUST render the server-owned menu model faithfully: grouping,
  ordering, role gating, and sign-out. Both native clients MUST render the model's top-bar
  controls — including the pulse digest, workspace timeline, and connection status controls —
  rather than client-invented substitutes; any model element a native client deliberately
  will not render MUST be server-omitted for that channel.
- **FR-016**: The four ported settings surfaces (Theme, User guide, LLM settings,
  Personalization) MUST complete full action round-trips on both native clients: load current
  values, submit changes, test/validate where offered, and show explicit success/failure
  feedback in the surface.
- **FR-017**: Surface delivery MUST be resilient: a bounded loading state with retry when
  content does not arrive, and no unreachable/dead screens (placeholder screens that can no
  longer be navigated to are removed).
- **FR-018**: Deliberately web-only capabilities MUST be invisible or explicitly signposted
  on native clients (server-side omission preferred), and any native menu entry MUST open
  something functional.
- **FR-019**: Applying a theme preset MUST visibly restyle both native clients immediately
  (chrome and canvas) and persist via the user's server-stored preference; any element a
  client cannot restyle natively MUST be disclosed on the surface rather than silently
  ignored.

**Attachments**

- **FR-020**: The Windows client MUST support the attachment lifecycle at parity with
  Android: staging via native picker, chips with per-file status and removal, upload with
  parser-status display, inclusion on the sent message, and re-hydration when reloading a
  chat.
- **FR-021**: Parser-status semantics MUST be presented consistently on every client that
  supports attachments (ready / preparing / pending admin approval / unavailable), including
  the no-parser escalation story.

**Verification, guards & documentation truth**

- **FR-022**: The feature MUST capture a committed verification bundle: the parity matrix,
  per-client legible screenshots of the canonical gallery and key journeys, and recorded
  results for every acceptance scenario in scope. The current unreadable-text capture defect
  MUST be diagnosed and fixed (whether it is a capture-environment or a client font issue).
- **FR-023**: Automated protocol-coverage guards MUST exist per native client: every server
  message type is classified (handled/ignored-with-log), and every advertised component type
  has a renderer — failing the build on unclassified additions.
- **FR-024**: Project documentation MUST be reconciled to reality: feature 041/042/043 task
  lists and statuses, client READMEs and known-issue lists, and the project instructions'
  description of the client technologies. Dead code paths identified in the audit (unused
  auth stubs, unreachable screens, unused dependencies, missing referenced build files) MUST
  be removed or wired, not left ambiguous.
- **FR-025**: All remediation MUST preserve the architectural boundaries: the server keeps
  owning content and menu/surface structure; clients keep owning presentation; no client-side
  reimplementation of server-owned logic. Remediation is full-stack — when the root cause of
  a parity gap lives in the server contract or the web client's behavior, the fix lands there
  (Clarifications, 2026-07-01) — but wire changes MUST stay additive/backward-compatible so
  existing clients keep working, and all existing quality gates stay green.
- **FR-026**: The default disposition for every functional gap in the parity matrix is
  build-to-parity on both native clients. Only deliberate channel decisions may remain
  web-only — admin tools, the guided tour, HTML-only chrome regions, and the audio/generative
  media types — and each MUST be recorded in the matrix with its graceful-degradation
  behavior verified.

### Key Entities

- **Parity Matrix**: The authoritative table of server-pushable message types and component
  vocabulary versus the three clients; each cell holds a disposition and evidence link. The
  review's organizing artifact and the verification bundle's index.
- **Client Capability Declaration**: The set of component types each native client advertises
  at registration; drives server-side substitution and the drift guards.
- **Defect Register**: The audited findings (baseline + newly found during review), each with
  severity, affected client(s), disposition (fixed / deferred-with-rationale), and the
  verifying evidence.
- **Verification Bundle**: Committed evidence — matrix, legible screenshots per client,
  scenario results — regenerable on a clean checkout.
- **Server Menu Model / Settings Surface**: The server-owned chrome structures all clients
  must render faithfully; surfaces carry load/submit actions whose round-trips are in scope.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of server-pushable message types have an explicit per-client disposition
  in the parity matrix, and zero inbound message types are dropped without a log on either
  native client (verified by automated guard + injected unknown-type test).
- **SC-002**: 100% of each native client's advertised component types render legibly and
  correctly in the canonical gallery on that client, with zero placeholder leaks for
  advertised types across the verification run.
- **SC-003**: All four settings surfaces complete load → change → save/test round-trips with
  visible success and forced-failure feedback on both native clients (8/8 surface-client
  pairs passing).
- **SC-004**: After sign-out on each of the three clients, the previous session credential is
  rejected by the server on the next connection attempt (3/3 clients).
- **SC-005**: After a forced disconnect, both native clients automatically reconnect and
  resume within 30 seconds of server availability, with connection state visible to the user
  throughout (0 manual restarts required).
- **SC-006**: Every turn reaches a visible terminal state on all three clients across the
  scripted failure-injection suite (server error, timeout, cancellation): 0 permanently
  "thinking" sessions.
- **SC-007**: The committed verification bundle contains legible screenshots for every
  client (0 unreadable-text captures) and is regenerable by a documented procedure.
- **SC-008**: All in-scope big-ticket features (per clarification) pass their end-to-end
  acceptance scenarios on first regeneration of the bundle; every out-of-scope item is
  recorded in the Defect Register with a rationale.
- **SC-009**: All pre-existing automated suites (backend, Windows client, Android client)
  pass after remediation, and the new drift/protocol guards run in the same gates.
- **SC-010**: The acceptance scenarios in scope are demonstrated by live end-to-end runs on
  all three clients — the Windows app on the development machine, the Android emulator, and
  the web browser — against the development backend, with the captured evidence committed
  (Clarifications, 2026-07-01).

## Assumptions

- The web client (server-rendered shell) is the behavioral baseline; where all three disagree,
  the server contract as implemented for the web client defines "correct". If the review
  proves the web client itself defective, fixing it is in scope (full-stack remediation per
  Clarifications).
- The two native clients legitimately differ from the web in *presentation* (native idioms,
  layout, navigation); parity is judged on capability, correctness, and information
  equivalence, not pixel identity.
- Deliberate channel decisions from features 042/043 stand: admin tools and the guided tour
  remain web-only; native clients receive structured surfaces rather than HTML chrome.
- The server's device profiles for both native clients remain full-capability with
  substitution driven solely by each client's declared component vocabulary.
- Remediation follows the project constitution: no new third-party runtime dependencies
  without approval, server changes additive and idempotent, existing CI gates apply.
- The cause of the unreadable-text desktop screenshots is unknown; the review diagnoses both
  the client's font handling and the capture pipeline and fixes the true cause (tracked under
  FR-022, per Clarifications).
- The client-hosted Windows tools agent (win_agent) is out of scope except where its UI
  touchpoints (permission prompts, registration status) affect the chrome being reviewed.
- Verification runs live on all three clients per Clarifications: the Windows app on the
  development machine, the Android emulator, and the web browser. Voice/watch/TV/tablet
  profiles and physical-device Android testing beyond the emulator remain out of scope.
