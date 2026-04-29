# Feature Specification: User-Configurable LLM Subscription

**Feature Branch**: `006-user-llm-config`
**Created**: 2026-04-28
**Status**: Draft
**Input**: User description: "As a user, I want to use my own LLM subscription. move env variables for openai_api_key, openai_base_url, and llm_model to the frontend so a user can use whatever model they want (openai api compatible)"

## Clarifications

### Session 2026-04-28

- Q: When a user signs out (or their session expires), what happens to their locally-stored LLM configuration? → A: Never auto-clear — credentials persist on the device until the user explicitly clicks "Clear." Sign-out and session/token expiry leave them in place for the next sign-in.
- Q: When a previously-server-side job (or any LLM call where the user has not configured their own credentials) needs LLM access, whose credentials are used? → A: The operator's `.env`-supplied LLM credentials remain the default. A user's own configuration overrides the default for that user's calls; if the user has not configured their own, the default is used and the feature simply works.
- Q: When a user's saved personal LLM configuration was valid at save-time but later fails at runtime (revoked key, billing lapsed, rate limit, endpoint down), should the system silently fall back to the operator's `.env` default? → A: No. Never fall back at runtime. The upstream failure is surfaced verbatim; the user must retry, fix their key, or explicitly clear their personal configuration to revert to the operator default.
- Q: What does the "Test Connection" probe actually exercise? → A: A minimal chat-completions request (single short prompt, `max_tokens: 1`) against the user's configured base URL and model. This proves auth + base URL + model name + the chat-completions contract end-to-end at a cost of ~1 token per probe. A `/models` GET alone is insufficient.
- Q: Should the system warn users when their provider tokens/credits are about to run out (Claude-style "you're running low" message)? → A: No predictive warning — there is no universal OpenAI-compatible "remaining balance" API. Instead, surface **observed cumulative token usage** for the current user (per session and lifetime, summed from each response's `usage.total_tokens`) in a "Token usage" dialog inside the LLM settings panel. No provider-specific balance probes; no proactive 402/429 prediction.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - User opts in to their own LLM provider (Priority: P1)

A user signs in and uses LLM-dependent features (the feedback proposal pre-pass, knowledge synthesis, any agent that calls a language model). By default these features work using the operator's deployment-level LLM credentials. The user wants to bring their own subscription — perhaps to use a model the operator hasn't configured, to keep their queries on their own bill, or to point the system at a local endpoint. They open settings, paste an API key, optionally override the base URL (e.g. to point at OpenRouter, LM Studio, a self-hosted OpenAI-compatible endpoint, or Anthropic via a proxy), choose a model name, and save. From that point on, every LLM call performed on their behalf uses their credentials and is billed against their account, not the operator's.

**Why this priority**: This is the core value proposition. Without it, the feature delivers nothing. It is also the change that lets users opt out of the operator's bill and choose their own model, which is the explicit business motivation in the user request.

**Independent Test**: A test account can open the settings panel, enter credentials, click "Test Connection," see a success indicator, then trigger any LLM-dependent feature (e.g. submit feedback that triggers a proposal pre-pass) and observe that the call uses the user's submitted credentials, not the operator's defaults.

**Acceptance Scenarios**:

1. **Given** a signed-in user with no personal LLM configuration, **When** they invoke an LLM-dependent feature, **Then** the call succeeds using the operator's default credentials and the user is not blocked.
2. **Given** a signed-in user with no personal LLM configuration, **When** they open the LLM settings panel and enter a valid API key, base URL, and model, **Then** the configuration is saved per-user on their own device and a "connected — using your own provider" status is shown.
3. **Given** a user has saved an LLM configuration, **When** they invoke a feature that requires an LLM (e.g. component feedback proposal generation), **Then** the call is performed using only their submitted credentials, the operator's defaults are not used, and the response is delivered to them.
4. **Given** a user enters credentials that fail the "Test Connection" probe, **When** they attempt to save, **Then** the system surfaces the failure reason and does not mark the configuration as connected; the operator's defaults remain in effect for that user until a valid configuration is saved.

---

### User Story 2 - User rotates, switches, or clears their LLM credentials (Priority: P2)

A user who already has a working configuration wants to switch providers (e.g. from a hosted OpenAI key to a local Ollama endpoint), rotate a leaked key, or clear the configuration entirely (e.g. when stepping away from a shared machine). They open the same settings panel, edit the fields or click "Clear," and save.

**Why this priority**: Credential lifecycle is part of normal operation but is not blocking initial value. P1 already proves the data path works; P2 covers the realistic "I changed my mind" and "my key was compromised" flows.

**Independent Test**: A user with a working configuration can change the model name, save, and see the next LLM call use the new model without restarting the app or signing out. Clearing the configuration immediately disables LLM-dependent features for that user, with no leakage of the prior key.

**Acceptance Scenarios**:

1. **Given** a configured user, **When** they change the model name in settings and save, **Then** the next LLM-dependent call uses the new model.
2. **Given** a configured user, **When** they click "Clear configuration," **Then** the credentials are removed from local storage and subsequent LLM-dependent calls revert to using the operator's `.env` default credentials (or, if those are also unavailable, to the "LLM unavailable" prompt).
3. **Given** a user clears their configuration on one device, **When** they sign in on a second device that never had configuration, **Then** that second device is also unconfigured (configuration is per-device, not synced server-side).

---

### User Story 3 - User reviews their cumulative token usage (Priority: P2)

A user who has connected their own LLM provider wants to know how many tokens they've spent through this app, so they can gauge their consumption against their provider's quota themselves. They open the LLM settings panel and see a "Token usage" section showing tokens used in the current session, tokens used today, tokens used in their lifetime against this app, and a per-model breakdown.

**Why this priority**: Users who bring their own key need *some* visibility into spend or they will hesitate to use LLM-heavy features. Without this, a user has no way to know whether the app has used 100 tokens or 100,000 of their key's quota. P2 (not P1) because the feature is still functional without it; the bring-your-own-key flow itself is the P1.

**Independent Test**: A user with a configured LLM triggers two LLM-dependent calls, opens the LLM settings panel, and sees the token-usage dialog show a non-zero session total whose value equals the sum of the two calls' `usage.total_tokens`. Closing and reopening the panel preserves the lifetime total; ending the session and starting a new one resets the session total but preserves the lifetime total.

**Acceptance Scenarios**:

1. **Given** a configured user who has just signed in for the first time today, **When** they open the LLM settings panel, **Then** the token-usage dialog shows session total = 0, today's total = 0, lifetime total = whatever was previously recorded.
2. **Given** a configured user who has just made an LLM-dependent call that returned `usage.total_tokens = 250`, **When** they open the token-usage dialog, **Then** session total, today's total, and lifetime total have each increased by 250.
3. **Given** a configured user, **When** they click "Reset usage stats," **Then** session, today, and lifetime totals all reset to 0 with no other side effects (the user's saved API key, base URL, and model are unchanged).
4. **Given** a user who has not configured personal credentials (i.e. their calls use the operator default), **When** they open the LLM settings panel, **Then** the token-usage dialog is hidden or shows "not tracked while using operator default" — operator-default usage is *not* attributed to the user.
5. **Given** a chat-completions response that does not include a `usage` block (some endpoints omit it), **When** the user opens the token-usage dialog, **Then** the call is recorded as "unknown tokens" in a counter, and the numeric totals reflect only calls where `usage.total_tokens` was reported.

---

### User Story 4 - Operator verifies that user-configured calls never fall back to operator credentials (Priority: P3)

The operator/admin (or a security reviewer) needs to verify the override semantics: once a user has supplied their own LLM configuration, the operator's `.env`-supplied credentials are never used for that user's calls. They also need to confirm that **unconfigured** users continue to be served by the operator's defaults (the system does not fail closed for them). Together, this proves the per-user override is honored and the default fallback is preserved.

**Why this priority**: This is verification scaffolding rather than user-visible value, but it is the principal billing-correctness and isolation guarantee promised by the feature: a user who set their own key never silently spends the operator's; a user who did not set one still gets a working product.

**Independent Test**: With operator env vars set and User A configured, User B unconfigured: User A's call uses A's endpoint and is billed to A; User B's call uses the operator's defaults and is billed to the operator. Audit-log events distinguish the two.

**Acceptance Scenarios**:

1. **Given** operator env vars are set and a user has valid personal configuration, **When** the user triggers an LLM-dependent feature, **Then** the call succeeds against the user's endpoint and the operator's env vars are not used.
2. **Given** operator env vars are set and a user has no personal configuration, **When** the user triggers an LLM-dependent feature, **Then** the call succeeds against the operator's default endpoint and an audit event identifies the call as having used the operator default.
3. **Given** operator env vars are unset and a user has no personal configuration, **When** the user triggers an LLM-dependent feature, **Then** the call fails closed with an "LLM unavailable — set your own provider in settings" prompt and the audit log records an `llm.unconfigured` event.
4. **Given** any user changes their LLM configuration, **When** the change is persisted, **Then** the audit log records an `llm.config_change` event that includes the base URL and model name but never the API key or any prefix/suffix of it.

---

### Edge Cases

- A user supplies a base URL that is reachable but does not implement the OpenAI-compatible chat-completions contract — the system surfaces an "endpoint did not respond in OpenAI-compatible format" failure, not a generic 500.
- A user supplies a model name that the endpoint does not host — the failure is surfaced to the originating UI with the upstream error message preserved verbatim, and no automatic fallback to a different model occurs.
- The user's chosen endpoint is slow or unreachable — the request times out within a bounded window (default: same upper bound as the existing orchestrator LLM timeout) and the user sees a retryable failure, not a hung UI. The system does NOT fall back to the operator's default credentials in this case.
- The user's saved key was valid at save time but later fails at runtime (key revoked, billing lapsed, 429 rate limit, 401 auth) — the upstream error is surfaced to the originating UI verbatim; the operator's default credentials are NOT consulted; the user must retry, fix their key, or clear their personal configuration to revert to the operator default for subsequent calls.
- A user clears their configuration mid-request — the in-flight request completes or fails as already dispatched, but no subsequent request reuses the cleared credentials.
- A user attempts to manipulate the request path to call the LLM proxy with somebody else's stored credentials — the system rejects the request because credentials are sourced exclusively from the caller's own session, never from a stored, server-side, per-user record.
- A previously-running server-initiated background job (e.g. the daily feedback quality / proposals job from feature 004) needs LLM access at a time when no user is connected — it uses the operator's `.env`-supplied default credentials, exactly as before; per-user overrides do not apply to system-initiated jobs because no individual user is the "caller."
- The operator's `.env` LLM credentials are unset AND the user has no personal configuration — the LLM-dependent feature fails closed with an "LLM unavailable — set your own provider in settings" prompt, and the audit log records an `llm.unconfigured` event scoped to that user.
- A user's stored configuration is deleted by the browser (cache wipe, private mode) — they are returned to the unconfigured prompt with no other side effects.
- A user signs out and signs back in on the same device — their previously saved LLM configuration is still present and active, exactly as they left it; sign-out does not clear it.
- A user's session token expires and silently refreshes — the stored LLM configuration is unaffected and continues to be used for the next LLM-dependent request.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow each authenticated user to set, view, update, and clear their own LLM configuration consisting of an API key, base URL, and model name, scoped to their own browser session/device.
- **FR-002**: The user's API key MUST never be persisted by the server (no database row, no log line, no audit field) and MUST never be readable by any other user.
- **FR-003**: When a user has saved a valid personal LLM configuration, all LLM-dependent features invoked on their behalf MUST use only that configuration; the server MUST NOT fall back to operator-controlled environment variables for that user's calls.
- **FR-004**: When a user has **not** saved a personal configuration, the system MUST use the operator's `.env`-supplied default LLM credentials (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`) to serve that user's LLM-dependent features. The user MUST NOT be blocked or forced to configure their own credentials.
- **FR-004a**: When a user has not saved a personal configuration AND the operator's default credentials are also unavailable (env unset or invalid), the system MUST surface a clear, actionable "LLM unavailable — set your own provider in settings" prompt that links to the settings panel, rather than a generic error.
- **FR-005**: The settings panel MUST provide a "Test Connection" action that issues a minimal **chat-completions** request (single short prompt, `max_tokens: 1`) against the user's configured base URL using the user's API key and model name, and reports success/failure with a human-readable reason. The probe MUST exercise the chat-completions path itself (a `/models` listing or other catalog-only call is insufficient because it does not prove the chosen model is served by the chat-completions endpoint). The probe result MUST NOT be cached in a way that could mask later changes; "connected" status reflects the most recent successful probe only.
- **FR-006**: The system MUST emit an audit event (consistent with feature 003) whenever a user creates, updates, clears, or **tests** their LLM configuration; this event MUST record the base URL and model name (and, for `tested`, the success/failure result and `error_class` on failure) and MUST NOT record the API key or any contiguous substring of it of length ≥ 4.
- **FR-007**: The system MUST emit an audit event whenever an LLM-dependent feature is invoked but cannot proceed because **neither** the user's personal configuration **nor** the operator's `.env` default is usable, so that operators can distinguish "feature failed" from "feature gated by missing credentials at all levels."
- **FR-007a**: For every LLM-dependent call served on a user's behalf, the system MUST emit an audit event whose payload identifies the credential source as either `user` (personal configuration) or `operator_default` (env fallback), so that operators can answer "for whom did the operator's account pay?" without ambiguity. The API key itself MUST NOT appear in the event under either source.
- **FR-008**: The system MUST be compatible with any endpoint that conforms to the OpenAI chat-completions request/response shape, including but not limited to the official OpenAI API, OpenRouter, Anthropic via an OpenAI-compatible proxy, LM Studio, Ollama's OpenAI-compatible mode, and vLLM.
- **FR-009**: Errors returned by the user's chosen endpoint (auth failure, rate limit, model-not-found, malformed response, transport/network failure) MUST be surfaced to the originating UI with the upstream error message preserved, and MUST NOT be silently retried against a different endpoint or model, **and MUST NOT silently fall back to the operator's `.env` default credentials**. The user retains the option to retry, fix their saved configuration, or clear it (which reverts them to the operator default for subsequent calls).
- **FR-010**: The server-side environment variables (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`) MUST continue to be supported as the operator's default credentials for users who have not configured their own. They MUST NOT be the source of truth for any user who has saved a personal configuration.
- **FR-011**: Server-initiated background jobs (e.g. the daily feedback quality / proposals job from feature 004) MUST continue to use the operator's `.env`-supplied default credentials, since no individual user is the caller. Per-user overrides do not apply to these jobs.
- **FR-012**: Clearing a user's configuration MUST take effect for all subsequent requests immediately; in-flight requests are unaffected, but no later request reuses the cleared values.
- **FR-013**: The system MUST NOT auto-clear a user's stored LLM configuration on sign-out, session expiry, or silent token refresh. Stored credentials persist on the device until the user explicitly clicks "Clear" (or the browser itself evicts the storage). Signing back in on the same device restores access to the previously saved configuration without re-prompting.
- **FR-014**: For each LLM-dependent call served using a user's *personal* configuration, the system MUST capture the response's `usage.total_tokens` (or record "unknown" if the field is absent) and accumulate it into three counters scoped to that user: session total, today's total (rolling 24h or calendar-day, see FR-015), and lifetime total. Per-model breakdown MUST also be maintained.
- **FR-015**: Token-usage counters MUST follow these reset rules: session total resets when the browser tab is closed or the user signs out and back in; today's total resets at the local-day boundary on the user's device; lifetime total persists indefinitely on the user's device until the user clicks "Reset usage stats." All counters are device-local — they are not synchronized server-side and are not aggregated across devices.
- **FR-016**: Token-usage counters MUST NOT include calls served from the operator's default credentials (no per-user attribution of operator-default spend). The dialog SHOULD make this distinction visible to the user.
- **FR-017**: The settings panel MUST include a "Token usage" section displaying session total, today's total, lifetime total, and a per-model breakdown, plus a "Reset usage stats" action. The dialog MUST NOT predict remaining balance, query provider-specific balance endpoints, or warn about impending quota exhaustion (these are explicitly out of scope per Clarifications).

### Key Entities

- **User LLM Configuration**: A per-user, browser-resident record holding `apiKey` (sensitive, never sent to backend storage), `baseUrl`, `modelName`, and a derived `connectedAt` timestamp set after a successful "Test Connection." Lives on the user's device only; is not synchronized across devices by the server.
- **LLM Config Change Event**: An audit-log entry (event class `llm.config_change`) recording who changed their configuration, when, and the non-sensitive fields (base URL, model name, action: created/updated/cleared). This is the only server-side trace of configuration activity.
- **LLM Unconfigured Event**: An audit-log entry (event class `llm.unconfigured`) recording the user, the feature that was gated, and the timestamp, emitted whenever an LLM-dependent feature could not proceed because **both** the user's personal configuration and the operator's `.env` default were unavailable.
- **LLM Call Credential-Source Event**: An audit-log entry (event class `llm.call`) recording, per LLM-dependent invocation, the user, feature, timestamp, and the credential source (`user` or `operator_default`). The base URL and model are recorded; the API key is never recorded.
- **Token Usage Counters**: A per-user, browser-resident set of three integer counters (`session`, `today`, `lifetime`) plus a per-model breakdown map. Updated on every personal-credential LLM call from the response's `usage.total_tokens`. Lives on the user's device only; is not synchronized server-side.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of LLM calls performed for users who have saved a personal configuration are paid for by that user's own provider account; 0% silently use the operator's defaults. Verifiable by an audit-log query filtering on `credential_source = user` and confirming the corresponding upstream billing matches the user's account, not the operator's.
- **SC-002**: 0 user API keys appear in server logs, the database, the audit log, or any backup artifact, verified by an automated grep of the relevant artifacts as part of release validation.
- **SC-003**: A new user can locate the LLM settings panel and complete a successful "Test Connection" round-trip (key entered, base URL and model set, success indicator shown) in under 90 seconds on the first attempt, measured against at least 5 trial users.
- **SC-004**: At least 95% of users who *choose* to bring their own LLM (i.e. start the settings flow) successfully save a configuration that passes the "Test Connection" probe on the same session, measured by funnel events from "settings opened" to "configuration saved & probe-passed."
- **SC-005**: For features that previously called the LLM (component feedback proposal pre-pass, knowledge synthesis, any agent integration), the user-perceived success rate after this feature ships is no more than 5 percentage points below the pre-change rate, holding the user's chosen model fixed.
- **SC-006**: Operators can answer "for which users did the operator's `.env` LLM credentials pay in the past 30 days?" with a single audit-log query against the `credential_source` field of `llm.call` events; the same query, filtered to users who *do* have a personal configuration on file, MUST return zero rows.
- **SC-007**: A user with personal LLM configuration who has just made N LLM-dependent calls can open the token-usage dialog and see session and lifetime totals that match the sum of `usage.total_tokens` reported across those N responses (allowing for "unknown" entries where the upstream omitted the field). 0 token-usage data leaks to other users or to server-side storage.

## Assumptions

- **Transport**: The server continues to perform LLM calls on behalf of the user (i.e. acts as a proxy), accepting the user's credentials transiently per request rather than the user's browser calling the LLM endpoint directly. Rationale: existing LLM-dependent flows are operated server-side and the user's request was framed as "move env variables to the frontend," not "move LLM calls to the frontend."
- **Storage**: Credentials are stored on the user's own device in persistent client-side storage, with a clear in-UI privacy notice that the key lives on the user's device and the user is responsible for protecting it (signing out, clearing storage on shared machines). No server-side per-user credential store is created.
- **Background jobs**: Server-initiated jobs that previously called an LLM (notably the daily feedback quality / proposals job from feature 004) continue to run on their existing schedule using the operator's `.env`-supplied credentials. They do not consume any user's personal configuration, since no individual user is the "caller." If the operator's `.env` credentials are unset, the job logs and skips, exactly as feature 004 already handles.
- **Migration**: The env vars (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`) remain part of the documented runtime configuration as the operator-default credentials. Their role is unchanged for users who have not configured their own; their role is *suppressed* for users who have. No existing deployment needs to remove them.
- **Compatibility surface**: "OpenAI-compatible" is interpreted as the chat-completions endpoint contract; embeddings, fine-tuning, and assistants APIs are out of scope.
- **Audit consistency**: New audit event classes (`llm.config_change`, `llm.unconfigured`, `llm.call`) follow the same per-user isolation, hash-chain, and retention rules established by feature 003 and require no schema changes beyond adding the event-class identifiers.

## Out of Scope

- Server-side per-user credential storage, syncing across devices, or team-shared keys.
- Provider-specific UIs beyond a single "API key / base URL / model" trio (no OAuth flow, no provider catalog beyond model name).
- **Predictive** balance/quota warnings ("you're running low") — no universal OpenAI-compatible API for remaining balance exists; observed cumulative usage (FR-014..FR-017) is in scope, but predictions are not.
- Provider-specific balance probes (OpenRouter `/api/v1/credits`, OpenAI billing endpoints, etc.) — explicitly deferred.
- Server-side aggregation of usage across users; cross-device sync of usage; per-user spend caps; cost-in-dollars estimation — these are downstream features that build on this one.
- Replacing or extending the existing `Ollama`-based knowledge-synthesis path; that module continues to operate, sourcing credentials from the calling user's personal configuration when set, otherwise from the operator's `.env` defaults.
- Migrating any non-LLM environment variables.
