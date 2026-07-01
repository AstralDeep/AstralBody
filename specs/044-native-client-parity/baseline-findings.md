# Baseline Findings — Cross-Client Native Parity Audit (input to spec 044)

**Captured**: 2026-07-01, from a three-way exploration of `windows-client/`, `android-client/`,
and the backend contract (`backend/rote/`, `backend/webrender/`, `backend/orchestrator/`),
plus specs 041/042/043 status. These findings ground the spec; the plan phase should verify
line numbers before relying on them (the tree moves).

Correction to project docs: the Windows client is **PySide6/Qt Widgets**, not tkinter
(tkinter is explicitly excluded from the bundle, `windows-client/AstralBody.spec:26`);
`CLAUDE.md` still says "PyInstaller + tkinter".

---

## 1. Authoritative server contract

### 1.1 Renderer vocabulary — 35 types (not 31)

`webrender.allowed_primitive_types()` (`backend/webrender/renderer.py:1139-1147`;
registrations `1105-1118` + `generative` at `1134`):

`container, text, button, input, param_picker, card, table, list, alert, progress, metric,
code, image, grid, tabs, divider, collapsible, bar_chart, line_chart, pie_chart, plotly_chart,
color_picker, theme_apply, file_upload, file_download, audio, badge, hero, keyvalue, timeline,
rating, skeleton, chat_history, download_card, generative`

Dashboard five (astralprims 0.2.0): `badge, hero, keyvalue, timeline, rating`.
041's contract doc (`specs/041-android-sdui-client/contracts/sdui-primitives.md:3`) confirms 35.

### 1.2 Device profiles (`backend/rote/capabilities.py`)

`windows` (`:49`) and `android` (`:60`) are **byte-identical to `browser`** — full capability,
no density limits. Substitution is driven **only** by the client's declared `supported_types`
(`DeviceProfile.supported_types`, `:156`; from `register_ui.device`, `:167-172`). Fallback
ladder `_degrade_unsupported` (`backend/rote/adapter.py:52-76`): timeline→list,
chart→table→text, keyvalue→table/list, else→text; recurses into content/children/tabs.
`windows`/`android` are never viewport-downgraded (`:180-199` applies only to `browser`).

### 1.3 WS messages the orchestrator can SEND to a UI client

Bootstrap: `rote_config` (orchestrator.py:1155), `chrome_menu` (native-only push, `:1176-1180`;
model `shared/protocol.py:203-215`), `user_preferences` (`:1189`), `system_config` (`:7613`),
`agent_list` (`:7868`), `agent_registered` (`:847`).
Auth: `auth_required{reason: expired|invalid|hard_cap}` (protocol.py:176-186; sent `:1297`).
Canvas/SDUI: `ui_render{components,target: canvas|chat|history,html?}` (`:7477`),
`ui_update` (`:2058`), `ui_upsert{chat_id,ops[]}` (`:7248`), `ui_append` (legacy),
`ui_stream_data` (stream_manager.py:1193-1204).
Chrome: `chrome_render{region,html,mode}` (web path; chrome_events.py:58-60),
`chrome_surface{region,surface_key,title,admin_only,components,mode}` (native path;
chrome_events.py:96-101).
Chat lifecycle/progress (NO token-delta type exists): `chat_status{status: thinking|executing|
fixing|done|info|combining|condensing}`, `chat_step` (chat_steps.py:366), `chat_created`,
`chat_loaded`, `chat_deleted` (api.py:157), `history_list`, `user_message_acked` (`:3091`),
`task_started` (`:2725`), `task_completed` (async_tasks.py:174), `tool_progress`
(protocol.py:319-331), `workspace_timeline_mode` (`:1597`), `heartbeat` (`:2622`).
Streaming control: `stream_subscribed`, `stream_unsubscribed`, `stream_list`, `stream_data`
(poll), `stream_error`.
Component verbs: `component_saved`, `component_save_error`, `saved_components_list`,
`component_deleted`, `combine_status`, `combine_error`, `components_combined`,
`components_condensed`.
Permissions: `agent_permissions`, `agent_permissions_updated`.
LLM: `llm_config_ack`, `llm_usage_report`.
Audit: `audit_append`. Creation: `agent_creation_progress`. Errors: `error`.

