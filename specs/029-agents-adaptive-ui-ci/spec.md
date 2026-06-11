# Feature Specification: Agent Catalog Overhaul, Adaptive UI Designer & Production CI

**Feature Branch**: `029-agents-adaptive-ui-ci`
**Created**: 2026-06-11
**Status**: Draft
**Input**: User description: "Remove email_tracker, grant_budgets, grants, linkedin, nefarious, and nocodb agents; consolidate remaining agents where they overlap; add plug-and-play agents informed by popular implementations (Claude Code agents, OpenClaw skills, Hermes agents); replace the deterministic per-round UI structure with an adaptive designer that composes all tool outputs from a round into one interactive, dynamic interface (still using only the preprogrammed primitives, still respecting ROTE device adaptation); add GitHub CI actions proving no drift and production readiness for https://sandbox.ai.uky.edu with Keycloak at https://iam.ai.uky.edu; make the website visually appealing through the SDUI backend with minimal/no frontend code."

## Clarifications

### Session 2026-06-11

- Q: Which consolidations should ship? → A: Merge the three external-service wrappers (classify, forecaster, llm_factory) into one `ml_services` agent only; medical, dice_roller, etf_tracker_1, general, weather, journal_review, connectors remain as-is.
- Q: How should the per-round UI designer behave? → A: Hybrid — the designer arranges the round's tool components (referenced by identity, never rewritten) into a layout and may author its own supplemental "garnish" components; on any designer failure the round falls back to today's append behavior.
- Q: Which plug-and-play agent pack ships in 029? → A: Research & Knowledge — a web research agent and a summarizer agent (both keyless by default, zero new third-party dependencies).
- Q: What does the CI pipeline do? → A: Verification gates on every PR/push (lint, full test suite against a database service, 90% changed-code coverage, image build, boot smoke incl. the fail-closed production gate, secret scan) plus a versioned container image published to GitHub Container Registry on main; no automated live deploy.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adaptive interface per chat round (Priority: P1)

A user asks a question that causes several tools to run in one round (e.g. a weather forecast, a data table, and a metric lookup). Instead of the current fixed vertical stack of raw tool outputs followed by a boilerplate "Analysis" card, the workspace presents a purpose-designed arrangement: related outputs grouped side-by-side, a headline takeaway up top, secondary detail tucked into collapsible or tabbed sections, and short connective narrative where it helps. Every tool output from the round is present — nothing is dropped or rewritten — and previously working interactions (refreshing a component, paging a table, viewing workspace history) continue to work exactly as before. On a phone, watch, or voice device the same designed round degrades gracefully through the existing device adaptation. If the design step is unavailable for any reason, the round renders the way it does today, with no user-visible error.

**Why this priority**: This is the centerpiece the user called "the most important currently." It changes every multi-tool interaction in the product and is the difference between a tool log and an interface.

**Independent Test**: Trigger a chat round that calls two or more UI-producing tools and observe the canvas: outputs are arranged (grouped/side-by-side/sectioned) rather than appended, all round outputs are present, table pagination and per-component refresh still work, and disabling the designer (or simulating its failure) yields the legacy append behavior.

**Acceptance Scenarios**:

1. **Given** a chat round whose tools return three rich components, **When** the round completes, **Then** the canvas shows a composed arrangement that contains all three components (identifiable by their existing component identities) plus optional designer-authored connective elements, not a flat append.
2. **Given** a designed round on the canvas, **When** the user pages a table or triggers a component refresh, **Then** the affected component updates in place inside the designed arrangement and the rest of the layout is undisturbed.
3. **Given** the design step fails, times out, or returns invalid output, **When** the round completes, **Then** the canvas shows the legacy append rendering and the conversation is otherwise unaffected (fail-open).
4. **Given** a designed round, **When** the same chat is viewed from a mobile/watch/voice device, **Then** the arrangement degrades per the existing device-adaptation rules without losing essential content.
5. **Given** a chat with designed rounds, **When** the user re-opens the chat later or views the workspace timeline, **Then** the designed arrangement (or its historical state) is restored faithfully.
6. **Given** a round that produces zero or one rich component, **When** the round completes, **Then** the system renders it directly without invoking the design step (no added latency for trivial rounds).

---

### User Story 2 - Trustworthy, consolidated agent catalog (Priority: P2)

