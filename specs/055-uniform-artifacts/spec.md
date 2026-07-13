# Feature Specification: Uniform Cross-Device Artifacts & First-Turn Loading Contract

**Feature Branch**: `055-uniform-artifacts`

**Created**: 2026-07-13

**Status**: Draft

**Input**: User description: "Uniform cross-device artifacts and first-turn loading contract — make the loading/skeleton experience reliable and identical on every client, and evolve the workspace component system into a first-class artifact experience: coherent, progressively-rendered, provenance-marked, iterable, and uniform across web, Windows, Android, iOS, macOS, and watchOS — positioned ahead of Claude/ChatGPT/Gemini web artifacts (thesis Direction C)."

## Why now (verified problem statement)

A live reproduction plus a multi-agent code audit (2026-07-13) confirmed the product's rich outputs do not yet behave like one artifact system:

1. **The first query of every new chat shows no loading state on web** — the user stares at a completely blank canvas for the whole first turn. Root cause is server-side: the welcome-canvas blanking frame (an empty full-canvas render sent at turn start) arrives one round-trip after the client optimistically showed its skeleton and destroys it; because the empty render still carries a non-empty HTML wrapper, even the idle empty-state hint is skipped. Later queries work only because the welcome flag has been popped.
2. **Every client family fails the first turn differently.** Windows never shows a skeleton for typed sends at all (only for welcome-card taps) and its empty-state hint replaces the loading state mid-turn. Android/iOS/macOS keep their skeleton but never clear the welcome examples from committed state — the welcome canvas leaks into the swipeable canvas history as "Canvas 1" and reappears after text-only turns. watchOS drops all empty canvas renders, so first-turn content lands *underneath* the retained welcome examples.
3. **Welcome content is unaddressable.** Welcome components carry no identities on the wire, so no client can distinguish them from real content and the server cannot remove them with targeted operations.
4. **Streaming and artifacts are disjoint worlds.** Live streams render into throwaway nodes with their own identity space; nothing a stream shows is ever persisted, streams die on any full canvas render, and an agent cannot progressively fill a durable component. Mid-stream narrative text renders raw markup tokens (observed live: `You rolled **`), and malformed model tool-call syntax leaked verbatim into a rendered document card (observed live: `update_component<arg_key>…NEW_PAGE@true…`) — the model was *trying* to update an existing component, an operation the contract does not offer.
5. **The same conversation produces different persisted canvases depending on which device sent the message.** The adaptive designer runs only for web-originated turns; workspace edit acknowledgements are web-only, so edits made on one device do not reconcile live on others.
6. **Artifacts carry no trust marks off the web**, no per-component iteration affordance, no version history, and no way to share or export anything.

This feature turns those verified defects into a single cross-device artifact contract. It is the product expression of thesis Direction C (the SDUI designer taken to the frontier: progressive rendering, provenance surfacing, conservative adaptation) — techniques C-U6/C-U10 from the 033 research corpus.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reliable first-turn loading on every device (Priority: P1)

A user opens AstralDeep on any device (web, Windows, Android, iPhone, Mac, or watch), sees the welcome examples, and sends their first message — typed or by tapping an example. From the instant they send until the first real content arrives, they see a clear "working" state (skeleton or equivalent), the welcome examples are cleanly and completely replaced, and at no point does the screen go blank or show stale welcome content mixed with results.

**Why this priority**: This is the single most-reported UX defect ("skeleton only works sometimes"), it is the first impression of every new chat, and it is fully diagnosed — highest value, lowest ambiguity. It is independently shippable.

**Independent Test**: On each of the six client targets, start a fresh session, send a first message (typed AND via example card where the target supports it), and record the canvas from send to first content. Verify: a loading state is visible within a perceptible instant of sending, no blank-canvas window occurs, welcome content is gone from the committed canvas (and from any canvas history), and the second query behaves identically to the first.

**Acceptance Scenarios**:

