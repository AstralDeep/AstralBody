# Quickstart — User-Configurable LLM Subscription

**Audience**: a developer who has just merged this branch and wants to verify the feature end-to-end on a local AstralBody instance. Uses the existing dev runtime (mock auth + Docker Compose).

---

## 0. Prereqs

- AstralBody repo checked out at branch `006-user-llm-config`.
- `docker compose up` style runtime as today (PostgreSQL + orchestrator + frontend dev server).
- An OpenAI-compatible endpoint and API key for *you* (the test user). Easiest options for verification:
  - A local Ollama with `ollama pull qwen2.5:0.5b` and serving on `http://localhost:11434/v1` — `api_key` can be the literal string `ollama`.
  - Or a real OpenAI key against `https://api.openai.com/v1` with model `gpt-4o-mini`.

---

## 1. Verify the operator-default path still works (US1:1, US4:2)

1. Set `.env` with valid `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL` pointing at *some* working endpoint (different from the one you'll use as your "personal" config later, so audit events are distinguishable).
2. Start the system: `cd backend && .venv/Scripts/python.exe start.py`.
3. Open the frontend, sign in as the dev user, do *not* visit LLM Settings.
4. Trigger an LLM-dependent action (e.g., submit a chat that goes through tool dispatch).
5. ✅ Expected: the call succeeds. `audit_events` shows one `llm.call` row with `credential_source='operator_default'`. No `llm_usage_report` arrives at the browser (because operator-default calls don't emit it). The Token Usage dialog shows zeros.

---

## 2. Verify the personal-config save path with Test Connection (US1:2, FR-005, Clarification Q4)

1. Open the LLM Settings panel (sidebar entry "LLM Settings").
2. Enter your *personal* `api_key`, `base_url`, `model`.
3. Click "Test Connection."
4. ✅ Expected: a green check, latency under 5 s. The probe makes a real `chat.completions.create` request with `max_tokens: 1`. `audit_events` shows one `llm.config_change` row with `action='tested', result='success'`.
5. Click "Save."
6. ✅ Expected: a second `llm.config_change` row with `action='created'`. The settings panel header now reads "Connected — using your own provider." `localStorage['astralbody.llm.config.v1']` is populated.

---

## 3. Verify user-credential override (US1:3, US4:1, FR-003)

1. Trigger an LLM-dependent action again.
2. ✅ Expected:
   - The call uses *your* endpoint (verifiable by hitting an endpoint where you can see request logs, or by setting `model` to something only your endpoint serves).
   - `audit_events` shows an `llm.call` row with `credential_source='user'`, your `base_url`, your `model`, the actual `total_tokens`.
   - A `llm_usage_report` WS message arrived; the Token Usage dialog now shows session/today/lifetime equal to that call's `total_tokens`. The per-model breakdown shows your model name.

---

## 4. Verify no runtime fallback when your key fails (FR-009, edge case)

1. In the settings panel, edit the `api_key` to `sk-deliberately-broken` and save (skip Test Connection).
2. Trigger an LLM-dependent action.
3. ✅ Expected:
   - The call fails. The UI surfaces the upstream error verbatim (e.g., "Incorrect API key provided…").
   - `audit_events` shows an `llm.call` row with `credential_source='user', outcome='failure', upstream_error_class='auth_failed'`.
   - **No** `llm.call` row with `credential_source='operator_default'` is emitted for this action — i.e., the system did not silently fall back to the operator's key. **This is the SC-006 invariant.**
4. Click "Clear configuration" in the settings panel.
5. Trigger the same action again.
6. ✅ Expected: the call succeeds against the operator default; one new `llm.call` row with `credential_source='operator_default'`.

---

## 5. Verify sign-out preserves the saved config (FR-013, US3:1)

1. Save a working personal config.
2. Sign out (whatever the existing dev sign-out path is — the JWT-clear mechanism).
3. Sign back in as the same user.
4. Open the LLM Settings panel.
5. ✅ Expected: the configuration is still there; the panel header still reads "Connected — using your own provider." `localStorage['astralbody.llm.config.v1']` was untouched. No re-prompt.

---

## 6. Verify "fail closed" when both env and user are missing (US4:3, FR-004a)

1. Stop the orchestrator. In `.env`, blank out `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`. Restart the orchestrator.
2. In the frontend, click "Clear configuration" in LLM Settings.
3. Trigger an LLM-dependent action.
4. ✅ Expected:
   - The UI surfaces "LLM unavailable — set your own provider in settings" and a link to the settings panel.
   - `audit_events` shows one `llm.unconfigured` row with `feature='tool_dispatch'` (or whichever call-site).

---

## 7. Verify token-usage counters (US3:2, US3:3, US3:5, FR-014..FR-017)

1. Restore a working personal config. Make 3 LLM-dependent calls.
2. Open the Token Usage dialog (inside LLM Settings).
3. ✅ Expected:
   - `session`, `today`, `lifetime` each equal the sum of the 3 responses' `usage.total_tokens`.
   - `perModel` shows your model with the same total.
4. Click "Reset usage stats."
5. ✅ Expected: all numeric counters → 0; `perModel` empty; `apiKey/baseUrl/model` untouched (still "Connected").
6. Make one more call against an endpoint that omits `usage` (e.g., a misbehaving local server you control).
7. ✅ Expected: numeric counters stay at 0; `unknownCalls` increments to 1.

---

## 8. Verify operator audit query (SC-006)

```sql
SELECT actor_user_id, COUNT(*)
FROM audit_events
WHERE event_class = 'llm.call'
  AND payload->>'credential_source' = 'operator_default'
  AND actor_user_id IN (
    SELECT DISTINCT actor_user_id
    FROM audit_events
    WHERE event_class = 'llm.config_change'
      AND payload->>'action' IN ('created', 'updated')
  )
  AND recorded_at > now() - interval '7 days'
GROUP BY actor_user_id;
```

✅ Expected: zero rows. (Any user with a personal config who shows up in this query is a bug in the credential-resolution path.)

---

## 9. Run the test suites

```bash
docker exec astralbody bash -c "cd /app/backend && python -m pytest llm_config/tests/ audit/tests/ feedback/tests/ -q"
cd frontend && npx vitest run src/components/llm/ src/hooks/useLlmConfig.test.ts src/hooks/useTokenUsage.test.ts
```

✅ Expected: all green; coverage ≥ 90% on changed files.

---

## What's *not* in this quickstart (and why)

- **Predictive token-runout warnings** — explicitly out of scope (Clarification Q5). If you're looking for a "you're running low" message, it's not there; observed cumulative usage in the Token Usage dialog is the only visibility offered.
- **Cross-device sync** — explicitly out of scope. Re-do step 2 on each device you sign in from.
- **Knowledge-synthesis credentials** — `KNOWLEDGE_LLM_*` env vars continue to drive `backend/orchestrator/knowledge_synthesis.py` unchanged; this feature does not touch them.