A user opening the agent picker sees a curated catalog: the six retired agents (email tracker, grant budgets, grants, LinkedIn, nefarious, NocoDB) are gone from every surface — tool lists, agent visibility settings, audit views of new activity — and the three external ML-service wrappers (classification, time-series forecasting, LLM-factory routing) now appear as one "ML Services" agent. A user who had credentials or per-tool permissions configured for any of the three merged agents finds them carried over without re-entry.

**Why this priority**: Dead and duplicate agents erode trust and clutter every picker, permission screen, and routing decision. Removal also deletes an intentionally-malicious test agent (nefarious) from the production catalog.

**Independent Test**: Boot the stack, list registered agents, and verify exactly the expected set; invoke each formerly-classify/forecaster/llm_factory tool through the consolidated agent; grep the codebase for references to the six removed agents and find none outside version history.

**Acceptance Scenarios**:

1. **Given** a fresh boot, **When** agents register, **Then** the six removed agents do not appear anywhere (catalog, tool lists, routing) and no startup errors reference them.
2. **Given** a user with saved credentials for the classify service, **When** they invoke a classification tool after the merge, **Then** the consolidated agent uses those credentials without re-entry.
3. **Given** the consolidated agent, **When** any tool formerly owned by classify, forecaster, or llm_factory is invoked, **Then** it behaves identically to before the merge (same names, same inputs, same outputs).
4. **Given** the full test suite, **When** it runs after removal, **Then** no test fails or errors due to a dangling reference to a removed agent.
5. **Given** an old chat transcript whose components originated from a removed agent, **When** the user attempts a component refresh on one, **Then** they receive a clear "this capability was retired" message rather than a crash.

---

### User Story 3 - Production confidence via CI (Priority: P2)

A maintainer pushes a branch or opens a PR. Within one pipeline run they learn whether the code lints clean, the full backend test suite passes against a real database, changed code meets the 90% coverage bar, the production container image still builds, a booted container answers its health and readiness probes, the fail-closed production posture still refuses to boot with placeholder secrets, and no secret material was committed. When changes land on main, a versioned container image is published to the project's container registry, ready for the production host (https://sandbox.ai.uky.edu, authenticating against https://iam.ai.uky.edu) to pull.

**Why this priority**: There is currently no CI at all; the constitution's coverage gate is unenforced and "production ready" is unverifiable. Every other pillar of this feature depends on this safety net to prove no drift.

**Independent Test**: Open a PR with an intentional lint error, a failing test, and an under-covered change — the pipeline must fail with distinct, attributable failures; push a clean commit to main — a tagged image appears in the registry.

**Acceptance Scenarios**:

1. **Given** a PR with a lint violation, **When** the pipeline runs, **Then** the lint job fails and names the violation.
2. **Given** a PR whose changed lines are under 90% covered by tests, **When** the pipeline runs, **Then** the coverage gate fails with a per-file report.
3. **Given** a clean commit on main, **When** the pipeline completes, **Then** a container image tagged with the commit (and a moving latest-style tag) is available in the registry.
4. **Given** the built image, **When** the pipeline boots it with deliberately missing/placeholder production secrets and no development override, **Then** the process exits with the documented configuration-error code, proving the fail-closed gate.
5. **Given** the built image booted in development posture with a database, **When** the pipeline probes liveness and readiness endpoints, **Then** both answer successfully.

---

### User Story 4 - Research & Knowledge agents (Priority: P3)

A user asks the assistant to "research X and give me a brief" or "summarize this article." Two new agents handle these without any setup: a web research agent that searches the public web (no API key required by default), fetches sources, and returns a cited brief rendered as rich components (key findings, a sources table, per-topic sections); and a summarizer agent that turns a URL, pasted text, or uploaded document into a TL;DR / key-points / notable-quotes view and can compare two documents side-by-side.

**Why this priority**: Highest cross-ecosystem demand signal (Claude Code packs, OpenClaw/ClawHub, Hermes all lead with research + summarization), and both agents exercise the new adaptive designer with naturally rich multi-component output. Valuable but additive — the product works without them.

**Independent Test**: With zero configuration, ask for research on a public topic and receive a cited multi-component brief; paste a long text and receive a structured summary; both agents appear in the catalog, pass the agent registration gate, and respect tool permissions like any other agent.

**Acceptance Scenarios**:

1. **Given** a fresh install with no extra credentials, **When** a user requests research on a topic, **Then** the web research agent returns a brief citing at least the sources it fetched, rendered as rich components (not a wall of text).
2. **Given** a URL or pasted text, **When** the user asks for a summary, **Then** the summarizer returns a structured TL;DR / key points / quotes view.
3. **Given** the research agent's search backend is unreachable or blocks the request, **When** a search is attempted, **Then** the user receives a clear, actionable error component (and any operator-configured fallback is used first).
4. **Given** both new agents, **When** the platform's permission, audit, and credential systems interact with them, **Then** they behave like any existing agent (scoped tools, audited calls, no special cases).

---

### User Story 5 - A visually appealing web interface (Priority: P3)

A user opening the product sees a modern, cohesive interface: consistent typography and spacing, a refined color system with clear hierarchy, polished cards/tables/charts/metric tiles, and tasteful motion on component arrival and update — all delivered entirely by the server-rendered UI system. No separate frontend application is introduced; the improvement comes from the server's render layer and its static assets.

**Why this priority**: First impressions and daily-use comfort matter, but polish without the designed layouts (US1) would be lipstick on a vertical stack — it depends on the other stories landing.

**Independent Test**: Load the site in a real browser; verify the shell, canvas, and every primitive type render with the refreshed visual system; confirm no new client framework, build step, or frontend application was added.

**Acceptance Scenarios**:

1. **Given** the web target, **When** any of the 26 primitive types renders, **Then** it uses the refreshed visual system (typography, spacing, color, elevation) consistently.
2. **Given** a designed round arriving on the canvas, **When** components appear or update in place, **Then** transitions are smooth (no flash/jank) and respect reduced-motion preferences.
3. **Given** the repository after this feature, **When** its client-side footprint is inspected, **Then** there is no new frontend framework, package manager artifact, or build step — only the existing no-build server-rendered assets.

---

### Edge Cases

- Designer output references a component identity that does not exist in the round or workspace → the reference is dropped and remaining valid content renders; if the output omits any of the round's components entirely, the system repairs the layout by appending the missing components rather than losing data.
- Designer output references the same component twice → only the first reference is honored.
- Designer emits a component type outside the supported palette → the offending node is sanitized per existing validation rules (never crashes the round).
- Designer latency exceeds its budget → round falls back to append rendering; the design attempt is abandoned, not queued.
- A designed arrangement exists and a later round updates one referenced component via single-source supersede → the leaf morphs in place; the arrangement is not regenerated.
- User views workspace timeline mid-design → timeline remains read-only and consistent; designed state appears once committed.
- Two parallel calls to the same tool in one round (duplicate source identities) → both appear in the designed layout as distinct components, as they do today.
- Voice/watch sockets receive a designed round → existing adaptation flattens it; essential text/titles must survive (designer must give composites meaningful titles).
- A user invokes component refresh on a component whose source agent was removed (old transcripts) → clear retirement message, audited, no crash.
- Credentials saved under the three pre-merge agent identities → carried forward; a user with conflicting bundles (e.g. different keys for two of the three services) keeps all three bundles intact since they remain distinct credential sets.
- The keyless web search endpoint rate-limits or serves a CAPTCHA → research agent degrades to its configured fallback or returns an actionable error; it never silently fabricates results.
- Web research agent asked to fetch an internal/private network address → refused by the existing egress-gating rules (server-side request forgery protection).
- A document submitted for summarization exceeds size limits → truncated with an explicit notice in the output, never a silent partial summary.
- CI runs on a PR that touches no Python files → coverage gate passes vacuously rather than failing on an empty denominator.
- Registry publish on main fails (registry outage) → verification gates still report; publish failure is distinct and retryable.

## Requirements *(mandatory)*

### Functional Requirements

#### Agent removal

- **FR-001**: The system MUST no longer contain the email_tracker, grant_budgets, grants, linkedin, nefarious, or nocodb agents: their directories, their auto-discovery/registration, and every out-of-directory reference (REST endpoints, tests, quality-audit fixtures, knowledge files, routing patterns, stub registries, configuration examples, documentation) MUST be removed or rewritten so no dangling reference remains.
- **FR-002**: The LinkedIn OAuth REST flow (authorize/callback/status endpoints and associated credential schema examples) MUST be removed with the linkedin agent; no orphaned endpoint may remain reachable.
- **FR-003**: Stored per-user rows (ownership, scopes, tool overrides, credentials) for removed agent identities MUST be inert after removal (never surfaced, never breaking boot or queries) and MUST be cleaned up by an idempotent, automatically-run migration with a documented rollback note.
- **FR-004**: Historical data referencing removed agents (audit events, chat transcripts, saved components) MUST remain viewable; re-execution attempts against removed agents MUST yield a clear retirement error and an audit record, not a failure cascade.
- **FR-005**: The full test suite MUST pass after removal with all removal-blast-radius test files deleted or pruned (grants test package, nefarious delegation test, nefarious quality-audit fixture usages, removed entries in the no-behavior-change harness).