1. **Given** a fresh web session showing the welcome canvas, **When** the user types a first message and sends, **Then** a loading skeleton is visible continuously from send until the first content frame, and the welcome examples never reappear in that chat.
2. **Given** a fresh Windows session, **When** the user sends a first message from the composer (typed), **Then** the same loading treatment appears as for an example-card tap, and no "your generated interface appears here" idle hint is shown mid-turn.
3. **Given** a fresh Android or iOS/macOS session, **When** the first turn completes, **Then** the committed canvas contains only that turn's content, the canvas history does NOT contain a "welcome" snapshot, and a text-only first turn does not resurrect the welcome examples.
4. **Given** a fresh watch session, **When** the first turn's content arrives, **Then** the welcome examples are gone and only the turn's content is on the canvas.
5. **Given** any client mid-turn, **When** the turn ends in error, cancellation, or a text-only answer, **Then** the loading state resolves (never a stuck skeleton), preserving today's terminal-resolution safety nets.
6. **Given** a user who completed first-run LLM provider setup (which re-shows the welcome canvas), **When** they send their first message after setup, **Then** the first-turn contract above holds identically.

---

### User Story 2 - Progressive artifacts: results stream into durable components (Priority: P1)

When an agent produces a long-running or streaming result, the user watches a single durable component fill in progressively — a skeleton that becomes a partially-populated component that becomes the final artifact — instead of a transient node that vanishes on the next canvas refresh. What they watched stream in is exactly what persists: reloading the chat shows the same component with its final content. Mid-stream text is always readable (no raw markup tokens), and malformed model output is never rendered verbatim.

**Why this priority**: This is the visible "artifact" behavior gap versus commercial systems, it is the perceived-performance win for every slow tool, and the audit confirmed the plumbing is bounded (identity at subscribe, one additive wire field, client keying, persist-on-terminal). Ships independently of US1.

**Independent Test**: Invoke a streaming-capable tool and a slow non-streaming tool. Verify the result component's identity is stable from placeholder through final state, survives an intervening full canvas render, persists across chat reload, and that mid-stream narrative shows clean text at every frame.

**Acceptance Scenarios**:

1. **Given** a tool that streams results, **When** the stream starts, **Then** a placeholder component with a stable identity appears in the workspace, and every subsequent stream frame updates that same component in place on every connected device viewing the chat.
2. **Given** an in-flight stream, **When** the turn's designed full-canvas refresh arrives, **Then** the streaming component is not destroyed or duplicated — precedence is defined and the live stream continues (or hands off) into the same identity.
3. **Given** a stream that completes, **When** the user reloads the chat (any device), **Then** the final streamed content is present as a normal persisted workspace component with correct source attribution, and later re-runs supersede it under the existing identity rules.
4. **Given** narrative text streaming into the chat rail, **When** any intermediate frame renders, **Then** markup is either rendered or withheld — never displayed as raw token characters.
5. **Given** a model response that contains malformed/unsupported tool-call syntax, **When** the turn is delivered, **Then** the leaked syntax is stripped from user-visible surfaces, the event is diagnosable by operators, and the user receives an honest fallback rather than gibberish.
6. **Given** a stream that dies mid-flight (agent crash, disconnect), **Then** the placeholder resolves to an honest partial/failed state — never a permanently-loading component.

---

### User Story 3 - One designed canvas, whatever device you're on (Priority: P2)

A user works in the same chat from their phone, their desktop, and the web. The canvas they see — content, arrangement, and edits (save/delete/combine/condense) — is the same everywhere, regardless of which device happened to send each message. Edits made on one device reconcile live on the others, not just after a reload.

**Why this priority**: Removes the originating-device asymmetry (designed arrangement exists only for web-sent turns) and the web-only edit acknowledgements — the two structural causes of "primitives feel isolated per device." Depends on nothing in US1/US2 but is larger and touches all client manifests.

**Independent Test**: Drive the same multi-component turn from a web socket and from a native socket into two chats; verify the persisted canvas state (content + arrangement) is equivalent. With two devices live on one chat, perform workspace edits on each and verify the other reconciles without reload.

**Acceptance Scenarios**:

1. **Given** a turn with 2+ rich components sent from a native device, **When** the turn completes, **Then** the persisted canvas for that chat is arrangement-equivalent to the same turn sent from web (both designed, or both flat by explicit configuration — never divergent by accident).
2. **Given** a designed arrangement produced for one device, **When** another device with different capabilities re-hydrates the chat, **Then** it receives the same arrangement materialized within its capability profile (degradation is per-capability, not per-origin).
3. **Given** two devices live on the same chat, **When** one saves, deletes, combines, or condenses components, **Then** the other reflects the change without a manual reload.
4. **Given** the designer fails or times out for any turn, **Then** flat components still deliver everywhere (fail-open), and tool output is never rewritten — preserving the existing designer invariants.
5. **Given** a watch viewing the chat, **Then** it continues to receive its pre-degraded compact rendition and speech behavior unchanged (no re-speak on re-presented content).

---

### User Story 4 - Iterate on an artifact, and know what to trust (Priority: P2)

A user can act on a single artifact: ask the AI to change *just this component* ("make this chart weekly", "add a column for cost") without re-describing it in chat, and see the artifact update in place with its version history recoverable. Every artifact, on every device, carries a visible provenance mark distinguishing tool-grounded data from AI-generated estimates — a hallucinated metric never looks identical to a verified one.

**Why this priority**: This is the iteration affordance that defines artifact UX in commercial systems, and provenance is a trust requirement in a health-adjacent multi-agent product. Builds on identities from US2 but independently testable.

**Independent Test**: On web and one native client, invoke "refine this component" on a produced artifact with a natural-language instruction; verify the targeted component (and only it) updates in place through the standard permission gates, that its prior version is recoverable, and that provenance marks render on all six targets.

**Acceptance Scenarios**:

1. **Given** a rendered artifact, **When** the user invokes its refine affordance with an instruction, **Then** the resulting update replaces that component in place (same identity), other components are untouched, and the action flows through the same permission, security, and audit gates as chat.
2. **Given** a refined artifact, **When** the user views its history, **Then** at least the previous version is viewable and restorable, and restoring is itself an audited, permission-gated action.
3. **Given** any component with tool-grounded source data, **Then** every target (including natives) renders a provenance mark distinguishing grounded / estimated / AI-generated content; components lacking source attribution default to the least-trusted mark.
4. **Given** a user viewing workspace history (timeline mode), **When** they attempt a refine, **Then** it is refused read-only exactly like existing timeline mutations.
5. **Given** a refine instruction that the source agent cannot satisfy, **Then** the artifact remains unchanged and the user gets an honest explanation in the chat rail.

---

### User Story 5 - Take an artifact with you (Priority: P3)

A user can export what they made: download a table's data, export the canvas as a self-contained page, or mint a read-only share link to a single artifact or canvas that a recipient can open without an AstralDeep account — with the owner able to revoke it.

**Why this priority**: Completes artifact parity with commercial systems, but is lower-risk and lower-urgency than the loading/streaming/parity work. Fully independent.

**Independent Test**: Export a table as tabular data and a canvas as a standalone page; open both outside the app. Mint a share link, open it unauthenticated, verify read-only rendering and PHI-gate compliance, then revoke it and verify access ends.

**Acceptance Scenarios**:

1. **Given** any table artifact, **When** the user chooses export, **Then** they receive its full data (all rows, not just the visible page) in a standard tabular format.
2. **Given** a canvas, **When** the user exports it, **Then** they receive a single self-contained page rendering the same content, marked with provenance and generation date.
3. **Given** a share link, **When** an unauthenticated recipient opens it, **Then** they see a read-only rendition with no workspace verbs, no chat access, and no other user data; **When** the owner revokes the link, **Then** subsequent opens are refused.
4. **Given** content blocked by the PHI gate for durable external exposure, **When** a user attempts to share it, **Then** sharing is refused fail-closed with an honest explanation.

---

### Edge Cases

