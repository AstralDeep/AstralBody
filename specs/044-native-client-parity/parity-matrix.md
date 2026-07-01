# Parity Matrix — Server Contract × Web / Windows / Android (044)

**Status**: SEEDED with target dispositions (plan phase). Evidence cells are `pending` until
the verification pass fills them; **no cell may be empty or "unknown" at completion** (FR-001,
SC-001/SC-002). Disposition vocabulary per [data-model.md §3](data-model.md).

Legend: ✅ native · ≈ native-equivalent · ⤵ server-substituted · ▫ degraded (labeled
placeholder) · ∅ ignored (deliberate, logged) · 🌐 web-only (Constitution XII v2.3.1 carve-out).
`※` = changed by this feature (target state shown).

## A. Server→client frame types (47)

| Frame | Web | Windows (target) | Android (target) | Notes |
|---|---|---|---|---|
| `rote_config` | ✅ | ∅ ※(logged) | ∅ ※(logged) | natives are full-capability; profile info unused |
| `chrome_menu` | ≈ (server-rendered HTML topbar) | ✅ | ✅ ※(topbar now rendered) | model v1 |
| `user_preferences` | ✅ (theme) | ✅ ※(theme boot) | ✅ ※(theme boot) | R9 |
| `system_config` | ✅ | ∅ ※(logged) | ∅ ※(logged) | dashboard data; natives use agent_list |
| `agent_list` | ✅ | ✅ | ✅ | |
| `agent_registered` | ✅ | ∅ ※(logged) | ∅ ※(logged) | |
| `auth_required` | ✅ | ✅ ※(+ sign-in affordance) | ✅ ※(+ sign-in on refresh fail) | R4 |
| `ui_render` | ✅ | ✅ ※(history routed; identity reconcile) | ✅ ※(identity reconcile) | R12/R14 |
| `ui_update` | ✅ | ∅ ※(logged) | ∅ ※(logged) | legacy; server no longer targets natives |
| `ui_upsert` | ✅ | ✅ | ✅ | |
| `ui_append` | ✅ | ∅ ※(logged) | ∅ ※(logged) | legacy |
| `ui_stream_data` | ✅ | ✅ ※(+seq guard) | ✅ | R12 |
| `chrome_render` | ✅ | ∅ ※(logged; server now sends native twins) | ∅ ※(logged) | R2/R8 device-aware paths |
| `chrome_surface` | n/a | ✅ ※(+timeout/retry) | ✅ ※(+timeout/retry) | R8 |
| `chat_status` | ✅ | ✅ ※(full vocab) | ✅ ※(full vocab) | |
| `chat_step` | ✅ | ✅ ※ | ✅ ※ | R13 |
| `chat_created` | ✅ | ✅ | ✅ | |
| `chat_loaded` | ✅ | ✅ | ✅ | rehydration scenario US1/US4 |
| `chat_deleted` | ✅ | ∅ ※(logged) | ∅ ※(logged) | cross-tab concern; natives single-window |
| `history_list` | ✅ | ✅ | ✅ | |
| `user_message_acked` | ✅ | ✅ ※ | ✅ | R13 |
| `task_started` | ✅ | ✅ ※ | ✅ ※ | R13 |
| `task_completed` | ✅ | ✅ ※ | ✅ ※ | R13 |
| `tool_progress` | ✅ | ✅ ※ | ✅ ※ | R13 |
| `workspace_timeline_mode` | ✅ | ✅ ※(read-only mode) | ✅ ※ | R7 |
| `heartbeat` | ✅ | ∅ ※(logged) | ∅ ※(logged) | keepalive |
| `stream_subscribed` | ✅ | ✅ | ✅ | |
| `stream_unsubscribed` | ✅ | ✅ | ✅ ※(state cleared) | |
| `stream_list` | ✅ | ∅ (logged — existing) | ∅ ※(logged) | no native surface |
| `stream_data` | ✅ | ✅ | ✅ | |
| `stream_error` | ✅ | ✅ | ✅ | |
| `component_saved` | ✅ | ∅ ※(logged) | ∅ ※(logged) | acks for web workspace verbs |
| `component_save_error` | ✅ | ∅ ※(logged) | ∅ ※(logged) | |
| `saved_components_list` | ✅ | ∅ ※(logged) | ∅ ※(logged) | |
| `component_deleted` | ✅ | ∅ ※(logged) | ∅ ※(logged) | |
| `combine_status` | ✅ | ∅ ※(logged) | ∅ ※(logged) | |
| `combine_error` | ✅ | ∅ ※(logged) | ∅ ※(logged) | |
| `components_combined` | ✅ | ∅ ※(logged) | ∅ ※(logged) | |
| `components_condensed` | ✅ | ∅ ※(logged) | ∅ ※(logged) | |
| `agent_permissions` | ✅ | ✅ | ✅ | native agents screens |
| `agent_permissions_updated` | ✅ | ✅ | ✅ | |
| `llm_config_ack` | ✅ | ∅ ※(logged) | ∅ ※(logged) | natives use LLM surface round-trip |
| `llm_usage_report` | ✅ | ∅ ※(logged) | ∅ ※(logged) | |
| `audit_append` | ✅ | ∅ ※(logged) | ∅ ※(logged) | natives fetch audit via REST |
| `agent_creation_progress` | ✅ | ∅ ※(logged) | ∅ ※(logged) | draft cards carry state in-chat |
| `notification` | ∅ ※(logged→toast optional) | ✅ ※(toast) | ✅ ※(toast) | newly catalogued (R1) |
| `error` (3 shapes + `code:internal` ※) | ✅ ※(toast added) | ✅ ※(banner+turn fail) | ✅ ※(banner+turn fail) | R2 |

