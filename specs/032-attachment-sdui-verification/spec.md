# Feature Specification: Agentic File-Upload SDUI & Delegated-Authority Verification

**Feature Branch**: `032-attachment-sdui-verification`
**Created**: 2026-06-15
**Status**: Draft
**Input**: User description: "Create a spec to check the file upload SDUI components being output from user queries. Test user queries that you come up with that a normal person, a researcher, a medical person, or a government official might use. Make sure the interface produces something tangible that other AI's can't achieve. Maintain focus on Delegated Authority (test via the keycloak credentials in the .env) and the frontend UI is generated only from the backend components with little to no rendering code on the frontend. you should mirror the agentic behavior of openclaw, hermes agent, and other agentic frameworks to accomplish this."

## Overview

This feature delivers an **autonomous agentic verification harness** that proves, end to end, that AstralBody's signature capability works as claimed: a user uploads a file in chat, asks a natural-language question about it, and receives back **tangible, interactive, server-generated UI** — not a wall of text — produced strictly **on that user's behalf under scoped delegated authority**, persisted in their workspace, and recorded in a tamper-evident audit trail.

The harness behaves like a modern agentic framework (it plans, acts, observes, and verifies in a closed loop, then adversarially re-checks its own conclusions and emits structured verdicts). It exercises four representative personas — an everyday person, a researcher, a medical professional, and a government official — each with realistic files and questions. Its purpose is to demonstrate and continuously re-confirm the three properties that distinguish this product from a generic text-only assistant: **(1) tangible server-driven UI**, **(2) delegated authority**, and **(3) a near-zero-logic frontend**.

This is a *verification and demonstration* feature. It does not change the upload, parsing, rendering, or authorization behavior of the product; it asserts that behavior is correct and produces evidence a stakeholder can read.

## Clarifications

### Session 2026-06-15 (resolved by informed default — confirm or override during `/speckit-clarify`)

- Q: Should the delegated-authority checks run against the **real Keycloak realm** using the configured client credentials, or against development mock auth? → A: **Both, with real as the goal.** The harness MUST exercise the real delegated-authority code paths (token exchange, the agent-as-actor claim, per-user scope/permission gates, ownership and admin gates, audit chaining). When the configured Keycloak credentials and connectivity are available it authenticates against the real realm; when only the development posture is available it runs against mock auth, which still exercises the permission, ownership, and admin gates but not the live token exchange. The report MUST state which mode each run used. Credentials are read from the environment by name only and never embedded or logged.
- Q: What form does the harness take — an in-process automated suite, or an external autonomous agent that drives the live application like a real client? → A: **Both surfaces, one harness.** The default, always-runnable path drives the orchestrator **in-process** (capturing the same server→client UI messages a browser would receive), so it runs in continuous integration without a live deployment. The harness MUST additionally be able to run as an **external agentic client** against the live endpoints to prove the thin-client and delegated-authority claims through the real network surface.
- Q: How is the "medical professional" persona handled given health-data sensitivity? → A: **Synthetic data only.** All medical-persona inputs are clearly synthetic and contain no real protected health information. The harness MUST additionally confirm that the product's health-data protections engage on health-categorized content, and MUST never require, store, or transmit real patient data.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Prove file-upload queries produce tangible, server-driven UI across real-world personas (Priority: P1)

Acting autonomously as each of four personas — an everyday person, a researcher, a medical professional, and a government official — the harness signs in as an authenticated user, uploads a realistic file, and asks a natural-language question about it (e.g. "show me where my money went last month," "plot dose versus response in this dataset," "flag any out-of-range labs," "break this budget down by department and show the year-over-year change"). For each, it captures what the application actually sends back to the client and confirms the answer is delivered as **genuine interactive UI components** — tables, charts, metric tiles, tabbed summaries, key-value cards, timelines, badges — that are derived from the file's real contents, persisted in the user's workspace, and re-runnable, rather than as plain prose.

**Why this priority**: This is the heart of the request and the product's core promise. A normal chatbot can describe a spreadsheet; AstralBody renders an interactive, persisted dashboard from it. Demonstrating that this happens reliably, from real files, for the kinds of people who would actually use it, is the single most valuable thing this harness can prove. It stands alone as a complete, demonstrable MVP: even with nothing else, it produces evidence that file-upload queries yield tangible UI.

**Independent Test**: Run the harness for one persona end to end — sign in, upload that persona's file, send that persona's query — and confirm the captured response contains one or more interactive components whose content reflects the uploaded file, that those components are persisted in the user's workspace, and that the same flow for a text-only assistant could not produce them. Fully testable with no other story implemented.