- **Reconnect mid-turn**: a client that reconnects while a turn is in flight must resolve its loading state from the authoritative re-render (the out-of-turn "empty render clears" contract is preserved for this path).
- **Multiple sockets, one user**: loading states and stream updates fan out per socket; a device joining mid-stream receives the current component state, not a blank placeholder.
- **Welcome identity collisions**: welcome components' new stable identities must be namespaced so they can never collide with or supersede real workspace identities (`wc_`/`au_`/`dg_` families) and are never persisted as workspace rows.
- **Text-only turns**: turns producing no components must still resolve loading states everywhere and must not resurrect welcome content (verified defect on Android/Apple today).
- **Interrupted first turn**: user cancels or the LLM pre-flight refuses (unconfigured provider) after welcome cleanup — the canvas must land in a coherent empty state with the idle hint, not a void.
- **Stream vs. designed canvas race**: a designed full-canvas push arriving while a stream is live must neither orphan the stream nor duplicate the component (explicit precedence rule required).
- **Capability-stripped interactivity**: on hosts where ROTE strips buttons (e.g., watch), refine/export affordances degrade to absent — never broken controls; ROTE host bounds remain security bounds.
- **Legacy chats**: chats recorded before this feature (no layouts, no provenance fields, no stream-backed components) must re-hydrate exactly as today.
- **Share-link abuse surface**: share tokens must be unguessable, scoped to a snapshot (not live data), revocable, and excluded from search indexing.
- **Designer latency on native-originated turns**: enabling design for native origins must not delay flat content delivery (components first, refinement later — the existing upsert-first contract).

## Requirements *(mandatory)*

### Functional Requirements

**First-turn loading & welcome lifecycle (US1)**

- **FR-001**: Every client target MUST display a visible loading state within a perceptible instant of the user sending a message (typed or via example card), continuously until the first content for that turn arrives or the turn terminates.
- **FR-002**: The system MUST NOT emit any turn-start frame that destroys a client's loading state before first content; welcome-canvas cleanup MUST be achieved by a mechanism that works on all six targets (including targets that ignore empty canvas renders).
- **FR-003**: Welcome components MUST carry stable, namespaced identities on the wire, distinguishable by every client and addressable by targeted removal, and MUST never enter workspace persistence or collide with workspace/designer identity namespaces.
- **FR-004**: After a chat's first turn completes (including text-only turns), no client may retain welcome content in its committed canvas or expose it in any canvas history view.
- **FR-005**: Windows typed-composer sends MUST arm the same loading treatment as example-card taps; the idle empty-state hint MUST never display while a turn is in flight.
- **FR-006**: The empty-canvas-render contract MUST be preserved: an authoritative out-of-turn empty render still clears the canvas (existing pinned client tests keep passing); in-turn semantics may change only in ways all six targets implement uniformly.
- **FR-007**: All existing terminal-resolution paths (turn done/idle, error, disconnect, timeline mode, new-chat) MUST continue to resolve loading states on every client.
- **FR-008**: The first-run provider-setup flow's welcome re-display MUST re-arm the same first-turn contract.

**Progressive artifacts & stream honesty (US2)**

- **FR-009**: A streaming or long-running tool result MUST be representable as a durable workspace component whose identity is assigned when the work starts and is stable through placeholder, partial, and final states.
- **FR-010**: Stream update frames MUST carry the component identity so every client (web and native) applies them to the identified component in place; frames remain sequence-deduplicated and chat-scoped.
- **FR-011**: On stream termination (success, failure, or abandonment), the final state MUST persist as a normal workspace component with full source attribution, participating in the existing four identity/supersede rules; abandoned streams resolve to an honest partial/failed state.
- **FR-012**: A full-canvas render MUST NOT orphan or duplicate an in-flight streamed component; the system MUST define and enforce a single precedence rule.
- **FR-013**: Mid-stream narrative text MUST never render raw markup tokens to the user; each visible frame is either correctly rendered or withheld until renderable.
- **FR-014**: Model output containing unrenderable tool-call or control syntax MUST be stripped from all user-visible surfaces (chat rail, canvas, native transcripts), logged for diagnosis, and replaced with an honest fallback message when stripping empties the response.
- **FR-015**: Progressive rendering MUST be feature-flagged with fail-open semantics: any failure in the bridge degrades to today's terminal-only delivery, never a lost result.

