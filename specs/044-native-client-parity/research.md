# Phase 0 Research — Cross-Client Native Parity Review & Remediation

**Feature**: 044-native-client-parity | **Date**: 2026-07-01
**Inputs**: [spec.md](spec.md), [baseline-findings.md](baseline-findings.md), plus a verified
re-read of the backend wire contract and both native clients (line refs current at c2d57b6).

No `NEEDS CLARIFICATION` markers existed in the Technical Context; the decisions below resolve
the *design* unknowns the spec deliberately left open (tofu-screenshot cause, logout mechanics,
guard architecture, per-gap remediation shape).

---

## R1. Protocol manifest & drift guards (FR-001, FR-014, FR-023, SC-001)

**Decision**: Create the project's first machine-readable UI-protocol manifest at
`backend/shared/ui_protocol.json` — the single committed source for (a) all **47**
server→client WS frame types (the 46 catalogued in the audit **plus `notification`**, found at
`scheduler/runner.py:44-47` → `orch.notify_user`), (b) the client→server `ui_event` action
vocabulary, and (c) the 35-type component vocabulary. Enforcement is three-sided:

- **Backend**: a pytest asserts the manifest's component list `== webrender.allowed_primitive_types()`,
  and a source-sweep test (regex over `{"type": "<literal>"` send sites in the UI-socket send
  modules, with an explicit allowlist for inbound/voice-endpoint types) asserts every UI-bound
  send site is manifested — a new frame type without a manifest entry fails the build.
- **Windows**: `astral_client/protocol_manifest.py` holds a `{frame_type: "handled" | "ignored"}`
  classification consumed by `_on_message`'s new default branch; a pytest asserts the
  classification covers the manifest exactly (no unclassified, no stale entries). The existing
  vocabulary guard (`tests/test_renderer.py:142-156`) switches its `BACKEND_TYPES` snapshot to
  read the manifest JSON.
- **Android**: `core/.../protocol/ProtocolManifest.kt` with the same classification, asserted by
  a `:core` JUnit test that reads the manifest JSON via a repo-relative path;
  `VocabularyParityTest` likewise re-anchors its expected set on the manifest instead of an
  in-file list.

**Rationale**: No registry exists today (verified — `Message.from_json` is inbound-biased and
covers ~20 of 47 types). A committed JSON is dependency-free for all three test stacks in this
monorepo and makes "silently dropped" mechanically impossible: a type is either handled or
ignored-with-log, per client, or a test fails.

**Alternatives considered**: (a) importing `backend/shared/protocol.py` from the Windows tests —
rejected: drags backend deps into the client venv; (b) generating per-client copies at build
time — rejected: adds build machinery for zero benefit in a monorepo; (c) keeping the parity
matrix (markdown) as the only source — rejected: not machine-checkable, which is how the drift
happened.

## R2. Visible errors + unknown-frame logging (FR-002, SC-006)

**Decision**:
- Both natives handle **all three existing `error` frame shapes** (`{code,message}`,
  `{payload:{message}}`, `{message}` — verified incompatible) through one normalizing decoder,
  surface them as a visible transient banner/toast plus a transcript notice, and resolve any
  active turn to a terminal failed state.
- **Backend (full-stack, additive)**: the generic `handle_ui_message` catch
  (`orchestrator.py:2296-2298`), which today logs and sends *nothing*, additionally emits
  `{"type":"error","code":"internal","message":…}`; `webrender/static/client.js` gains matching
  toast handling so the web baseline improves too.
- `chrome_events.py`'s three web-only HTML error paths (unknown action `:245-248`, admin-denied
  action `:257-260`, uncaught handler exception `:269-278`) become **device-aware**: native
  targets get a `chrome_surface` carrying an error Alert; web keeps its HTML modal.
- Unknown inbound frames: Windows `_on_message` gains a default branch that logs
  `unhandled frame type=<t>`; Android's reducer logs `Inbound.Unknown` types instead of the
  silent `else -> s`.