#### Agent consolidation

- **FR-006**: The classify, forecaster, and llm_factory agents MUST be replaced by a single consolidated ML-services agent exposing the union of their tools with unchanged input schemas, scopes, and output behavior. Tool names remain unchanged except where the merge creates a name collision (five dataset/job verbs shared by the classification and forecasting services); colliding names gain a service prefix, and stored per-user tool permissions for the old names MUST be remapped automatically. *(Planning finding 2026-06-11: a flat tool namespace cannot hold two `submit_dataset` tools — see research.md R7.)*
- **FR-007**: The consolidated agent MUST be built on one shared external-service-wrapper foundation (single credential-probe pattern, retry shim, and egress-gated HTTP usage) rather than three copies.
- **FR-008**: The three credential bundles (classification service URL/key, forecaster service URL/key, LLM-factory service URL/key) MUST remain distinct and MUST surface through the existing credential-management experience; credentials and per-user tool permissions saved under the three retired agent identities MUST carry forward to the consolidated agent via an idempotent, automatically-run remap migration.
- **FR-009**: Knowledge files (capabilities/techniques) for the three merged agents MUST be carried into the consolidated agent's knowledge identity so routing quality does not regress.
- **FR-010**: Existing per-agent test suites for the three merged agents MUST be preserved (relocated/adapted), not deleted, and MUST pass against the consolidated agent.

#### New plug-and-play agents (Research & Knowledge pack)

- **FR-011**: A web research agent MUST provide at minimum: a web search capability, a page-fetch capability, and a research-brief capability that synthesizes fetched sources into a cited brief rendered as rich components.
- **FR-012**: The web research agent MUST work with zero configuration via a keyless public search path, MUST prefer an operator-configured search provider when present, and MUST degrade with actionable errors when search is unavailable — never fabricating sources.
- **FR-013**: All outbound HTTP from the new agents MUST go through the platform's existing egress-gated HTTP layer (SSRF protection, private-host blocking) and MUST enforce bounded fetch sizes and timeouts.
- **FR-014**: A summarizer agent MUST provide at minimum: summarize-a-URL, summarize-provided-text/document, and compare-two-documents capabilities, producing structured multi-section output (TL;DR, key points, notable quotes) and explicit truncation notices when inputs exceed limits.
- **FR-015**: Both new agents MUST follow the existing plug-and-play agent contract (auto-discovered agent module, tool registry, agent card, registration key enforcement) and MUST integrate with permissions, auditing, scoping, and ROTE with no special cases; they MUST add zero new third-party dependencies.
- **FR-016**: Both new agents MUST ship with capability/technique knowledge files and test suites meeting the constitution's coverage bar.

#### Adaptive UI designer

