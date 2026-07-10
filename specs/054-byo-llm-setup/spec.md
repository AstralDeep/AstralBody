# Feature Specification: Bring-Your-Own-LLM — Mandatory Provider Setup & Shipped-Credential Removal

**Feature Branch**: `054-byo-llm-setup`

**Created**: 2026-07-10

**Status**: Draft

**Input**: User description: "Remove the shipped operator-default LLM credentials (.env and others) so the product never ships with a working LLM. When a user logs into any client and no LLM is configured for them, a mandatory setup dialog — the absolute first thing after login, before the tutorial — collects their own LLM provider: a dropdown of popular providers plus a custom OpenAI-compatible endpoint option. Server-persisted per-user credentials (encrypted); admin-configured system credential for background work; the operator-default code path is deleted entirely."

## Clarifications

### Session 2026-07-10

- Q: Where should a user's LLM credentials live once configured? → A: Server-side, encrypted per-user record (API key encrypted at rest under the deployment's existing credential-encryption posture); configure once on any client, applies everywhere.
- Q: How completely should the operator-default env credentials be removed? → A: Delete the code path entirely — no deployment can supply a default LLM credential for user traffic; legacy env vars become inert.
- Q: What should server-initiated LLM work use without an operator default? → A: One admin-configured, deployment-wide system credential (encrypted, admin-only surface); absent ⇒ degrade gracefully with honest failure reporting.
- Q: Which providers should the dropdown offer? → A: OpenAI, Anthropic, Google Gemini, xAI Grok, OpenRouter, Groq, Together AI, Mistral, Ollama, LM Studio, plus Custom OpenAI-compatible endpoint.
- Q: Which credential powers in-session AI helpers — conversation compaction and workspace combine/condense? → A: The system credential (accepted tradeoff: these helpers route content through the admin-designated provider and bill the deployment; direct chat/answer generation always uses the user's own credentials).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - First login triggers mandatory provider setup (Priority: P1)

A brand-new user signs into the app on any client (web, Windows, Android, iOS, macOS). Because they have no AI provider configured, the very first thing they see after authentication — before the welcome content, before any tutorial, before chat is usable — is a setup dialog asking them to connect their own AI provider. They pick a provider from a dropdown of popular options (or choose "Custom OpenAI-compatible endpoint"), enter their API key, pick or type a model, verify the connection with a live test, and save. The dialog closes and the normal first-run experience (welcome content; tutorial available exactly as today) proceeds.

**Why this priority**: The entire product revolves around the LLM. With shipped credentials removed, an unconfigured user can do nothing — this dialog is the only path to a working product, so it must be the first and unavoidable step.

**Independent Test**: Create a fresh user with no stored provider configuration; sign in on each client family; verify the setup dialog is the first surface shown, cannot be dismissed, and that completing it unlocks the normal experience.

**Acceptance Scenarios**:

1. **Given** an authenticated user with no stored provider configuration, **When** their client finishes connecting, **Then** the provider-setup dialog is presented before any welcome content, tutorial, or chat surface, on web, Windows, Android, iOS, and macOS alike.
2. **Given** the setup dialog is displayed, **When** the user attempts to dismiss it (close button, Escape, clicking outside, back navigation, opening another menu surface), **Then** the dialog remains and the rest of the app stays unavailable.
3. **Given** the setup dialog is displayed, **When** the user selects a popular provider from the dropdown, **Then** the provider's endpoint address is prefilled (not editable confusion — custom option offers a free-form address), the API key field is shown (marked optional for local runtimes that don't require one), and the user can fetch that provider's available model list or type a model name manually.
4. **Given** the user has filled in provider details, **When** they run the connection test and it succeeds, **Then** they can save; **When** the test fails, **Then** a category-level reason is shown (bad key / model not found / endpoint unreachable) and saving without a subsequent successful test is refused.
5. **Given** the user completes setup, **When** the dialog closes, **Then** the welcome content appears and the tutorial ("Take the tour") remains available and unchanged from today's behavior.
6. **Given** a user who is mid-setup, **When** they reload / relaunch the client, **Then** the dialog reappears (still unconfigured) and no other functionality has leaked through.

