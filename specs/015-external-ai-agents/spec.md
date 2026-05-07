# Feature Specification: External AI Service Agents (CLASSify, Timeseries Forecaster, LLM-Factory)

**Feature Branch**: `015-external-ai-agents`
**Created**: 2026-05-07
**Status**: Draft
**Input**: User description: "As a developer, I want to connect CLASSify-2, timeseries-forecaster, and LLM-Factory-2 as agents to the AstralBody system. Each of these 3 services need API credentials and a URL field. classify's url is: classify.ai.uky.edu/, timeseries-forecaster's url is forecaster.ai.uky.edu, and llm factory's url is https://llm-factory.ai.uky.edu/. I provided these URLs for your reference, but when these 3 agents are enabled the user will need to input the url and their api key. Please explore the current AstralBody/backend/agents/ directory to see how agents currently interact with the system, then begin to implement each of these 3 agents based on their code. each should have an API interface that AstralBody can interact with."

## Clarifications

### Session 2026-05-07

- Q: Tool scope per agent for v1 — minimal MVP (1–2 tools), curated useful set (~4–6 tools), or full coverage of every public endpoint? → A: Curated useful set (~4–6 tools per agent) covering the most chat-relevant flows; skip admin/internal endpoints.
- Q: Long-running job result delivery — return a job handle only, auto-poll and push progress + final result into chat, or block the chat turn until completion? → A: Auto-poll on the server side and push progress + final result into chat using the existing progress-notification mechanism.
- Q: Concurrent long-running jobs per user per agent — unlimited, small fixed cap, hard cap of 1, or defer? → A: Small fixed cap (3 concurrent jobs per user per agent); attempts beyond the cap are rejected with a clear "you already have N jobs running" message.

### Session 2026-05-08

- LLM-Factory upstream retargeted from `LLM-Factory-2` (mixed adapter) to `LLM-Factory-Router-2` (pure OpenAI-compatible reverse proxy at the same DNS name). The original Input description and FR-012's wording about "embedding a file" / "listing available datasets" are preserved here as the historical record; this clarifications entry is the authoritative override.
- Resulting LLM-Factory tool surface: `list_models` (`GET /v1/models`), `chat_with_model` (`POST /v1/chat/completions`, synchronous), `create_embedding` (`POST /v1/embeddings`, text input), `transcribe_audio` (`POST /v1/audio/transcriptions`, multipart). The `embed_file` and `list_datasets` tools were dropped because Router-2 does not expose those routes; their responsibilities are subsumed (embeddings) or dropped (datasets — no Router-2 equivalent). The `_credentials_check` legacy fallback to `/models/` was also dropped — Router-2 always serves `/v1/models`.
- `agent_id` (`llm-factory-1`) and credential keys (`LLM_FACTORY_URL`, `LLM_FACTORY_API_KEY`) intentionally unchanged so that any per-user credentials saved before the swap remain valid; only the agent's description string and tool registry shifted.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect a New External AI Service With My Own Credentials (Priority: P1)

A user opens AstralBody, sees one of three new external-service agents (CLASSify, Timeseries Forecaster, or LLM-Factory) listed alongside the existing agents, opens its permissions/configuration panel, enters the service's base URL and their personal API key, saves, and the agent's tools become callable from chat. Without those credentials the agent's tools remain locked and chat surfaces a clear "configuration required" message that links the user to the configuration panel.

**Why this priority**: This is the foundational capability. The user must be able to plug in any one of the three services with their own credentials before any of its tools can do anything useful. Without this slice nothing else in the feature has value.

**Independent Test**: Pick one of the three agents (e.g., CLASSify). Verify (a) it appears in the agent list, (b) it shows up as "configuration required" with locked tools when no credentials are saved, (c) saving a valid URL and API key unlocks the tools and the agent can successfully call at least one read-only endpoint of the live service, (d) clearing the credentials re-locks the tools, and (e) credentials saved by user A are not visible or usable by user B.

