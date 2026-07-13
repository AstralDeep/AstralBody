# Parity Matrix — Server Contract × Web / Windows / Android (044) × iOS / macOS / Watch (051)

**Status**: 044 columns VERIFIED (live run 2026-07-01, see Evidence below). **Extended by
feature 051 (T050/FR-037)** with `iOS (051)` / `macOS (051)` / `Watch (051)` columns whose
authoritative disposition source is
`apple-clients/AstralCore/Sources/AstralCore/Protocol/Dispositions.swift` (drift-guarded
against `backend/shared/ui_protocol.json`); Apple evidence cells reference
[specs/051-apple-native-clients/verification/](../051-apple-native-clients/verification/)
(bundle in progress). **No cell may be empty or "unknown" at completion** (FR-001,
SC-001/SC-002). Disposition vocabulary per [data-model.md §3](data-model.md).

Legend: ✅ native · ≈ native-equivalent · ⤵ server-substituted · ▫ degraded (labeled
placeholder) · ∅ ignored (deliberate, logged) · 🌐 web-only (Constitution XII v2.3.1 carve-out).
`※` = changed by this feature (target state shown); in the three Apple columns `※` marks
cells introduced by feature 051. `★` = changed by feature 055 (uniform artifacts — target
state shown; dispositions land with the 055 PR). iOS and macOS share one frame table by design
(`ClientDispositions.macos.frames == ios.frames`), so their Table A cells are identical.

## A. Server→client frame types (47)