**Rationale**: FR-002's "visibly surface" and SC-001's "zero unlogged drops" are unreachable
client-side alone when the server itself emits nothing on generic failure; the additive `error`
frame and device-aware chrome errors fix root causes per the full-stack clarification while
staying backward-compatible (new frames are additive; old clients already ignore unknowns).

**Alternatives**: normalizing the three legacy error shapes server-side into one — rejected as a
breaking wire change; the manifest documents all shapes and clients decode all of them.

## R3. Windows reconnect / outbound queue (FR-003, SC-005)

**Decision**: Port Android's transport semantics into
`windows-client/astral_client/protocol.py::OrchestratorClient`: an auto-reconnect loop around
`_main` with exponential backoff (1 s base, ×2, 30 s cap, reset on successful open), a bounded
outbound queue (64 frames) flushed on open, and a widened status vocabulary
(`connecting/connected/reconnecting:<n>/auth_required:*/closed:*`). On reconnect the existing
`connected` handler already re-registers and re-pulls agents/history. **Queue overflow fails
visibly on both clients** (status banner note), replacing Android's current silent drop-oldest
(`OrchestratorClient.kt:147`) — FR-003 forbids frames vanishing.

Windows gains a real visible connection indicator: the brand-mark tooltip tint
(`TopBar.set_status`, app.py:403-409) is supplemented by a status text chip in the top bar
(rendered as the server model's `status` control — see R6) and a reconnect banner over the
canvas while disconnected.

**Rationale**: Android's `backoffDelayMs` + `pending` queue + `ConnectionState` is proven,
matches SC-005's 30-second bound, and porting it keeps the two natives behaviorally identical.

**Alternatives**: reconnect driven from `app.py._on_status` — rejected: the transport owns the
socket lifecycle; app-side reconnect is what produced today's teardown/rebuild-on-auth hack.

## R4. Session expiry → silent refresh or explicit sign-in (FR-004)

**Decision**: Windows keeps silent refresh on `auth_required` (existing, `app.py:1154-1162`) but
the dead-end branches (dev-token/no-session, refresh failure, `_reauth_tries` exhausted) now
present an explicit **sign-in dialog** (button → the existing `oidc_login` loopback flow on a
worker thread → `_reconnect(new_token)`) instead of the frozen "Re-authenticating…" caption.
Android's cold-start/`AuthRequired` refresh failures (currently log-only,
`MainActivity.kt:122-131,164-173`) route to the existing `SignInScreen`.

**Rationale**: FR-004's "never a dead session" is a state-machine completeness fix; both clients
already own every needed piece (refresh, interactive login, reconnect) — they're just not wired
into the failure branches.

## R5. Native sign-out revokes the server session (FR-005, SC-004)

**Decision**: Add one **additive REST endpoint** `POST /api/auth/logout` (bearer-JWT authed via
the existing `get_current_user_payload`), body `{"refresh_token": str, "client_id": str}` with
`client_id` validated against the existing `KEYCLOAK_ALLOWED_AZP` allowlist. Server-side it
mirrors web logout exactly: `_revoke_or_queue(user_id, refresh_token, client_id=…)` →
`OfflineGrantStore().revoke_for_user(user_id)` → audit `auth.logout` (channel recorded).
`_revoke_refresh_token` gains an optional `client_id` override (Keycloak only revokes a token
for its issuing client — `astral-desktop`/`astral-mobile`, not the web client id). The
offline-tolerant queue keeps working for native tokens via **one additive nullable column**
`auth_revocation_queue.client_id` (idempotent `_init_db` delta; rollback = drop column; NULL
falls back to the configured web client id, preserving old rows).

