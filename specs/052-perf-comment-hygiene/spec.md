# Feature Specification: System-Wide Performance Optimization + Repo-Wide Comment Hygiene

**Feature Branch**: `052-perf-comment-hygiene`

**Created**: 2026-07-08

**Status**: Draft

**Input**: User description: "Create a new spec for optimizations of this entire system (backend AND clients, not Apple devices). The system is extremely slow to load: on first login the example cards are slow to load, building the UI is slow (partly a byproduct of LLM latency), and loading each of the pages such as agent manager and conversation history is abysmally slow — these should be near instant. Also clean up comments throughout the repo: a file-purpose header at the top of each file, comments in code limited to Python function docstrings at the top of the function, and all other comments removed unless a specific line would confuse a senior developer."

Two workstreams, one feature:

- **Workstream A — Performance**: backend (orchestrator, webrender, agents), web client (server-driven shell + static JS), `windows-client/` (PySide6), `android-client/` (Kotlin/Compose). `apple-clients/` is **excluded** from performance work.
- **Workstream B — Comment hygiene**: the repo's first-party source code **except `apple-clients/`**, which this feature does not touch in either workstream (Clarification 2026-07-08).

## Clarifications

### Session 2026-07-08

- Q: Should the comment-hygiene cleanup include `apple-clients/` (35 Swift files)? → A: Exclude `apple-clients/` entirely — this feature touches it in neither workstream.
- Q: With progressive rendering in place, what is the adaptive UI designer's default budget? → A: One design pass by default (existing ~8s per-pass cap, so ≈8s total instead of up to 24s); multi-round remains available via existing operator configuration; fail-open fallback unchanged.
- Q: Where do the numeric latency targets bind for acceptance? → A: Both — the dev reference environment is the pass/fail gate, AND a documented production measurement report (same metrics, deployed instance) is required as evidence without being a gate.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pages and settings surfaces open near-instantly (Priority: P1)

A signed-in user clicks any settings-menu page — Agent Manager, Conversation History, Audit, Attachments, Personalization, Theme, Guide, Workspace Timeline, Admin Tools, Drafts — and the page appears essentially immediately: an instant loading indicator, followed by full content well under half a second on a healthy connection. Today these opens take from several hundred milliseconds to well over a second, with a silent blank wait, and one slow user operation can stall every other user of the instance.

**Why this priority**: This is the loudest daily pain ("abysmally slow… should be near instant") and fixing it requires curing the systemic backend problems (blocking data access on the event loop, connection-per-query, redundant queries) that also drag down every other interaction. It is the highest-leverage slice.

**Independent Test**: With the stack running, instrument and time each surface open from click to rendered content on web, Windows, and Android; run automated query-count assertions per surface; run a concurrency test (many simultaneous opens) proving one user's work no longer serializes others.

**Acceptance Scenarios**:

1. **Given** a signed-in user with a warm session, **When** they open any settings surface, **Then** a loading indicator appears within 100ms and the full surface content is visible within 400ms (P95) on web, Windows, and Android.
2. **Given** the Conversation History page, **When** it is opened, **Then** the chat list (with last-message previews) is produced from a single data-store query rather than one query per chat.
3. **Given** the Agent Manager, **When** an agent's detail view is opened, **Then** no more than 3 data-store round trips are made, one-time data backfills do not run on every open, and the agents list does not perform unbounded full-table scans.
4. **Given** 20 users (or 20 parallel sessions) opening surfaces simultaneously, **When** latencies are measured, **Then** P95 stays within 2× the single-user P95 — no cross-user serialization.
5. **Given** a user whose permission to an agent was just revoked, **When** they next open a permission-dependent surface or invoke a tool, **Then** they see the post-revocation state — no cache may serve stale permission decisions across requests or across users.

---

### User Story 2 - First login reaches the welcome cards fast (Priority: P2)

A user completing sign-in lands on the welcome canvas and sees the example cards (Business dashboard, Weather outlook, Research brief, …) promptly — no long blank or partially-styled page. Today the pipeline in front of those (static) cards — external font fetch, a multi-megabyte chart library, re-downloaded assets, a cold identity-provider key fetch, an artificial connect delay, and sequential data reads — adds up to multiple seconds.