- **FR-017**: After each chat round that produces two or more rich top-level components, the system MUST invoke a design pass that composes the round's outputs into a single arranged interface; rounds with fewer components MUST render directly without the design pass.
- **FR-018**: The design pass MUST treat the round's tool-produced components as immutable referenced leaves: each appears exactly once, identified by its workspace component identity; the designer MUST NOT rewrite, merge, or drop tool-produced content. If the design output omits any round component, the system MUST repair the layout by appending the missing components.
- **FR-019**: The designer MAY author supplemental components (headline metrics, narrative text, dividers, grouping containers such as grids/tabs/cards/collapsibles) drawn ONLY from the existing primitive palette; supplemental components MUST carry deterministic, namespaced identities so re-designed rounds update rather than duplicate them.
- **FR-020**: The full registered primitive palette (every renderable type in the renderer registry — 31 since the dashboard primitives landed) MUST be available to the design pass; the existing narrower validation whitelists MUST be widened to match the renderer's registry so validation and rendering agree.
- **FR-021**: Component identity semantics MUST be preserved end-to-end: in-place refresh, table pagination, single-source supersede, and component re-execution provenance MUST behave identically for components inside a designed arrangement as they do today for flat-appended components.
- **FR-022**: On designer failure of any kind (LLM unavailable, timeout, invalid or unparseable output, validation failure), the round MUST render via the legacy append path with no user-visible error and no data loss; the failure MUST be logged with enough structure to diagnose (fail-open).
- **FR-023**: The design pass MUST run within a bounded time budget; exceeding it triggers the fallback. The budget MUST be operator-configurable with a sensible default.
- **FR-024**: The design pass MUST compose for the richest device target; per-device adaptation MUST continue to be applied downstream per socket exactly as today (no designer awareness of individual sockets), and designer-authored composites MUST carry meaningful titles so degraded targets (watch/voice) retain useful content.
- **FR-025**: Designed arrangements MUST persist with the chat workspace: re-opening a chat restores the arrangement; per-turn workspace snapshots and the read-only timeline reflect designed state; deleting a chat removes its arrangements.
- **FR-026**: The canvas-context summary provided to the conversational model MUST continue to describe the live workspace accurately when arrangements exist (components remain individually listed; arrangements do not hide them).
- **FR-027**: The fixed per-round boilerplate (always-"Analysis" card, fixed "Summary" card on long rounds) MUST be replaced: chat-panel narrative keeps flowing to the chat panel, but titles/containers MUST be contextual rather than hard-coded; the "Reasoning" disclosure remains available but MUST NOT be duplicated by the designer.
- **FR-028**: The designer MUST use the same LLM configuration resolution as the conversation that produced the round (per-user session configuration when present, operator default otherwise), and its calls MUST be audited consistently with existing LLM-call auditing.
- **FR-029**: The adaptive designer MUST be controlled by an operator feature flag, enabled by default, whose disabled state restores today's behavior exactly.
- **FR-030**: Designer activity MUST be observable: structured logs for invocation, success, fallback reason, and latency; failures MUST be diagnosable from logs alone.

#### Visual refresh (server-rendered web target)

- **FR-031**: The web target's shell and static assets MUST receive a cohesive visual refresh (typography scale, spacing system, color tokens with clear hierarchy, elevation, focus states, smooth component-arrival/update transitions honoring reduced-motion preferences) applied across all registered primitive renderers (26 at the time of the refresh; 31 today) and the chrome surfaces.
- **FR-032**: The refresh MUST introduce no frontend framework, package management, or build step: only the existing server-rendered HTML/CSS/JS assets may change, and they MUST remain lint-clean per the constitution.
- **FR-033**: The refreshed rendering MUST remain correct on the existing device classes (browser, tablet, mobile and the degraded watch/TV/voice shapes) and MUST preserve all existing interactive behaviors (actions, forms, pagination, uploads).

#### Production CI

- **FR-034**: The repository MUST gain a CI pipeline that runs on every pull request and push to main, with independently-reported jobs for: lint (repo-root configuration), the complete backend test suite (default suite excluding live-orchestrator integration markers, plus all module suites) against a real database service in development posture, and a changed-code coverage gate enforcing the constitution's 90% threshold.
- **FR-035**: The pipeline MUST build the production container image on every run, proving the image (including its model-bake step) still builds from a clean checkout.
- **FR-036**: The pipeline MUST boot-smoke the built image: liveness and readiness probes MUST answer in development posture with a database, and a production-posture boot with placeholder/missing secrets MUST exit with the documented configuration-error code (proving the fail-closed gate).
- **FR-037**: The pipeline MUST include a secret scan that fails on committed credential material.
- **FR-038**: On pushes to main that pass all gates, the pipeline MUST publish the image to GitHub Container Registry with both an immutable commit-derived tag and a moving latest-style tag; publish failures MUST be distinguishable from verification failures.
- **FR-039**: Production deployment documentation MUST be updated with the registry-pull deployment path for https://sandbox.ai.uky.edu (TLS reverse proxy posture, public origin configuration, Keycloak at https://iam.ai.uky.edu per the existing realm-settings document); no live deploy job is included.
- **FR-040**: The project constitution MUST be amended to encode the CI pipeline's gates as the enforceable definition of the existing CI requirements (coverage, lint, production readiness), keeping templates in sync per its governance rules.

### Key Entities