**Acceptance Scenarios**:

1. **Given** the harness is authenticated as the everyday-person persona, **When** it uploads a bank/credit-card statement and asks where the money went, **Then** the captured response contains interactive components derived from the statement (e.g. a transactions table, a category breakdown chart, and summary metric tiles) rather than only prose, and those components persist in the user's workspace.
2. **Given** the researcher persona, **When** it uploads a results dataset and asks to plot a relationship and report summary statistics, **Then** the response includes a chart and a table built from the dataset's actual values plus at least one summary metric, and the chart/table can be re-executed (e.g. re-filtered) as a workspace component.
3. **Given** the researcher persona, **When** it uploads a paper and asks for a summary with key quotes, **Then** the response is delivered as a structured multi-section component (e.g. tabbed "summary / key points / quotes") rather than an undifferentiated block of text.
4. **Given** the medical persona with clearly synthetic lab data, **When** it asks to flag out-of-range results, **Then** the response presents the panel as a structured component that visually distinguishes out-of-range values, and no real patient data is required at any point.
5. **Given** the government-official persona, **When** it uploads a public budget and asks for a departmental breakdown with year-over-year change, **Then** the response includes a breakdown table, a comparison chart, and metric tiles built from the file, persisted as a shareable workspace dashboard.
6. **Given** any persona run, **When** the harness inspects the captured response, **Then** every rendered component's type is one of the product's recognized component types and every component carries a stable identity that ties it to the source file and the tool that produced it.
7. **Given** an uploaded file of a type the product cannot yet read, **When** the persona asks about it, **Then** the harness observes the safe auto-creation path engage (a parser capability is drafted, self-tested, and held for administrator approval) rather than a silent failure, and records that outcome as evidence rather than a harness error.

---

### User Story 2 - Prove delegated authority is enforced on every file-upload interaction (Priority: P2)

The harness verifies that everything in Story 1 happens **on behalf of the authenticated user, under that user's scoped permissions, and nobody else's**. Using the configured Keycloak identities (and the development mock identities as a fallback), it confirms that an agent reads and acts only within the scopes a user has granted; that one user can never read or reference another user's attachment; that privileged actions (such as approving an auto-created parser) require an administrator and cannot be self-approved by the uploader; and that each interaction is recorded in the append-only audit trail with the acting agent and the on-behalf-of user both attributable.

**Why this priority**: Delegated authority is the explicit focus of the request and the property most responsible for the product being trustworthy with real people's financial, research, medical, and government documents. It is P2 because it builds on the Story 1 ability to drive persona flows, but it is independently valuable: proving that the authorization boundaries hold is meaningful even before the full tangible-UI catalogue is exercised.

**Independent Test**: With two distinct authenticated identities and one administrator identity, drive a file-upload flow as user A, then attempt to reference A's attachment as user B and confirm refusal; attempt a scoped tool action the user has not granted and confirm it is withheld; trigger an auto-created-parser approval as a non-administrator and confirm it is denied; and confirm each of these produced an audit record attributing the action to the right principal. Testable independently of the full persona catalogue.

**Acceptance Scenarios**:

1. **Given** user A has uploaded a file, **When** user B attempts to reference that file in a message, **Then** the reference is refused, the file is treated as not found, and the denial is recorded in the audit trail.
2. **Given** a user who has not enabled a particular capability scope for an agent, **When** a query would require a tool in that scope, **Then** that tool is not made available to the agent for that user and is not executed on their behalf.
3. **Given** an interactive component produced earlier by a tool the user has since disabled, **When** the harness re-triggers that component's action, **Then** the action is refused under the same permission gate as the original chat path and the refusal is audited.
4. **Given** an auto-created parser awaiting approval, **When** a non-administrator (including the uploading user) attempts to approve it, **Then** approval is refused; **When** an administrator approves it, **Then** it goes live and becomes available to the fleet, and both outcomes are audited.
5. **Given** any successful file-upload interaction, **When** the harness inspects the audit trail, **Then** there is a record that attributes the action to the acting agent and the on-behalf-of user, and the audit records form an unbroken, tamper-evident chain.
6. **Given** the harness is configured with the real Keycloak realm, **When** it drives a persona flow, **Then** the agent's authority to act is obtained through the real delegated-authority exchange (the agent acts as a delegate of the user, scoped to the user's enabled capabilities) rather than with the user's own credentials.
7. **Given** a run executed in development mock-auth mode, **When** the report is produced, **Then** it clearly labels which authority checks were exercised against real delegated authority versus mock, so no reader mistakes a mock run for a real-realm guarantee.