Notes: no `sound`/`tutorial` WS frames (tour = chrome surface, web-only on native);
`parser_status` is an **upload REST response field**, not a WS frame.

### 1.4 WS messages ACCEPTED from a UI client

`register_ui{token,capabilities,session_id,device{device_type,screen/viewport,pixel_ratio,
has_touch,supported_types[]},llm_config?,resumed?}` (protocol.py:403-431);
`llm_config_set`/`llm_config_clear`; `ui_event{action,payload,session_id}` with actions
(orchestrator.py:1364-2294): `chat_message` (payload incl. `attachments`, `display_message`,
`async_mode`), `cancel_task`, `watch_task`, `component_feedback`/`feedback_retract`/
`feedback_amend`, `get_dashboard`, `discover_agents`, `register_external_agent`,
`get_history`, `load_chat`, `save_component`, `get_saved_components`,
`delete_saved_component`, `combine_components`, `condense_components`,
`get_agent_permissions`, `set_agent_permissions`, `enable_recommended_agents`,
`schedule_decision`, `update_device`, `save_theme`, `component_action`, `authorize_action`,
`table_paginate`, `stream_subscribe`/`stream_unsubscribe`/`stream_list`, and all `chrome_*`
actions via chrome_events.py:218-278 (`chrome_close`, `chrome_open{surface,params}`, plus
surface handlers: `chrome_theme_preset`, `chrome_llm_save/_clear/_test/_models`,
`chrome_memory_update`, `chrome_profile_save`, `chrome_audit_page`, …) and draft/revision
decisions (`draft_approve`, `draft_refine`, `draft_discard`, `revision_apply`,
`revision_discard`).

`chrome_events._render_surface` branches on device type (chrome_events.py:104-191):
web→`chrome_render` HTML; windows/android→`chrome_surface` ROTE-adapted components;
surfaces without `components()` fall back to `_sdui.placeholder(title)` (`:168-172`).

### 1.5 REST surface for UI clients

`/auth/{login,callback,session,logout,error}` (web_auth.py:439-616); `POST /api/upload`
(returns `parser_status: covered|preparing|pending_admin_approval|unavailable`;
attachments/router.py:86), `GET /api/attachments` (`:220`), `GET/DELETE /api/attachments/{id}`
(`:241,258`); `/api/feedback`; `GET /api/chrome/menu` (api.py:1504); `GET /api/audit`,
`GET /api/audit/{event_id}`; `/healthz`, `/readyz`; plus `/api/chats`, components, agents
(+`/permissions`), users/me, drafts, voice, tasks, async-tasks.
043's "native file download" added **no backend endpoint** (client-only; consumes existing
`file_download`/`download_card` + existing routes).

### 1.6 Settings surfaces (webrender/chrome/surfaces/)

With `components()` (native-ready SDUI): `theme.py`, `guide.py`, `llm.py`,
`personalization.py`. Native screens instead: `agents.py`, `audit.py`. Web-only:
`admin_tools.py` (ADMIN_ONLY), `tour.py` (removed from native menus, 043). Flag-gated:
`pulse.py` (FF_PULSE_DIGEST). No `components()` (native gets placeholder if opened):
`drafts.py`, `attachments.py`, `workspace_timeline.py`.

---

## 2. Windows client inventory (`windows-client/`, PySide6, v0.2.2)

### 2.1 Handles (inbound)

`ui_render` (chat→rail flatten; **history→silent `pass`** app.py:1187-1188; else canvas),
`ui_upsert`, `chat_created`, `chat_loaded`, `agent_list`, `history_list`,
`ui_stream_data`/`stream_data`, `stream_subscribed`/`stream_error`/`stream_unsubscribed`
(`stream_list` explicitly no surface, app.py:1269), `chrome_render` (status notice only,
never HTML), `chrome_menu` (042 server-owned menu), `chrome_surface` (043 host),
`chat_status`, `auth_required` (via protocol.py:108-110).

