# T030 — Real-browser end-to-end parity pass (evidence)

**Date**: 2026-06-10
**Environment**: Docker `astraldeep` (Python 3.11) + `astraldeep-postgres`, single port `:8001`,
mock auth (`VITE_USE_MOCK_AUTH=true`), LLM `deepseek-ai/DeepSeek-V4-Pro` at the UKY factory endpoint.
**Method**: headless Chromium (Playwright) driving the live stack; WebSocket frames captured;
server-side renders produced by the production `webrender` inside the running container.
Scenario scripts: `backend/tmp/e2e/`. Screenshots: this directory.

## Defects found and fixed during the pass

1. **`webrender/renderer.py` failed to import on Python 3.11** (the container runtime) —
   `f-string expression part cannot include a backslash` at the `file_download` renderer
   (legal only on 3.12+; the local venv is 3.13, so local tests passed). The live app rendered
   **no HTML at all**: every `ui_render` fell back to components-only and the browser showed
   empty canvas/bubbles. Fixed by hoisting the escaped-quote expression out of the f-string.
   Guard added: root `ruff.toml` with `target-version = "py311"` (ruff now rejects this class).
   Also removed a stray dead `agent_text` renderer (a misdiagnosis of this same bug — no
   producer of that type exists in code, git history, or the DB).
2. **`chat_steps` stuck `in_progress` forever** (feature-014 machinery, pre-existing):
   `ChatStepRecorder.start()` logged with `extra={... "name": ...}` — `name` is a reserved
   `LogRecord` attribute, so the logging call raised `KeyError` *after* persisting/emitting the
   in-progress row; callers got `step_id=None` and `complete()/error()` never ran. Invisible in
   unit tests (pytest's WARNING level skips record creation). Fixed (`step_name`), regression
   test added (`TestLoggingDoesNotBreakLifecycle`), live-verified: steps now transition
   `in_progress → completed` with result summaries. Same pattern fixed at `api.py`
   voice error logging (`extra={"message": ...}`).
3. **`api.py admin_review` referenced undefined `orch`** → admin draft review would 500
   (`NameError`). One-line fix (flagged by the new ruff config, F821).
4. **Stale config**: `.env PUBLIC_BASE_URL` still pointed at the removed `:5173` (now `:8001`);
   `.env LLM_MODEL=google/gemma-4-31B-it` 404s at the factory endpoint despite being listed by
   `/v1/models` (now `deepseek-ai/DeepSeek-V4-Pro`, verified working).

## Scenario results

| Scenario | Result | Key evidence |
|---|---|---|
| Infra: shell, static, auth, WS handshake | PASS | `GET /` 200 with token injection; client.js/astral.css/plotly/tailwind served; `/auth/session`+`/auth/login` (mock) OK; `register_ui` → `rote_config`/`user_preferences`/`system_config`/`history_list` within 15s. (`agent_list` is pull-only by design — roster arrives in `system_config.config.agents`.) `infra-shell.png` |
| Chat, text round-trip | PASS | User bubble → `Thinking…` → assistant bubble = server-rendered "Analysis" card (markdown). Empty-bubble regression gone on success AND error paths. Every `ui_render` carries **both** `html` + `components` (FR-018). `chat-text-*.png` |
| Chat, tool round-trip | PASS | "CPU and memory usage" → general-1 `get_cpu_info`/`get_memory_info` → canvas card + metric cards + per-core table in ~8s; chat_step trail now reaches ✓ after fix #2; zero webrender errors in logs. `chat-tools-*.png` |
| All primitive types | PASS 29/29 | All **26** registered types rendered by the production renderer and layout-verified in the browser, incl. 4 chart types via the self-hosted real Plotly. Escaping (SC-008): literal `<script>` stays inert text; markdown opt-in sanitized. `primitives-*.png` |
| Interactions (FR-012) | PASS 5/5 | Button action / `table_paginate` / param-picker submit / `save_theme` (live CSS-var change) / file upload (`POST /api/upload` 201 + attachment chat message) — exact WS frames captured, server receipt proven. `interactions-after.png` |
| Streaming (SC-007) | PASS | `stream_subscribe` on `live_system_metrics` (push) → `ui_stream_data` seq 1→2→3, same `stream_id`, each with server `html`; `#stream-*` node mutated in place (3 distinct content hashes); zero page reloads. `followup-stream-mid.png` |
| Audio playback (SC-002) | PASS | Production-rendered audio primitive (real 0.3s WAV data URI): `readyState 4`, `currentTime` advanced. `followup-audio.png` |
| File download | PASS | Production-rendered `file_download` anchor → browser download, sha256 byte-identical to `GET /static/astral.css`. `followup-download.png` |
| Live table pagination | PASS | `.astral-page-next` → `table_paginate {get_disk_info, general-1, limit 5/offset 5}` → real tool re-executed, fresh `ui_render` html replaced canvas in 0.52s. `followup-paginate-*.png` |

Full backend suite in-container after fixes: feature-026 suites green
(98 passed / 1 skipped) + chat_steps suites green (66 passed across the protocol/wire/webrender/steps set).
Remaining full-suite failures (~15) are pre-existing test-environment issues unrelated to 026
(py3.11 `asyncio.get_event_loop()` idioms, a NRRD content-sniff fixture, a REST auth fixture, ordering pollution) —
each verified to fail identically without the 026 changes.

## Out of scope for this pass (explicitly deferred)

Per the operator's direction in [SERVER_RENDERED_CHROME_SPEC.md](../../../../SERVER_RENDERED_CHROME_SPEC.md)
(spec-only, no implementation; recommended as feature 027), the **application chrome** is a follow-up
feature: sidebar/topbar/dashboard, floating chat panel, component-flow toolbar, and the modal suite —
which carries the **settings / audit-log / feedback / tutorials-tooltips UI surfaces** named by FR-008/SC-002.
The *backend* capabilities behind them are live and verified (`/api/audit` 200 + `audit_append` frames,
feedback/tutorial REST routers, `save_theme`/`user_preferences` round-trip); the minimal 026 shell simply has
no chrome to surface them, by design. Also deferred: a non-mock Keycloak browser sign-in (operator realm
required; server-side OIDC covered headlessly by `test_auth_server_oidc.py`), and a markdown pipe-table
rendering gap in chat bubbles (polish; tracked for 027).