---

### User Story 2 - The product ships with no working AI credential (Priority: P1)

The operator/product owner builds and distributes the app (app-store submissions, container images, release artifacts) and deploys it. No artifact, environment template, or deployment mechanism carries a working LLM credential, and the platform no longer even supports supplying a deployment-wide default LLM credential for user traffic. A fresh deployment has zero LLM capability until each user brings their own provider.

**Why this priority**: This is the compliance driver — public app-store distribution requires that the product not embed or depend on the developer's own LLM subscription.

**Independent Test**: Boot a fresh deployment with no LLM-related settings anywhere; verify it starts cleanly, serves login, and gates every user behind the setup dialog; verify the legacy environment variables have no effect when set.

**Acceptance Scenarios**:

1. **Given** a deployment with no LLM configuration anywhere, **When** the system boots, **Then** startup succeeds (no new boot requirement) and all users without personal configuration are gated by the setup dialog.
2. **Given** the legacy operator environment variables are set in the deployment environment, **When** the system boots, **Then** they are ignored for user-facing LLM calls — there is no code path that turns them into a usable default.
3. **Given** the repository, environment templates, deployment docs, and shipped artifacts (web assets, container image, desktop/mobile binaries), **When** scanned, **Then** no working LLM credential and no operator-default credential mechanism is present.

---

### User Story 3 - Configure once, works everywhere, survives sessions (Priority: P2)

A user configures their provider on one client (say, the web). Their configuration is stored server-side (API key encrypted at rest) and applies to all their clients and sessions: their phone, desktop, and watch start working without re-entry; logging out and back in does not re-trigger the dialog; disconnecting/reconnecting keeps working. Clearing the configuration from settings immediately re-gates them behind the setup dialog on all their connected clients.

**Why this priority**: Without durable per-user storage, the mandatory dialog would reappear on every reconnect on every device, making the product unusable in practice — and the watch (which cannot host a dialog) would never work at all.

**Independent Test**: Configure on client A; verify client B (already connected and freshly connected) works without setup; sign out/in; verify no dialog; clear configuration; verify all clients re-gate.

**Acceptance Scenarios**:

1. **Given** a user configures their provider on the web, **When** they sign in on Android/iOS/Windows/macOS, **Then** no setup dialog appears and chat works using their stored configuration.
2. **Given** a user with stored configuration, **When** they sign out and sign back in (any client), **Then** the configuration persists and no dialog appears.
3. **Given** a user clears their configuration from LLM settings, **When** the clear completes, **Then** the mandatory setup dialog re-appears immediately on their connected clients and chat is refused server-side until reconfigured.
4. **Given** a user updates their configuration (new key/model/provider) from the regular LLM settings surface, **When** saved after a successful test, **Then** subsequent calls use the new configuration on all their clients.
5. **Given** one user has stored configuration, **When** any other user connects, **Then** the other user's calls can never use the first user's credentials.

---

### User Story 4 - Admin configures a system credential for background work (Priority: P2)

An administrator opens a new admin-only settings surface and stores a single deployment-wide "system" LLM credential (encrypted at rest). Server-initiated background work — scheduled/recurring jobs, automatic file-parser generation, knowledge synthesis, conversation compaction, workspace combine/condense, job result narration — uses exclusively this system credential. When it is absent, those background features degrade gracefully and honestly: they log, skip, and report failure status where a user would otherwise be misled (a scheduled run must not claim success when no AI was available). User-facing calls never fall back to the system credential, and system/background calls never use a user's personal credential.

**Why this priority**: Removing the operator default would otherwise silently break every server-initiated AI feature; this restores them under explicit admin control without re-introducing a shipped credential.

**Independent Test**: With no system credential, trigger each background feature and verify honest failure/skip reporting; configure the system credential via the admin surface; verify background features run; verify a user without personal config is still gated (no fallback).

