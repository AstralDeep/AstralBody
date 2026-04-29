# WebSocket Message Contracts

All messages flow over the existing `ws://localhost:8001/ws` connection established by `useWebSocket.ts`. Authentication piggybacks on the existing `register_ui` token-validation path — every new message type below is rejected unless the connection is already authenticated.

Three new message types and one extension to an existing message.

---

## 1. `register_ui` (extension to existing message)

**Direction**: Client → Server. **When**: once, on initial WebSocket setup.

**Existing fields**: `token`, `device` (already used by ROTE — see project memory).

**New optional field**: `llm_config`.

```jsonc
{
  "type": "register_ui",
  "token": "<JWT>",
  "device": { /* existing ROTE capabilities */ },
  "llm_config": {                       // OPTIONAL
    "api_key": "sk-…",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini"
  }
}
```

**Server behavior**:
1. Validate the JWT exactly as today.
2. If `llm_config` is present and all three fields are non-empty strings, populate `_session_llm_creds[id(ws)]`. **Do not log the `api_key`.**
3. Emit an `llm.config_change` audit event (`action: "created"` if no prior session creds, `"updated"` otherwise) — payload omits the API key.
4. If `llm_config` is malformed (one or two of three fields present, or empty strings), respond with the existing `error` message type and **do not partially populate** `_session_llm_creds`.

**Backward compatibility**: A `register_ui` without `llm_config` continues to work exactly as today — the user is unconfigured server-side and falls back to operator default creds for any LLM-dependent calls.

---

## 2. `llm_config_set`

**Direction**: Client → Server. **When**: the user saves new credentials in the settings panel mid-session (after the initial `register_ui`).

```jsonc
{
  "type": "llm_config_set",
  "config": {
    "api_key": "sk-…",
    "base_url": "https://…",
    "model": "…"
  }
}
```

**Server behavior**:
1. Reject if the WS is not authenticated → `error` response.
2. Validate that all three fields are present and non-empty strings. If not, send back `{ "type": "error", "code": "llm_config_invalid", "message": "<details>" }` and do not mutate state.
3. Replace `_session_llm_creds[id(ws)]` with the new `SessionCreds`.
4. Emit an `llm.config_change` audit event (`action: "updated"` if a prior key existed for this socket, `"created"` otherwise; the determination is made *before* the swap).
5. Respond with `{ "type": "llm_config_ack", "ok": true }`.

**Note**: Test Connection is **not** triggered by this message — the client probes via the REST endpoint *before* sending `llm_config_set`. The server takes the client's word that the config is valid; the next real LLM call will surface any genuine failure.

---

## 3. `llm_config_clear`

**Direction**: Client → Server. **When**: the user clicks "Clear configuration" in the settings panel.

```jsonc
{ "type": "llm_config_clear" }
```

**Server behavior**:
1. Reject if not authenticated.
2. `_session_llm_creds.pop(id(ws), None)`.
3. Emit `llm.config_change` audit event (`action: "cleared"`) — only if there *was* a prior entry; clearing an already-empty slot is a no-op (no audit event).
4. Respond with `{ "type": "llm_config_ack", "ok": true }`.

---

## 4. `llm_usage_report`

**Direction**: Server → Client. **When**: immediately after every LLM-dependent call **whose `credential_source == USER`**. Suppressed for `operator_default` calls (FR-016).

```jsonc
{
  "type": "llm_usage_report",
  "feature": "tool_dispatch",                 // call-site identifier
  "model": "gpt-4o-mini",
  "total_tokens": 247,                        // null if upstream omitted usage
  "prompt_tokens": 180,                       // null if upstream omitted
  "completion_tokens": 67,                    // null if upstream omitted
  "outcome": "success",                       // "success" | "failure"
  "at": "2026-04-28T15:42:09.231Z"
}
```

**Client behavior** (`useTokenUsage` hook):
- On `success`: increment `session`, `today` (with date-rollover handling), `lifetime`, and the `perModel[model]` entry by `total_tokens` (if non-null) or by 0 + `unknownCalls += 1` (if null). Persist to localStorage.
- On `failure`: do not increment numeric counters; the failed call did not consume the user's tokens (or if it did, the upstream didn't tell us, in which case the failure surface elsewhere is more useful than fudging the count).

**Server behavior**:
- Emit immediately after the `await asyncio.to_thread(client.chat.completions.create, …)` returns or raises, in the same `_call_llm` flow that already records the audit event.
- Send is best-effort fire-and-forget (the orchestrator already pattern-matches this for `audit:append`-style notifications). A delivery failure does not affect the LLM call's user-facing result.

---

## 5. `error` (existing message type, extended values)

The existing `error` message gains two new `code` values:

| `code`                      | Meaning                                                                  |
|-----------------------------|--------------------------------------------------------------------------|
| `llm_config_invalid`        | `llm_config_set` payload was malformed (validation failure in §2).        |
| `llm_unavailable`           | A user-initiated LLM call was requested but neither user nor operator-default credentials are usable. (Carries no detail beyond the existing user-facing prompt; the audit log has the full record.) |