Client behavior on sign-out (both natives): (1) call `POST /api/auth/logout` (server queues if
Keycloak is down — the web's offline-tolerant posture, inherited); (2) if the *backend* is
unreachable, best-effort direct `POST {authority}/protocol/openid-connect/logout` with
`client_id` + `refresh_token`; (3) **always** clear local credentials and return to the
signed-out state; log the revocation outcome. Windows then quits (current UX); Android returns
to `SignInScreen`. SC-004 is verified by attempting a refresh with the old refresh token
post-logout (must be rejected) — for token-holding natives the refresh credential *is* the
durable session credential (unexpired access JWTs remain signature-valid until `exp`, exactly as
on the web after its session row dies; documented in the matrix).

**Rationale**: Verified that no native-callable revocation path exists (`/auth/logout` is
cookie-bound; `api.py` has none). Routing through the backend is the only way to honor the
web's queued-revocation posture — a client that clears its local token cannot retry later
itself. Direct-to-Keycloak stays as the backend-unreachable fallback.

**Alternatives**: (a) client-only direct Keycloak revocation — rejected: loses offline
tolerance and the `auth.logout` audit trail; (b) AppAuth browser `EndSessionRequest` on Android
— rejected: interactive browser bounce for a background concern, and no Windows twin.

## R6. Server-driven top bar on both natives (FR-015)

**Decision**: Both natives render the `chrome_menu` model's `topbar` array (shape verified:
`brand`, `status`, optional `pulse` action, `timeline` action, `settings` menu — there is **no
separate connection-status control to invent**; `kind:"status"` *is* it). Android's
`RootScaffold.AstralTopBar` composes: brand image ← `brand`, live connection text/dot ←
`status` (reviving the dead `connectionLabel()`), `IconButton` per `kind:"action"` control with
a semantic icon map (`sparkle`/`history`/`gear`), and the existing `SettingsMenu` anchored on
the `menu` control. Windows `TopBar` renders the already-parsed-but-unrendered
`topbar_actions` (rest.py:100-108) as buttons beside the settings gear and binds its status
chip to the `status` control. Client-invented navigation (Android New/Recent, Windows chat
list) stays — it is the form-factor adaptation of the web shell's sidebar (chat navigation is
not part of the server chrome model), recorded as `native equivalent` in the matrix.

**Rationale**: The model already carries everything (Android even decodes and unit-tests it —
zero render call sites); this is pure client wiring plus R7 making the target surfaces real.

## R7. Surfaces gaining `components()` — and the ones that deliberately don't (FR-016–FR-018)

**Decision** (server-side, per the verified surface inventory):
- **`workspace_timeline.py`** gains `components()` (snapshot list + Newer/Older + Back-to-live
  buttons on existing vocabulary) — required because the `timeline` top-bar control natives must
  now render (R6) would otherwise open a placeholder. Its `_view`/`_live` handlers (which push
  their own output) become device-aware. Natives honor `workspace_timeline_mode` by disabling
  mutating affordances while viewing history (FR-007).
- **`pulse.py`** gains `components()` (digest cards already exist as primitives via
  `build_digest`; flag-off state is a notice Alert) — same reason, when `FF_PULSE_DIGEST` is on.
- **`attachments.py`** gains `components()` (upload rows + Attach/Delete buttons + empty state)
  — required by US4: both native composers get the web paperclip's "Choose from your files"
  entry (`chrome_open {surface:"attachments"}`). "Attach" is the client-local action
  `attach_existing {attachment_id, filename, category}` (the SDUI twin of the web's
  `astral-attach-existing` handling): each client intercepts it to stage a chip locally, no
  server round-trip. Delete keeps the existing `chrome_attachment_delete` handler.
- **`drafts.py` stays as-is** — verified reachable from **no** client's menu (web included);
  draft decisions already arrive as in-chat cards whose buttons round-trip on all three
  clients. Recorded in the matrix as equal-reachability, not a gap.
- **`agents.py` / `audit.py` stay native-equivalent screens** (the deliberate 042/043
  disposition): the native menu items open the clients' existing native screens, recorded as
  `native equivalent` with a Defect-Register note that converging them onto `components()` is
  deferred with rationale.