**Acceptance Scenarios**:

1. **Given** no system credential is stored, **When** a scheduled job that needs the AI runs, **Then** the run is recorded as failed (not success) and the owner's notification states the AI was unavailable.
2. **Given** no system credential is stored, **When** knowledge synthesis or other periodic background AI work would run, **Then** it logs and skips without data loss, as an explicit "system AI not configured" condition.
3. **Given** an administrator stores a valid system credential (with connection test), **When** background features next run, **Then** they use the system credential and complete normally.
4. **Given** a system credential exists, **When** an unconfigured user tries to chat, **Then** they are still gated — the system credential is never used for user-context calls.
5. **Given** a non-admin user, **When** they attempt to view or modify the system credential surface, **Then** access is refused.

---

### User Story 5 - Watch guidance when unconfigured (Priority: P3)

A user signs in on the watch (which by design has no settings surfaces or keyboard) before configuring a provider anywhere. When they try to use the assistant, the watch shows — and speaks — a short instruction to set up their AI provider on their phone or the web first. Once they configure on another client, the watch starts working without any watch-side action.

**Why this priority**: The watch cannot host the dialog; without an explicit posture, watch-first users would hit a dead end with a generic error.

**Independent Test**: With an unconfigured user, dictate a message on the watch; verify the spoken/displayed guidance; configure on the web; verify the next watch message works.

**Acceptance Scenarios**:

1. **Given** an unconfigured user on the watch, **When** they send a dictated message, **Then** the watch displays and speaks guidance to configure their provider on phone/web (not a generic error), and the message is not silently lost into a broken turn.
2. **Given** the user then configures a provider on any other client, **When** they next use the watch, **Then** it works with no watch-side steps.

---

### Edge Cases