## B. Component vocabulary (35)

| Type | Web | Windows (target) | Android (target) | Notes |
|---|---|---|---|---|
| container, text, card, grid, tabs, divider, collapsible, list, alert, progress, metric, code, badge, hero, keyvalue, timeline, rating, skeleton, chat_history | ✅ | ✅ | ✅ | already native both |
| button, input, param_picker | ✅ | ✅ | ✅ | interactive round-trip verified in gallery |
| table | ✅ (paginated) | ✅ ※(+pager) | ✅ ※(+pager) | R11 |
| image | ✅ | ✅ ※(QPixmap; was ▫) | ✅ (Coil) | FR-026 build-to-parity |
| bar_chart, line_chart, pie_chart | ✅ | ✅ (QtCharts) | ✅ (Canvas) | |
| plotly_chart | ✅ | ✅ ※(QtCharts approximation; was ▫; unsupported trace kinds → table, disclosed) | ✅ (Canvas approximation) | FR-026 |
| color_picker | ✅ (editable) | ✅ ※(editable; was read-only) | ✅ ※(editable; was readout) | R9 |
| theme_apply | ✅ (live restyle) | ✅ ※(live restyle; was no-op) | ✅ ※(live restyle; was no-op) | R9 |
| file_upload | ✅ | ✅ (QFileDialog) | ✅ | |
| file_download, download_card | ✅ | ✅ | ✅ | 043 |
| audio | ✅ | 🌐 ⤵ (server degrade ladder; labeled placeholder as safety net) | 🌐 ⤵ | sanctioned web-only (FR-026) |
| generative | ✅ | 🌐 ⤵ | 🌐 ⤵ | sanctioned web-only (FR-026) |

Windows advertised vocabulary moves 31 → 33 (adds `image`, `plotly_chart`), matching Android;
`audio`/`generative` remain the only server-substituted types on both (drift guards pin this).

## C. Chrome & journeys (dispositions)

| Capability | Web | Windows (target) | Android (target) |
|---|---|---|---|
| Top-bar from server model (brand/status/pulse/timeline/settings) | ✅ | ✅ ※ | ✅ ※(was unconsumed) |
| Settings menu from server model + sign-out | ✅ | ✅ | ✅ |
| Server-revoking sign-out (offline-tolerant) | ✅ | ✅ ※(was local quit) | ✅ ※(was local clear) |
| Reconnect w/ backoff + visible state + queue | ≈ (browser reload) | ✅ ※(was none) | ✅ ※(+visible overflow) |
| Surfaces: theme/guide/llm/personalization round-trips | ✅ | ✅ ※(feedback verified) | ✅ ※(feedback + timeout) |
| Surfaces: workspace_timeline, pulse, attachments | ✅ | ✅ ※(new components()) | ✅ ※ |
| Surfaces: agents, audit | ✅ | ≈ (native screens, deliberate) | ≈ |
| Surface: drafts | ≈ (in-chat cards; surface unreachable from any menu) | ≈ | ≈ |
| Admin tools, guided tour | ✅ | 🌐 (server-omitted) | 🌐 |
| Attachments compose (chips + parser status) | ✅ | ✅ ※(was none) | ✅ |
| Attachment library | ✅ (paperclip → surface) | ✅ ※ | ✅ ※ |
| Table pagination | ✅ | ✅ ※ | ✅ ※ |
| Theme live restyle + persistence | ✅ | ✅ ※(+disclosure) | ✅ ※ |
| Markdown links | ✅ | ✅ | ✅ ※(was raw text) |
| History rehydration + read-only timeline | ✅ | ✅ ※ | ✅ ※ |

**Evidence**: captured in [verification/results.md](verification/results.md) (live run
2026-07-01) — per-scenario outcomes across web (Chromium), the Windows app (native Qt), and
the Android emulator, with legible screenshots in `verification/{web,windows,android}/` and
suite tallies (backend 3037 / Windows 210 / Android 58+72 unit + 10 instrumented). No cell
is "unknown"; the one blocked path (Android real-Keycloak logged-in chat) is recorded as
D-032 with its compensating on-device rendering evidence.