**No `else` branch in `_on_message` (app.py:1178-1235) → any unlisted type is silently
dropped, unlogged.** Not handled: `error`, `user_message_acked`, `chat_step`,
`tool_progress`, `task_started`/`task_completed`, `chat_deleted`, `workspace_timeline_mode`,
`user_preferences`, `rote_config`, `system_config`, component-verb acks, `llm_usage_report`,
`audit_append`, `agent_creation_progress`, `heartbeat`.

### 2.2 Emits (outbound)

`register_ui` (device_type "windows", `supported_types` = live registry keys,
protocol.py:91-98 + app.py:852-853), `chat_message` (send_chat supports `attachments` param
but **composer never populates it**, protocol.py:124-131), `new_chat`, `discover_agents`,
`get_history`, `load_chat`, `register_external_agent`, `enable_recommended_agents`,
`set_agent_permissions`, `chrome_open{surface,params}`, arbitrary SDUI-carried actions.
**Sign out emits nothing — local confirm + quit only (app.py:1090-1100)** despite the menu
model carrying `signout.action:"logout"` (rest.py:110).

### 2.3 Renderer — 31 types (renderer.py:863-893,928)

text, card, container, grid, hero, badge, **metric** (not `metric_card`), keyvalue, timeline,
rating, alert, button, param_picker (the form; multi-action Load/Test/Save submits +
write-only password fields — 043), input, file_upload (native QFileDialog), file_download +
download_card (authed save-dialog download via rest.fetch_bytes, app.py:1043-1074), code,
divider, progress, list, table (**no pagination**, fixed-height, renderer.py:733-753), tabs,
collapsible, bar/line/pie chart (QtCharts), chat_history, skeleton, color_picker (read-only
swatch), theme_apply (**no-op spacer — live restyle unimplemented**, renderer.py:919-925).
Degraded to labeled placeholder: `image, audio, plotly_chart, generative`
(tests/test_renderer.py:133-139 KNOWN_DEGRADED). Unknown type → dashed `[type]` fallback
(renderer.py:848-860); per-component try/except guards (renderer.py:936-941).
Drift guard: test_renderer.py:142-156.

### 2.4 Auth / connection

OIDC Auth-Code+PKCE loopback (RFC 8252), client `astral-desktop`, direct Keycloak token
exchange (auth.py:79-155); token in memory only; silent refresh (auth.py:64-76).
`auth_required` + live session + `_reauth_tries<2` → refresh + reconnect (app.py:1154-1176);
**dev-token/no-session → dead "Re-authenticating…" caption, no path back**
(app.py:1142-1144). **No reconnect/backoff on socket drop** — `closed:*` just shows
"Disconnected" (app.py:1136-1141). Blocking loopback login (≤300 s) on main thread pre-exec
(auth.py:120-142).

### 2.5 Key gaps (Windows)

1. No attachments UI at all (no picker/chips/parser_status/library; wire ready).
2. No reconnect/backoff; queued-send absent.
3. `error` frames invisible; unknown frames unlogged.
4. Sign-out never revokes server session.
5. Theme live-apply no-op; color_picker read-only.
6. No table pagination.
7. `ui_render target=history` dropped; `user_message_acked`, `chat_step`, `tool_progress`,
   `task_*` unhandled (async flows invisible).
8. Hardcoded `Launch-AstralBody.bat` authority/WS URL.
9. No automated tests for `_on_message` routing, chrome_surface E2E, auth_required
   reconnect, attachments.

Tests that exist: 15 pytest files (renderer incl. drift guard, streaming translation, REST
parsing, chrome notice, audit dialog, auth/PKCE, config precedence, confirm bridge, codegen
tool security, win_agent, integrity, slash-command completer) + manual harnesses
(`tests/e2e_live.py`, `tests/screenshot.py`, `tests/verify_live.py`).

---

## 3. Android client inventory (`android-client/`, Kotlin 2.0.21 + Compose, v0.1.0)

### 3.1 Handles (inbound) — Wire.kt:38-97 → AppViewModel.reduce:409-512

