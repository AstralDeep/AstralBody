# Live verification — feature 054 (bring-your-own-LLM)

**Run**: 2026-07-10, local orchestrator booted with mock auth
(`USE_MOCK_AUTH=true`, `ASTRAL_ENV=development`) on `:8021` against the dev
Postgres, driven over the real WebSocket wire (`ws://localhost:8021/ws`) as
the `test_user` principal with a `browser` device profile. The provider used
was the former UK LLM factory (`https://api-llm-factory.ai.uky.edu/v1`,
`zai-org/GLM-5.2-FP8`) configured **through the in-app flow**, not the
environment.

Health: `/healthz` 200, `/readyz` 200.

## Observed (web wire)

1. **Mandatory gate at register (FR-013/FR-016)** — a fresh (unconfigured)
   `register_ui` produced a `chrome_render` modal whose card carried
   `data-mandatory="1"`, had **no** `astral-modal-close` button, and included
   the `/auth/logout` sign-out link. The welcome `ui_render` was
   **suppressed** while gated. `[1] gate=True welcome_suppressed=True`.
2. **Server-authoritative refusal (FR-014)** — a `chat_message` while gated
   returned the guidance Alert ("Set up your AI provider …"), never an LLM
   call. `[2] gated chat refused server-side OK`.
3. **Probe-gated save + unlock fan-out (FR-008/FR-015)** — `llm_config_set`
   with the real provider produced, in order:
   `audit_append(llm_config.tested, success)` → `audit_append(llm_config.updated)`
   → `llm_config_ack{ok:true}` → `chrome_render` (empty = gate close) →
   `ui_render` (welcome). The **tested-success audit is a real
   `chat.completions.create(max_tokens:1)` round-trip** against the live
   endpoint — proof the configured provider works.
   `[2] post-save frames: [audit_append, audit_append, llm_config_ack, chrome_render, ui_render]; ack=True close_frame=True welcome_rendered=True`.
4. **Real LLM-backed chat turn** — after configuration, a chat turn
   ("Reply with exactly … LIVE_OK_054") rendered a `text`/markdown component
   containing exactly `LIVE_OK_054` from the live provider.
   `live reply contains LIVE_OK_054: True`.
5. **Clear → immediate re-gate (FR-009/FR-013)** — `llm_config_clear`
   re-pushed the mandatory `data-mandatory="1"` dialog on the same socket.
   `[3/4] clear re-gated: True`.

## Not driven here (covered by automated tests / CI)

- Windows / Android / iOS / macOS mandatory-surface rendering — covered by
  each client's unit/drift suites (T019–T021, T025); the Chrome
  browser-automation extension was not connected in this session, and the
  native GUIs are not scriptable from this host. The server-side frames they
  consume (`chrome_surface {mode:"mandatory"}`, blank-key close) are the same
  ones asserted in `backend/tests/test_llm_first_run_gate.py`.
- Watch spoken guidance — `backend/tests/test_watch_llm_guidance.py`.
- Admin System LLM surface — `backend/tests/test_system_llm_credential.py`.
