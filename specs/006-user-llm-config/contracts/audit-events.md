# Audit Event Contracts — `llm.*` family

Three new `event_class` identifiers, all recorded via the existing `audit/recorder.py` machinery from feature 003. Per-user isolation, hash-chain, retention, and `verify-chain` / `purge-expired` CLIs apply unchanged.

---

## 1. `llm.config_change`

**Emitted when**: a user creates, updates, clears, or *tests* their personal LLM configuration.

**Payload**:

```json
{
  "action": "created" | "updated" | "cleared" | "tested",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "result": "success" | "failure",          // present only when action="tested"
  "error_class": "auth_failed" | "model_not_found" | "transport_error" | "contract_violation" | "other",  // present only when action="tested" and result="failure"
  "transport": "ws" | "rest"
}
```

**MUST NOT contain**: `api_key` or any prefix/suffix/hash of it. Asserted by a unit test: `payload_serializer(SessionCreds("sk-real",…))` is run through the recorder and the resulting JSON is scanned for `"sk-"` and any substring of the input key.

**`actor_user_id`**: the authenticated user who initiated the change. Cross-user emission is impossible by construction (the WS handler and REST endpoint both source `user_id` from the JWT alone, never from the request body — same pattern as feature 003).

**`outcome`**: `"success"` for created/updated/cleared/tested-success; `"failure"` for tested-failure.

---

## 2. `llm.unconfigured`

**Emitted when**: a user invokes an LLM-dependent feature but neither their personal config nor the operator's `.env` defaults are usable. Distinguishes "feature is gated" from "feature failed mid-flight."

**Payload**:

```json
{
  "feature": "tool_dispatch" | "tool_summary" | "agent_generation" | "feedback_proposal_pre_pass" | "<other call-site>",
  "reason": "no_user_config_no_env_default"
}
```

**`outcome`**: always `"failure"`.

**Frequency cap**: in real usage this can fire once per user-action; we do **not** rate-limit the audit recorder for this class because the feature 003 `audit_events` partial-index-on-failures already handles the query path.

---

## 3. `llm.call`

**Emitted when**: an LLM-dependent call is *served*, regardless of credential source or outcome. This is the event class operators will query against to answer "for whom did the operator's account pay?" (SC-006).

**Payload**:

```json
{
  "feature": "tool_dispatch" | "tool_summary" | "agent_generation" | "feedback_proposal_pre_pass" | "test_connection" | "<other>",
  "credential_source": "user" | "operator_default",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "total_tokens": 247,                       // null if upstream omitted usage
  "outcome": "success" | "failure",
  "upstream_error_class": "auth_failed" | "rate_limit" | "model_not_found" | "transport_error" | "other"  // present only on failure
}
```

**`actor_user_id`**: the WS-authenticated user who triggered the call. Background-job calls (no user) emit `llm.call` events with `actor_user_id = "system"` (matching the existing convention for system-initiated audit events from feature 004 — see project memory note on the daily quality job).

**Per-user isolation**: identical to feature 003's enforcement. A user querying `GET /api/audit?event_class=llm.call` only sees their own rows.

**Volume note**: this is the highest-volume new event class — one per LLM call. For comparison with feature 003's volumetrics, expect roughly the same order as `tool dispatch` events (which also pair in_progress→success/failure, but `llm.call` only emits the terminal event). The existing partial-index strategy is sufficient.

---

## Operator queries enabled by these events

| Question | Query |
|----------|-------|
| Did any user with personal config silently use the operator default? | `event_class='llm.call' AND credential_source='operator_default' AND actor_user_id IN (SELECT actor_user_id FROM audit_events WHERE event_class='llm.config_change' AND payload->>'action' IN ('created','updated'))` — must return zero (SC-006). |
| Which users have personal configs? | `SELECT DISTINCT actor_user_id FROM audit_events WHERE event_class='llm.config_change' AND payload->>'action' IN ('created','updated') AND actor_user_id NOT IN (SELECT actor_user_id FROM audit_events WHERE event_class='llm.config_change' AND payload->>'action'='cleared' AND recorded_at > <prior-update-timestamp>)` |
| What's the operator's monthly LLM bill driven by unconfigured users? | `SELECT COUNT(*), SUM((payload->>'total_tokens')::int) FROM audit_events WHERE event_class='llm.call' AND credential_source='operator_default' AND outcome='success' AND recorded_at > now() - interval '30 days'` |
| Did any audit event ever leak an API key? | Automated test in `audit/tests/` greps the entire `audit_events.payload` corpus for any string matching `\bsk-[A-Za-z0-9]{20,}\b` and several common provider key prefixes; expected match count = 0 (SC-002). |