| Frame | Web | Windows (target) | Android (target) | iOS (051) | macOS (051) | Watch (051) | Notes |
|---|---|---|---|---|---|---|---|
| `rote_config` | ✅ | ∅ ※(logged) | ∅ ※(logged) | ∅ ※ | ∅ ※ | ∅ ※ | natives are full-capability; profile info unused |
| `chrome_menu` | ≈ (server-rendered HTML topbar) | ✅ | ✅ ※(topbar now rendered) | ✅ ※ | ✅ ※ | ∅ ※(no chrome surfaces on the wrist) | model v1 |
| `user_preferences` | ✅ (theme) | ✅ ※(theme boot) | ✅ ※(theme boot) | ✅ ※ | ✅ ※ | ∅ ※(wrist is system-styled) | R9 |
| `system_config` | ✅ | ∅ ※(logged) | ∅ ※(logged) | ∅ ※ | ∅ ※ | ∅ ※ | dashboard data; natives use agent_list |
| `agent_list` | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ∅ ※(agent mgmt on phone/desktop/web) | |
| `agent_registered` | ✅ | ∅ ※(logged) | ∅ ※(logged) | ∅ ※ | ∅ ※ | ∅ ※ | lifecycle acks have no native surface |
| `auth_required` | ✅ | ✅ ※(+ sign-in affordance) | ✅ ※(+ sign-in on refresh fail) | ✅ ※ | ✅ ※ | ✅ ※(wipe → QR device-grant screen) | R4 |
| `ui_render` | ✅ | ✅ ※(history routed; identity reconcile) | ✅ ※(identity reconcile) | ✅ ※ | ✅ ※ | ✅ ※(server pre-degraded via watch profile) | R12/R14 |
| `ui_update` | ✅ | ∅ ※(logged) | ∅ ※(logged) | ∅ ※ | ∅ ※ | ∅ ※ | legacy; server no longer targets natives |
| `ui_upsert` | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ✅ ※ | |
| `ui_append` | ✅ | ∅ ※(logged) | ∅ ※(logged) | ∅ ※ | ∅ ※ | ∅ ※ | legacy |
| `ui_stream_data` | ✅ | ✅ ※(+seq guard) | ✅ | ✅ ※ | ✅ ※ | ✅ ※ | R12 |
| `chrome_render` | ✅ | ∅ ※(logged; server now sends native twins) | ∅ ※(logged) | ∅ ※ | ∅ ※ | ∅ ※ | R2/R8 device-aware paths |
| `chrome_surface` | n/a | ✅ ※(+timeout/retry) | ✅ ※(+timeout/retry) | ✅ ※ | ✅ ※ | ∅ ※(no chrome surfaces on the wrist) | R8 |
| `chat_status` | ✅ | ✅ ※(full vocab) | ✅ ※(full vocab) | ✅ ※ | ✅ ※ | ✅ ※(the wrist progress channel) | |
| `chat_step` | ✅ | ✅ ※ | ✅ ※ | ✅ ※ | ✅ ※ | ✅ ※ | R13 |
| `chat_created` | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ✅ ※ | |
| `chat_loaded` | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ✅ ※ | rehydration scenario US1/US4 |
| `chat_deleted` | ✅ | ∅ ※(logged) | ∅ ※(logged) | ∅ ※ | ∅ ※ | ∅ ※ | cross-tab concern; natives single-window |
| `history_list` | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ∅ ※(recents come from REST) | |
| `user_message_acked` | ✅ | ✅ ※ | ✅ | ✅ ※ | ✅ ※ | ✅ ※ | R13 |
| `task_started` | ✅ | ✅ ※ | ✅ ※ | ✅ ※ | ✅ ※ | ∅ ※(async detachment is larger-screen) | R13 |
| `task_completed` | ✅ | ✅ ※ | ✅ ※ | ✅ ※ | ✅ ※ | ∅ ※(async detachment is larger-screen) | R13 |
| `tool_progress` | ✅ | ✅ ※ | ✅ ※ | ✅ ※ | ✅ ※ | ∅ ※(chat_status is the wrist channel) | R13 |
| `workspace_timeline_mode` | ✅ | ✅ ※(read-only mode) | ✅ ※ | ✅ ※ | ✅ ※ | ∅ ※(timeline is larger-screen) | R7 |
| `heartbeat` | ✅ | ∅ ※(logged) | ∅ ※(logged) | ∅ ※ | ∅ ※ | ∅ ※ | keepalive |
| `stream_subscribed` | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ∅ ※(no live-stream nodes on the wrist) | |
| `stream_unsubscribed` | ✅ | ✅ | ✅ ※(state cleared) | ∅ ※(terminal state via ui_stream_data done flag) | ∅ ※(same) | ∅ ※(same) | |
| `stream_list` | ✅ | ∅ (logged — existing) | ∅ ※(logged) | ∅ ※ | ∅ ※ | ∅ ※ | no native surface |
| `stream_data` | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ∅ ※(no live-stream nodes on the wrist) | |
| `stream_error` | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ✅ ※ | |
| `component_saved` | ✅ | ✅ ★(status surface) | ✅ ★(status surface) | ✅ ★ | ✅ ★ | ∅ ★(workspace verbs are larger-screen affordances) | 055 US3 promotion (was web-only acks) |
| `component_save_error` | ✅ | ✅ ★(status surface) | ✅ ★(status surface) | ✅ ★ | ✅ ★ | ∅ ★(carve-out) | 055 US3 promotion |
| `saved_components_list` | ✅ | ✅ ★(saved-components refresh) | ✅ ★(refresh) | ✅ ★ | ✅ ★ | ∅ ★(carve-out) | 055 US3 promotion |
| `component_deleted` | ✅ | ✅ ★(identity-keyed remove) | ✅ ★(identity-keyed remove) | ✅ ★ | ✅ ★ | ∅ ★(carve-out) | 055 US3 promotion |
| `combine_status` | ✅ | ✅ ★(status surface) | ✅ ★(status surface) | ✅ ★ | ✅ ★ | ∅ ★(carve-out) | 055 US3 promotion |
| `combine_error` | ✅ | ✅ ★(status surface) | ✅ ★(status surface) | ✅ ★ | ✅ ★ | ∅ ★(carve-out) | 055 US3 promotion |
| `components_combined` | ✅ | ✅ ★(apply result + remove consumed) | ✅ ★(same) | ✅ ★ | ✅ ★ | ∅ ★(carve-out) | 055 US3 promotion |
| `components_condensed` | ✅ | ✅ ★(apply result + remove consumed) | ✅ ★(same) | ✅ ★ | ✅ ★ | ∅ ★(carve-out) | 055 US3 promotion |
| `agent_permissions` | ✅ | ✅ | ✅ | ∅ ※(web verb acks; natives re-discover) | ∅ ※(same) | ∅ ※(same) | native agents screens |
| `agent_permissions_updated` | ✅ | ✅ | ✅ | ∅ ※(web verb acks; natives re-discover) | ∅ ※(same) | ∅ ※(same) | |
| `llm_config_ack` | ✅ | ∅ ※(logged) | ∅ ※(logged) | ∅ ※ | ∅ ※ | ∅ ※ | natives use LLM surface round-trip |
| `llm_usage_report` | ✅ | ∅ ※(logged) | ∅ ※(logged) | ∅ ※ | ∅ ※ | ∅ ※ | |
| `audit_append` | ✅ | ∅ ※(logged) | ∅ ※(logged) | ∅ ※(audit via REST) | ∅ ※(audit via REST) | ∅ ※ | natives fetch audit via REST |
| `agent_creation_progress` | ✅ | ∅ ※(logged) | ∅ ※(logged) | ∅ ※ | ∅ ※ | ∅ ※ | draft cards carry state in-chat |
| `notification` | ∅ ※(logged→toast optional) | ✅ ※(toast) | ✅ ※(toast) | ✅ ※ | ✅ ※ | ∅ ※(speech covers deliveries) | newly catalogued (R1) |
| `error` (3 shapes + `code:internal` ※) | ✅ ※(toast added) | ✅ ※(banner+turn fail) | ✅ ※(banner+turn fail) | ✅ ※ | ✅ ※ | ✅ ※ | R2 |