**Acceptance Scenarios**:

1. **Given** a user with no credentials saved for the agent, **When** they open the agent's configuration panel, **Then** they see fields for "Service URL" and "API Key" and the agent's tools are shown as locked.
2. **Given** the user enters a syntactically valid URL and a non-empty API key and saves, **When** the system tests the credentials against the service, **Then** a success indicator is shown and the agent's tools become callable.
3. **Given** the user enters credentials that the live service rejects, **When** they save, **Then** the system surfaces a "credentials rejected" error with the underlying reason (e.g., 401, network error) and the tools remain locked.
4. **Given** valid credentials are saved, **When** the user invokes a tool from chat, **Then** the request reaches the external service authenticated with the saved API key and the response is rendered in the conversation.
5. **Given** the user clears their saved credentials, **When** they reload the agent panel, **Then** the URL and API-key fields are empty and the tools are locked again.
6. **Given** user A has saved credentials for the agent, **When** user B logs in, **Then** user B sees no credentials and must save their own; user B's tool calls never use user A's credentials.

---

### User Story 2 - Use the Three External Agents from a Conversation (Priority: P2)

Once configured, a user invokes capabilities from each agent inside a normal AstralBody conversation. Specifically: classify a tabular dataset (CLASSify), produce a forecast for a time series (Timeseries Forecaster), and chat with a model registered in LLM-Factory. Long-running operations (model training, forecast generation) report progress and final results without the user having to manually poll.

**Why this priority**: This is what makes the integration useful — the existence of a connected agent is meaningless if the user can't drive a real workflow through it. P2 because P1 must work first.

**Independent Test**: With each agent configured, ask the orchestrator (in plain language) to perform one representative action per agent. Confirm that the request reaches the right external service, returns a result the user can read, and that long-running jobs eventually deliver their output to the chat without further user action.

**Acceptance Scenarios**:

1. **Given** CLASSify is configured, **When** the user asks to train a classifier on an uploaded CSV, **Then** the chat shows the job has started, periodic progress updates appear, and on completion the chat surfaces a result summary with key metrics and any explainability artifacts the service returns.
2. **Given** Timeseries Forecaster is configured, **When** the user asks for an N-step forecast on an uploaded time-series CSV, **Then** the chat shows job start, progress, and a final forecast summary the user can read inline.
3. **Given** LLM-Factory is configured, **When** the user asks the LLM-Factory agent to answer a question using a specific registered model, **Then** the assistant's reply is streamed (or returned) into the chat using the user-configured LLM-Factory endpoint, not the platform's default LLM.
4. **Given** any of the three agents is invoked while the external service is unreachable, **When** the call is attempted, **Then** the user sees a "service unreachable / try again" message, no partial state is left dangling, and the agent does not become permanently broken.

---

### User Story 3 - Reconfigure or Disconnect an External Agent (Priority: P3)

A user who originally entered one URL/key for an agent later needs to point it at a different deployment (e.g., from a personal sandbox to a shared instance) or revoke the agent entirely. They reopen the configuration panel, edit the URL or key (or clear them), save, and the agent immediately uses the new credentials on the next tool call. Stale results from previous configurations are not reused.

**Why this priority**: Important for operational hygiene and security (rotating compromised keys, switching environments) but not blocking the core "connect and use" experience.

**Independent Test**: Configure an agent with one URL/key, run a tool call to confirm it works, change the URL to a wrong value, run the same tool call, confirm failure with a clear error. Restore the correct URL/key, confirm it works again. Clear the credentials and confirm the tools lock.

**Acceptance Scenarios**:

1. **Given** an agent is configured and has been used at least once, **When** the user updates the URL or API key and saves, **Then** the next tool call uses the updated credentials and never the old ones.
2. **Given** a user clears their credentials for an agent, **When** any subsequent tool call for that agent is attempted, **Then** the call is rejected with a "configuration required" message and the user is offered a path back to the configuration panel.