- **Connection test passes but model list fetch fails**: manual model entry must always remain available; model list fetch is a convenience, not a gate.
- **Keyless local runtimes** (e.g., a self-hosted runtime with no API key): presets flagged as keyless allow saving with an empty key after a successful connection test. The endpoint must be reachable *from the server*, and guidance must make that clear (a "localhost" runtime on the user's laptop is not reachable by a hosted deployment).
- **Multiple simultaneous sockets/tabs**: configuring on one tab unblocks the user's other connected clients without requiring re-login; clearing re-gates them all.
- **Encryption key rotation / undecryptable stored credential**: treated as "not configured" — the user is re-gated at next connect (no crash, no partial state), and the unusable record is discarded.
- **Partial submissions**: missing endpoint/model (or missing key for a key-required provider) are rejected with field-level messages; nothing partial is stored.
- **Admin clears the system credential while background work is queued**: in-flight work completes or fails honestly; subsequent work follows the "absent" path.
- **A user's provider starts failing after setup** (revoked key, provider outage): calls fail with the existing per-call error reporting; the user is NOT re-gated behind the mandatory dialog (it gates absence of configuration, not provider health); the settings surface remains the fix-it path.
- **Legacy environment variables present in an old deployment's .env**: ignored; deployment docs describe removal; no migration of the operator credential into any store (deliberate — the shipped credential must die, not move).
- **Old transcripts / historical chats**: remain viewable while unconfigured is false; while unconfigured, the gate applies to new AI work — viewing history is not AI work (but is still behind the dialog on gated clients, since the dialog precedes the whole UI).
- **User with only the dialog available but an unreachable provider** (e.g., firewalled endpoint): the user can retry the test, switch provider, or sign out; the dialog never traps them without those options.

## Requirements *(mandatory)*

### Functional Requirements

#### Removal of shipped/operator credentials

- **FR-001**: The system MUST NOT support a deployment-supplied default LLM credential for user-context calls. The operator-default credential mechanism (environment-variable trio and every code path that reads it as a fallback for user traffic) MUST be removed, not merely left unset.
- **FR-002**: Setting the legacy environment variables (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`, `KNOWLEDGE_LLM_MODEL`) MUST have no effect on any LLM call. Environment templates (`.env.example`), developer `.env` guidance, and deployment documentation MUST be scrubbed of them (with a documented migration note for existing operators).
- **FR-003**: System startup MUST NOT require any LLM configuration; boot, login, and non-AI functionality MUST work on a deployment with zero LLM settings.
- **FR-004**: No shipped artifact (container image, web assets, desktop/mobile/watch binaries, release archives) may contain a working LLM credential. Release validation MUST include automated checks at the layers where credential material could enter: the repository/history secret scan (existing), a source-tree guard asserting no live operator-credential reads remain, and a built-container-image filesystem scan for credential material added to the CI pipeline. Native client artifacts are covered by these same checks because the clients contain no LLM credential inputs or embedded configuration (verified fact; the binaries are built from the scanned tree).

#### Per-user provider configuration (server-persisted)

- **FR-005**: The system MUST store at most one LLM provider configuration per user — provider choice, endpoint address, model, and API key — durable across sessions, devices, and sign-outs, and resolvable by user identity (not tied to a single connection).
- **FR-006**: The stored API key MUST be encrypted at rest using the deployment's existing credential-encryption posture. The API key MUST never appear in logs, audit records, diagnostic output, or any client-bound payload (write-only semantics: once saved, clients see only a "saved" indicator, never the key). Audit payloads MUST NOT contain the key or any contiguous substring of it of length ≥ 4.
- **FR-007**: A user's stored credentials MUST never be readable or usable by any other user; system/background work MUST NOT use any user's personal credentials.
- **FR-008**: Saving a configuration MUST require a successful live connection test (a real minimal chat-completion round-trip against the exact endpoint/key/model being saved). Test results MUST be reported with a category-level reason on failure (authentication failed / model not found / endpoint unreachable / other).
- **FR-009**: Users MUST be able to update or clear their stored configuration from the existing LLM settings surface on every client that has settings surfaces. Clearing MUST take effect immediately and re-gate the user (see FR-013) — there is no longer any default to revert to.
- **FR-010**: An undecryptable or corrupted stored configuration MUST be treated as absent (user re-gated), discarded safely, and MUST NOT crash any flow.

#### Provider catalog

- **FR-011**: The setup dialog and the LLM settings surface MUST offer a dropdown of popular providers — OpenAI, Anthropic, Google Gemini, xAI Grok, OpenRouter, Groq, Together AI, Mistral, Ollama, LM Studio — plus a "Custom OpenAI-compatible endpoint" option. Selecting a provider prefills its OpenAI-compatible endpoint address; the custom option provides a free-form endpoint field. All options collect model (with optional model-list fetch from the provider) and API key; presets for local runtimes that don't require a key mark the key optional.
- **FR-012**: The provider catalog MUST be maintainable in one server-side place so that all clients present the same catalog without client releases when a preset's address changes.

#### Mandatory first-run gate

- **FR-013**: When an authenticated user with no stored provider configuration connects on web, Windows, Android, iOS, or macOS, the provider-setup dialog MUST be presented before any other post-login content (welcome content, tutorial, chat, history, settings), and MUST NOT be dismissible by any client affordance (close/Escape/outside-click/back/menu navigation) until a configuration is saved — with exactly one exception: **sign-out MUST remain available from the gated state on every client** (an explicit affordance on or alongside the dialog), and the server MUST continue to permit sign-out while the gate is active. The dialog never traps a user who cannot or will not configure a provider.
- **FR-014**: The gate MUST be server-authoritative: while a user is unconfigured, the server MUST refuse AI-dependent actions (chat turns, component re-execution, AI-driven settings actions) and navigation away from the setup surface, regardless of client behavior. Refusals MUST be audited.
- **FR-015**: Completing setup MUST unlock the session without re-login: the connected client proceeds to the normal post-login experience, and the user's other connected clients unblock without re-connecting.
- **FR-016**: The tutorial/tour MUST be unaffected in content and remain user-initiated exactly as today; it MUST only become reachable after the gate clears. First-run ordering MUST be: authentication → provider setup (if unconfigured) → welcome content → everything else.
- **FR-017**: The watch, which has no settings surfaces by design, MUST NOT receive the dialog; when an unconfigured user attempts AI use on the watch, the watch MUST display and speak concise guidance to configure the provider on phone/web. Once configured elsewhere, watch use MUST work with no watch-side steps.

#### Admin system credential for background work

- **FR-018**: Administrators MUST be able to store, test, update, and clear exactly one deployment-wide system LLM credential via a new admin-only settings surface, with the same encryption, write-only, and hygiene rules as user credentials (FR-006). Non-admin access MUST be refused server-side. The surface is **deliberately web-only**, joining the existing admin-tooling carve-out under the cross-client-consistency principle (like Tool quality and Tutorial admin): the server omits it from native menu channels (natives never receive admin groups), the omission is enforced server-side, and it applies uniformly to every non-web client.
- **FR-019**: System-credential LLM work comprises: server-initiated flows (scheduled/recurring job turns, automatic file-parser generation, knowledge synthesis, job narration, draft-agent self-tests and similar system flows) AND — by explicit decision (Clarifications, Session 2026-07-10) — the in-session helpers conversation compaction and workspace combine/condense. All of these MUST use exclusively the system credential. Direct user-context calls (chat turns, tool summaries, chat titles, adaptive layout, and all other per-user AI work) MUST use the user's own stored credentials and MUST never fall back to the system credential.
- **FR-020**: When the system credential is absent or failing, background features MUST degrade gracefully and honestly: log and skip without data loss, and any user-visible outcome MUST reflect failure — a scheduled run that could not run its AI turn MUST be recorded and reported as failed, never as success.
- **FR-021**: Every LLM call MUST be attributable in the audit trail to its credential source — `user` or `system` — without recording key material; the audit vocabulary MUST reflect the removal of the operator-default source for new events.

#### Feature 006 supersessions

- **FR-022**: This feature amends feature 006 as follows (a conformance note MUST be added to the 006 spec): the no-server-persistence rule (006 FR-002 storage clause) is replaced by encrypted server-side per-user storage (key-hygiene clauses survive verbatim); the operator-default fallback and "user must not be blocked" rules (006 FR-004/FR-004a/FR-010, Clarifications Q2/Q3) are replaced by the mandatory gate; the background-jobs-use-operator-default rule (006 FR-011) is replaced by the system credential; "clear reverts to operator default" (006 FR-012/US2) becomes "clear re-gates the user"; the "no provider catalog" out-of-scope line is rescinded. The test-connection semantics (006 FR-005), key-redaction rules (006 FR-006), per-call source auditing (006 FR-007a), and no-cross-user/no-silent-fallback invariants (006 FR-009) survive.

### Key Entities

- **User LLM Configuration**: one per user — provider identifier (preset or custom), endpoint address, model name, API key (encrypted at rest; write-only to clients), created/updated timestamps. Absence of this record is what triggers the mandatory gate.
- **Provider Preset**: catalog entry — display name, endpoint address, whether an API key is required, ordering; maintained server-side; "Custom" is the escape hatch with a free-form endpoint.
- **System LLM Credential**: zero-or-one per deployment — same shape as a user configuration, admin-managed, used only for server-initiated background work.
- **First-Run Gate State**: derived (not stored) per user — "configured" iff a decryptable User LLM Configuration exists; governs the server-side refusal of AI-dependent actions and the client-side mandatory dialog.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a fresh deployment, 100% of new users on web, Windows, Android, iOS, and macOS see the provider-setup dialog as the first post-login surface, and no AI-dependent action succeeds server-side before setup (verified per client family).
- **SC-002**: A user who completes setup on one client can use every other client family — including the watch — without re-entering configuration, and without seeing the dialog again across sign-out/sign-in cycles (verified across at least two client families + watch).
- **SC-003**: A new user with a valid provider account completes the setup dialog (select provider → key → model → test → save) in under 90 seconds.
- **SC-004**: Automated scans of the repository, environment templates, release artifacts, and server logs/database/audit trail find zero working LLM credentials shipped with the product and zero user API keys in plaintext (encrypted-at-rest storage only), as part of release validation.
- **SC-005**: With no system credential configured, zero background runs report success while their AI step was unavailable (verified by triggering each background feature); with a system credential configured, all resume normal operation.
- **SC-006**: The tutorial's behavior and content are unchanged for configured users (regression check), and for new users it is reachable only after setup completes.
- **SC-007**: Setting the legacy environment variables on a deployment changes nothing user-visible (verified by boot + user flows with and without them).

## Assumptions

- **Provider presets are OpenAI-compatible endpoints only.** Every cataloged provider exposes an OpenAI-compatible API surface (all listed do); no provider-native protocols, OAuth flows, or per-provider SDKs are added. "Anthropic" etc. mean their OpenAI-compatible endpoints.
- **Endpoint reachability is server-relative.** All LLM calls originate from the backend, so preset/custom endpoints (including local runtimes) must be reachable from the server; the dialog copy notes this for local-runtime presets. Existing egress/SSRF posture for user-supplied endpoints is unchanged in kind (same exposure as feature 006 today) but widened in prominence: the connection probe is now mandatory on every save and reachable while gated, and the catalog suggests server-local addresses. This is an **accepted risk, consciously recorded**: probes are authenticated, audited (`llm_config_change{action:"tested"}`), and rate-limited per user; probe error categories are the same ones feature 006 already returns.
- **No migration of the operator credential.** Existing deployments (e.g., the university sandbox) do not get their env credential auto-seeded into the system credential or any user's configuration; every user configures fresh, and the admin explicitly sets the system credential if background features are wanted. A short migration note in deployment docs covers this.
- **Clear-mid-session re-gates immediately.** Clearing configuration re-triggers the mandatory dialog on the user's connected clients right away (not at next login).
- **Admins are users too.** The admin's personal chat traffic requires their own user configuration like everyone else; the system credential is exclusively for server-initiated work.
- **The knowledge-synthesis model setting collapses into the system credential.** The separate knowledge-model environment setting is removed; knowledge synthesis uses the system credential's endpoint/key/model.
- **Dev/test posture uses injection, not env.** Test suites, CI, and the in-process verification harness obtain LLM clients via the existing client-factory injection seam; development convenience does not resurrect an env-based default for user traffic. CI boots (dev and production-posture smoke) are unaffected because LLM settings were never part of boot gating.
- **Existing wire vocabulary suffices.** The mandatory dialog is delivered with the existing server-driven UI machinery (settings-surface composition and existing frame vocabulary, including reserved fields); native clients gain handling for the mandatory marker in a client release; no new third-party runtime dependencies anywhere (Constitution V).
- **Token-usage counters (006 FR-014..017) continue unchanged** in their current per-session form; making them durable is out of scope here.
- **Concurrency**: the per-user configuration is last-write-wins across a user's simultaneous sessions; no locking UI is needed.
- **Accepted privacy/billing tradeoff for helpers**: conversation compaction and workspace combine/condense route the affected content through the admin-designated system provider and bill the deployment (explicit owner decision, Clarifications Session 2026-07-10). When no system credential is configured, these helpers follow FR-020 (compaction skips with its existing non-AI fallback note; combine/condense report an honest error).

## Out of Scope

- Provider-native (non-OpenAI-compatible) APIs, OAuth sign-in to providers, or provider billing/quota display.
- Multiple stored configurations per user, per-agent/per-feature model routing, or model tier mapping changes.
- Making the device-local token-usage counters durable or server-side.
- Any change to the tutorial's content or to the tour's user-initiated trigger.
- Watch-side configuration UI.
- Rotation tooling for the deployment encryption key (existing posture applies).