**Cross-device canvas parity (US3)**

- **FR-016**: Whether a turn's canvas receives a designed arrangement MUST NOT depend on which device sent the message; arrangement generation is decided by chat/content and explicit configuration only.
- **FR-017**: Designed arrangements MUST be materialized server-side into renderable structures per receiving device's capability profile; a device's rendition degrades by capability, never by turn origin.
- **FR-018**: Workspace mutations (save, delete, combine, condense, refine, restore) MUST reconcile live on every connected device viewing the chat, within the same delivery guarantees as content frames.
- **FR-019**: The designer fail-open invariant is preserved: flat components always deliver first on every target; designer failure means the refinement never arrives; tool output is never rewritten.
- **FR-020**: Watch behavior is explicitly bounded: pre-degraded compact renditions, speech attached only to live deliveries with no re-speak on re-presented content, no chrome/workspace verbs.
- **FR-021**: Any new frame types, component fields, or accept actions MUST be added to the shared protocol manifest and classified (handled/ignored-with-reason) by every client family in the same change, keeping all drift guards green.

**Iteration & provenance (US4)**

- **FR-022**: Every rendered artifact MUST expose a component-scoped refine affordance (where host capability allows interactivity) accepting a natural-language instruction that updates that component in place under its existing identity.
- **FR-023**: Refine MUST flow through the same permission, security-flag, credential, PHI, and audit gates as the chat path, be refused in read-only timeline mode, and be attributable in the audit chain to the human principal.
- **FR-024**: The system MUST retain at least the immediately-previous version of a refined component and allow viewing and restoring it; restore is itself gated and audited.
- **FR-025**: Provenance (grounded / estimated / AI-generated) MUST be part of the component's structured data — not a web-rendering nicety — and MUST render visibly on all six targets; components without source attribution default to AI-generated.
- **FR-026**: Provenance marks MUST be tamper-resistant from the model's perspective: agents and the designer cannot upgrade a component's provenance level; only tool-sourced attribution can.

**Sharing & export (US5)**

- **FR-027**: Users MUST be able to export a table artifact's complete data in a standard tabular format and a canvas as a single self-contained page (provenance and generation date included).
- **FR-028**: Users MUST be able to mint, list, and revoke read-only share links scoped to a snapshot of an artifact or canvas; recipients need no account; revocation takes effect immediately; tokens are unguessable and non-indexable.
- **FR-029**: Sharing/export MUST respect the PHI gate fail-closed: content flagged for durable-exposure restrictions is refused with an honest explanation; every mint/open/revoke is audited.

**Cross-cutting**

- **FR-030**: All new behavior ships behind feature flags whose OFF state is byte-equivalent to today's behavior; LLM-assisted parts fail open to current behavior, authority/sharing parts fail closed.
- **FR-031**: No new third-party runtime dependencies on any surface (backend, ES5 web layer, Swift, Kotlin, PySide6). Any schema change ships as an idempotent, guarded startup migration with documented rollback.
- **FR-032**: Artifacts are delivered to native clients as structured component dicts (never HTML); escape-by-default rendering and ROTE host security bounds are preserved everywhere.

### Key Entities