---

### Edge Cases

- The user enters a URL with no scheme (e.g., `classify.ai.uky.edu/`): the system must treat it as a valid HTTPS URL and not silently fail with an obscure protocol error.
- The user enters a URL pointing to a host that doesn't speak the expected service protocol (e.g., a generic web page): credential test must fail fast with a clear message rather than hang.
- The external service is reachable but rate-limits or returns 5xx: the agent must surface a retryable error rather than a generic "internal error."
- A long-running job (CLASSify training, Timeseries forecasting) is started, then the user closes the browser. On reconnect, the user must still be able to discover the job's outcome (or, at minimum, must not be told the job "succeeded" when it has not).
- The user saves credentials, the API key is later rotated externally and the old key now returns 401. The next tool call must fail clearly and the configuration panel must indicate the credentials are no longer valid.
- An admin disables one of the three external-service agents at the platform level. Users with credentials saved for it must see it as "disabled by administrator" rather than "configuration required."
- Two browser tabs for the same user edit credentials simultaneously. The system must end up in a deterministic state (last-write-wins is acceptable) without corruption.
- The same external service is reachable at two different URLs (e.g., the user has a private deployment). The user-supplied URL is honored, even if it differs from the production URL hinted at in the UI placeholder.
- The user already has the maximum allowed concurrent jobs in flight (per FR-026) and tries to start one more. The system must reject the new attempt immediately with a message that names the limit and lists the in-flight jobs the user could cancel; it must not silently queue.

## Requirements *(mandatory)*

### Functional Requirements

#### Agent presence and discoverability

- **FR-001**: System MUST list three new agents — "CLASSify", "Timeseries Forecaster", and "LLM-Factory" — in the same agent inventory the user already uses to view, enable, and configure existing AstralBody agents.
- **FR-002**: Each of the three agents MUST be presented in the configuration UI with a human-readable name, a one-sentence description of what it does, and a placeholder/example for the production URL of that service to help the user paste the right value.
- **FR-003**: An administrator MUST be able to disable any of the three agents platform-wide; when disabled, the agent MUST appear as such in every user's UI and its tools MUST NOT be callable.

#### Per-user credentials

- **FR-004**: For each of the three agents, the user MUST be able to enter a Service URL and an API Key, save them, see them as saved, edit them, and clear them, all from the same configuration surface used for other agents that require credentials.
- **FR-005**: Saved credentials MUST be scoped strictly per-user — one user's credentials MUST NOT be readable, usable, or otherwise observable by any other user, including admins, through the application's normal interfaces.
- **FR-006**: API keys MUST be stored in a way that an attacker who reads the application database without also obtaining the agent's secret key cannot recover the plaintext key.
- **FR-007**: API keys MUST never be returned to the frontend after they are saved (the input field MUST be re-rendered as empty/masked on subsequent loads, with a "saved" indicator), and MUST never appear in logs or audit-event payloads.
- **FR-008**: When the user saves credentials, the system MUST perform a lightweight live test against the supplied URL using the supplied API key and report the result (success / authentication failed / unreachable / unexpected response) before treating the credentials as ready for use.
- **FR-009**: When a user has not saved credentials (or has cleared them), every tool exposed by that agent MUST be presented as locked/unavailable, and any attempted invocation MUST be rejected with a "configuration required" message that points the user to the agent's configuration panel.

#### Tool surface per agent

