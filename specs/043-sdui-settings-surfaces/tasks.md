# Tasks: Native SDUI Settings Surfaces

**Input**: Design documents from `specs/043-sdui-settings-surfaces/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/chrome-surface.md

**Tests**: REQUIRED by this feature (spec FR-018/FR-019, Constitution III/X/XI). Test tasks accompany their implementation and a surface is done only when exercised on **every** affected client (web + Windows + Android).

**Organization**: Grouped by user story (US1 render, US2 actions, US3 theme) for independent implementation, testing, and delivery. `[P]` = parallelizable (distinct files, no ordering dependency). `[USx]` = owning story. Surfaces are delivered **one at a time, simplest first** (guide → theme → llm → personalization); a surface's US1 + US2 slices ship and are verified together before the next surface. Per clarification, **Take the tour is removed from the native clients** (not ported) — a small menu-model change omits it from the native channels.

## Context (builds on feature 042)

Feature 042 delivered the server-owned menu to native clients (`chrome_menu`) and left five items opening a *"coming soon"* placeholder (Windows `app.py:924-941` `QMessageBox`; Android `AppViewModel.kt:317-328` → `SurfacePlaceholderScreen`). Per clarification, **Take the tour is removed from the native clients** (its `tour` item is omitted from the native menu channels — web-only, like admin tools); the **four** ported surfaces are **guide, theme, llm, personalization**. The chrome surfaces are HTML-first (`webrender/chrome/__init__.py:1-14`); only `theme.py` emits primitives. `astralprims` has one action-carrying primitive (`Button`); no savable `Select`/`Toggle`/action-bound input. 043 adds the `chrome_surface` delivery frame + a `components()` path per surface + native surface hosts + a minimal interactive-vocabulary extension (`ParamPicker` action-submit; `color_picker`/`theme_apply` native renderers), reusing every existing `chrome_*` handler unchanged.

## Path conventions

- Backend: `backend/shared/protocol.py`, `backend/orchestrator/chrome_events.py`, `backend/webrender/chrome/surfaces/`, `backend/webrender/renderer.py`, `backend/webrender/static/client.js`, `backend/rote/`, per-module `tests/`.
- astralprims: first-party package (Astral-Primitives repo, consumed as a wheel); additive `ParamPicker` change, version-gated.
- Windows: `windows-client/astral_client/{renderer.py,chrome.py,app.py,theme.py}`, `windows-client/tests/`.
- Android: `android-client/core/...` (`:core`, pure Kotlin, Kover ≥90%), `android-client/app/...` (`:app`, Compose, thin).

---

## Phase 1: Setup

- [x] T001 Add a `ChromeSurface` dataclass scaffold to `backend/shared/protocol.py` (fields `region, surface_key, title, admin_only, components, mode`; `to_json()`), beside `ChromeRender`/`ChromeMenu`. No delivery wiring yet.
- [x] T002 [P] Create `backend/webrender/chrome/surfaces/_sdui.py` scaffold (module docstring + empty helper signatures: `surface(...)`, `form(...)`, `button(...)`, `notice_alert(...)`, `placeholder(...)`).
- [x] T003 [P] Create backend test skeletons `backend/orchestrator/tests/test_chrome_surface.py` and `backend/webrender/chrome/tests/test_surface_components.py` (import targets, no assertions yet).
- [ ] T004 [P] Android `:core` scaffold: add `Inbound.ChromeSurface(...)` to `core/protocol/Messages.kt` + a `Wire.decode` case scaffold in `core/protocol/Wire.kt` + `core/src/test/.../protocol/ChromeSurfaceDecodeTest.kt` skeleton.
- [ ] T005 [P] Windows scaffold: a `render_surface_modal(...)` stub in `windows-client/astral_client/chrome.py` + `windows-client/tests/test_surface_host.py` skeleton.

---

## Phase 2: Foundational (BLOCKS all user stories) ⚠️

**Purpose**: the `chrome_surface` delivery path + native surface hosts + the interactive-vocabulary foundation. Until this exists, no surface can render natively.

### Backend delivery
- [x] T006 Complete `ChromeSurface` in `backend/shared/protocol.py` per `contracts/chrome-surface.md §2` (+ tolerant `to_json`).
- [x] T007 Branch `backend/orchestrator/chrome_events.py::_render_surface` (`:62-89`) on the session device target (`orch.ui_sessions[websocket].device_type`): `browser` → existing `chrome_render` HTML (unchanged); `windows`/`android` → call `mod.components(...)`, ROTE-adapt, push `chrome_surface`. A surface without `components()` → a single labeled placeholder component (`_sdui.placeholder`).
- [x] T008 Branch the handler re-render path (`chrome_events.py:140-165`): on a native session re-render via the `chrome_surface` path with the `notice_html` mapped to a prepended `Alert` component; web unchanged. Preserve the server-side `ADMIN_ONLY` re-check for both paths.
- [x] T009 Implement `backend/webrender/chrome/surfaces/_sdui.py` helpers: `surface(title, [components])`; `form(fields, submit_action, submit_payload, submit_label)` → a `ParamPicker` action-submit dict; `button(label, action, payload, variant)`; `notice_alert(kind, text)`; `placeholder(label)`. Emit plain `astralprims` `.to_dict()` shapes.
- [ ] T010 astralprims `ParamPicker` **action-submit** extension (`submit_action`/`submit_payload` + `password`/`textarea` field kinds) per `data-model.md`; make `backend/webrender/renderer.py` render the action-submit variant and `backend/webrender/static/client.js` post `ui_event{action, payload:{fields}}` on submit (web parity — **no visual change**). Backward-compatible (no `submit_action` ⇒ existing chat-message submit).
- [ ] T011 Confirm `backend/webrender/renderer.py` renders `color_picker`/`theme_apply` (already registered `:1111-1112`); `allowed_primitive_types()` set unchanged. Document the extended `param_picker` + the two theming primitives in the renderer docs (Constitution VI/VIII).
- [x] T012 [P] Backend tests `test_chrome_surface.py`: `chrome_open` on a `windows`/`android` session → `chrome_surface` with valid `astralprims` dicts; `browser` session → `chrome_render` HTML; unconverted surface → placeholder component; non-admin `admin_tools` open on a native session refused + audited; a `ParamPicker` action-submit round-trips to `payload.fields`.

### Native hosts
- [x] T013 Windows `renderer.py`: add `color_picker` + `theme_apply` builders; honor the `ParamPicker` action-submit (submit → `ctx.emit(submit_action, {fields, …})`); expose a `render_components(list) -> QWidget` entry for the modal host.
- [x] T014 Windows `chrome.py` + `app.py`: implement the surface host (`render_surface_modal` builds a modal from `chrome_surface.components` via `renderer.render_components`); route the four ported surfaces in `_open_surface` (`app.py:924-941`) to emit `chrome_open` + render the returned `chrome_surface` (replace the `QMessageBox` placeholder); consume the `chrome_surface` frame in `_on_message` (`app.py:1090-1145`); retire `chrome_render_notice` (`chrome.py:29-45`).
- [ ] T015 [P] Windows tests `test_surface_host.py`: a `chrome_surface` frame → modal with the expected widgets (incl. an unknown-type `_r_fallback` placeholder); a submit/button → `send_event` with the right action+payload.
- [x] T016 Android `:core`: complete `Inbound.ChromeSurface` + `Wire.decode` mapping; add a reducer case in `:app` `AppViewModel.reduce` storing the decoded surface in `UiState` (twin of `Inbound.ChromeMenu` at `AppViewModel.kt:501`).
- [x] T017 Android `:app`: add a `Screen.Surface` host that renders the held `chrome_surface.components` via the existing `render/Renderer.kt` in a modal/sheet; route `AppViewModel.openMenuItem` (`:317-328`) `else` for the four ported surfaces to it (replace `SurfacePlaceholderScreen`); add `color_picker`/`theme_apply` composables + `ParamPicker` action-submit (`emit.event(submit_action, {fields})`).
- [x] T018 [P] Android `:core`/`:app` tests: `ChromeSurface` decode (unknown-field tolerant); surface-host maps a component list to the renderer; submit/button → `sendEvent` payload. (`:core` logic Kover ≥90%.)

**Checkpoint**: the delivery path works end-to-end on both clients; every one of the five opens a native modal showing a labeled placeholder component (not the old text placeholder). Surface conversions can begin.

---

## Phase 3: User Story 1 — Surfaces render natively (Priority: P1) 🎯 MVP

**Goal**: each of the five items opens a working native surface with the same content/controls as the web; no "coming soon" placeholder, no web view.

**Independent Test**: open each of the five on Windows + Android; the surface renders natively (screenshot vs. web).

*(Order = simplest first. `components()` uses only types in `allowed_primitive_types()` + the extended `param_picker`; web `render()` unchanged, or delegates to `components()` only where HTML is byte-identical — D6.)*

- [x] T019 [P] [US1] `surfaces/guide.py::components()` — TOC as `Button`s (`chrome_open` w/ `section`) + the selected section's article as `Text`/`Card`; reuse `_visible_sections(roles)` (`guide.py:29-39`). Port the 16 `guide_content.py` articles to SDUI text blocks. Web unchanged.
- [x] T020 [P] [US1] `surfaces/theme.py::components()` — 5 preset `Card`/`Button`s (`chrome_theme_preset`) with swatch rows + 7 `color_picker`s (fine-tune). Reuse `PRESETS`/`_stored_theme`. Web `render()` unchanged (`components()` native-only).
- [x] T021 [P] [US1] **Remove "Take the tour" from the native menu channels** — mark the `tour` item web-only in `backend/webrender/chrome/menu_model.py` so the `chrome_menu` WS frame (`orchestrator.py:1161-1180`) + `GET /api/chrome/menu` (`api.py:1504-1519`) omit it (mirror `include_admin=False`); the web menu + `tour.py` surface stay unchanged. No native tour surface is built (per clarification).
- [x] T022 [US1] `surfaces/llm.py::components()` — one `ParamPicker` action-submit form (base_url `text`, api_key `password` write-only, model `text`/`select` when `params["models"]`) + action `Button`s (Load models/Test/Save/Clear) + saved/not-configured `Badge`. Reuse `_user_creds`/`_model_field`.
- [x] T023 [US1] `surfaces/personalization.py::components()` — `Tabs` (soul/memory/skills/schedule/dreaming) → per-tab bodies: soul `ParamPicker` (profession/goals `textarea`/notes `textarea`); memory `List_` of per-row edit (`ParamPicker` + `Button`s); skills catalog rows (`Button` toggles, reason text when scope not granted); schedule job `Card`s (`Badge` status + Pause/Resume/Run/Delete `Button`s + run history); dreaming toggle+trigger `Button`s. Reuse every existing data read.
- [x] T024 [P] [US1] Backend tests `test_surface_components.py`: each `components()` returns valid `astralprims` dicts using only allowed types; audience filtering (guide admin section); **no `render()` HTML change** (snapshot before/after — all four keep their web HTML); the native menu omits `tour` while the web menu keeps it.
- [ ] T025 [P] [US1] Client render tests: Windows `test_surface_host.py` + Android surface-host test render each surface's `components()` sample into widgets/composables (no live backend).
- [ ] T026 [US1] Live: open all five on web (unchanged), Windows (launched), Android (emulator) — each renders natively, no placeholder; screenshot per surface per client for the parity comparison (SC-002).

**Checkpoint**: US1 shippable — all five render natively on both clients; zero placeholders, zero web views (SC-001).

---

## Phase 4: User Story 2 — Surface actions take effect natively (Priority: P1)

**Goal**: each surface's controls actually persist/apply via the same server actions + audit as the web.

**Independent Test**: perform each surface's primary action on each native client; it takes effect and is reflected/audited as on the web.

*(Handlers are reused unchanged — `collect_handlers()`; US2 wires + verifies each surface's round-trip and the native re-render-with-`Alert`.)*

- [ ] T027 [P] [US2] Theme: preset `Button` → `chrome_theme_preset` persists to `user_preferences` and the re-render reflects the choice; native re-render carries the success `Alert`. (Live restyle is US3.)
- [ ] T028 [P] [US2] Verify **"Take the tour" is absent** from the native menu on Windows + Android (and present + unchanged on the web) — the documented parity exception (spec FR-009). No native tour action exists.
- [ ] T029 [US2] LLM: `chrome_llm_models`/`_test`/`_save`/`_clear` round-trip from the native form; the `ParamPicker` `fields` shape matches `_fields` (`llm.py:60-78`); api-key write-only (blank keeps); Save then re-open reflects base_url/model; Test shows latency/error `Alert`.
- [ ] T030 [US2] Personalization: profile save (PHI-gated), memory update/delete, skill toggle (scope-bounded — denied when scope not granted), job pause/resume/run_now/delete, dreaming toggle/trigger — each persists and the re-rendered tab reflects it with a notice `Alert`.
- [ ] T031 [P] [US2] Backend tests: each surface's emitted actions resolve to their existing handler; the `ParamPicker` action-submit `payload.fields` is accepted by `chrome_llm_save`/`chrome_profile_save`/`chrome_memory_update`; PHI/scope gates + audit rows fire identically to the web (no native bypass).
- [ ] T032 [P] [US2] Client tests: Windows + Android — each surface's button/submit emits the correct `ui_event{action, payload}` (fake transport); a returned `chrome_surface` re-render replaces the modal with the notice `Alert`.
- [ ] T033 [US2] Live: perform each surface's primary action (quickstart §5) on Windows + Android; confirm effect + `Alert` + reflected on re-open, matching the web.

**Checkpoint**: US2 shippable — every surface's actions work natively through the same gates/audit as the web (SC-003).

---

## Phase 5: User Story 3 — Theme restyles the native app (Priority: P2)

**Goal**: choosing a preset natively updates the client's own colors live; other clients honor the saved preset on next load.

**Independent Test**: pick a preset on a native client → its colors update live; open another client → it loads with the preset from first paint.

- [ ] T034 [US3] Backend: include the user's active theme (7 channels from `PRESETS`) in the register bootstrap, and have `chrome_theme_preset` ship the chosen preset's channels to native (a `theme_apply`-style side-effect payload) alongside the re-render.
- [ ] T035 [US3] Windows `theme.py`: make the palette tokens a runtime object driven by the active preset's channels; re-apply `APP_STYLESHEET`/`ROOT_BG_STYLE` on preset change (`app.py:1454-1466`); theme correctly on connect.
- [ ] T036 [US3] Android `ui/theme/Theme.kt`: `AstralTheme` takes a dynamic `ColorScheme` from the VM-held preset (replace fixed `AstralDarkColors`); recompose live on preset change; theme on connect.
- [ ] T037 [P] [US3] Tests: preset persistence + channel delivery; Windows palette rebuild from channels; Android `ColorScheme` mapping; theme-on-connect from the bootstrap.
- [ ] T038 [US3] Live: pick a preset on one native client → restyles live; open a second client → opens with the preset (SC-004), verified across web + Windows + Android.

---

## Phase 6: Polish & Verification (cross-cutting)

- [ ] T039 [P] Update `CLAUDE.md` (manual-additions section) + `docs/` with the `chrome_surface` frame, the `components()` surface contract, and the `ParamPicker` action-submit extension.
- [ ] T040 [P] Cross-reference `specs/042-cross-client-chrome-parity/tasks.md` — mark its deferred Phase-5 (US3) surface tasks delivered by feature 043.
- [ ] T041 astralprims: publish the `ParamPicker` action-submit extension (version-gated, push main) + document the primitive change; adjust `requirements.txt` floor if the wheel is required in-image (else the orchestrator keeps emitting the dict — feature-029 precedent).
- [ ] T042 Run `quickstart.md` end-to-end: backend up; web screenshots (confirm **unchanged**, SC-006); Windows launch + per-surface screenshots; Android build + emulator per-surface screenshots (or JVM tests + CI instrumented); side-by-side parity (SC-001..SC-007).
- [ ] T043 Coverage: backend changed-line ≥90% (diff-cover) — add tests where short; Android `:core:koverVerify` ≥90%; ktlint + Android Lint clean; `:app:assembleDebug` green; ruff clean.
- [ ] T044 Push branch, open PR; drive `CI` + `android-ci` green; trigger the Android `instrumented` job via `workflow_dispatch`; confirm the Windows release workflow builds on `workflow_dispatch`.

---

## Dependencies & Execution Order

- **Phase 1 Setup** → **Phase 2 Foundational** (delivery frame + native hosts + `ParamPicker` action-submit + `color_picker`/`theme_apply`) BLOCKS everything.
- **US1 (Phase 3)** depends on Foundational. Within US1, `guide`/`theme` (T019–T020) use only existing vocab and are mutually `[P]`; the tour-removal menu edit (T021) is an independent `[P]` change; `llm`/`personalization` (T022–T023) additionally depend on the `ParamPicker` action-submit foundation (T010/T013/T017).
- **US2 (Phase 4)** depends on US1 per surface (a surface must render before its actions are wired/verified). Handlers themselves are unchanged, so US2 is mostly round-trip wiring + verification + the native re-render-with-`Alert`.
- **US3 (Phase 5)** depends on the Theme surface (US1/US2 for `theme`) + is native theming work; independent of the other surfaces.
- **Phase 6** last.

### Within a surface
`components()` (render) → action round-trip (wire) → live verification on **every** affected client (web + Windows + Android) before the surface is declared done (Constitution X/XII), with its CI gates green.

### Parallel opportunities
- Foundational: `[P]` tests (T012/T015/T018) alongside impl; Windows (T013–T015) and Android (T016–T018) host tracks are independent.
- US1: `guide`/`theme` `components()` (T019–T020) + the tour-removal menu edit (T021) are `[P]`; `llm`/`personalization` (T022–T023) are larger and serialized after the vocab foundation.
- US2: per-surface action tasks are `[P]` across surfaces once each has rendered.

## Implementation Strategy

1. **Foundational first** — the `chrome_surface` path + native hosts + the interactive-vocabulary extension. Nothing renders natively without it; ship it with every surface showing a labeled placeholder component.
2. **Surface-by-surface, simplest first** — take each surface through US1 (render) + US2 (actions) **together**, ship it, and **verify it on web + Windows + Android** before starting the next: guide → theme → llm → personalization. Each replaces its placeholder as it lands (SC-001 grows monotonically). "Take the tour" is removed from the native menu (T021), not ported.
3. **US3 (P2) theme apply** — after the Theme surface renders + saves, make the native palettes dynamic so a preset restyles live across clients.
4. Keep every CI gate green throughout; the web presentation of every surface stays unchanged (SC-006).
