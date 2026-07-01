# Tasks: Cross-Client Chrome & Settings Parity

**Input**: Design documents from `specs/042-cross-client-chrome-parity/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/chrome-menu.md

**Tests**: REQUIRED by this feature (spec FR-022/FR-023, Constitution III/XI). Test tasks are included and precede/accompany their implementation.

**Organization**: Grouped by user story (US1–US4) for independent implementation, testing, and delivery. `[P]` = parallelizable (distinct files, no ordering dependency). `[USx]` = owning story.

## Path conventions

- Backend: `backend/webrender/chrome/`, `backend/orchestrator/`, `backend/rote/`, per-module `tests/`.
- Android: `android-client/core/...` (`:core`, pure Kotlin, Kover ≥90%), `android-client/app/...` (`:app`, Compose, thin).
- Windows: `windows-client/astral_client/`.

---

## Phase 1: Setup

- [ ] T001 Create `backend/webrender/chrome/menu_model.py` scaffold (module docstring, dataclasses `ChromeModel/TopBarControl/MenuGroup/MenuItem/SignOutItem`, `to_dict()`), no logic yet.
- [ ] T002 [P] Create test files: `backend/webrender/tests/test_menu_model.py`, `backend/orchestrator/tests/test_chrome_menu.py` (empty skeletons that import the targets).
- [ ] T003 [P] Create Android `:core` package `com/kyopenscience/astral/core/chrome/` with `ChromeMenu.kt` scaffold + `android-client/core/src/test/kotlin/.../chrome/ChromeMenuTest.kt`.

---

## Phase 2: Foundational (BLOCKS all user stories) ⚠️

**Purpose**: the single server-owned menu model + its delivery + the web consuming it. Nothing renders on native clients until the model exists and is served.

- [ ] T004 [US1] Implement `build_menu_model(roles, *, pulse_enabled)` in `menu_model.py` — canonical top-bar controls + ACCOUNT/HELP/ADMIN groups + items + SignOut, role-filtered + flag-resolved, matching the exact labels/order in `contracts/chrome-menu.md`. Reuse the existing tuples from `topbar._menu_entries` as the seed so there is exactly one definition.
- [ ] T005 [US1] Implement `ChromeModel.to_dict()` serialization (version=1) per data-model.md.
- [ ] T006 [US1] Refactor `backend/webrender/chrome/topbar.py` so `render_topbar`/`_menu_html`/top-bar icons render **from** `build_menu_model(...)` (no second menu definition; **no visual change** to the web). Keep `_pulse_button`/timeline/gear markup but drive presence/labels/order/payloads from the model.
- [ ] T007 [US1] Add `GET /api/chrome/menu` (role-aware, Bearer-JWT) in `backend/orchestrator/api.py` returning `build_menu_model(session_roles).to_dict()`.
- [ ] T008 [US1] Emit the `chrome_menu` WS frame after `register_ui` ack (and re-emit on role/flag change) in the orchestrator register path (`async_tasks.py`/`orchestrator.py`), role-filtered per socket.
- [ ] T009 [P] [US1] Unit tests `test_menu_model.py`: exact order/labels; admin vs non-admin filtering; Pulse present iff `FF_PULSE_DIGEST`; every `MenuItem.surface` ∈ `SURFACE_MODULES`.
- [ ] T010 [P] [US1] Integration tests `test_chrome_menu.py`: REST body == WS-frame model for the same session; 401 unauth; non-admin never receives `admin` group; web `render_topbar` derives from the same builder (no divergence).
- [ ] T011 [US1] Android `:core` `ChromeMenu.kt`: kotlinx.serialization data classes + `decode(json)` + helpers (`topbar order`, `groups`, `signout`); tolerant of unknown fields.
- [ ] T012 [P] [US1] `ChromeMenuTest.kt` (`:core`, JVM): decode the contract sample; assert order/labels/gating; unknown-field tolerance. (Kover ≥90% on `:core` chrome logic.)

**Checkpoint**: model exists, is served (REST + WS), web renders from it, `:core` can decode it. User-story work can begin.

---

## Phase 3: User Story 1 — One consistent menu everywhere (Priority: P1) 🎯 MVP

**Goal**: web/Windows/Android render the identical top bar + Settings dropdown from the model; Android duplication removed; real sign-out.

**Independent Test**: open all three; menus match; Android shows each destination once; Sign out ends the session.

### Android
- [ ] T013 [US1] `:app` — replace `RootScaffold.AstralTopBar`/`HamburgerMenu` with a top bar (brand · status · [pulse] · timeline · gear) + a Settings dropdown built from the injected `ChromeMenu` model (order/labels/groups verbatim); gear toggles the dropdown.
- [ ] T014 [US1] `:app` — DELETE the duplicated Settings screen ACCOUNT links (`Screens.kt` `SettingsScreen` Agents/Audit rows); route menu items to their destinations via the model's `surface` (existing native screens for agents/audit/history/timeline; placeholder for not-yet-SDUI).
- [ ] T015 [US1] `:app`/`AppViewModel` — consume the `chrome_menu` frame (store model in `UiState`); render menu reactively; `signOut()` calls the server logout then returns to `SignInScreen`.
- [ ] T016 [P] [US1] `:app` test `RootChromeTest`/`DeviceCapsTest` extension — menu maps to the model (order, groups, no duplicates), sign-out triggers the logout path (fake transport).

### Windows
- [ ] T017 [US1] `windows-client/astral_client/app.py` — replace the flat `TopBar` button row with brand · status · [pulse] · timeline(icon) · gear; the gear opens a grouped popup (`QMenu`/framed popup) built from the model (fetched via `GET /api/chrome/menu` and/or the `chrome_menu` frame in `protocol.py`).
- [ ] T018 [US1] `app.py` — move Agents/Audit into the popup (open the existing `AgentsDialog`/`AuditDialog`); History/Timeline + placeholder for not-yet-SDUI; **Sign out red at the bottom**; `_sign_out` calls the server logout then returns to sign-in.
- [ ] T019 [US1] `windows-client/astral_client/chrome.py`/`protocol.py` — parse + hold the menu model; helper to build the popup from it (single source; no hard-coded menu).
- [ ] T020 [P] [US1] Windows test (pytest under `windows-client/tests/`) — menu builder maps the model to popup entries in order with correct gating; sign-out invokes logout.

**Checkpoint**: US1 shippable — identical, de-duplicated menu on all three clients + real sign-out.

---

## Phase 4: User Story 2 — Only admins see admin tools (Priority: P1)

**Goal**: ADMIN TOOLS group appears only for admins on every client; non-admins can't open admin surfaces.

**Independent Test**: admin vs non-admin token → group present/absent on all three; non-admin admin-surface open refused + audited.

- [ ] T021 [US2] Confirm/annotate server-side gate: `chrome_events._render_surface` refuses `ADMIN_ONLY` surfaces for non-admins for BOTH `chrome_render` (web) and `chrome_surface` (native) paths; audit `settings.admin_tools.denied`.
- [ ] T022 [P] [US2] Backend test — non-admin `chrome_open{surface:"admin_tools"}` over a native-target session is refused + audited (extends `test_chrome_menu.py`).
- [ ] T023 [P] [US2] Android `:core` test — a non-admin model has no `admin` group; `:app` never renders admin items.
- [ ] T024 [P] [US2] Windows test — non-admin popup omits ADMIN TOOLS.

**Checkpoint**: role-gating verified on all three clients + server-enforced.

---

## Phase 5: User Story 3 — Settings open as native SDUI surfaces (Priority: P2)

**Goal**: every settings item opens a working native surface via SDUI; no web view, no whole-surface placeholder.

**Independent Test**: open each item on Windows + Android; surface renders natively and performs its core action.

### Backend delivery
- [ ] T025 [US3] `webrender/chrome/surfaces/_sdui.py` — helpers to compose astralprims component surfaces + bind actions to the existing `chrome_*` keys.
- [ ] T026 [US3] `orchestrator/chrome_events.py` — branch surface delivery on device target: web → `chrome_render` (HTML), native SDUI → `chrome_surface` (ROTE-adapted `components()`); not-yet-converted surface → labeled placeholder component on native.
- [ ] T027 [P] [US3] Backend test — `chrome_open` on a `windows`/`android` session returns a `chrome_surface` frame with valid components; web session still returns HTML.

### Surface conversions (ascending complexity; each independently shippable)
- [ ] T028 [P] [US3] `surfaces/theme.py` — add `components()` (5 presets + 7 color pickers); web modal renders from it too (single source).
- [ ] T029 [P] [US3] `surfaces/guide.py` — `components()` (sectioned text).
- [ ] T030 [P] [US3] `surfaces/audit.py` — `components()` (filter controls + table + pagination via `chrome_audit_page`).
- [ ] T031 [P] [US3] `surfaces/llm.py` — `components()` (models list + test/save/clear actions).
- [ ] T032 [US3] `surfaces/personalization.py` — `components()` (profile/memory/skills/jobs/dreaming; larger).
- [ ] T033 [US3] `surfaces/agents.py` — `components()` (agent rows, per-scope toggles, visibility/safe, credentials; largest).
- [ ] T034 [P] [US3] `surfaces/tour.py` — `components()` (or keep client-run tour with an SDUI launcher).
- [ ] T035 [P] [US3] Backend tests per converted surface — `components()` returns valid astralprims dicts; actions map to existing handlers; admin surfaces stay gated.

### Native rendering of surfaces
- [ ] T036 [US3] Android `:app` — render `chrome_surface` components in a modal/sheet via the existing `CanvasHost`/`Renderer`; wire component actions back over `ui_event`; unknown component → labeled placeholder (FR-013).
- [ ] T037 [US3] Windows `astral_client/renderer.py`/`chrome.py` — render `chrome_surface` components in a modal via the existing renderer; wire actions; replace the "not available in the desktop app yet" notice.
- [ ] T038 [P] [US3] Android `:core`/`:app` tests — component→native mapping for surface content; action round-trip (fake transport).
- [ ] T039 [P] [US3] Windows tests — surface render maps components to widgets; action round-trip.

**Checkpoint**: all non-admin surfaces render natively on both clients.

---

## Phase 6: User Story 4 — Theme, Timeline, Pulse parity (Priority: P3)

**Goal**: theme presets apply+persist across clients; Timeline opens everywhere; flag-gated Pulse appears uniformly.

**Independent Test**: change a preset on one client, honored on others; Timeline on each; toggle Pulse flag → control appears/disappears on all.

- [ ] T040 [US4] Backend — include the user's active theme (7 channels) in the register bootstrap + a `theme_apply` side-effect on preset change; ensure `chrome_theme_preset` persists to `user_preferences.theme`.
- [ ] T041 [US4] Android `:app` — map theme channels to the Compose color scheme (replace fixed `AstralColors`); apply live on `theme_apply`; theme on connect.
- [ ] T042 [US4] Windows `astral_client/theme.py` — build a Qt palette from theme channels (add a light path); apply live; theme on connect.
- [ ] T043 [US4] Admin surfaces `admin_tools.py` — `components()` for Tool quality + Tutorial admin (SDUI), gated; native render.
- [ ] T044 [US4] Native top bars — render the flag-gated Pulse control from the model (`pulse` present iff `FF_PULSE_DIGEST`); opens the `pulse` surface (SDUI).
- [ ] T045 [P] [US4] Tests — theme persistence + cross-client apply; Pulse presence toggles with the flag; Timeline opens on native.

---

## Phase 7: Polish & Verification (cross-cutting)

- [ ] T046 [P] Update `CLAUDE.md` (agent context) + `docs/` with the menu-model + SDUI-surface architecture.
- [ ] T047 [P] `specs/041` cross-reference: mark the LLM/personalization/theme/etc. "roadmap" surfaces delivered by 042.
- [ ] T048 Run `quickstart.md` end-to-end: backend up; web screenshot; Windows launch+screenshot; Android build + emulator screenshot (or JVM tests + CI instrumented); side-by-side parity check (SC-001..SC-007).
- [ ] T049 Backend coverage: ensure changed-line ≥90% (diff-cover) — add tests where short.
- [ ] T050 Android coverage: `:core:koverVerify` ≥90%; ktlint + Android Lint clean; `:app:assembleDebug` green.
- [ ] T051 Push branch, open PR; drive `CI` + `android-ci` green; trigger Android `instrumented` job via `workflow_dispatch`; confirm the Windows release workflow builds on `workflow_dispatch`.

---

## Dependencies & Execution Order

- **Phase 1 Setup** → **Phase 2 Foundational** (the model + delivery + web refactor) BLOCKS everything.
- **US1 (Phase 3)** and **US2 (Phase 4)** are both P1 and depend only on Foundational; US2 largely falls out of the role-filtered model.
- **US3 (Phase 5)** depends on Foundational + the native menu (US1) to open surfaces; surface conversions T028–T034 are mutually `[P]`.
- **US4 (Phase 6)** depends on US3 (surface path) for theme/admin/pulse surfaces.
- **Phase 7** last.

### Within a story
Tests accompany implementation; models before delivery; delivery before native rendering; a story is done only when exercised on **every** affected client (Constitution X/XII) and its CI gates pass.

### Parallel opportunities
- Foundational: `[P]` tests T009/T010/T012 alongside impl.
- US1: Android (T013–T016) and Windows (T017–T020) tracks are independent `[P]` once the model is served.
- US3: surface conversions T028–T031/T034 are `[P]`; T032/T033 are larger and serialized.

## Implementation Strategy

1. **Foundational first** (model + delivery + web-from-model) — nothing works cross-client without it.
2. **US1 + US2 (P1)** — the headline consistent, de-duplicated, role-gated menu + real sign-out on all three clients. **Ship/verify.**
3. **US3 (P2)** — SDUI surfaces, converted surface-by-surface, each shippable, replacing placeholders. **Ship/verify per surface.**
4. **US4 (P3)** — theme/timeline/pulse/admin polish. **Ship/verify.**
5. Keep every CI gate green throughout; verify on web + Windows + Android at each checkpoint.