- **FR-010**: The CLASSify agent MUST expose a curated set of approximately 4–6 tools covering the chat-relevant workflows of the underlying service (e.g., starting a training run, checking job status, retesting a trained model, retrieving results / explainability summaries, and listing available datasets or models). Admin-only and internal-housekeeping endpoints (e.g., dataset deletion, internal column-type remapping, low-level training callbacks) are explicitly out of scope for v1.
- **FR-011**: The Timeseries Forecaster agent MUST expose a curated set of approximately 4–6 tools covering the chat-relevant workflows of the underlying service (e.g., starting a forecast / training run, checking job status, generating new forecasts, fetching a results summary, and producing model recommendations). Admin-only and internal-housekeeping endpoints are explicitly out of scope for v1.
- **FR-012**: The LLM-Factory agent MUST expose a curated set of approximately 4–6 tools covering the chat-relevant workflows of the underlying service (e.g., listing registered models, sending a chat completion to a chosen model via the OpenAI-compatible endpoint, embedding a file, and listing available datasets). Model-registration / model-deletion administrative endpoints are explicitly out of scope for v1.
- **FR-013**: Each tool exposed by any of the three agents MUST declare a machine-readable input schema (parameter names, types, required vs. optional) so that the orchestrator can validate calls and the chat UI can solicit missing arguments.
- **FR-014**: Tool results MUST be rendered into the chat using AstralBody's standard rendering primitives (text/cards/tables/etc.); no agent-specific UI surface is introduced for displaying results.

#### Long-running operations

- **FR-015**: For operations the underlying service performs asynchronously (e.g., model training, forecast generation), the agent MUST poll the underlying service for the job's status server-side and push both interim progress updates and the final result into the originating chat using the existing progress-notification mechanism — without requiring the user to invoke a separate "check status" tool.
- **FR-016**: The auto-poll-and-push result-delivery behavior of FR-015 MUST be applied consistently across all three agents whenever the underlying operation is asynchronous, so a user does not learn one pattern for CLASSify and a different pattern for Timeseries Forecaster.
- **FR-017**: If a long-running job is in flight and the underlying service becomes unreachable mid-job, the user MUST eventually be told the job's last known state (started / in-progress / unknown) via the same progress-notification channel, rather than being silently abandoned. Polling MUST stop after a bounded number of consecutive failures and surface a final "status unknown — try again later" notification rather than retrying indefinitely.

#### File / data inputs

- **FR-018**: Where an external service requires a tabular file (CSV) as input (CLASSify training, Timeseries forecasting), the agent MUST accept that file via AstralBody's existing file-upload mechanism so the user does not need to learn a separate upload flow.

#### Auditing

- **FR-019**: Saving, editing, clearing, or testing credentials for any of the three agents MUST emit an audit event (per the existing audit-log subsystem) recording the actor, the agent, and the action, but MUST NOT include the API key value.
- **FR-020**: Each tool invocation against any of the three agents MUST emit the same paired in-progress / success-or-failure audit events that other agent tool calls already emit, including the orchestrator's correlation id.

#### Failure modes and clarity

- **FR-021**: When a tool call fails because the external service returned an authentication error, the system MUST present a distinct, actionable message ("the saved API key was rejected by the service — update it in the agent's settings") rather than a generic error.
- **FR-022**: When a tool call fails because the external service is unreachable (DNS failure, connection refused, timeout), the system MUST present a distinct retryable error ("service unreachable, try again") and MUST NOT mark the credentials as invalid.
- **FR-023**: The system MUST tolerate the user pasting a URL with or without a trailing slash, and with or without an explicit `https://` scheme, normalizing to a canonical form internally.

#### Independence and isolation

- **FR-024**: Each of the three agents MUST run independently; a failure or outage of one MUST NOT prevent the other two from being configured or used.
- **FR-025**: Each of the three agents MUST be installable, upgradable, and disableable independently of the other two.

#### Concurrency limits

- **FR-026**: For agents whose underlying service runs asynchronous jobs, the system MUST limit each (user, agent) pair to at most 3 concurrent in-flight jobs. Attempts to start a 4th job MUST be rejected immediately with an actionable message identifying that the user already has 3 jobs running and offering options to wait or cancel an existing one (no silent queueing).
- **FR-027**: When a job ends (success, failure, or cancellation), its slot under the FR-026 cap MUST become free immediately so the user can start a replacement without artificial delay.

### Key Entities *(include if feature involves data)*