`ui_render` (chat append / reasoning split / doc_*+skeleton drop / canvas merge),
`ui_upsert` (foreign-chat drop; doc_*→chat), `ui_stream_data`+`stream_data`,
`stream_subscribed`, `stream_error`, `stream_unsubscribed` (**no-op**), `chat_created`,
`user_message_acked`, `chat_loaded`, `agent_list`, `history_list`, `chat_status`
(commit-on-done canvas lifecycle), `chrome_render` (**decoded then ignored**), `chrome_menu`,
`chrome_surface`, `auth_required` (transport → silent refresh+reconnect,
MainActivity.kt:164-173). Unknown/malformed → `Inbound.Unknown` → reducer `else -> s`
(**dropped, unlogged**).

Not handled: `error`, `chat_step`, `tool_progress`, `task_started`/`task_completed`,
`chat_deleted`, `workspace_timeline_mode`, `user_preferences`, `rote_config`,
`system_config`, component verbs, `llm_usage_report`, `audit_append`,
`agent_creation_progress`, `heartbeat`, `stream_list`.

### 3.2 Emits (outbound)

`register_ui` (device_type always "android", supported_types = registry keys,
Wire.kt:101-125, DeviceCaps.kt:11-26), `chat_message` (with attachments,
Wire.kt:139-165), `new_chat`, `discover_agents`, `get_history`, `load_chat`,
`set_agent_permissions`, `enable_recommended_agents`, `chrome_open{surface}`
(AppViewModel.kt:327), arbitrary SDUI actions. **Sign-out local-only** (store.clear(),
MainActivity.kt:186-190); `endSessionEndpoint` configured but never called (OidcAuth.kt:33).

### 3.3 Renderer — 33 types (Renderers.kt:14-20; VocabularyParityTest.kt:16-26)

text (dependency-free markdown: headings/lists/fenced+inline code/bold/italic — **no links,
tables, images, blockquotes**, Markdown.kt:29-146), card, container, alert, button, grid,
hero, badge, metric, keyvalue, timeline, rating, divider, progress, collapsible, list,
table (**no pagination**, Data.kt:57-78), tabs, chat_history, skeleton (renders nothing),
input, param_picker (043 form incl. password/select), color_picker (readout only),
theme_apply (**empty no-op**, Input.kt:48), code, file_upload, file_download +
download_card (system DownloadManager + Bearer + toast, MainActivity.kt:72-90),
bar/line/pie/plotly chart (native Compose Canvas), image (Coil).
Excluded deliberately: `audio`, `generative` (Renderers.kt:9-12). Unknown → `[type]`
placeholder (Renderer.kt:60-69).

### 3.4 Auth / connection

AppAuth PKCE, client `astral-mobile`, redirect `com.kyopenscience.astral:/oauth2redirect`,
offline_access scope; AuthState in EncryptedSharedPreferences (TokenStore.kt:13-37); cold
start uses cached token then silently refreshes (MainActivity.kt:122-131).
**Reconnect: forever, exponential 1 s→30 s cap** (OrchestratorClient.kt:28-37,61-74);
bounded outbound queue MAX_QUEUE=64 flushed on open (`:134-150`). Endpoints hardcoded via
BuildConfig (debug 10.0.2.2 / release sandbox.ai.uky.edu, AppConfig.kt:17-29) — **no in-app
override**.

### 3.5 Key gaps (Android)

1. **042 top-bar model never consumed** — pulse digest, workspace-timeline, connection-status
   controls decoded+tested but not rendered (RootScaffold.kt:98-135; zero call sites for
   `.topbar`/`topbarActions`/`settingsControl`); client-invented New/Recent buttons instead;
   `connectionLabel()` dead code (Screens.kt:275-281); no disconnected banner.
2. Sign-out local-only (no end-session/logout; 042 FR-018/SC-007 unmet).
3. Theme live-restyle absent (static dark scheme Theme.kt:37-57; 043 US3).
4. **Infinite skeleton** if `chrome_surface` never arrives (Screens.kt:255-258); no
   in-surface action error state (fire-and-forget param_picker).
5. `error` frames invisible; unknown frames unlogged; swallowed `runCatching` everywhere
   (silent upload failure → chip flip only; audit failure → empty list; permission write
   results discarded).