- **Artifact**: a durable, identity-bearing workspace component with lifecycle states (placeholder → partial → final → superseded/restored), source attribution, provenance level, optional version history, and per-target renditions. Extends today's `saved_components` identity model — it does not replace it.
- **Welcome canvas**: the pre-first-turn example content; now identity-bearing and addressable, never persisted, cleanly retired by the first turn on every target.
- **Stream-backed component**: an artifact whose content arrives incrementally; owns the mapping between a live stream and a workspace identity, including precedence versus authoritative canvas renders and persist-on-terminal.
- **Designed arrangement**: the per-turn layout overlay; becomes origin-independent and capability-materialized per device.
- **Provenance mark**: structured trust classification (grounded / estimated / AI-generated) carried with the component across all targets.
- **Share grant**: a revocable, snapshot-scoped, unguessable read-only access token for an artifact or canvas, with audit trail.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On all six client targets, a loading state is visible within 200 ms of sending the first message of a new chat and persists until first content — measured over 20 fresh-chat trials per target with zero blank-canvas windows and zero welcome-content leaks (committed canvas or history).
- **SC-002**: First-query and Nth-query loading behavior are indistinguishable: across trials, the variance in time-to-first-feedback between the first and later queries of a chat is imperceptible (< 100 ms difference in when feedback appears).
- **SC-003**: For streaming tools, users see the first partial content in a durable component in under half the tool's total runtime (median), and 100% of completed streams are present after chat reload with identical final content.
- **SC-004**: Zero occurrences of raw markup tokens or tool-call syntax in user-visible surfaces across a 200-turn scripted soak covering streaming narratives and malformed-output injections.
- **SC-005**: The same scripted multi-component turn driven from web and from a native origin yields arrangement-equivalent persisted canvases in 100% of trials; a workspace edit on one live device is reflected on a second within 2 seconds without reload.
- **SC-006**: Provenance marks render on 100% of components on all six targets in the component-gallery verification pass; a grounded and an AI-generated metric are visually distinguishable in every target's screenshot set.
- **SC-007**: Component-scoped refine succeeds end-to-end (update in place, prior version restorable, audit rows present) on web and at least one native client; refine attempts in timeline mode are refused 100% of the time.
- **SC-008**: Exported canvases open and render standalone (no app, no network) with all content present; revoked share links refuse access on the next request; zero PHI-gated items are shareable in the negative-path suite.
- **SC-009**: With all feature flags OFF, the full existing test suite and all client drift guards pass unchanged (byte-equivalent wire behavior), demonstrating safe rollback.

## Assumptions

- The six client targets in scope are exactly: web shell, Windows (PySide6), Android (Compose), iOS, macOS (SwiftUI), watchOS. Voice/AOM render targets remain out of scope except where the watch speech channel is explicitly preserved.
- The artifact identity substrate is the existing workspace identity model (four rules + ordinal grammar); this feature extends it (lifecycle states, provenance, versions) and must not alter resolution semantics for existing content.
- Cross-device designed canvases reuse the existing server-side materialization path (the one already used to fan designed canvases to web and to re-hydrate natives) rather than teaching clients to resolve layout references.
- Version history for refined artifacts may reuse the existing per-turn workspace snapshot mechanism if it can address single components; a per-component store is acceptable only as an idempotent additive migration.
- Share links serve snapshot renditions (server-rendered, self-contained) — never live workspace reads — which bounds the auth surface to token validity and keeps live data per-user-scoped.
- The "ask AI to change just this" refine path is expected to route through the existing chat/permission machinery with the component's source context attached; it costs a normal LLM turn (billed per the user's provider config).
- The streaming bridge covers the push-stream subsystem (the one with stream identities); the legacy interval-polling path is out of scope and may be retired separately.
- The 054 first-run LLM gate, PHI gate, audit chain, and ROTE host bounds are unchanged dependencies; this feature composes with them and may not weaken any of them.
- The thesis framing (Direction C) treats this as the designer-to-the-frontier UX contribution; net-new open-ended generative primitives (C-N2) remain explicitly out of scope per the 045 deprioritization.
- Native manifest/disposition updates (protocol manifest + three client disposition tables + parity matrix) are in scope wherever a new frame/field/action is introduced, per the drift-guard constitution.

## Dependencies

- Feature 048's identity/attenuation work is unrelated; the sibling spec (056) covers agent chaining. This spec has no dependency on it.
- Builds on: workspace identity model (028/029/030), designer delivery pipeline (029/052), stream manager (014/052), native parity matrices (041/042/044/051), 054 LLM gate, PHI gate (030), audit chain (003 onward).
- Verified root causes and constraint inventory: research digest of 2026-07-13 (13-agent audit; per-client first-turn table, stream/identity bridge analysis, designer-skip analysis) — file:line evidence available in the session research digest and reproducible from the cited modules.
