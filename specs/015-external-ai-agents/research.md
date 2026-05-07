# Phase 0 Research — External AI Service Agents

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-05-07

This document records the design decisions reached during Phase 0. Each section follows the **Decision / Rationale / Alternatives considered** format. All `[NEEDS CLARIFICATION]` markers from the spec were resolved in the 2026-05-07 `/speckit-clarify` session and are not re-litigated here.

---

## R-001 Agent layout & file structure

**Decision**: Each new agent lives in its own directory under [backend/agents/](backend/agents/) and follows the canonical four-file layout used by every existing agent: `{name}_agent.py`, `mcp_server.py`, `mcp_tools.py`, `__init__.py`. Two further files (`http_client.py`, `job_poller.py`) are added per agent for HTTP egress and async-job polling respectively, kept agent-local because each service's API surface and async semantics are different.

**Rationale**: The auto-discovery loop in [backend/start.py:37-101](backend/start.py) scans `backend/agents/` for `*_agent.py` files. Following the existing layout means **zero changes to discovery** and predictable port assignment (the next free slot from `AGENT_PORT`, default 8003). [backend/agents/nocodb/](backend/agents/nocodb/) is the closest existing precedent because it also requires user-supplied URL + API key.

**Alternatives considered**:
- *One mega-module wrapping all three services.* Rejected — breaks per-agent enable/disable (FR-024, FR-025) and the existing card/credential model.
- *Plug-in style with each service as a "driver" loaded by one shared agent.* Rejected — interesting but premature; would require new abstraction with a single instance of value (saving boilerplate is not a constitutional goal).

---

## R-002 Per-user credential storage

