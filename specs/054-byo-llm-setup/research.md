# Phase 0 Research: Bring-Your-Own-LLM (054)

All unknowns from Technical Context are resolved below. Findings derive from a
full-repo exploration sweep (2026-07-10, 11 parallel investigations over
`backend/llm_config/`, every `_call_llm` consumer, the tutorial system, the web
shell + chrome machinery, all four native client families, spec 006/043 docs,
and the packaging/CI/secret-scan posture), with the load-bearing claims
re-verified against the working tree.

## R1. Where user LLM credentials live today (and why that must change)

**Decision**: Replace the per-socket in-memory store with a server-persisted,
per-user record; keep the in-memory store as a read-through cache keyed by
`user_id`.

**Rationale**: Today `SessionCredentialStore`
([backend/llm_config/session_creds.py](../../backend/llm_config/session_creds.py))
is `Dict[int, SessionCreds]` keyed by `id(websocket)`, seeded only by
`register_ui.llm_config` (dead — no client sends it since the React frontend
was removed in 026), `llm_config_set`, or `chrome_llm_save`; wiped on
disconnect (`orchestrator.py:8484/8517`). The server therefore cannot know "is
this user configured?" at login, and the watch/VirtualWebSocket paths can never
carry creds. A mandatory login-time gate is impossible without user-keyed,
durable state.

**Alternatives considered**: Device-local persistence on each of the four
client families (web localStorage, Windows, Android Keystore, Apple Keychain) —
rejected: 4× the client work, re-entry per device, watch permanently broken,
background jobs still credential-less, and the "configured?" question still
unanswerable server-side at gate time.

## R2. Storage precedent for the encrypted record

**Decision**: New tables `user_llm_config` (PK `user_id`) and
`system_llm_config` (single guarded row), with `api_key_enc` Fernet-encrypted
under `CREDENTIAL_ENCRYPTION_KEY`, added via idempotent `_init_db` deltas.

**Rationale**: The agent credential store
([backend/orchestrator/credential_manager.py](../../backend/orchestrator/credential_manager.py))
is the exact precedent: Fernet mode is documented as the "orchestrator itself
needs the plaintext" case, and `CREDENTIAL_ENCRYPTION_KEY` is already enforced
by the production boot gate (`session_store.py::assert_production_posture`).
A dedicated table (rather than pseudo-agent rows in `user_credentials`) keeps
the non-secret fields (`provider`, `base_url`, `model`) queryable, avoids the
029/040 catalog-migration deletion sweeps that operate on `user_credentials`
by agent id, and gives the system row an unmistakable authz boundary.

**Alternatives considered**:
- `user_preferences` JSON blob — plaintext, no encryption seam; fine for
  non-secrets only. Rejected for the key.
- `web_session` Fernet store — right crypto, wrong lifecycle (rows keyed by
  sid, deleted on logout/purge). Rejected.
- Pseudo-agent rows under `__orchestrator__` in `user_credentials` — workable
  but entangled with agent-catalog migrations; rejected for clarity.

## R3. Credential resolution seams (per-socket → per-user + system)

**Decision**: Re-key `Orchestrator._resolve_llm_client_for`
(`orchestrator.py:4457`) to resolve `websocket → user_id` via the existing
`ui_sessions[websocket]["sub"]` lookup (the same keying `_llm_audit_principals`
already uses), then read the user store. `websocket=None` **and**
`VirtualWebSocket` turns resolve to the **system** credential.
`build_llm_client(session_creds, default_creds)`
([backend/llm_config/client_factory.py](../../backend/llm_config/client_factory.py))
keeps its shape: `default_creds` becomes the system credential for
system-context calls and an always-empty sentinel for user-context calls
(preserving "user calls never fall back" mechanically).

**Rationale**: One choke point already exists; every caller
(`3166` chat pre-flight, `4566` `_call_llm`, `5185` tool summary, `9037` chat
title) passes `websocket` and needs no signature change. Direct per-socket
reads that must be re-keyed: the `_session_llm_credentials` injection into
agent tool args (`orchestrator.py:5795-5804`) and the disconnect cleanup calls
(`8484`, `8517` — deleted; persisted creds survive disconnect).

**Consumers inventory** (from the sweep) and their new source:

| Consumer | Context | New source |
|---|---|---|
| Chat turns, narrative, tool summaries, chat titles, UI designer | user socket | user record |
| Agent LLM tools (`_session_llm_credentials` injection) | user socket | user record; system record on system-context turns |
| Compaction (`compaction.py`, called with `websocket=None`) | in-session helper | **system** (explicit owner decision) |
| Workspace combine/condense (`_combine_components_llm`, prebuilt `self.llm_client`) | user-initiated REST/WS | **system** (explicit owner decision); the `self._operator_creds.is_complete` fast-fail at `orchestrator.py:2454` re-pointed to the system record |
| Scheduled job turns (`scheduler/runner.py` → VirtualWebSocket) | server-initiated | system; run marked FAILED when unavailable (fixes today's silent-success bug — the VWS alert is swallowed and `outcome="success"` recorded) |
| Knowledge synthesis (`knowledge_synthesis.py:121-123`, direct env reads at init) | server-initiated | system, re-checked per cycle (not init-once) |
| Agent codegen incl. attachment autoparse (`agent_generator.py:213-224`, direct env reads) | server-initiated | system |
| Job narration (`_narrate_job_result`), feedback-quality job | server-initiated | system (keeps its deterministic fallback) |

## R4. Operator-default removal inventory

**Decision**: Delete `OperatorDefaultCreds.from_env` usage everywhere; the
legacy env vars become inert. Full inventory of the trio's readers:
`llm_config/operator_creds.py` (the declared read point),
`orchestrator.py:543` (`_operator_creds`), `:557-559` (`self.llm_model`
fallback incl. a hardcoded model name), `:588-604` (prebuilt `self.llm_client`),
`agent_generator.py:213-224`, `knowledge_synthesis.py:107-144`
(+ `KNOWLEDGE_LLM_MODEL`), agent tools env fallback (general/summarizer/
web_research `mcp_tools.py`), `verification/drivers/in_process.py:110-117`
(fakes `OPENAI_*` to pass the pre-flight — must seed the store instead), and
`sandbox.py:43-47` (env denylist — keep; harmless defense-in-depth).

**Packaging facts** (verified): `.env` is gitignored with zero git history —
the live key was never committed; docker-compose consumes `env_file: .env`
at runtime; the Dockerfile bakes no config; CI/smoke run with no LLM vars; the
exit-78 production gate has never included LLM vars; `docs/production-deployment.md`
never mentions `OPENAI_*`; native binaries contain zero LLM references. So
"removal" = scrub `.env`/`.env.example` lines 11-23 + delete the code paths +
add a migration note; **no CI, compose, Dockerfile, or boot-gate change**.

**Rationale**: The user decision is "delete the code path" — no deployment can
ship a user-facing default. Boot stays LLM-free (FR-003 preserved by
construction).

## R5. Mandatory-dialog delivery mechanism (zero new frame types)

**Decision**: Reuse the existing `llm` chrome surface
([backend/webrender/chrome/surfaces/llm.py](../../backend/webrender/chrome/surfaces/llm.py))
extended with the provider dropdown. Delivery:
- **Web**: `chrome_render {region:"modal", html}` with a mandatory variant of
  `render_modal_shell` (no ✕ button, `data-mandatory` attribute); `client.js`
  gates `closeModal()` (single choke point covering ✕/backdrop/Escape).
- **Natives (Windows/Android/iOS/macOS)**: existing `chrome_surface` frame with
  its **reserved `mode` field** (`shared/protocol.py:255`, "reserved; only
  'replace' today") set to `"mandatory"`. Verified: all four drift guards
  assert frame **type names only** against `ui_protocol.json` — an additive
  field value requires **no manifest edit**.
- **Watch**: deliberately excluded (chrome-free by design,
  `Dispositions.swift:125`); gets a spoken/displayed Alert on AI use (the
  existing alert-only `ui_render` auto-routes to chat and is spoken via
  `webrender/voice.py`), with copy "Set up your AI provider on your phone or
  the web first."

**Client-side changes required** (verified per client):
- Web: `closeModal()` guard (`client.js:895/930-939`); menu interactions
  remain but the server-side gate makes them no-ops.
- Windows: `SurfaceDialog` is `setModal(False)` with default QDialog
  close/Esc; needs application-modal + close/reject suppression while
  `mode=="mandatory"` (`app.py:498-570`, `_on_chrome_surface` ~1537 already
  renders unsolicited pushes).
- Android: `Wire.kt:89-94` parses only `surface_key/title/components` — parse
  `mode`; `AppViewModel.kt:681-713` demotes unsolicited surfaces to an error
  banner — add the mandatory branch (accept + navigate to `Screen.Surface`);
  gate top-bar/back navigation while mandatory.
- iOS/macOS: `AppModel.swift:585-607` — identical twin of Android; same two
  changes; gate top-bar navigation.

**Ordering guarantee**: the `register_ui` handler
(`orchestrator.py:1228-1317`) emits over one ordered `_safe_send` stream:
`rote_config` → `chrome_menu` → dashboard → `user_preferences` → welcome
`ui_render` (`:1304`, guarded by no-chat-to-resume). The gate push is inserted
before the welcome render, and the welcome render is suppressed while
unconfigured; clients reduce frames in arrival order, history is pull-only,
and the tour is strictly user-initiated (web-only, `include_tour=False` for
natives) — so nothing can precede or preempt the dialog.

**Alternatives considered**: a new frame type (`llm_setup_required`) —
rejected: 5 coordinated manifest/classification edits + a watch disposition
for zero benefit; a blocking REST redirect page pre-shell — rejected: doesn't
exist for natives and breaks the SDUI chrome model.

## R6. Server-authoritative gate

**Decision**: A per-user "configured" predicate (decryptable `user_llm_config`
row exists; small TTL cache) enforced at: (a) `register_ui` (push gate surface,
suppress welcome), (b) the existing chat pre-flight (`orchestrator.py:3159-3181`,
today's `LLMUnavailable` Alert branch becomes the gate branch), (c)
`chrome_events` dispatch — while unconfigured, `chrome_open` of any other
surface is forced back to the `llm` surface and `chrome_close` is refused,
(d) LLM-dependent `ui_event`/REST verbs (`component_action`, combine/condense)
refuse with the audited `llm_unconfigured` event that already exists. On save
success, the server closes the gate on **all** of the user's sockets and sends
each its welcome render (fan-out precedent: workspace `ui_upsert` fan-out).
Kill switch `FF_LLM_FIRST_RUN` (default on) governs only the register-time
mandatory push; the credential requirement itself is structural (no default
exists to fall back to).

**Rationale**: Client affordance-gating is cosmetic; every unlock/deny must be
server-side (Constitution VII/XII). Reusing `llm_unconfigured` keeps the audit
vocabulary stable.

## R7. Provider preset catalog

**Decision**: A first-party in-code registry `backend/llm_config/providers.py`
— ordered list of `{key, label, base_url, key_required, key_prefix_hint}` —
consumed by the surface composition (web `<select>` + native SDUI picker) and
served to all clients from the one server-side definition (Constitution XII).

| Provider | OpenAI-compatible base URL | Key |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | required (`sk-`) |
| Anthropic | `https://api.anthropic.com/v1` | required (`sk-ant-`) |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | required (`AIza`) |
| xAI Grok | `https://api.x.ai/v1` | required (`xai-`) |
| OpenRouter | `https://openrouter.ai/api/v1` | required (`sk-or-`) |
| Groq | `https://api.groq.com/openai/v1` | required (`gsk_`) |
| Together AI | `https://api.together.xyz/v1` | required |
| Mistral | `https://api.mistral.ai/v1` | required |
| Ollama (local) | `http://localhost:11434/v1` | optional (keyless default) |
| LM Studio (local) | `http://localhost:1234/v1` | optional (keyless default) |
| Custom | free-form | per user |

Local-runtime presets carry copy noting the endpoint must be reachable **from
the server**. Redaction pattern lists in `audit_events.py::_KEY_PREFIX_PATTERNS`
and `log_scrub.py::_KEY_TOKEN_PATTERNS` gain the new providers' key shapes
(`sk-ant-`, `AIza`, `sk-proj-`); implementation must re-verify each base URL
against provider docs at build time (they are stable but externally owned).

**Alternatives considered**: DB-backed admin-editable catalog — rejected as
scope creep; in-code registry ships catalog changes with the image exactly like
the chrome menu model.

## R8. Key-hygiene invariants carried forward (and one latent gap)

**Decision**: Preserve unchanged — `_assert_no_api_key` on every audit payload,
`SessionCreds.__repr__` eliding (replicated on the new persisted dataclass),
write-only password semantics in the surface (saved key never echoed), the
probe/list REST endpoints' never-persist behavior, and the "no key substring
≥ 4 in audit" rule. **Gap found and adopted into scope**: `install_redaction_filter`
([backend/llm_config/log_scrub.py](../../backend/llm_config/log_scrub.py)) is
implemented but never installed at boot — wire it in this feature (keys now
transit more paths).

## R9. Tutorial interaction

**Decision**: No tutorial changes. Verified: the tour is strictly
user-initiated (Settings → "Take the tour"; `maybeStartTour` fires only when a
modal containing `[data-tour-steps]` renders; natives get `include_tour=False`)
and nothing auto-launches at login. The gate simply precedes the whole UI;
after save, the welcome render proceeds and the tour remains reachable exactly
as today. One stale copy block in `backend/webrender/chrome/guide_content.py`
(~454) claims the tour auto-launches on first sign-in — fix the copy alongside
this feature.

## R10. Dev/test/CI posture

**Decision**: Tests and the 032 verification harness seed credentials through
the store/factory seams (fixtures write `user_llm_config`/`system_llm_config`
rows or inject `client_factory`), replacing env fakes
(`verification/drivers/in_process.py:110-117`). Existing suites that assert
operator-default behavior (`test_background_jobs_use_operator_default.py`,
`test_call_llm_credential_resolution.py`, `test_no_api_key_leak.py`, chrome
`test_surface_llm.py`, sandbox/env tests) are retargeted to the
user/system-record model. CI needs no pipeline change (R4). Local dev: the
developer goes through the dialog once (persisted); `CREDENTIAL_ENCRYPTION_KEY`
already has the dev key-file fallback.

## R11. Audit vocabulary

**Decision**: `CredentialSource.OPERATOR_DEFAULT` is retired for new events;
new value `SYSTEM` ("system") tags system-credential calls. `llm_config_change`
gains `scope: "user"|"system"` on payloads for the admin surface actions;
`llm_unconfigured` unchanged (it is the gate's audit event). Historical rows
keep their `operator_default` strings (append-only audit; no rewrite).