**Why this priority**: First impressions and every subsequent page load share the same asset/boot pipeline; fixing it speeds every visit, not just the first.

**Independent Test**: Measure, with browser tooling and server timings, the time from post-sign-in redirect to visible example cards, on both a cold and a warm browser cache; verify no external-origin request occurs before first paint and that repeat-visit network transfer is under budget.

**Acceptance Scenarios**:

1. **Given** a returning user with a warm browser cache, **When** they complete sign-in, **Then** the welcome canvas with example cards is visible within 1.5s (P95) of the post-sign-in redirect.
2. **Given** a brand-new browser profile (cold cache), **When** the user completes sign-in, **Then** the welcome canvas is visible within 3.0s (P95).
3. **Given** any page load, **When** the critical render path is inspected, **Then** no request to an external origin (e.g., font CDNs) is required before first paint, and the multi-megabyte chart library is not fetched or parsed unless/until a chart actually needs to render.
4. **Given** a repeat visit after no deploy, **When** network transfer is measured, **Then** total static-asset transfer is under 100KB (long-lived immutable caching); **and given** a new deploy, **Then** changed assets are picked up immediately (versioned URLs).
5. **Given** the sign-in handshake, **When** the server validates the user's token, **Then** it does not pay a cold identity-provider key fetch in the interactive path (keys are warmed at boot and refreshed in the background); identity-provider unavailability at boot neither blocks boot nor weakens fail-closed authentication.

---

### User Story 3 - Chat turns feel responsive despite LLM latency (Priority: P3)

A user sends a message that produces rich components. Components appear as soon as they are produced; the polished arrangement (adaptive UI designer) arrives as a smooth in-place refinement afterward instead of gating first paint. Narrative answers stream in as they are generated rather than appearing only when complete.

**Why this priority**: LLM latency itself is out of scope, but today the system stacks avoidable seconds on top of it (up to ~24s of sequential designer rounds before the arranged canvas, no token streaming), so perceived latency is far worse than model latency.

**Independent Test**: Drive a component-producing turn through the in-process harness and through a live client; assert first component visibility does not wait for the designer; measure per-phase turn timings; verify streaming text on all three clients with a streaming-capable model and clean fallback without one.

**Acceptance Scenarios**:

1. **Given** a turn that produces 2+ rich components, **When** the components are ready, **Then** they are visible to the user immediately, and the designed arrangement (if any) arrives later as an in-place update without flicker, duplication, or identity loss.
2. **Given** default configuration, **When** the designer runs, **Then** it performs a single design pass within the existing ~8s cap (vs. today's 24s worst case), multi-round refinement stays available via operator configuration, and any designer failure/timeout falls back to the existing flat delivery exactly as today (fail-open).
3. **Given** a streaming-capable model configuration, **When** a narrative answer is generated, **Then** text begins rendering incrementally on web, Windows, and Android before generation completes; with a non-streaming model, behavior is unchanged.
4. **Given** any of the above, **When** permission gates, audit records, and PHI-gate behavior are compared before/after, **Then** they are unchanged.

---

### User Story 4 - Native clients start instantly and render efficiently (Priority: P4)

A Windows user launches the app and sees a window immediately — sign-in progress happens inside the window instead of a blank desktop while a browser flow completes. An Android user's canvas updates apply without re-rendering unchanged components.

**Why this priority**: The Windows pre-window blocking auth is the single worst native-client experience; Android is already healthy but leaves easy rendering wins.

**Independent Test**: Time Windows launch-to-window and verify auth progresses in-window (including timeout/cancel states); on Android, use composition-tracking tests/metrics to verify unchanged components are not recomposed on frame apply.

**Acceptance Scenarios**:

1. **Given** a Windows user launching the app, **When** the process starts, **Then** a window is visible within 1s on reference hardware and OIDC sign-in (discovery, browser hand-off, token exchange) proceeds with visible in-window status, without freezing the UI thread, and remains cancellable.
2. **Given** a first-ever Windows launch, **When** the app needs a workspace folder, **Then** no modal dialog blocks the window from painting first (the prompt is deferred until the workspace is actually needed).
3. **Given** a Windows theme change or canvas update, **When** components are unaffected by the change, **Then** they are not fully rebuilt.
4. **Given** an Android canvas update or streamed frame, **When** state is applied, **Then** unchanged components skip recomposition (stability-annotated state) and frame application does not re-apply the whole canvas needlessly.
5. **Given** all native changes, **When** the 044 parity and protocol drift-guard suites run in all three test stacks, **Then** they pass with a wire protocol that is unchanged or strictly additive.

---

### User Story 5 - The stack boots fast (Priority: P5)

An operator (or developer) starts the container and it becomes ready quickly: schema initialization takes a fast path when the schema is already current, heavy ML models warm in the background instead of stalling the first user, and startup does not sleep on fixed timers.

**Why this priority**: Boot time hits deploys, CI smoke, and local iteration; the first-user PHI-model stall (2–5s) also leaks into interactive latency.

**Independent Test**: Time `docker compose up` to `/readyz` before/after; assert schema init duration when current; verify the first personalization write no longer pays a model-load stall; production-posture boot semantics (fail-closed, exit 78) unchanged.

**Acceptance Scenarios**:

1. **Given** a restart with an already-current schema, **When** the orchestrator initializes storage, **Then** initialization completes within 250ms (fast-path version check) while still running full idempotent migrations whenever the schema is not current.
2. **Given** a container cold boot, **When** time-to-ready is measured, **Then** it improves by at least 40% versus the captured pre-change baseline.
3. **Given** boot completes, **When** the first personalization memory write occurs, **Then** it does not stall on a first-use ML model load (model pre-warmed in the background, feature-flag semantics unchanged, boot not blocked on the warm-up).

---

### User Story 6 - A maintainer finds every file clean and self-describing (Priority: P6)

A maintainer opening any in-scope source file (the repo minus `apple-clients/` and exclusions) sees: a concise header stating the file's purpose; docstrings/doc-comments on functions where rationale lives; and otherwise comment-free code — except the rare line-level comment that saves a senior developer from a genuine "wait, why?" moment. No section banners, no narrating-the-obvious, no commented-out code, no spec-ticket breadcrumbs.

**Why this priority**: Explicitly requested and valuable, but it must not delay the performance work and is safest done as its own reviewable, behavior-neutral slice.

**Independent Test**: Run an automated comment-policy conformance check over the repo (zero violations); verify 100% of directive comments (`# noqa`, `# pragma: no cover`, `# type: ignore`, formatter/linter directives, shebangs, encodings) survived; full test suite, lint, and CI green; no functional diff.

**Acceptance Scenarios**:

1. **Given** any source file in scope, **When** inspected, **Then** it begins with a concise file-purpose header (module docstring for Python; header comment for JS/CSS; file-level KDoc/comment for Kotlin).
2. **Given** any function or method, **When** inspected, **Then** rationale/traceability worth keeping lives in its docstring/doc-comment, not in inline comments.
3. **Given** the whole repo, **When** the conformance check runs, **Then** there are zero comments outside the allowed categories (file-purpose header, function/class doc-comments, qualifying senior-developer rationale lines, functional directives).
4. **Given** the ~588 inventoried directive comments, **When** the cleanup lands, **Then** all of them are intact, and lint (`ruff` from repo root), the full test suites, coverage gates, secret scanning, and CI are green.
5. **Given** a comment that carried real non-obvious rationale (e.g., a race/atomicity note or protocol quirk), **When** the cleanup lands, **Then** the rationale survives — rewritten in plain language in a docstring or as a qualifying line comment — while provenance-only markers (`T031`, `FR-016`, `US2`) are gone.

---

### Edge Cases

- **Database restart mid-session**: pooled/reused connections must detect staleness and recover; at most one failed user action, then normal service — no wedged pool, no leaked connections.
- **Connection-pool exhaustion** under parallel tool bursts or many simultaneous surface opens: bounded wait with graceful degradation, no deadlock; concurrency limits and pool size must be compatible.
- **Identity provider unreachable at boot**: boot proceeds; key warm-up retries in the background; interactive logins keep today's fail-closed behavior (bounded retry page); nothing caches "unavailable" as "valid".
- **Permission changes vs. caching**: permission decisions may be memoized only within a single request/turn; user-scoped surface caches must be invalidated by writes that affect them; no cache may ever be readable across users; historical timeline views remain read-only with mutations refused.
- **Multiple sockets per user on one chat**: fan-out and per-socket/per-device adaptation must still occur; any caching happens at a stage that preserves per-device rendering.
- **Designer refinement arrives after the user switched chats or navigated away**: the refinement applies only to its own chat/canvas or is dropped; never to the wrong canvas.
- **Older/other clients without streaming support**: streamed narrative degrades to whole-message delivery via strictly additive protocol behavior; no client is broken by new frames.
- **Chart-bearing turn arrives before the lazily-loaded chart library finishes loading**: the chart renders when the library is ready (queued render), never a permanently blank component.
- **Very long chats (hundreds of messages)**: chat load stays within budget via bounded hydration; nothing previously visible becomes unreachable.
- **Loading indicator without content** (server error mid-render): the indicator resolves to a visible error/retry state within a bounded time — never an infinite spinner (the Windows surface-timeout pattern is the precedent).
- **Asset version changes mid-session**: open pages keep working; the next navigation/load picks up new hashed URLs.
- **Comment cleanup correctness**: `#`/`//` sequences inside string literals are not comments and must be untouched (parser-aware, not regex-only); a line carrying both noise and a directive keeps the directive; TODO/FIXME items that represent real outstanding work are converted to tracked items before removal; behavior neutrality is provable (comment/docstring-only diffs, full suite green).

## Requirements *(mandatory)*

### Functional Requirements

**A. Pages & settings surfaces (US1)**

- **FR-001**: Every settings/chrome surface (agents list & detail, conversation history, audit, attachments, drafts, personalization tabs, theme, guide, tour, workspace timeline, admin tools) MUST present visible content within the SC-001 latency budgets on web, Windows, and Android.
- **FR-002**: Every surface open MUST show a loading indicator within 100ms of the user's action on all three clients; on web this extends the existing canvas skeleton pattern to modal/chrome surfaces (today the modal waits silently for HTML).
- **FR-003**: Surface data access MUST be bounded: conversation-history listing in exactly 1 data-store query (including last-message previews); agents list in ≤2 queries with no unbounded full-table scans; agent detail in ≤3 round trips; one-time backfills/migrations MUST NOT execute per-open.
- **FR-004**: Any surface/data caching introduced MUST be user-scoped (never readable across users), MUST be invalidated by writes that affect it, MUST NOT bypass per-device adaptation, and MUST NOT extend permission decisions beyond the current request/turn (see FR-019).
- **FR-005**: Workspace-timeline read-only semantics and mutation refusals while viewing history MUST be unchanged.

**B. First login & web asset pipeline (US2)**

- **FR-006**: From the post-sign-in redirect, the welcome canvas (example cards, plus the enable-agents consent card when applicable) MUST be visible within the SC-003 budgets.
- **FR-007**: The critical render path MUST NOT depend on any external-origin resource; fonts are self-hosted assets or a system-font stack.
- **FR-008**: Heavy visualization assets (the multi-megabyte chart library) MUST NOT be fetched or parsed before first paint; they load on demand when a chart first needs to render, and charts still render correctly (including a chart arriving before the library finishes loading).
- **FR-009**: Static assets MUST be delivered with immutable, versioned URLs and long-lived cache headers; a deploy with changed assets takes effect on the next load; repeat-visit transfer meets SC-004.
- **FR-010**: Client boot MUST NOT include artificial fixed delays (e.g., the 200ms pre-connect timer); the realtime connection starts as soon as the shell is ready.
- **FR-011**: Interactive token validation MUST NOT pay a cold identity-provider key fetch: keys are warmed at boot and refreshed in the background; provider unavailability neither blocks boot nor weakens fail-closed authentication.
- **FR-012**: The sign-in handshake pipeline (session/profile/preferences/permission reads, dashboard and welcome delivery) MUST batch or parallelize its data reads, and MUST NOT make the user's first paint wait on non-essential writes (profile save, audit emission may complete asynchronously) while preserving audit completeness.

**C. Chat-turn responsiveness (US3)**

- **FR-013**: Rich components MUST become visible as soon as they are produced; the adaptive UI designer MUST NOT gate first visibility — its arrangement arrives as a later in-place refinement that preserves component identity (no flicker, duplication, or lost state), and applies only to its own chat/canvas.
- **FR-014**: The designer MUST default to a single design pass within the existing per-pass time cap (≈8s total by default, down from today's 3 × 8s worst case); multi-round refinement remains available through the existing operator configuration, and today's fail-open fallback is kept (any failure → existing flat delivery).
- **FR-015**: Narrative text MUST stream incrementally to web, Windows, and Android when the configured model supports streaming, using strictly additive protocol behavior with graceful whole-message fallback when it does not.
- **FR-016**: Tool-call semantics, permission gates, audit records (including start/end tool-call rows), and PHI-gate behavior MUST be byte-for-byte semantically unchanged by US1–US3 work.

**D. Systemic backend (enables US1–US3)**

- **FR-017**: No synchronous data-store call may execute on the request-serving event loop in any HTTP, WebSocket, or chat-turn path; compliance MUST be enforced by an automated detector that runs in CI.
- **FR-018**: Data-store access MUST reuse pooled connections instead of opening a new connection per query; the pool MUST be size-configurable, resilient to database restarts (stale-connection detection/recovery), and leak-free under parallel tool execution.
- **FR-019**: Per-tool permission resolution MUST NOT repeat identical lookups within a single turn (request-scoped memoization only); permission changes MUST be visible no later than the next request/turn.
- **FR-020**: Known N+1 patterns on hot paths MUST be eliminated: recent-chats last-message lookup, chat-load attachment hydration, agent-detail permission/scope reads.
- **FR-021**: Chat-load transcript HTML MUST NOT be re-rendered from scratch for unchanged messages on every load (render-once via cache or persisted render), and long chats MUST stay within latency budgets via bounded hydration.
- **FR-022**: Per-turn persistence (workspace snapshots, audit chain) MUST NOT add user-visible latency on the critical path (asynchronous/batched where safe) while preserving existing ordering and integrity invariants (per-user hash chain, snapshot completeness).

**E. Native clients (US4)**

- **FR-023**: Windows: a window MUST be visible within 1s of launch; OIDC sign-in (discovery, browser hand-off, loopback wait, token exchange) MUST run off the UI thread with visible in-window progress and a cancel path; no modal dialog (e.g., workspace picker) may block first paint — deferred until actually needed.
- **FR-024**: Windows: theme restyles and canvas reconciliation MUST avoid full rebuilds of unaffected components.
- **FR-025**: Android: UI/wire state types MUST be stability-annotated so unchanged components skip recomposition; streamed frame application MUST avoid whole-canvas re-application.
- **FR-026**: Both native clients MUST keep 044 parity behavior; the committed UI-protocol manifest stays unchanged or strictly additive, and drift-guard suites in all three test stacks stay green.

**F. Boot & readiness (US5)**

- **FR-027**: Storage initialization MUST take a fast path (≤250ms) when the schema is already current via a schema-version marker, while still running the full idempotent, guarded migration set whenever it is not; the marker mechanism itself ships as an idempotent guarded migration with documented rollback.
- **FR-028**: Heavy first-use model loads (PHI analyzer) MUST be pre-warmed in the background at boot so the first interactive use does not stall; feature-flag semantics unchanged; boot readiness MUST NOT block on the warm-up.
- **FR-029**: Startup supervision MUST NOT rely on fixed sleeps where readiness can be detected; production-posture boot behavior (fail-closed, exit-78 semantics) is unchanged.

**G. Instrumentation & verification (cross-cutting)**

- **FR-030**: The system MUST record lightweight timing measurements (surface render duration, sign-in pipeline phases, turn phases, boot phases) sufficient to verify every success criterion, with negligible overhead and no sensitive data in the measurements.
- **FR-031**: CI MUST gain automated regression guards where feasible: query-count assertions for the FR-003/FR-020 paths, the FR-017 event-loop detector, and a first-paint asset budget check; wall-clock criteria not testable in CI get a documented, repeatable manual measurement protocol (environment, trial count, percentile). The feature MUST also deliver a one-time production measurement report capturing the same metrics against the deployed instance (evidence, not an acceptance gate).
- **FR-032**: Baseline measurements for every relative target (e.g., boot improvement) MUST be captured and recorded before optimization work begins.

**H. Comment hygiene (US6, repo-wide)**

- **FR-033**: Every in-scope source file MUST begin with a concise file-purpose header: module docstring (Python), header comment (JS/CSS), file-level KDoc/comment (Kotlin).
- **FR-034**: Function/method/class doc-comments are permitted and are the destination for any rationale or traceability worth keeping (including in tests).
- **FR-035**: All other comments MUST be removed, with exactly one exception: a short line-level comment may remain where the adjacent code would otherwise confuse a senior developer (non-obvious invariant, race/atomicity note, protocol quirk, compatibility workaround), and it must state that rationale rather than narrate the code.
- **FR-036**: Functional/directive comments MUST be preserved verbatim: shebangs, encoding lines, `# noqa`, `# type: ignore`, `# pragma: no cover`, formatter/import-sorter/linter directives (ruff/fmt/isort/eslint), and their non-Python analogs.
- **FR-037**: Noise categories MUST be removed: section banners, narrating-the-obvious comments, commented-out code, and provenance-only spec markers (`T0xx`, `FR-0xx`, `US x`); where such a marker carries genuine rationale, the rationale is rewritten in plain language (docstring or qualifying comment). TODO/FIXME comments are removed; any representing real outstanding work are first converted to tracked items.
- **FR-038**: The cleanup MUST be behavior-neutral: comment/docstring-only diffs, zero functional change, full test suites and lint green; conformance MUST be verified by an automated, parser-aware policy check (string literals containing comment-like sequences untouched; mixed noise+directive lines keep the directive).
- **FR-039**: Hygiene scope: all first-party source under `backend/` (Python and the static JS/CSS render layer), `windows-client/`, `android-client/`, and repo scripts; excluded: the entire `apple-clients/` tree, vendored third-party assets (chart library, runtime CSS compiler, fonts), generated artifacts, virtualenvs, SQL seed/data files, and documentation/spec Markdown.

**I. Shared constraints**

- **FR-040**: Zero new third-party runtime dependencies (Constitution V): only capabilities of already-shipped libraries, the standard library, database indexes, HTTP semantics, and self-hosted static assets.
- **FR-041**: Any schema delta (version marker, indexes) ships as an idempotent guarded startup migration with documented rollback (Constitution IX); all CI gates stay green (lint from repo root, both in-image test invocations, changed-line coverage ≥90%, smoke including production-posture exit 78, secret scan) (Constitution XI).
- **FR-042**: Security posture is non-negotiable: fail-closed auth, permission gates, audit completeness and chain integrity, PHI gating, and egress gating are all unchanged; no cache or async write may weaken any of them.

### Key Entities

- **Schema Version Marker**: a persisted record of the current storage schema revision enabling the boot fast path; created/updated by the migration runner; its absence means "run full migrations".
- **Timing Measurement**: a lightweight record (phase name, duration, context ids only) emitted for surface renders, sign-in phases, turn phases, and boot phases; contains no message content or PHI.
- **Versioned Static Asset**: a static file addressed by a content-derived URL enabling immutable caching; a deploy changes the URL, never the cached content's meaning.
- **User-Scoped Surface Cache Entry**: optional short-lived cached data for a surface, keyed by user (and device-adaptation stage), invalidated by relevant writes; never holds cross-user or stale-permission data.
- **Comment Policy Category**: the classification each comment falls into — file-purpose header, doc-comment, qualifying rationale line, functional directive, or disallowed — used by the conformance check.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Opening any settings surface shows a loading indicator within 100ms and full content within 400ms (P95, warm session, reference environment) on web, Windows, and Android — measured over ≥20 trials per surface.
- **SC-002**: Hot-path query budgets hold under automated test: conversation-history list = exactly 1 query; agents list ≤2; agent detail ≤3; chat-load attachment hydration is one bulk read regardless of message count.
- **SC-003**: First login (post-sign-in redirect) to visible example cards: ≤1.5s P95 with a warm browser cache; ≤3.0s P95 with a cold cache (reference environment).
- **SC-004**: Repeat visits transfer <100KB of static assets, and zero external-origin requests occur before first paint.
- **SC-005**: The event-loop detector finds zero synchronous data-store calls on the serving loop across the exercised HTTP/WS/chat paths, and runs green in CI.
- **SC-006**: In component-producing turns, the first rich component is visible with zero added wait from arrangement work, and total non-model overhead per turn (everything except LLM generation and tool execution) is ≤1.0s P95.
- **SC-007**: With a streaming-capable model, narrative text visibly streams on all three clients before generation completes; with a non-streaming model, delivery is unchanged.
- **SC-008**: Windows: window visible ≤1s from launch (P95, reference hardware), sign-in progresses in-window, and no first-launch dialog precedes first paint.
- **SC-009**: Android: composition tracking shows unchanged components are not recomposed on canvas/frame updates, with no frame-timing regression.
- **SC-010**: With a current schema, storage initialization completes ≤250ms; container cold boot to ready improves ≥40% versus the recorded baseline.
- **SC-011**: With 20 concurrent surface opens on one instance, P95 latency stays within 2× the single-user P95.
- **SC-012**: 100% of in-scope source files carry a purpose header; the conformance check reports zero disallowed comments; 100% of inventoried directive comments remain; the cleanup diff is comment/docstring-only with the full suite green.
- **SC-013**: The full CI pipeline is green on the feature branch, the UI-protocol manifest is unchanged or strictly additive, and all three clients' parity/drift-guard suites pass.
- **SC-014**: A documented production measurement report exists covering the SC-001/SC-003/SC-004 metrics against the deployed instance (evidence deliverable; dev reference environment remains the pass/fail gate).

## Assumptions

- **Reference environment** (clarified 2026-07-08): latency targets bind (pass/fail) on the standard dev deployment (docker compose on the primary dev machine, same-host browser/clients, LAN-class network), P95 over ≥20 trials, per a measurement protocol documented with the feature. In addition, a documented production measurement report (the same metrics captured once against the deployed instance) is a required deliverable as evidence — production numbers inform but do not gate acceptance.
- **Definitions**: "warm session" = authenticated, realtime connection established, server caches warmed; "warm cache" = repeat browser visit with no intervening deploy; "cold cache" = fresh browser profile.
- **Scope split**: `apple-clients/` is excluded from this feature entirely — no performance work and no comment-hygiene edits there (clarified 2026-07-08); its hygiene can be a later feature.
- **Caching policy**: permission decisions are never cached beyond a single request/turn; any longer-lived caches are user-scoped, short-TTL, and write-invalidated. Where stronger guarantees conflict with latency targets, correctness wins and the latency target is renegotiated rather than weakened.
- **Streaming is conditional** on the configured model/provider supporting it through the existing client-factory seam; SC-007 does not fail when no streaming-capable model is configured.
- **Designer default** (clarified 2026-07-08): one design pass per turn with the existing per-pass cap; operators can restore multi-round refinement via the existing configuration. The capability itself and its fail-open fallback are unchanged.
- **Relative targets** (boot ≥40% faster) bind against baselines captured per FR-032 before optimization begins.
- **TODO/FIXME**: removed by policy; any that mark real outstanding work are first recorded as tracked items so nothing is silently lost.
- **Comment-policy conformance tooling** is CI/dev-side only (no runtime dependency) consistent with the existing CI-tooling carve-out.
- **No architectural rescoping**: single-instance orchestrator, no-build ES5 web static layer, and the server-driven UI model all stay; this feature optimizes within them.
- **Deployment model**: performance work must not change operational requirements (same container, same env contract, same probes).

## Out of Scope

- Making the LLM itself faster (model choice, provider latency, prompt-size reduction beyond what streaming/progressive delivery already addresses).
- Any change to `apple-clients/` — no performance work and no comment-hygiene edits (clarified 2026-07-08).
- Wire-protocol redesign or non-additive changes; client rewrites; introducing web build tooling or frameworks.
- Horizontal scaling / multi-process orchestration.
- New third-party runtime dependencies of any kind.

## Context: Diagnosed Root Causes (evidence for planning)

Code-level investigation (2026-07-08) grounding this spec; the plan phase should verify line numbers before relying on them.

| Area | Finding | Evidence |
|---|---|---|
| Data store | New connection per query; no pooling | `backend/shared/database.py:25-29`, `:1263-1296` |
| Data store | 20+ synchronous DB calls inside `async def`s block the event loop, serializing all users | `backend/orchestrator/orchestrator.py:2996`, `:3169`, `:1189`, `:7649` among others |
| Surfaces | Agent detail ≈7 sequential round trips incl. unconditional backfill + credentials read | `backend/webrender/chrome/surfaces/agents.py:474-483`, `:407` |
| Surfaces | Agents list full-table ownership scan per open | `backend/webrender/chrome/surfaces/agents.py:106`, `backend/shared/database.py:1336-1339` |
| Surfaces | Permission resolution: 2-query effective-permissions; 3 queries per `is_tool_allowed`, no request memo | `backend/orchestrator/tool_permissions.py:390-404`, `:245-288` |
| Surfaces | No caching of surface renders; no modal loading skeleton (037 skeleton is canvas-only) | `backend/orchestrator/chrome_events.py:155-182`, `backend/webrender/static/client.js:793-808` |
| History | Recent-chats N+1 (one query per chat for last message) | `backend/orchestrator/history.py:211-235` |
| First login | Example cards are static; the pipeline in front is the cost | `backend/orchestrator/welcome.py:17-38` |
| First login | Blocking external font `@import`; ~4.5MB chart lib loaded unconditionally; ~450KB runtime CSS compiler; all static served `no-cache`; artificial 200ms pre-connect timer | `backend/webrender/static/astral.css:11`, `shell.html`, `backend/orchestrator/orchestrator.py:~360`, `backend/webrender/static/client.js:1026` |
| First login | Cold IdP key fetch inside the sign-in handshake; sequential prefs/permissions/dashboard reads before welcome | `backend/shared/jwks_cache.py:49-64`, `backend/orchestrator/orchestrator.py:8637`, `:1189`, `:1219`, `:7649-7660`, `:1225-1227` |
| Chat turn | Designer (default 3 LLM rounds × 8s) runs per tool-round and GATES web delivery — no component frame is sent to web clients until `design_round` returns (persistence-only upsert at `:6922`; first frame at `:6983`/`:6988`); native clients bypass it (immediate `ui_upsert`, `:6915-6918`); no token streaming from `_call_llm` (no `stream=True` anywhere; narrative is the final iteration of the route-LLM loop, not a separate call); all three clients already handle `ui_stream_data` frames | `backend/orchestrator/ui_designer.py:47-51`, `backend/orchestrator/orchestrator.py:6892-6988`, `:3824`, `:4343-4594`, `backend/shared/ui_protocol.json` (streaming category) |
| Chat load | Per-message attachment N+1; per-message HTML re-render each load; layout materialization queries | `backend/orchestrator/orchestrator.py:1627-1645`, `:1615-1622`, `:6840-6875` |
| Per-turn writes | Full-canvas snapshot row each turn (50–200KB); audit chain per-user advisory lock ~10–30ms (already off-thread) | `backend/orchestrator/workspace.py`, `backend/audit/repository.py:159-245` |
| Boot | ~130+ idempotent DDL/guard statements every start with no schema-version marker (`audit_events.schema_version` is an unrelated column — the marker table needs a distinct name); PHI analyzer lazy-load stalls first use 2–5s (no boot preload; `/readyz` never touches it); `start.py` sleeps: 2s post-orchestrator, 1s per spawned custom agent, no readiness polling | `backend/shared/database.py:23,41-47,49-1002`, `backend/personalization/phi_gate.py:66-87,190-198`, `backend/start.py:83-119` |
| Windows | OIDC blocks main thread before any window (discovery 15s, loopback wait ≤300s, sync exchange 20s; `resolve_auth` at `app.py:2642` precedes `MainWindow` at `:2648`); modal workspace picker in `__init__`; theme restyle is an intentional full rebuild; per-frame reuse gated on deep dict equality; an existing rebuild-with-new-token flow (`app.py:1936-1953`) can carry in-window auth | `windows-client/astral_client/auth.py:45,97,137-142`, `app.py:2609-2652`, `:2336-2362`, `:1363-1396`, `:357-438` (Canvas lives in app.py, not renderer.py) |
| Android | Healthy async posture; costs are unannotated recomposition and whole-canvas frame apply | `android-client/.../Renderer.kt:68-71`, `AppViewModel.kt:558-767`, `:597-611` |
| Comments | ~837 in-scope source files / ~43.7k LOC (apple-clients' 35 files excluded per clarification); ~1,416 section banners; ~600 spec markers; ~25 commented-out blocks; 53 backend files missing module docstrings; 588 directive comments across 234 files must survive | repo-wide inventory, 2026-07-08 |
