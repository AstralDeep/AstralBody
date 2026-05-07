# Quickstart — External AI Service Agents

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-05-07

A developer walkthrough for bringing the three new agents (CLASSify, Forecaster, LLM-Factory) up locally and exercising one tool per agent against the live services.

---

## Prerequisites

- Local AstralBody dev environment is running (the `astralbody` Docker container, or `cd backend && .venv/Scripts/python.exe start.py` natively).
- A Keycloak login or the dev mock-auth (`dev-token` / sub `test_user`).
- API keys for the three external services (request from your team lead if you don't have them — they are personal, not shared).

---

## 1. Start the system

```powershell
# From the repo root
cd backend
.venv/Scripts/python.exe start.py
```

`start.py` will auto-discover the three new agents under [backend/agents/classify/](../../backend/agents/classify/), [backend/agents/forecaster/](../../backend/agents/forecaster/), and [backend/agents/llm_factory/](../../backend/agents/llm_factory/) and assign them sequential ports starting from `AGENT_PORT` (default 8003). Look for log lines like:

```
[start] launching agent classify-1 on port 800N
[start] launching agent forecaster-1 on port 800M
[start] launching agent llm-factory-1 on port 800L
```

If you want to pin them, set `CLASSIFY_AGENT_PORT`, `FORECASTER_AGENT_PORT`, `LLM_FACTORY_AGENT_PORT` in your env.

---

## 2. Open the frontend and verify the agents appear

Navigate to the running frontend (port 5173 in dev). Open the agent list / tool picker — you should see three new entries with the placeholder URL hints from `card_metadata`:

- **CLASSify** — placeholder: `https://classify.ai.uky.edu/`
- **Timeseries Forecaster** — placeholder: `https://forecaster.ai.uky.edu/`
- **LLM-Factory** — placeholder: `https://llm-factory.ai.uky.edu/`

All three should show as "configuration required" (locked tools).

---

## 3. Configure CLASSify

1. Click into the CLASSify agent's permissions / settings panel.
2. Enter your URL (the placeholder text is fine to copy if you're using the production deployment) and your CLASSify API key.
3. Click **Save**.

Expected within 5 seconds:

- Modal shows green "Credentials accepted by service."
- Tools become unlocked in the picker.
- A `tool` audit event is visible in the Audit Log panel for `_credentials_check` with verdict `ok`.

If you see "Credentials rejected by service.", your API key is wrong or expired. If you see "Service unreachable", check the URL or your network.

Repeat for Forecaster and LLM-Factory.

---

## 4. Smoke-test one tool per agent

### CLASSify — `get_ml_options`

In a fresh chat, ask: *"Use CLASSify to list the ML options."*

Expected:
- Orchestrator routes to `classify-1.get_ml_options`.
- Tool returns within ~2 seconds.
- Chat renders the list of supported hyperparameters as a `Card` or `Table`.
- Audit log shows paired `in_progress` / `success` events with a single correlation id.

### CLASSify — `train_classifier` (long-running, smoke-tests the poller)

Upload a small CSV via the chat upload mechanism, then ask: *"Use CLASSify to train a classifier on the column `target`."*

Expected:
- Tool returns immediately with a "Job started" message and a `task_id`.
- Within ~5 seconds, the chat shows a progress bar with `phase: training`.
- Periodic updates appear (every ~5 seconds) until the upstream marks the job done.
- A final "Training complete" message appears with metrics and SHAP URL.
- The `(test_user, classify-1)` slot in `ConcurrencyCap._inflight` is empty afterward (verify via `python -c "from orchestrator.app import orchestrator; print(orchestrator.concurrency_cap._inflight)"` against a debug shell — temporary; remove before merge).

### Forecaster — `get_results_summary` (synchronous, lightest probe)

Ask: *"Use Forecaster to show the results summary for dataset `demo`."*

If the dataset doesn't exist, expect a `bad_request` error — that still confirms the wiring is correct.

### LLM-Factory — `chat_with_model`

Ask: *"Use LLM-Factory with model `<your-model-id>` to answer: what is 2 + 2?"*

Expected:
- Tool streams the answer back via `ToolStreamData` chunks.
- Final aggregated answer appears in chat as a normal assistant message rendered through the existing primitives.

---

## 5. Verify the FR-026 concurrency cap

Start three CLASSify training jobs in quick succession (any three CSVs). All three should kick off normally and you should see three `tool_progress` streams.

Try to start a fourth before any has finished. Expected:

- The orchestrator returns an `RenderAlert` immediately (no upstream HTTP call made).
- The alert reads: *"You already have 3 jobs running on CLASSify. Wait for one to finish or cancel one before starting another. (Running: <job_id_1>, <job_id_2>, <job_id_3>)"*
- No new entry appears in `ConcurrencyCap._inflight`.

Wait for one to finish, then retry — it should succeed.

---

## 6. Verify SSRF guards reject obviously-bad URLs

In the agent permissions modal, enter `http://localhost:8001/` as the CLASSify URL and save.

Expected: `credential_test: "unreachable"` with detail `"private/loopback hosts are not allowed"`. The credentials are still saved (they are syntactically valid), but the agent will continue to refuse all HTTP egress to that URL until it is changed. Tools remain effectively unusable.

---

## 7. Run the test suite

```powershell
# Inside the astralbody container if you're using Docker
docker exec astralbody bash -c "cd /app/backend && python -m pytest agents/classify/tests/ agents/forecaster/tests/ agents/llm_factory/tests/ shared/tests/test_external_http.py orchestrator/tests/test_concurrency_cap.py -q"
```

Expected: all green. Coverage on changed files ≥ 90% (Constitution Principle III).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Agent doesn't appear in the frontend list | `start.py` couldn't import the agent (e.g. syntax error). | Check the orchestrator log for ImportError; usually a missing `__init__.py` re-export. |
| "Credential test failed: unreachable" but the URL is correct | SSRF guard is blocking a legitimate private host. | Add the host to `EXTERNAL_AGENT_ALLOWED_PRIVATE_HOSTS` env var. |
| Long-running job never completes in chat | `progress_streaming` flag is OFF. | Enable it in the system feature-flag config. |
| `concurrency_cap` never frees slots | Poller crashed before calling `release`. | Check `try/finally` in `JobPoller.run`. |
| 401 on every call but the key works in curl | Header is being normalized somewhere. | Confirm `Authorization: Bearer ...` is being passed verbatim by `external_http.py::request`. |