- **External Service Agent**: One of the three new agents (CLASSify, Timeseries Forecaster, LLM-Factory). Has a stable identifier, a human-readable name, a description, a declared list of tools it can perform, and a declared schema of credentials it requires (always: a Service URL and an API Key).
- **Per-User Agent Credentials**: The (user, agent) → (URL, API key) record. Encrypted at rest such that only the agent can recover the plaintext API key. Created/edited/cleared by the user; never shared across users; never reflected back to the frontend after save.
- **Tool**: A single capability exposed by an agent (e.g., "train a classifier", "generate forecast", "chat with model"). Has a name, a description, and an input schema. Tools become callable only after the agent's credentials have been successfully saved and validated.
- **Long-Running Job** *(only for agents whose underlying service is async)*: A unit of work started by a tool invocation that the external service runs in the background. Has a job identifier, a status (started / in-progress / succeeded / failed), and an eventual result delivered into the originating chat.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user, given the production URL for one of the three services and a valid API key, can go from "agent not configured" to "agent successfully ran one tool" in under 3 minutes without reading developer documentation.
- **SC-002**: 100% of saved API keys are unreadable to any other authenticated user of the platform via every documented application interface (UI, REST, WebSocket).
- **SC-003**: When a user enters credentials that the live service rejects, they see an actionable error within 5 seconds of pressing "Save" — not a spinner that never resolves.
- **SC-004**: Each of the three agents can be deployed, upgraded, or disabled without restarting or affecting the other two; verified by toggling each in isolation.
- **SC-005**: For each agent, at least one representative read-only end-to-end workflow (configure → invoke → receive result in chat) completes successfully against the live production endpoint of the corresponding service.
- **SC-006**: 0 occurrences of an API key value appearing in any log, any audit event payload, or any HTTP response body in the test suite covering credential save / edit / clear / test / use.
- **SC-007**: For long-running operations, 95% of jobs that complete successfully on the underlying service are visible to the user in their chat (with their final result) within 30 seconds of the underlying service marking them done — i.e., the user does not have to manually re-ask.
- **SC-008**: A platform admin can disable any one of the three agents and within 10 seconds every connected user sees its tools become unavailable, with a "disabled by administrator" message and not a confusing generic error.

## Assumptions

- The three external services authenticate callers with a Bearer token (`Authorization: Bearer <API_KEY>`) — true for CLASSify, Timeseries Forecaster, and LLM-Factory's OpenAI-compatible endpoint as observed in their codebases. If a future service variant uses a different scheme, that variant is out of scope for this feature.
- AstralBody's existing per-user, end-to-end-encrypted agent-credential storage pattern (currently used by other credentialed agents) is the storage mechanism — no new credential-storage subsystem is introduced.
- AstralBody's existing agent auto-discovery convention (one directory per agent under the agents folder, with the canonical `*_agent.py` / `mcp_server.py` / `mcp_tools.py` / `__init__.py` layout) is followed; no changes to the orchestrator's discovery or registration flow are required.
- AstralBody's existing audit-log, file-upload, and progress-notification subsystems are reused as-is. None of them need extension for this feature.
- The user interface for configuring agent credentials is the existing agent-permissions / configuration panel; no new top-level settings page is added.
- The default placeholder URLs shown to users in the configuration panel are the production URLs supplied in the feature description (`classify.ai.uky.edu`, `forecaster.ai.uky.edu`, `https://llm-factory.ai.uky.edu/`), but the user-entered URL always wins — including for self-hosted or alternate deployments.
- File uploads required by CLASSify and Timeseries Forecaster (CSV inputs) flow through AstralBody's existing file-upload mechanism; no separate upload UI is built per agent.
- "Admin" in the platform-disable scenarios refers to whatever admin role AstralBody already recognizes; no new role is introduced.
- The three agents are intended to ship together as a single feature, but each is independently testable and independently deployable per FR-024 and FR-025.