## B. Component vocabulary (35)

| Type | Web | Windows (target) | Android (target) | iOS (051) | macOS (051) | Watch (051) | Notes |
|---|---|---|---|---|---|---|---|
| container, text, card, divider, list, alert, progress, metric, badge, keyvalue | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ✅ ※(the watch-profile native set) | already native both (row split for 051 watch column) |
| grid, tabs, collapsible, code, hero, timeline, rating, skeleton, chat_history | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ⤵ ※(outside watch profile; server degrades, client text fallback) | already native both (row split for 051 watch column) |
| button, input, param_picker | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ⤵ ※ | interactive round-trip verified in gallery |
| table | ✅ (paginated) | ✅ ※(+pager) | ✅ ※(+pager) | ✅ ※(+pager) | ✅ ※(+pager) | ⤵ ※ | R11 |
| image | ✅ | ✅ ※(QPixmap; was ▫) | ✅ (Coil) | ✅ ※ | ✅ ※ | ⤵ ※ | FR-026 build-to-parity |
| bar_chart, line_chart, pie_chart | ✅ | ✅ (QtCharts) | ✅ (Canvas) | ✅ ※ | ✅ ※ | ⤵ ※ | |
| plotly_chart | ✅ | ✅ ※(QtCharts approximation; was ▫; unsupported trace kinds → table, disclosed) | ✅ (Canvas approximation) | ✅ ※(approximation) | ✅ ※(approximation) | ⤵ ※ | FR-026 |
| color_picker | ✅ (editable) | ✅ ※(editable; was read-only) | ✅ ※(editable; was readout) | ✅ ※ | ✅ ※ | ⤵ ※ | R9 |
| theme_apply | ✅ (live restyle) | ✅ ※(live restyle; was no-op) | ✅ ※(live restyle; was no-op) | ✅ ※(live restyle) | ✅ ※(live restyle) | ⤵ ※(wrist is system-styled) | R9 |
| file_upload | ✅ | ✅ (QFileDialog) | ✅ | ✅ ※ | ✅ ※ | ⤵ ※ | |
| file_download, download_card | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ⤵ ※ | 043 |
| audio | ✅ | 🌐 ⤵ (server degrade ladder; labeled placeholder as safety net) | 🌐 ⤵ | 🌐 ⤵ ※(readable fallback as safety net) | 🌐 ⤵ ※(readable fallback as safety net) | ⤵ ※ | sanctioned web-only (FR-026) |
| generative | ✅ | 🌐 ⤵ | 🌐 ⤵ | 🌐 ⤵ ※ | 🌐 ⤵ ※ | ⤵ ※ | sanctioned web-only (FR-026) |

Windows advertised vocabulary moves 31 → 33 (adds `image`, `plotly_chart`), matching Android;
`audio`/`generative` remain the only server-substituted types on both (drift guards pin this).
※ 051: iOS/macOS advertise the same 33-type native set (everything except `audio`/`generative`,
which stay web-only/server-substituted with a readable fallback as safety net). The watch
natively renders the 10-type set its ROTE profile can emit (`alert, badge, card, container,
divider, keyvalue, list, metric, progress, text`); every other type is server-degraded via the
`watch` profile with a client readable-text fallback as safety net (FR-032/033). Apple drift
guard: `ManifestDriftTests` asserts `Dispositions.swift` matches `ui_protocol.json` exactly.

## C. Chrome & journeys (dispositions)

