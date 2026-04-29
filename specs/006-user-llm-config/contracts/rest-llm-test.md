# REST Contract — `POST /api/llm/test`

The Test Connection probe. Stateless: the credentials in the request body are used to construct a one-shot `OpenAI` client, the probe fires, and the result is returned. The credentials are **never** persisted, **never** logged, and **never** stored in `_session_llm_creds` (saving credentials is the WS path's job — `llm_config_set` — not this endpoint's).

---

## Request

```http
POST /api/llm/test HTTP/1.1
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "api_key": "sk-…",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini"
}
```

**Authentication**: standard Keycloak JWT validation via the existing FastAPI dependency. **Authorization**: any authenticated user may probe their own credentials; this endpoint never accepts a `user_id` parameter and always operates on the caller alone (matching the per-user-isolation pattern from feature 003's REST routes).

**Validation**:
- `api_key`, `base_url`, `model` MUST all be non-empty strings.
- `base_url` MUST parse as an absolute URL with `http(s)://` scheme.
- 422 on validation failure (FastAPI default).

---

## Probe behavior

```python
client = OpenAI(api_key=req.api_key, base_url=req.base_url, timeout=PROBE_TIMEOUT_SECONDS)
resp = await asyncio.to_thread(
    client.chat.completions.create,
    model=req.model,
    messages=[{"role": "user", "content": "ping"}],
    max_tokens=1,
)
```

`PROBE_TIMEOUT_SECONDS = 15` (matches the existing orchestrator LLM timeout upper bound).

---

## Response — success

```http
200 OK
Content-Type: application/json

{
  "ok": true,
  "model": "gpt-4o-mini",
  "latency_ms": 612,
  "probed_at": "2026-04-28T15:42:09.231Z"
}
```

`latency_ms` is wall-clock around the `chat.completions.create` call; useful for the settings panel to show "responded in 0.6 s."

---

## Response — failure

```http
200 OK
Content-Type: application/json

{
  "ok": false,
  "model": "gpt-4o-mini",
  "error_class": "auth_failed" | "model_not_found" | "transport_error" | "contract_violation" | "other",
  "upstream_message": "<verbatim message from the SDK exception>",
  "probed_at": "2026-04-28T15:42:09.231Z"
}
```

**Why HTTP 200 on a failed probe**: the request itself succeeded — we got a definitive answer that the user's credentials don't work. Returning 4xx/5xx would conflate "your request was malformed" with "your saved credentials don't work." The frontend distinguishes by reading `ok`. (HTTP 4xx/5xx is reserved for actual API-side failures like missing JWT or malformed body.)

**`error_class` mapping** (deterministic, for UI copy):
- HTTP 401 from upstream → `auth_failed`
- HTTP 404 / SDK `NotFoundError` mentioning the model → `model_not_found`
- Network/DNS/timeout → `transport_error`
- Response missing the expected `choices[0].message` shape → `contract_violation`
- Anything else → `other` (UI shows `upstream_message` verbatim)

---

## Audit

The endpoint emits an `llm.config_change` audit event with `action: "tested"` and a `result: "success" | "failure"` field, plus the `error_class` if applicable. The `api_key` is never recorded; the `base_url` and `model` are.

---

## Logging

Standard FastAPI request logging applies, but the request body is filtered before logging via the existing log scrubber pattern (extended in `backend/llm_config/log_scrub.py` to recognize the `api_key` field of the `POST /api/llm/test` payload).