- **Canvas Arrangement (new)**: A per-chat, per-round description of how the round's components are laid out — a tree of grouping/garnish elements whose leaves reference workspace components by identity. Persisted with the workspace, included in per-turn snapshots, restored on chat load, removed with the chat. Never owns tool-produced content; only references it.
- **Designer Garnish Component (new)**: A designer-authored supplemental component (headline metric, narrative text, divider, grouping container) with a deterministic namespaced identity, persisted alongside the arrangement, replaced — not duplicated — when a round is re-designed.
- **Consolidated ML-Services Agent (changed)**: Single agent identity owning the union of classify/forecaster/llm_factory tools; three distinct credential bundles; carries forward per-user scopes, overrides, credentials, and knowledge from the three retired identities via migration.
- **Web Research Agent / Summarizer Agent (new)**: Standard plug-and-play agents per the existing contract; no new stored entities beyond standard registration/ownership rows.
- **Removed Agent Identity (changed)**: The six retired identities; their historical artifacts (audit rows, transcripts, saved components) remain readable, their stored permission/credential rows are cleaned by migration, and any re-execution against them resolves to a retirement error.
- **CI Pipeline & Published Image (new)**: The verification gate set and the registry-published, version-tagged container image that production pulls.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of chat rounds producing ≥2 rich components render as a designed arrangement when the designer is enabled and healthy; 0 rounds lose or alter tool-produced content (every round component present, byte-identical, in the arrangement or its repair-append).
- **SC-002**: With the designer disabled or failing, 100% of rounds render identically to pre-feature behavior — verified by the existing no-behavior-change harness.
- **SC-003**: The design pass adds no more than its configured time budget to any round (default ≤ 8 seconds, typical ≤ 3) and never blocks a round beyond it.
- **SC-004**: Per-component refresh, table pagination, supersede-in-place, timeline view, and chat re-open behave correctly in 100% of exercised designed-round test scenarios.
- **SC-005**: Zero references to the six removed agents remain in the codebase (verified by automated search in CI-able form), and the boot sequence registers exactly the expected agent set with zero errors.
- **SC-006**: All tools formerly owned by classify/forecaster/llm_factory respond through the consolidated agent with unchanged contracts; previously saved credentials and tool permissions work without user re-entry in 100% of migration test cases.
- **SC-007**: Both new agents produce cited/structured rich-component output with zero configuration on a fresh install; their unreachable-backend paths produce actionable errors in 100% of failure-injection tests.
- **SC-008**: The CI pipeline distinguishes and reports lint, test, coverage, build, smoke, secret-scan, and publish outcomes independently; an intentionally bad PR (lint error + failing test + under-covered change) fails with three distinct attributable failures; a clean main push yields a pullable registry image.
- **SC-009**: The changed-code coverage gate enforces ≥90% on every PR; the full suite passes in the container after all removals/merges with zero dangling-reference failures.
- **SC-010**: The live site, loaded in a real browser, presents the refreshed visual system on every primitive type and the chrome, with smooth component arrival/update and no new client-side framework or build artifacts in the repository.

## Assumptions

- The designer runs only for rounds with ≥2 rich top-level components (decided default); single-component rounds keep direct rendering for zero added latency.
- The designer composes once per round for the richest target; ROTE's existing per-socket adaptation is the sole device-variation mechanism (no per-device design passes).
- Designer time budget defaults to 8 seconds with an operator-configurable override; the budget is consumed concurrently with nothing else (the round is otherwise complete when design begins).
- The keyless search path uses a public HTML search endpoint with conservative request behavior; an operator-configured search provider key (existing credential mechanisms) takes precedence when present. Search-provider fragility is accepted and handled by the actionable-error requirement.
- "Plug and play" means: drop-in directory following the existing agent contract, zero mandatory configuration, automatic discovery/registration under the existing agent-key enforcement.
- The consolidated agent reuses one of the existing static port slots; the port range compacts automatically since it is derived from the directory count.
- medical, dice_roller, etf_tracker_1, general, weather, journal_review, and connectors are explicitly out of scope for consolidation or removal in this feature (user decision).
- GitHub-hosted runners are sufficient; no self-hosted runner or live deploy credentials exist for sandbox.ai.uky.edu, so deployment remains a documented manual pull (user decision).
- The GHCR image is the deployment artifact; the production host has (or will be granted) pull access to the repository's package registry.
- Coverage tooling for the CI gate is a development-time addition to the pipeline environment only, not a runtime dependency of the product (consistent with the constitution's dependency rule; flagged in the PR per its documentation requirement).
- The constitution amendment (FR-040) is a MINOR governance change expanding the Development Workflow/CI sections, authorized by the user in this session.
- Visual refresh scope is the web target only; native/watch/TV/voice targets continue to rely on ROTE adaptation of the same primitives.