| Capability | Web | Windows (target) | Android (target) | iOS (051) | macOS (051) | Watch (051) |
|---|---|---|---|---|---|---|
| Top-bar from server model (brand/status/pulse/timeline/settings) | ✅ | ✅ ※ | ✅ ※(was unconsumed) | ✅ ※ | ✅ ※ | ∅ ※(no chrome on the wrist) |
| Settings menu from server model + sign-out | ✅ | ✅ | ✅ | ✅ ※ | ✅ ※ | ≈ ※(one-tap sign-out on home; no server-model menu) |
| Server-revoking sign-out (offline-tolerant) | ✅ | ✅ ※(was local quit) | ✅ ※(was local clear) | ✅ ※ | ✅ ※ | ✅ ※(one-tap, POST /api/auth/logout) |
| Reconnect w/ backoff + visible state + queue | ≈ (browser reload) | ✅ ※(was none) | ✅ ※(+visible overflow) | ✅ ※(shared WSClient: 1 s base ×2 cap 30 s, bounded queue + drop signal) | ✅ ※(shared WSClient) | ✅ ※(shared WSClient; "Reconnecting…" state) |
| Surfaces: theme/guide/llm/personalization round-trips | ✅ | ✅ ※(feedback verified) | ✅ ※(feedback + timeout) | ✅ ※ | ✅ ※ | ∅ ※(no chrome surfaces on the wrist) |
| Surfaces: workspace_timeline, pulse, attachments | ✅ | ✅ ※(new components()) | ✅ ※ | ✅ ※ | ✅ ※ | ∅ ※ |
| Surfaces: agents, audit | ✅ | ≈ (native screens, deliberate) | ≈ | ≈ ※(native screens) | ≈ ※(native screens) | ∅ ※ |
| Surface: drafts | ≈ (in-chat cards; surface unreachable from any menu) | ≈ | ≈ | ≈ ※(in-chat cards) | ≈ ※(in-chat cards) | ∅ ※ |
| Admin tools, guided tour | ✅ | 🌐 (server-omitted) | 🌐 | 🌐 ※ | 🌐 ※ | 🌐 ※ |
| Attachments compose (chips + parser status) | ✅ | ✅ ※(was none) | ✅ | ✅ ※ | ✅ ※ | ∅ ※(no compose on the wrist) |
| Attachment library | ✅ (paperclip → surface) | ✅ ※ | ✅ ※ | ✅ ※ | ✅ ※ | ∅ ※ |
| Table pagination | ✅ | ✅ ※ | ✅ ※ | ✅ ※ | ✅ ※ | n/a ※(tables degraded by watch profile) |
| Theme live restyle + persistence | ✅ | ✅ ※(+disclosure) | ✅ ※ | ✅ ※ | ✅ ※ | ∅ ※(system-styled) |
| Markdown links | ✅ | ✅ | ✅ ※(was raw text) | ✅ ※(AttributedString) | ✅ ※(AttributedString) | ▫ ※(plain text) |
| History rehydration + read-only timeline | ✅ | ✅ ※ | ✅ ※ | ✅ ※ | ✅ ※ | ≈ ※(REST recents + chat_loaded; no timeline) |
| QR device-grant sign-in (RFC 8628) ※ | ≈ ※(short-code entry at verification page) | n/a | n/a | n/a | n/a | ✅ ※(on-watch QR + polling grant) |
| Voice dictation input ※ | n/a | n/a | n/a | n/a | n/a | ✅ ※(system dictation into chat) |
| Spoken rendition output ※ | n/a | n/a | n/a | n/a | n/a | ✅ ※(server `speech` field + on-device TTS) |
| Watch degradation guarantees ※ | n/a | n/a | n/a | n/a | n/a | ✅ ※(FR-032 sweep test: every manifest type yields readable output) |
| `ui_stream_data`/`stream_subscribed` `component_id` additive field ★ | ✅ ★(keys streamed node by identity from first frame) | ✅ ★(same keying rule) | ✅ ★(typed decode + keying rule) | ✅ ★(dynamic read + keying rule) | ✅ ★(same) | ∅ ★(status-text treatment unchanged; terminal `ui_upsert` carries streamed content) |
| `component_refine` / `component_restore` accept actions ★ | ✅ ★(component chrome affordance + history restore) | ✅ ★(context menu) | ✅ ★(overflow menu) | ✅ ★(context menu) | ✅ ★(context menu) | ∅ ★(declared carve-out: no affordance; server refuses honestly if received) |
| `provenance` component field render ★ | ✅ ★(existing footer, field-driven) | ✅ ★(compact badge in component chrome) | ✅ ★(compact badge) | ✅ ★(compact badge) | ✅ ★(compact badge) | ▫ ★(inherited via text degradation) |

**Evidence**: captured in [verification/results.md](verification/results.md) (live run
2026-07-01) — per-scenario outcomes across web (Chromium), the Windows app (native Qt), and
the Android emulator, with legible screenshots in `verification/{web,windows,android}/` and
suite tallies (backend 3037 / Windows 210 / Android 58+72 unit + 10 instrumented). No cell
is "unknown"; the one blocked path (Android real-Keycloak logged-in chat) is recorded as
D-032 with its compensating on-device rendering evidence. **051 Apple evidence** lives in
[specs/051-apple-native-clients/verification/](../051-apple-native-clients/verification/)
(bundle in progress); Apple dispositions above are code-backed by
`apple-clients/AstralCore/Sources/AstralCore/Protocol/Dispositions.swift` and its
manifest drift guard.