- Web-only carve-outs (already server-enforced, verified: native channels get
  `include_admin=False, include_tour=False`) stay; the matrix records each with its degradation.

**Rationale**: FR-018 says every native menu/topbar entry must open something functional;
after R6 the timeline and pulse controls become reachable, so their surfaces must be real.
FR-026's build-to-parity default applies to gaps a user can hit — drafts isn't one.

## R8. Surface delivery resilience (FR-017)

**Decision**: Both native surface hosts implement a **bounded loading state (10 s)** after
`chrome_open`; on expiry they show an inline error with a **Retry** button that re-emits
`chrome_open`. Android's infinite `SkeletonList` branch (`Screens.kt:255-258`) and the
unreachable `SurfacePlaceholder` trio are removed (R16); Windows' host gets the same
timeout+retry. `chrome_close` becomes device-aware server-side (native: `chrome_surface` with
empty `components` — the documented "clear modal" form — instead of the web-only empty-HTML
`chrome_render`). Action submits from surfaces show a brief in-flight state until the re-pushed
`chrome_surface` (verified: tuple-returning handlers already re-render device-aware, with the
notice as a leading Alert — so success/failure feedback needs **zero** new server work beyond
R2's device-aware error paths) or the 10 s bound trips.

**Rationale**: The server re-push already provides the feedback loop natives need; the clients
just never bounded their waits. Verified `_render_surface` re-runs the device-aware path on
handler return.

## R9. Theme live-restyle (FR-019, US5)

**Decision**: One token contract, three appliers. The seven verified channels
(`bg, surface, primary, secondary, text, muted, accent`) with three source events: boot
`user_preferences.preferences.theme`, surface-apply `theme_apply` component (in the re-pushed
surface), fine-tune `save_theme` ui_event (persisting server-side, already implemented).
- **Windows**: `theme.py` refactors from module constants to a mutable `Palette` whose values
  feed a `build_stylesheet(palette)`; applying a theme mutates the palette, re-sets
  `app.setStyleSheet`, re-renders the canvas from its retained component dicts, and restyles
  chrome widgets via a repolish pass. Transcript bubbles and other construction-baked styles
  that cannot repaint in place are re-created where cheap; anything that only restyles on next
  render is **disclosed on the Theme surface** (FR-019's disclosure clause) rather than left
  silent.
- **Android**: `UiState` gains a `themePalette`; `AstralTheme` derives its `ColorScheme` from it
  (static defaults when unset) at the single `MaterialTheme` call site (`Theme.kt:56`); Compose
  recomposition restyles everything live — no disclosure needed.
- Both natives also handle the `user_preferences` frame (currently ignored by both) so the
  persisted preset survives restart (US5 acceptance 1), and both make `color_picker`
  interactive (native color dialog → `save_theme {theme:{color_key,color_value}}`), replacing
  the read-only swatches — matching the web's fine-tune behavior.

**Rationale**: The server side is verified complete (persist + re-push + boot push); both
no-ops are purely client-side. Compose makes Android trivial; Qt's construction-baked styles
make Windows the honest-disclosure case the spec anticipated.

**Alternatives**: restyling Windows via per-widget dynamic properties + full repolish only —
rejected as insufficient: inline f-string QSS with baked hex values (verified pervasive) never
re-reads tokens; the stylesheet must be regenerated and component views re-rendered.

## R10. Windows attachments (FR-020, FR-021, US4)

**Decision**: Mirror Android's verified flow. `rest.py` gains a stdlib multipart
`upload_attachment(http_base, token, filename, mime, bytes) → {attachment_id, filename,
category, parser_status}` (POST `/api/upload`; urllib, no new dependency — Android's
`AstralRest.uploadAttachment` is the reference). The composer row gains a paperclip button
(menu: *Upload files…* → multi-select `QFileDialog` (≤10) / *Choose from your files* →
`chrome_open attachments`) and a chips strip above the input: per-chip filename +
parser-status glyph (ready / preparing / pending admin approval / unavailable — the REST
response's `parser_status` vocabulary, presented with the same escalation story as
web/Android) + remove. Send maps ready chips into the already-supported
`send_chat(attachments=…)` payload (verified dead param, `protocol.py:124-131`). Chat reload
renders per-turn attachment chips in the rail from `load_chat`'s transcript data, matching
Android. Staged-but-unsent uploads are simply orphaned rows (identical to web/Android
behavior; edge case documented).

## R11. Table pagination on both natives (FR-011)

**Decision**: Implement the verified existing contract — no wire change. A native table
renders a pager when `total_rows`+`page_size` are present and the component carries a
`component_id`: `‹ Prev / rows X–Y of Z / Next ›` (page-size selector optional, from
`page_sizes`). Interaction emits
`ui_event {action:"table_paginate", payload:{component_id, chat_id, params:{page_offset, page_size}}}`;
the reply is a `ui_upsert` op keyed to the same `component_id` (both clients already apply
upserts in place). Provenance stays server-resolved (the 028 path) — natives never echo
`source_*`. Windows keeps its fixed-height table; Android's all-rows Column becomes bounded by
the page.

## R12. Canvas convergence (FR-013)

**Decision**: Write the canonical canvas-semantics contract from the web baseline + verified
send sites, then make all three clients implement it: `ui_upsert` = authoritative keyed
merge/remove; `ui_render target=canvas` = full-canvas replace **reconciled by component
identity** (replace the set, morph matching ids in place); `ui_stream_data` = keyed frame
update with sequence protection (Android's `seqState` pattern ported to Windows'
`streaming.py` if absent); `chat_status done` = turn commit. Client fixes: Android's
out-of-turn wholesale replace (`AppViewModel.kt:446`) and Windows' unconditional
`Canvas.set_components` (app.py:232 full rebuild) both move to identity-reconciled
application. **Server guarantee (full-stack)**: a backend regression test asserts canvas-target
`ui_render`s always carry the full materialized canvas (the 029 designer contract) — if live
verification finds a send site that omits identified live components, the fix lands server-side
rather than teaching clients to guess. The known clobber sequence becomes a scripted
convergence scenario replayed on all three clients (US2.5).

**Rationale**: KNOWN-ISSUES' own fix direction ("reconcile by component identity rather than
wholesale replace") matches the web DOM-morph behavior; pinning the server's full-canvas
guarantee closes the ambiguity that made clients guess.

## R13. Progress-signal parity (FR-006)

**Decision**: Native handling for the verified progress vocabulary: `user_message_acked`
(Windows adds; Android has), `chat_step` (both: step-trail line under the status),
`tool_progress` (both: transient progress line), `task_started`/`task_completed` (both:
async-handoff notice + completion toast + turn state), full `chat_status` vocabulary including
`processing_async`, and the newly-catalogued `notification` frame (toast). `heartbeat`,
`rote_config`, `system_config`, component-verb acks, `llm_usage_report`, `audit_append`,
`agent_creation_progress`, `stream_list` are **classified deliberate-ignore (logged)** on
natives in the manifest/matrix unless a client already surfaces them. Every turn resolves to a
terminal visible state on error/disconnect (ties into R2/R3).

## R14. History consistency (FR-007)

**Decision**: Windows stops dropping `ui_render target=history` (app.py:1187-1188): the frame
routes to its history view; `load_chat` re-hydration (transcript + components) is verified on
all three clients as a scripted scenario. Read-only history/timeline state disables mutating
affordances on natives (R7's `workspace_timeline_mode` handling).

## R15. Screenshot/tofu diagnosis & the verification bundle (FR-022, SC-007, SC-010)

**Decision**: The code evidence points to a **capture-environment font failure**, not a client
defect: `tests/screenshot.py` forces `QT_QPA_PLATFORM=offscreen` and `QWidget.grab()`; nothing
bundles or registers a font (`AstralBody.spec` `datas=[]`); in a font-less offscreen
environment `QFontDatabase` resolves no usable family and every glyph paints as tofu. Per the
clarification we still verify **both** hypotheses live: (1) run the real app windowed on the
dev machine (fonts must render — client exonerated), (2) reproduce the offscreen capture and
confirm tofu appears only there. Fixes: the capture harness runs on the **default Windows
platform** (real window, `grab()`), gains a **font sanity gate** (fail loudly if
`QFontDatabase` yields no requested family instead of emitting tofu evidence), and the
verification procedure documents the requirement. Android captures via
`adb exec-out screencap -p` on the emulator; web via the browser. The bundle lives at
`specs/044-native-client-parity/verification/` — parity matrix (final dispositions + evidence
links), per-client legible screenshots of the canonical gallery + key journeys, per-scenario
results, and a regeneration procedure (quickstart) runnable from a clean checkout. The
canonical **35-type gallery** is pushed by a small backend driver script through the real WS
path so all three clients render identical server output. Docker and the Android emulator are
already running on the dev machine — live verification is unblocked.

## R16. Docs truth & dead code (FR-024)

**Decision** (reconciliation list, all verified):
- `CLAUDE.md`: Windows client is **PySide6/Qt Widgets** (tkinter excluded in
  `AstralBody.spec:26`) — fix the Project Structure line.
- 041 spec header `Status: Draft` → shipped; 042 `tasks.md` all-unchecked → reconcile to
  shipped reality (evidence links); 043 open tasks (T015, T025/T026, US2 T027–T033, US3
  T034–T038, polish) → completed by this feature's work or explicitly re-homed to 044 tasks
  with cross-references; commit-or-regenerate the untracked verification captures.
- Client READMEs + KNOWN-ISSUES: update to post-044 reality (Android README's DevAuth claim
  removed).
- Dead code removed: Android `DevAuth` (both build variants, zero references),
  `Screen.SurfacePlaceholder` + `SurfacePlaceholderScreen` + `pendingSurfaceLabel`
  (unreachable), unused `navigation-compose` dependency (a removal, not an addition), dangling
  `proguard-rules.pro` reference resolved (add the file or drop the reference); Windows
  `Launch-AstralBody.bat` hardcodes → `if not defined` env guards so operator overrides win.
- `connectionLabel()` is *revived* by R6 rather than deleted.

## R17. CI additions (FR-023, SC-009)

**Decision**: (a) New **windows-client job** in `ci.yml` (none exists today — verified):
ubuntu runner, `pip install -r windows-client/requirements.txt`, run the headless-safe pytest
suite (`QT_QPA_PLATFORM=offscreen` — logic/registry tests don't assert glyph rendering, so the
font caveat doesn't apply); it carries the new protocol-coverage + manifest drift guards.
(b) Backend manifest tests ride the existing `test` job. (c) Android guards ride
`android-ci.yml`'s existing per-PR `:core:test`/`:app:testDebugUnitTest`. (d) `:app` unit
coverage remains ungated (only `:core:koverVerify` gates today) — recorded in the Defect
Register as a deferred CI improvement with rationale (the Principle III diff-cover gate is
Python-scoped; Kotlin gating is a pre-existing project-wide posture, not a 044 regression).
CI-only tooling additions: none beyond what the runners already provide (PySide6 install in
the new job is the product's own client dependency set, not a new tool).

## R18. Dependencies & schema summary (Constitution V, IX)

**Decision**: **Zero new third-party runtime dependencies** on any of the three targets (one
dependency *removal* on Android). No astralprims change (pager, `attach_existing`, error
banners are client-side or plain Buttons). Schema delta: exactly one additive nullable column
`auth_revocation_queue.client_id TEXT` via idempotent guarded `_init_db` (rollback: drop
column; NULL-compatible with all existing rows and code paths). Wire deltas are all additive:
`POST /api/auth/logout`, the `error{code:"internal"}` emission, device-aware
`chrome_surface` error/close frames, and new `components()` payloads for three surfaces —
every existing client keeps working untouched.