---

### User Story 3 - Prove the interface is generated only from backend components, with a near-zero-logic frontend (Priority: P3)

The harness verifies the product's structural differentiator: the user-facing interface is produced entirely by the backend, and the client does little more than paint server-provided output and forward user actions. It confirms that every component a persona receives is described by the backend's own component vocabulary and arrives as server-produced markup; that the client contains no component-construction logic (no per-type "build this widget" code, no client-side rendering framework); and that the same backend output is what drives the interface, so the "intelligence to UI" mapping lives on the server where it can be governed and audited.

**Why this priority**: This is what makes the tangible UI reproducible, governable, and hard for a generic assistant to replicate: because the UI is server-authored, it can be permission-gated, audited, persisted, device-adapted, and re-executed centrally. It is P3 because it is an architectural assurance rather than a direct user task, but it underpins the credibility of Stories 1 and 2 and the "other AIs can't achieve this" claim.

**Independent Test**: Capture the backend output for a persona response and confirm each component is expressed in the backend's recognized component vocabulary and accompanied by server-produced markup; then inspect the client surface and confirm it has no component-construction logic and no client-side rendering framework — it only injects server output and forwards actions. Testable independently using captured output plus a static inspection of the client surface.

**Acceptance Scenarios**:

1. **Given** any persona response, **When** the harness inspects each delivered component, **Then** its type belongs to the backend's published set of recognized component types and nothing outside that set appears.
2. **Given** any persona response, **When** the harness inspects how the component reached the client, **Then** it arrives as server-produced markup (and/or the backend's structured component description), not as instructions for the client to construct the component itself.
3. **Given** the client surface, **When** the harness inspects it statically, **Then** it finds no per-component construction logic and no client-side rendering framework — only generic injection of server output and forwarding of user actions.
4. **Given** the same backend response delivered to differently-capable devices, **When** the harness compares outputs, **Then** the differences are explained by backend-side adaptation of the components (not by client-side rendering decisions).
5. **Given** a component that carries an interactive action, **When** the harness inspects it, **Then** the action is expressed as backend-defined intent that the client forwards, and re-runs through the backend's permission-gated path.

---

### Edge Cases

- **Unsupported file type for a persona**: when a persona uploads a type with no existing reader, the harness must record the safe auto-creation outcome (draft → self-test → pending administrator approval) as an expected result, not crash and not report a false failure.
- **Parse failure on a supported type** (corrupt, password-protected, truncated, or image-only document): the harness must observe a clear, specific error surfaced to the user and confirm the conversation can continue, and must not count a graceful error as a tangible-UI success.
- **Empty or text-only document routed to visual understanding**: the harness verifies the response is non-empty and meaningful rather than a silent empty result.
- **Prose-only answer is legitimately correct** (e.g. a yes/no question): the harness must distinguish "appropriately answered in prose" from "failed to produce UI when UI was warranted," so it does not penalize correct short answers — the tangible-UI assertions apply to queries that warrant a component.
- **Real Keycloak unreachable**: the harness degrades to development mock auth, clearly labels the run, and does not report real-realm delegated-authority guarantees it did not actually exercise.
- **Self-verification disagreement**: when the harness's initial verdict and its adversarial re-check disagree, the result is reported as "uncertain" with both pieces of evidence rather than silently resolved to pass.
- **Non-determinism in model output**: because the underlying assistant is generative, the harness must assert on structural and authority properties (component types present, content derived from the file, permission denied where expected) rather than exact wording, and must bound retries so a flaky generation does not loop indefinitely.
- **Secret exposure**: the harness must fail safe if a credential value would ever appear in a captured artifact, log, or report — redacting it and flagging the run.
- **Cross-user leakage via persistence**: the harness confirms that a component or attachment persisted for one user never appears in another user's workspace or history.
- **Termination**: every persona run must reach an objective pass/fail/uncertain verdict within a bounded number of steps and a bounded time/turn budget; the harness must never declare success merely because the agent "thinks" it is done.

## Requirements *(mandatory)*

### Agentic verification behavior (cross-cutting — mirrors modern agentic frameworks)

- **FR-001**: The harness MUST operate as an autonomous closed-loop agent for each scenario: it plans the verification (which file, which query, which properties to expect), acts (signs in, uploads, queries), observes (captures the application's actual responses, the persisted workspace state, and the audit trail), and verifies (evaluates the observations against expected properties) — never asserting on a step it did not actually drive and observe.
- **FR-002**: Each verification probe and check the harness performs MUST be expressed as a structured, inspectable, replayable unit (a named check with typed inputs and a typed result), so a reviewer can see exactly what was asserted and reproduce it.
- **FR-003**: The harness MUST adversarially re-verify its own positive findings: after concluding that a property holds (e.g. "this is tangible server-driven UI" or "authority was enforced"), it MUST run an independent check that attempts to falsify that conclusion before recording a pass.
- **FR-004**: Every finding MUST be emitted as a machine-readable verdict with at minimum an outcome (pass / fail / uncertain), the evidence it rests on, a confidence indication, and a reference back to the scenario, persona, and check that produced it.
- **FR-005**: Completion MUST be gated on objective, automated checks rather than the agent's own declaration that it is finished; each run MUST enforce a hard upper bound on steps and on time/turns, and MUST exit with a definite verdict (including "uncertain") rather than looping.
- **FR-006**: On a failed or inconclusive check, the harness MAY retry or refine, but MUST carry forward a record of the prior attempt's failure so a retry is informed rather than blind, and MUST cap the number of retries.
- **FR-007**: The harness MUST generate its probe queries conditioned on the stated persona (everyday person, researcher, medical professional, government official) so coverage reflects realistic usage rather than generic prompts, and MUST keep the persona catalogue extensible so new personas can be added without redesigning the harness.
- **FR-008**: The harness MUST persist its run state and evidence to a durable, human-inspectable artifact (a run record and report) so a run can be reviewed after the fact and progress is not lost if the process restarts.

### Persona-driven tangible-output verification (US1)

- **FR-009**: For each persona, the harness MUST drive at least one complete flow of: authenticate → upload a realistic file → send a natural-language query about it → capture the response the application sends to the client.
- **FR-010**: The harness MUST confirm that, for queries that warrant it, the response is delivered as one or more **interactive components** (such as tables, charts, metric tiles, tabbed summaries, key-value cards, timelines, badges, or ratings) and not solely as prose.
- **FR-011**: The harness MUST confirm that the delivered components are **derived from the uploaded file's actual contents** (e.g. values, rows, figures, or text that originate in the file), not generic or fabricated content.
- **FR-012**: The harness MUST confirm that delivered components are **persisted in the user's workspace** with a stable identity that ties each component to its source file and the tool that produced it, and that they survive reloading the conversation.
- **FR-013**: The harness MUST confirm that at least one delivered interactive component is **re-executable** (its action can be re-triggered to update it in place) and that re-execution flows through the product's permission-gated path.
- **FR-014**: The harness MUST cover, across the persona catalogue, a representative breadth of the product's tangible component types and of common file categories (at minimum: tabular data, a document, and an image), and MUST record which component types and file categories were actually exercised.
- **FR-015**: The harness MUST treat a graceful, specific error on an un-parseable file, and an appropriately-prose answer to a question that does not warrant UI, as **correct outcomes** — distinct from a failure to produce warranted UI.

### Delegated-authority conformance (US2)

- **FR-016**: The harness MUST verify that an agent acts only within the capability scopes the authenticated user has granted, and that a query requiring an ungranted scope does not cause that capability to be exercised on the user's behalf.
- **FR-017**: The harness MUST verify cross-user isolation: a user can never read, reference, or receive a component or attachment belonging to another user, including via persisted workspace or conversation history.
- **FR-018**: The harness MUST verify that privileged lifecycle actions tied to file handling — specifically approving an auto-created parser — require an administrator, cannot be self-approved by the uploading user, and are refused for non-administrators.
- **FR-019**: The harness MUST verify that the agent's authority to act on the user's behalf is obtained as a **delegation** (the agent is recorded as acting as a delegate of the user, scoped to the user's enabled capabilities) rather than by the agent assuming the user's own identity or using the user's raw credentials.
- **FR-020**: The harness MUST verify that security-relevant decisions in the file-upload path (successful action, denied cross-user reference, denied scope, denied non-admin approval, rejected upload, parse failure) are recorded in the append-only audit trail, attributing each to the acting agent and the on-behalf-of user, and that the audit records form an unbroken, tamper-evident chain.
- **FR-021**: The harness MUST be able to exercise these checks against the **real configured identity provider** using credentials supplied through the environment, and MUST fall back to the development identities only when the real provider is unavailable — labelling every run with which mode it used.
- **FR-022**: The harness MUST read all identity/provider credentials from the environment **by name only**, MUST NOT embed credential values in code, fixtures, logs, captured artifacts, or reports, and MUST redact and flag any run in which a credential value would otherwise have been exposed.

### Backend-only-UI / thin-client assurance (US3)

- **FR-023**: The harness MUST confirm that every component delivered to the client is expressed in the backend's own published vocabulary of recognized component types, and that nothing outside that published set is delivered.
- **FR-024**: The harness MUST confirm that components reach the client as **server-produced output** (server-authored markup and/or the backend's structured component description) rather than as instructions for the client to construct components itself.
- **FR-025**: The harness MUST confirm, by static inspection of the client surface, that the client contains **no per-component construction logic and no client-side rendering framework** — only generic injection of server output and forwarding of user actions — and MUST record an objective measure of client-side rendering logic (its presence/absence) as evidence.
- **FR-026**: The harness MUST confirm that device-specific differences in the interface are attributable to **backend-side adaptation** of components, not to client-side rendering decisions.
- **FR-027**: The harness MUST confirm that an interactive action on a component is expressed as **backend-defined intent** that the client merely forwards, and that activating it re-enters the backend's permission-gated path.

### Differentiation, reporting & operational constraints (cross-cutting)

- **FR-028**: The harness MUST produce a consolidated report that, per persona and per property (tangible UI, delegated authority, backend-only UI), states the verdict, the evidence, and the run mode (real provider vs. development), in a form a non-technical stakeholder can read.
- **FR-029**: The report MUST explicitly articulate the **differentiation claim** — enumerating, from the evidence actually collected, the capabilities demonstrated that a text-only assistant cannot provide (interactive components from real file content, persisted and re-executable, produced under scoped delegated authority with a tamper-evident audit trail, with safe on-demand capability creation for unknown formats) — and MUST base that enumeration only on what the run actually observed.
- **FR-030**: The harness MUST be runnable both **in-process** (driving the application and capturing the same component messages a client would receive, suitable for continuous integration without a live deployment) and as an **external client** against the live endpoints, and MUST reuse the product's existing verification primitives (the in-process driving and response-capture mechanism, and the existing self-test/observation flow) rather than introducing a parallel mechanism.
- **FR-031**: The harness MUST be safe to run repeatedly: it MUST isolate its own users, conversations, attachments, and any drafted capabilities so runs do not pollute real user data, and MUST clean up or clearly namespace its artifacts.
- **FR-032**: The harness MUST NOT require any change to the product's upload, parsing, rendering, authorization, or audit behavior, and MUST NOT add any new third-party runtime dependency to the product; it is an observer and driver, not a modification of the system under test.
- **FR-033**: The harness MUST fail safe and report a clear, actionable diagnosis when the system under test is unavailable, misconfigured, or returns an unexpected shape, distinguishing "the product is wrong" from "the harness could not observe."

### Key Entities *(include if feature involves data)*

- **Persona**: A named, realistic user profile (everyday person, researcher, medical professional, government official) with an associated set of representative files and natural-language queries and a description of the tangible outcomes expected. Extensible — new personas can be added.
- **Verification Scenario**: One persona-conditioned flow — a file, a query, an authenticated identity, the run mode, and the set of properties expected to hold (tangible UI, authority enforcement, backend-only UI). The atomic unit the harness plans, drives, and verifies.
- **Probe / Check**: A single structured, replayable assertion with typed inputs and a typed result (e.g. "response contains an interactive component derived from the file," "cross-user reference is refused," "client surface contains no component-construction logic"). Includes its adversarial counter-check.
- **Captured Evidence**: The concrete observations a scenario produced — the component messages the application sent to the client, the persisted workspace state, the audit records, and any static client-surface inspection results — retained so a verdict can be justified and reproduced.
- **Verdict**: A machine-readable result for a check or scenario: outcome (pass / fail / uncertain), the evidence it rests on, a confidence indication, the run mode, and references to the persona, scenario, and check.
- **Run Record / Report**: The durable, human-inspectable artifact aggregating verdicts and evidence across all personas and properties for one execution, including the differentiation summary and the real-vs-mock run labelling. Credential values never appear in it.
- **Delegated-authority assertion**: The specific evidence that the agent acted as a scoped delegate of the user — the recorded acting-agent and on-behalf-of-user attribution, the scope that authorized the action, and the audit chain linkage.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of the four personas, the harness completes an authenticate → upload → query → observe flow and reaches a definite verdict (pass / fail / uncertain) within its bounded step and time budget, with no run left hanging.
- **SC-002**: For every persona query that warrants it, the harness confirms the response contains at least one interactive component derived from the uploaded file's real contents, and records the specific component types observed.
- **SC-003**: Across the full persona catalogue, the harness exercises at least the three core file categories (tabular data, document, image) and a representative breadth of tangible component types, and the report names exactly which categories and types were observed (no unsubstantiated coverage claims).
- **SC-004**: The harness demonstrates at least one persisted, re-executable component per applicable persona, and confirms it survives reloading the conversation.
- **SC-005**: 100% of cross-user reference attempts are refused, with zero instances of one user receiving another user's attachment or component, including through persistence or history.
- **SC-006**: 100% of attempts to use an ungranted capability scope on a user's behalf are withheld, and 100% of non-administrator attempts to approve an auto-created parser are refused.
- **SC-007**: 100% of successful and denied file-upload interactions produce an audit record attributing the action to the acting agent and the on-behalf-of user, and the audit chain verifies as unbroken for every run.
- **SC-008**: Every delivered component's type is within the backend's published recognized-type set (zero out-of-vocabulary components), and the harness records an objective measurement that the client surface contains no per-component construction logic and no client-side rendering framework.
- **SC-009**: Every positive property verdict is corroborated by an independent adversarial counter-check; any verdict whose counter-check disagrees is reported as "uncertain," and the proportion of uncertain verdicts is reported.
- **SC-010**: Every run is labelled with its authority mode (real provider vs. development mock), and the report makes no real-realm delegated-authority guarantee for a run that executed in mock mode.
- **SC-011**: Zero credential values appear in any code, fixture, log, captured artifact, or report across all runs; any near-exposure is redacted and flagged.
- **SC-012**: The harness runs in continuous integration with no live deployment (in-process mode) and, when pointed at a live deployment, reproduces the same property verdicts through the real network surface.
- **SC-013**: Running the harness introduces zero changes to the product's upload/parse/render/authorization/audit behavior and zero new third-party runtime dependencies, and leaves no residual harness data in real users' workspaces or history.

## Assumptions

- **Verification, not modification**: This feature observes and drives the existing system. The upload endpoint, user-scoped attachment storage, accepted-type/size definitions, the per-category reader capabilities, the server-driven component vocabulary and renderer, the workspace persistence and adaptive arrangement, the delegated-authority model, and the append-only audit trail already exist and are consumed as the system under test — not rebuilt.
- **Reuse of existing verification primitives**: The in-process driving and response-capture mechanism used by the product's self-test flow, the existing observation/summarization of captured responses, and the development mock-auth identities are reused as the foundation of the harness, rather than building a parallel driver. The external-client mode reuses the product's normal client-facing endpoints.
- **Authority modes** (per clarification): The harness targets the real configured identity provider using environment-supplied credentials and treats development mock auth as a labelled fallback that still exercises permission, ownership, and admin gates but not the live token exchange. Credentials are referenced by environment-variable name only; their values are out of scope for the spec and must never be embedded.
- **Synthetic, non-sensitive inputs** (per clarification): All persona files — especially the medical persona's — are clearly synthetic and contain no real personal, financial, health, or government-sensitive data; the medical-data protections of the product are exercised for engagement, not fed real protected data.
- **Generative non-determinism**: Because the underlying assistant is generative, the harness asserts on structural and authority properties (component presence and type, content provenance from the file, permission outcomes, audit attribution) rather than exact wording, and bounds retries to tolerate flaky generations without masking real regressions.
- **Persona catalogue is representative, not exhaustive**: Four personas with a handful of realistic files and queries each are sufficient to demonstrate the properties; the catalogue is intentionally extensible for future coverage.
- **"Tangible that other AIs can't achieve" is grounded in the evidence**: The differentiation claim is limited to what the run actually observed — interactive components from real file content, persisted and re-executable, produced under scoped delegated authority with a tamper-evident audit trail, plus safe on-demand capability creation for unknown formats — and is not asserted beyond the collected evidence.
- **Fail-closed posture inherited**: All harness-driven operations require an authenticated identity and inherit the product's fail-closed security posture (an unset environment defaults to the stricter production behavior); the harness does not weaken that posture to make checks pass.
- **No product behavior change and no new runtime dependency** (Constitution alignment): the harness adds only verification/test-side code and artifacts and consumes the existing system; any test-only tooling it needs is confined to the verification side and does not enter the product runtime.