6. Known-issue: full `ui_render` can clobber earlier keyed components (KNOWN-ISSUES.md:9-24).
7. No table pagination; markdown gaps (links!); charts lack accessibility semantics.
8. Dead code: DevAuth (both variants unreferenced — README claims it works), 
   Screen.SurfacePlaceholder + SurfacePlaceholderScreen + pendingSurfaceLabel unreachable,
   unused navigation-compose dependency; referenced `app/proguard-rules.pro` missing.
9. No attachment library surface (staging is ephemeral per message; upload+chips+parser note
   from REST response DO work — AstralRest.kt:91-124, AppViewModel.kt:244-275,608-614).
10. CI: instrumented tests nightly-only, `:app` coverage ungated, no screenshot tests.

---

## 4. Cross-client asymmetries (the preliminary parity matrix seeds)

| Behavior | Web | Windows | Android |
|---|---|---|---|
| Reconnect/backoff | page reload / browser | **none** | ✓ (1–30 s exp) |
| `error` frame visible | ✓ | **dropped** | **dropped** |
| Unknown frame logged | ✓ (console) | **no** | **no** |
| Sign-out revokes server session | ✓ (+offline queue) | **no (local quit)** | **no (local clear)** |
| `user_message_acked` | ✓ | **no** | ✓ |
| `chat_step`/`tool_progress`/`task_*` | ✓ | **no** | **no** |
| Attachments compose (chips + parser status) | ✓ | **none** | ✓ |
| Attachment library | ✓ (chrome surface) | none | none |
| Table pagination | ✓ (`table_paginate`) | **no** | **no** |
| Theme live restyle | ✓ | **no-op** | **no-op** |
| Settings surface action feedback | ✓ | partial (unverified) | **none** |
| Surface load timeout/retry | n/a (HTML push) | unverified | **infinite skeleton** |
| Top-bar from server model | ✓ | partial (fixed buttons + server menu) | **model unconsumed** |
| workspace_timeline_mode | ✓ | no (menu→History dialog) | no (client-side pill) |
| `ui_render target=history` | ✓ | **silent pass** | n/a (handled via load) |
| Renderer vocabulary | 35 | 31 (−image, −audio, −plotly, −generative) | 33 (−audio, −generative) |
| Markdown links | ✓ | ✓ (QLabel rich text) | **no** |
| supported_types drift guard | n/a | ✓ | ✓ |

## 5. Spec-status findings (docs truth)

- **041**: tasks T001–T056 all `[X]`; spec header still "Status: Draft".
- **042**: shipped via PR #99 + follow-ups, but **tasks.md T001–T051 all unchecked**;
  verification tasks (T023/T045/T048/T051) never recorded; `verification/` has 4 tracked
  screenshots + **3 untracked** (`android-app-emulator.png`, `shot_chat.png`,
  `shot_settings_menu.png`). The two desktop shots render **all text as tofu boxes** and a
  broken logo — capture-environment font issue vs client defect unresolved.
- **043**: PR #100 merged; render path (T013–T014, T016–T018, T019–T024) done, but
  **T015 (Windows surface-host test), T025/T026 (client render tests + live verification),
  US2 actions T027–T033, US3 theme T034–T038, polish T039–T044 all unchecked**;
  T004/T005/T010/T011 unchecked (protocol scaffolds + astralprims publish/docs).
- **CLAUDE.md**: says Windows client is tkinter; it is PySide6/Qt.

## 6. Verification assets available today

- `backend/verification/` (032 harness): live drivers register **browser only**
  (external.py:119); `enrich_thin_client` statically re-adapts captured components through
  browser+mobile profiles (in_process.py:469-497). **No windows/android live driver.**
- `backend/qual_audit/suites/test_rote_adaptation.py`: 6 profiles × 8 sample cases (not the
  native profiles' concern — they're full-capability).
- `backend/tests/chrome/test_chrome_surface.py:103`: parametrized windows/android →
  chrome_surface vs browser → chrome_render (delivery parity).
- `backend/tests/test_astralprims_parity.py`: 30+5 catalog parity.
- Per-client vocab drift guards (Windows test_renderer.py:142-156; Android
  VocabularyParityTest.kt).
- **Missing**: full 35-type × 3-client render matrix; native live drivers; protocol-coverage
  guard (every server-sendable type classified per client); legible desktop capture pipeline.