**Decision**: Reuse the existing `user_credentials` PostgreSQL table (defined in [backend/shared/database.py](backend/shared/database.py)) and the existing E2E ECIES encryption pipeline in [backend/orchestrator/credential_manager.py](backend/orchestrator/credential_manager.py). Each new agent declares its required credentials via `card_metadata.required_credentials` exactly as [backend/agents/nocodb/nocodb_agent.py:31-55](backend/agents/nocodb/nocodb_agent.py#L31-L55) does.

**Rationale**: The infrastructure is already correct: the orchestrator never sees plaintext API keys (encrypts with the agent's registered ECIES public key), the frontend modal automatically renders any field declared in `required_credentials`, and the unique constraint on `(user_id, agent_id, credential_key)` already enforces per-user isolation (FR-005). Adding a parallel storage path would be net-worse on every dimension.

**Alternatives considered**:
- *Session-only credentials (mirror the LLM-config pattern in [backend/llm_config/session_creds.py](backend/llm_config/session_creds.py)).* Rejected — the spec's user stories (especially Story 3, "reconfigure or disconnect") require persistence across sessions; users expect their CLASSify URL to still be saved tomorrow.

---

## R-003 Credential fields per agent

**Decision**: Each of the three agents declares exactly two required credentials: a `*_URL` (Service URL) and a `*_API_KEY`, both with `type: "api_key"` (the existing modal renders this as a masked-input field). Specifically:

| Agent | URL key | API-key key |
|-------|---------|-------------|
| CLASSify | `CLASSIFY_URL` | `CLASSIFY_API_KEY` |
| Forecaster | `FORECASTER_URL` | `FORECASTER_API_KEY` |
| LLM-Factory | `LLM_FACTORY_URL` | `LLM_FACTORY_API_KEY` |

**Rationale**: All three services authenticate via `Authorization: Bearer <API_KEY>` (verified in [Phase 0 service survey](#r-008-external-service-api-shapes) below). Two fields keep the modal clean and the user's mental model simple. The existing `type: "api_key"` value is honored by [AgentPermissionsModal.tsx](frontend/src/components/AgentPermissionsModal.tsx) — no new field-type support is needed.

**Alternatives considered**:
- *Different schemes per service (e.g., `X-API-Key` header for one, `?token=` query for another).* Not needed — every observed endpoint of all three services accepts Bearer.
- *A "saved profiles" abstraction letting users keep multiple URL/key pairs per agent.* Out of scope for v1; the spec asks for "enter URL + key, save, use," not multi-profile.

---

## R-004 SSRF mitigation for user-supplied URLs

**Decision**: All HTTP egress from the three new agents goes through a small helper `backend/shared/external_http.py` that:
1. Normalizes the URL (adds `https://` scheme if missing, strips trailing slash, lowercases host).
2. Resolves the hostname **before** the request and rejects:
   - Loopback (`127.0.0.0/8`, `::1`).
   - RFC1918 (`10/8`, `172.16/12`, `192.168/16`) and link-local (`169.254/16`, `fe80::/10`).
   - `0.0.0.0`, multicast, broadcast.
   - Schemes other than `http`/`https`.
3. Enforces a 30 s connect + read timeout.
4. Disables HTTP redirects by default (caller can opt-in for endpoints that legitimately redirect).
5. Caps response size at 50 MB (prevents an attacker-controlled service from exhausting agent memory).

The block-list is the default; an admin allow-list (env var `EXTERNAL_AGENT_ALLOWED_PRIVATE_HOSTS`, comma-separated) can grant exceptions for ops scenarios where one of these services is hosted internally.

**Rationale**: User-controlled URLs are the canonical SSRF vector. The agent runs with no privileged egress (it's just a Python process in the cluster), but blocking RFC1918 by default prevents trivial cloud-metadata exfiltration (`169.254.169.254`) and lateral movement to internal services. The per-feature decision honors Constitution Principle VII without requiring a system-wide proxy.

**Alternatives considered**:
- *No SSRF guard, trust the user.* Rejected — Constitution Principle VII; users are not always sophisticated and a stolen API key plus a malicious URL = arbitrary internal HTTP request from inside the cluster.
- *Mandatory egress proxy.* Disproportionate; adds operational complexity and a new dependency, neither of which is approved.

---

## R-005 Credential validation ("test connection") at save time

**Decision**: When the user saves credentials, the orchestrator (already routes `PUT /api/agents/{agent_id}/credentials`) calls a new MCP tool on the target agent named `_credentials_check` (underscore-prefixed by convention so it does not appear in the user-facing tool picker). Each agent implements `_credentials_check` to make one cheap, read-only request against a known endpoint of the underlying service:

| Agent | Probe endpoint | Pass criterion |
|-------|---------------|----------------|
| CLASSify | `GET /get-ml-options` | HTTP 200 |
| Forecaster | `GET /download-model?probe=true` (or service's lightest GET; final choice in T-tasks) | HTTP 200 / 404 (404 ⇒ auth ok, just no model) |
| LLM-Factory | `GET /v1/models` (Router-2 always serves this when auth is valid; no fallback) | HTTP 200 |

Outcome is reported back over the same `PUT` response as `{ "credential_test": "ok" \| "auth_failed" \| "unreachable" \| "unexpected" }`. The spec's 5-second budget (SC-003) is met because the probe is a single request with a 5 s timeout.

**Rationale**: A live test catches two of the three things users get wrong (typo'd URL, expired key) before they hit a real tool call. The third (rate-limit / outage) cannot be diagnosed at save time and is deferred to runtime error handling (FR-021, FR-022).

**Alternatives considered**:
- *No save-time test.* Rejected — leaves users in a state where the agent says "ready" but the next tool call fails with 401. Bad UX (SC-003 fails).
- *Test asynchronously after save with WebSocket push.* Adds protocol surface for a 5-second-bounded check. Not worth it.

---

## R-006 Long-running job result delivery (resolves FR-015)

**Decision**: Tools that start asynchronous jobs (CLASSify training, Forecaster training/forecasting) return synchronously with a small acknowledgment containing the upstream `task_id` and a friendly "Job started" message. Immediately after returning, the agent spawns an `asyncio.create_task` (held in `job_poller.py`) that polls the upstream service every 5 s. Each poll iteration:
1. Calls upstream's status endpoint with the saved API key.
2. Emits a [`ToolProgress`](backend/shared/protocol.py:228-240) WebSocket message back to the orchestrator with `tool_name`, `agent_id`, `message`, `percentage` (if available), and `metadata={"job_id": ..., "phase": ...}`.
3. On terminal status (success / failed), emits one final `ToolProgress` with `phase: "completed"` and includes the result summary in `metadata.result`.

The orchestrator already forwards `tool_progress` messages into the originating chat ([orchestrator.py:695](backend/orchestrator/orchestrator.py#L695), feature-flagged on `progress_streaming` which is on by default).

**Rationale**: Reuses feature-014 plumbing end-to-end; satisfies the user's choice of Option A in [Q2](spec.md#clarifications); avoids the "cluttered tool picker" problem of a separate `check_job_status` tool.

**Alternatives considered**: All three were presented during clarification; the user explicitly chose this one.

**Polling-failure semantics** (FR-017): the poller stops after 5 consecutive transport failures (≈25 s of unavailability) and emits a final `ToolProgress` with `phase: "status_unknown"` and `message: "Couldn't reach the service to confirm job status — try again later"`. It does **not** mark the credentials invalid (that's reserved for explicit 401s).

---

## R-007 Concurrency cap (resolves FR-026 / FR-027)

**Decision**: A new module [backend/orchestrator/concurrency_cap.py](backend/orchestrator/concurrency_cap.py) defines a `ConcurrencyCap` class with two methods, `acquire(user_id, agent_id, job_id) → bool` and `release(user_id, agent_id, job_id) → None`. The orchestrator instantiates one global `ConcurrencyCap(max_per_user_agent=3)` at startup. The orchestrator's tool-dispatch path consults `acquire()` immediately before forwarding any tool whose name appears in a per-agent `LONG_RUNNING_TOOLS` allow-list (e.g., for CLASSify: `{"train_classifier", "retest_model"}`). On `True` the dispatch proceeds and `release()` is called by the agent's poller on terminal job state. On `False` the orchestrator returns an `RenderAlert` to the user with the message specified in FR-026.

State is held in process memory:
```python
self._inflight: Dict[Tuple[str, str], Set[str]] = defaultdict(set)
```

**Rationale**: 3 concurrent jobs is the user's choice. Memory storage is sufficient because in-flight tracking only matters during a process lifetime — if the orchestrator restarts, no jobs are "in flight" from its perspective and ClearML retains its own job state independently. Locking is simple (`asyncio.Lock`); no cross-process coordination needed.

**Alternatives considered**:
- *Persist in PostgreSQL.* Rejected — schema change for ephemeral state; restart-loss is a feature, not a bug (the user can simply re-issue the call after a restart, and the underlying ClearML job continues regardless).
- *Redis.* Adds an unapproved dependency (Constitution V).

---

## R-008 External service API shapes

The three services were surveyed; the curated tool sets the agents will expose match Clarification Q1 (~4–6 tools each).

### CLASSify (`classify.ai.uky.edu`)

Auth: `Authorization: Bearer <key>`.
Selected tools (5):
- `train_classifier(file_directory, options)` → kicks off ClearML training; returns `task_id`. **Long-running.**
- `get_training_status(task_id)` → terminal-state probe (used internally by poller; also exposed for diagnostics).
- `retest_model(file_directory, dataset_name)` → re-evaluates a trained model on a new test set. **Long-running.**
- `get_class_column_values(filename, class_column)` → discovery helper for the class column.
- `get_ml_options()` → enumerate hyperparameter options (also serves as `_credentials_check` probe).

Out of scope for v1: dataset deletion, internal column-type remapping, low-level training callbacks.

### Timeseries Forecaster (`forecaster.ai.uky.edu`)

Auth: `Authorization: Bearer <key>`.
Selected tools (4):
- `train_forecaster(user_uuid, dataset_name, parameters)` → starts ClearML training. **Long-running.**
- `generate_forecast(user_uuid, dataset_name, parameters)` → starts new N-step forecast. **Long-running.**
- `get_results_summary(user_uuid, dataset_name)` → returns the LLM-generated summary of forecast results.
- `get_recommendations(user_uuid, dataset_name)` → returns model recommendations.

Out of scope for v1: download-model artifact (binary delivery is a separate concern and not chat-friendly), retrain-file parsing.

### LLM-Factory (`llm-factory.ai.uky.edu`) — LLM-Factory Router

Backed by [LLM-Factory-Router-2](https://github.com/AstralDeep/LLM-Factory-Router-2): a pure OpenAI-compatible reverse proxy with usage analytics. Authenticates with `Authorization: Bearer <key>` (validated by the Router; cached for `auth.cache_ttl` seconds — default 300 s — so per-request validation latency stays low).

Selected tools (4 user-facing + 1 internal probe):
- `list_models()` → `GET /v1/models`. Returns Router-2's model list (id, owned_by, max_model_len, permission). **Synchronous.**
- `chat_with_model(model_id, messages, options)` → `POST /v1/chat/completions` with `stream=false`. **Synchronous** in v1; SSE streaming is a documented future enhancement.
- `create_embedding(model_id, input)` → `POST /v1/embeddings` with `input` as a string or list of strings. Returns vectors + usage in the OpenAI shape.
- `transcribe_audio(model_id, file_handle, language=None)` → `POST /v1/audio/transcriptions` with multipart upload. Resolves `file_handle` via the shared attachment helper (per-user ownership enforced).

Out of scope for v1: admin / observability routes (`/api/servers` add/remove backends, `/usage-dashboard/*` analytics, `/health` operator probe). The agent does not expose a dataset registry — Router-2 has no dataset layer.

**Differences from the originally surveyed `LLM-Factory-2`**: the older mixed adapter exposed `/models/embed-file` (custom multipart) and `/datasets/list` (custom dataset registry). Router-2 does not. The agent's earlier `embed_file` and `list_datasets` tools were removed; `create_embedding` and `transcribe_audio` replace them with shapes that match what Router-2 actually serves. The credential-test fallback to `/models/` is also dropped.

---

## R-009 File upload integration (FR-018)

**Decision**: For tools that need a CSV input (CLASSify `train_classifier` + `retest_model`; Forecaster `train_forecaster` + `generate_forecast`), the input schema accepts an opaque `file_handle` string. AstralBody's existing file-upload mechanism (feature 002) already deposits uploaded files in a known location and gives the orchestrator a handle the agent can resolve via the existing `attachments` flow used by the medical, journal-review, and grants agents (see [backend/agents/general/file_tools/list_attachments.py](backend/agents/general/file_tools/list_attachments.py)). The agent reads the file off disk and forwards it as `multipart/form-data` to the upstream `/upload_testset` (CLASSify) or `/parse_retrain_file` (Forecaster) endpoint.

**Rationale**: Reuse, no new upload UI; consistent with how existing agents work with files.

**Alternatives considered**:
- *Pass file content as base64 in tool args.* Rejected — kills usability for CSVs over a few MB and bloats audit logs.

---

## R-010 Audit events (FR-019, FR-020)

**Decision**: No new audit `event_class` values are introduced. The existing audit subsystem already records:
- Tool dispatch in/out via the `ws.<action>` and tool-correlation hooks ([backend/audit/hooks.py](backend/audit/hooks.py)) — these cover FR-020 unchanged.
- Credential save/edit/clear via the existing `PUT /api/agents/{agent_id}/credentials` endpoint, which already emits an audit event for credential mutations.
- A new `_credentials_check` invocation result (R-005) emits the same `tool` audit event as any other tool call, with the action embedded in the tool name. The API key value is **not** part of the recorded payload (only the agent_id and the verdict).

**Rationale**: FR-019 explicitly forbids the API-key value in audit; the existing hooks already redact via [backend/audit/pii.py](backend/audit/pii.py)'s redactor. Adding a new event class would be net-zero functional benefit.

---

## R-011 Frontend changes

**Decision**: One TypeScript file may be touched: [frontend/src/components/AgentPermissionsModal.tsx](frontend/src/components/AgentPermissionsModal.tsx). The change is limited to tagging the new agents' URL credential field with a `placeholder` derived from the production URL hint each agent declares in its `card_metadata`. This is a one-line additive change (the modal already reads `card_metadata.required_credentials`; no logic changes needed if we put the placeholder in the credential descriptor directly).

**Rationale**: The credential UI is already declarative. Each agent's `required_credentials` entry can carry a new optional `placeholder` field that the modal renders into the input's `placeholder=` attribute. No new component, no new prop drilling, no new state.

**Alternatives considered**:
- *Hard-code per-agent placeholders in the React component.* Rejected — brittle and breaks the "add an agent without changing the frontend" property.

---

## R-012 Test strategy

**Decision**: For each agent:

1. **Unit tests** (`backend/agents/{name}/tests/test_{name}_tools.py`):
   - Each tool is invoked with a mocked `requests.Session` (using `responses` library, already in `dev-requirements.txt` of similar agents).
   - Mocked happy path, 401 (auth-failed mapping), 404, 5xx, network timeout, malformed JSON.
   - SSRF guard rejects `http://localhost:1234`, `http://10.0.0.5/`, `file:///etc/passwd`, `gopher://...`.

2. **HTTP-client tests** (`test_http_client.py`): URL normalization edge cases (no scheme, trailing slash, mixed case host, port specification, query string preservation), redirect-disable behavior, response-size cap.

3. **Job-poller tests** (`test_job_poller.py`, only for the two ClearML-backed agents): poll loop emits `ToolProgress`, terminal states fire the final emission, 5-failure cutoff fires `status_unknown`, `release()` is always called even on poller exception.

4. **Concurrency-cap tests** ([backend/orchestrator/tests/test_concurrency_cap.py](backend/orchestrator/tests/test_concurrency_cap.py)): under the cap, allow; at the cap, deny with the right alert; release frees a slot; releasing an unknown job_id is a no-op.

5. **End-to-end smoke** (manual, gated by env vars `CLASSIFY_E2E_URL` / `CLASSIFY_E2E_API_KEY` etc., otherwise skipped): one read-only call per agent against the live service, run against staging once before merge per Constitution Principle X.

Coverage target: ≥ 90% on changed files (Constitution Principle III). Frontend coverage unchanged because no new components.

**Rationale**: This mirrors the test layout used in the audit-log, feedback, and llm-config features and keeps `responses` (already a dev dependency) as the only mock-HTTP mechanism.
