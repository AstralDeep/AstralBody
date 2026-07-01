# Implementation Plan: Native SDUI Settings Surfaces

**Branch**: `043-sdui-settings-surfaces` | **Date**: 2026-07-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/043-sdui-settings-surfaces/spec.md`

## Summary

Port the settings items that currently open a *"This settings screen is coming to the app soon"* placeholder on the Windows and Android clients so they render as real native screens. Per clarification, **Take the tour is removed from the native clients** (it stays web-only, like the admin surfaces — a web-DOM-anchored walkthrough with no native analog); the **four** surfaces ported are **LLM settings, Personalization, Theme, and User guide**. The mechanism is the one feature 042 designed but deferred: deliver each surface as **server-driven UI** (astralprims components → orchestrator render → ROTE adapt) over a new `chrome_surface` WS frame, and have each native client render it through the **component renderer it already uses for the chat canvas** (Windows `renderer.py`; Android `render/Renderer.kt`). No web view, no per-client hand-built surface.

The current chrome surfaces are **HTML-first** (`webrender/chrome/__init__.py` intentionally builds `esc()`-escaped HTML, not primitives; only `theme.py` emits any primitives today), so the real work is additive on three seams:

1. **Delivery** — a `chrome_surface` frame (`shared/protocol.py`) + a device-target branch in `orchestrator/chrome_events.py::_render_surface` and its re-render path (web → existing `chrome_render` HTML unchanged; native → ROTE-adapted `components()`), plus a `components(orch, user_id, roles, params)` path added to each surface module. The existing `HANDLERS` are transport-agnostic (`fn(orch, ws, user_id, roles, payload)` → persist → `(surface, params, notice)`), so **surface actions are reused unchanged**.
2. **Interactive vocabulary** — `astralprims` today has exactly one action-carrying primitive (`Button`); there is no savable `Select`/`Toggle`/action-bound input. Savable forms/toggles are expressed by reusing `Button` (per-row actions, theme presets) and extending the existing, already-natively-rendered `ParamPicker` with an **action-submit mode** (submit posts `ui_event{action: chrome_*, payload:{fields}}` instead of a chat message), plus native renderers for the existing `color_picker`/`theme_apply` primitives. Minimal `astralprims` churn.
3. **Native hosts** — a settings-surface host on each client that feeds a delivered component list into the existing renderer inside a modal/sheet and **replaces the placeholder branch**, wiring component actions back over the existing `ui_event` path; and (P2) a dynamic theme so a chosen preset restyles the app live.

Delivered **surface-by-surface, simplest first** (guide → theme → llm → personalization); each surface is production-ready and verified on web + Windows + Android before the next. A small menu-model change omits the `tour` item from the native menu channels (web-only), mirroring how 042 keeps admin tools off native.

## Technical Context

**Language/Version**: Python 3.11 (backend, in Docker image); Kotlin 2.0.x / JVM 17 (Android `:core` + `:app`); Python 3.11 + PySide6 ≥6.6 (Windows client); ES5 vanilla JS/CSS (web render layer, no build step).
**Primary Dependencies**: FastAPI, websockets, psycopg2, `astralprims` (UI primitives), the `webrender` render layer + `rote` adapter (existing); Jetpack Compose + OkHttp + kotlinx.serialization (Android, existing); PySide6/Qt (Windows, existing). **No new third-party runtime dependency** (Constitution V). `astralprims` (first-party) MAY take a minor, additive change (a `ParamPicker` action-submit binding; optional `password`/`textarea` field kinds) — documented in the PR, version-gated publish; the orchestrator may emit the extended component as a plain dict until the wheel updates (the feature-029 dashboard-primitive precedent).
**Storage**: PostgreSQL via `shared/database.py::_init_db()` idempotent guarded startup migrations. **No new tables expected**; the theme preset already persists in `user_preferences.theme` (written by `theme.py::_handle_theme_preset`). Any addition ships as an idempotent `_init_db` delta with a documented rollback (Constitution IX).
**Testing**: pytest (backend, changed-line coverage ≥90% via diff-cover); Kotlin JUnit in `:core` (Kover ≥90% on pure logic: component/chrome decoders, surface-host mapping) + Compose UI/instrumented tests in `:app`; pytest for the Windows client; manual/live verification of Windows via launch+screenshot and Android via emulator (Constitution X/XII).
**Target Platform**: Web (browser), Windows desktop, Android phone/tablet/foldable; the design must extend to a future iOS client with no per-surface re-specification (Constitution XII).
**Project Type**: Server-driven-UI system with a shared backend and multiple thin native clients.
**Performance Goals**: A settings surface opens within ~1s of selection; a data-heavy surface (personalization memory/jobs lists, the 16-section guide) renders without freezing the client UI (compose off the UI thread / paginate long lists).
**Constraints**: Match the web surface's content and actions exactly (Constitution XII); no web view on either native client (no QtWebEngine, no Android WebView); no per-client hand-built surface that can diverge; the **web presentation and behavior of every ported surface MUST be unchanged** by the port.
**Scale/Scope**: 4 ported surfaces × 3 client targets; ~14 `chrome_*` actions total (theme 1, guide 0, llm 4, personalization 10); personalization spans 5 tabs and ~5 data backends. Plus a small menu-model change to omit the `tour` item from the native menu channels.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. Primary Language (Python backend)**: PASS — backend changes are Python; client changes are in the clients' own sanctioned languages (Kotlin, PySide6). No new backend language.
- **II. UI Delivery Architecture (SDUI; astralprims defines → orchestrator renders → ROTE adapts; chrome composed from primitives; thin clients; new targets are additive renderers)**: PASS — this feature *completes* the expanded Principle II by making the settings surfaces astralprims-composed, orchestrator-rendered, ROTE-adapted, and consumed by the native clients' existing renderers. No parallel per-client surface. The one nuance — the interactive-input vocabulary — is resolved **inside** the model: the extension lives in `astralprims` (define) → `webrender` (render) → `rote` (adapt) → each client renderer, documented before use (Principle VIII).
- **III. Testing Standards (≥90% changed-line)**: PASS — backend `components()` builders + the `chrome_surface` delivery branch + handler reuse covered by pytest; Android surface-host mapping + component decode in `:core` covered by Kover ≥90%; Windows surface-host mapping in pytest; diff-cover gate honored.
- **IV. Code Quality (ruff; ktlint/Android Lint; JS lint)**: PASS — ruff (Python), ktlint + Android Lint (Kotlin), the web layer's existing JS lint — all in CI.
- **V. Dependency Management (no new third-party runtime dep w/o approval)**: PASS — **zero new third-party runtime dependencies**. The only package change is a minor additive extension to first-party `astralprims`, documented in the PR per the first-party clause and shipped via the version-gated publish path.
- **VI. Documentation**: PASS — the `chrome_surface` frame + the `components()` surface-module contract documented in `contracts/`; any extended/newly-rendered primitive (`ParamPicker` action-submit; `color_picker`/`theme_apply` native renderers) documented before use; each client renderer documents the surface-host behavior.
- **VII. Security (Keycloak roles; server-side authz; audit)**: PASS — surface open and every action re-check the owning surface's `ADMIN_ONLY` server-side in `chrome_events` regardless of client; the in-scope five set no `ADMIN_ONLY`, and admin surfaces stay web-only (042). Actions run through the **same** `HANDLERS` (same permission/PHI/scope gates + audit as the web), so there is no native privilege bypass.
- **VIII. User Experience (astralprims-driven; new primitives added + documented before use)**: PASS — surfaces render from astralprims primitives; the `ParamPicker` extension and the `color_picker`/`theme_apply` renderers are added to the primitive/renderer layers and documented before use.
- **IX. Database Migrations (idempotent guarded startup)**: PASS — no schema change expected; theme persists in existing `user_preferences`. If a preference key is added it ships as a guarded `_init_db` delta with rollback.
- **X. Production Readiness (no stubs; verify every affected client)**: PASS — each surface is production-ready and verified on web + Windows + Android before it is declared done; no whole-surface placeholder remains for the five; graceful per-component degradation is a labeled placeholder, never a blank/crash.
- **XI. Continuous Integration (gate set green)**: PASS — backend `ci.yml` (lint/build/test/coverage/smoke/secret-scan) and `android-ci.yml` (ktlint/lint/unit/Kover/assemble, plus the `workflow_dispatch` instrumented job) must pass; the Windows release workflow builds on tag/dispatch.
- **XII. Cross-Client Consistency (shared server-owned surfaces; thin consumers; role-gating from one source)**: PASS — this feature is the second realization of Principle XII (after 042's menu): one server-composed surface per item, rendered identically across web/Windows/Android from the same `components()`, so the surfaces cannot drift. Removing "Take the tour" from native is a deliberate **web-only** scoping (server-enforced omission from the native menu channels, documented in this spec), sanctioned by the **v2.3.1 carve-out** to XII — not drift.

**Result: PASS. No violations; Complexity Tracking not required.**

## Project Structure

### Documentation (this feature)

```text
specs/043-sdui-settings-surfaces/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions & alternatives
├── data-model.md        # Phase 1 — the chrome_surface payload + per-surface component vocabulary + theme channels
├── quickstart.md        # Phase 1 — how to run & verify each surface across clients
├── contracts/
│   └── chrome-surface.md # Phase 1 — chrome_surface frame + components() surface contract + action round-trip
├── checklists/
│   └── requirements.md   # Spec quality checklist (from /speckit-specify)
└── tasks.md             # Phase 2 — /speckit-tasks output
```

### Source Code (repository root)

```text
backend/
├── shared/
│   └── protocol.py                 # ADD — ChromeSurface frame dataclass (region, surface_key, title, admin_only, components[]); sits beside ChromeRender/ChromeMenu
├── webrender/
│   ├── chrome/
│   │   ├── surfaces/
│   │   │   ├── __init__.py         # (unchanged registry/collect_handlers) — module contract gains optional `components(...)`
│   │   │   ├── _sdui.py            # NEW — helpers to compose astralprims component surfaces + bind actions to existing chrome_* keys (form via ParamPicker action-submit, per-row Button, notice→Alert)
│   │   │   ├── guide.py            # ADD components() — TOC (Buttons→chrome_open) + section article (Text/Card); admin-section filter reused
│   │   │   ├── theme.py            # ADD components() — preset cards (Buttons→chrome_theme_preset) + color_picker×7; already emits color_picker/theme_apply
│   │   │   ├── llm.py              # ADD components() — one ParamPicker form (base_url/api_key/model) + action Buttons (models/test/save/clear)
│   │   │   ├── personalization.py  # ADD components() — 5 tabs (Tabs) → per-tab forms/lists (ParamPicker + Button rows)
│   │   │   └── tour.py             # UNCHANGED — web render()/HANDLERS stay; NOT ported (omitted from native menu)
│   │   ├── menu_model.py           # MODIFY — omit the `tour` item from the native menu channels (web-only), mirroring 042's include_admin filtering
│   │   └── __init__.py             # (web HTML helpers unchanged)
│   ├── renderer.py                 # (web) ensure color_picker/theme_apply + the ParamPicker action-submit variant render correctly; allowed_primitive_types() set unchanged
│   └── static/client.js            # (web) honor ParamPicker action-submit (post chrome_* with fields) — web parity, no visual change
├── orchestrator/
│   └── chrome_events.py            # BRANCH — _render_surface + the handler re-render path emit chrome_surface (native) vs chrome_render (web); not-yet-converted native surface → single labeled placeholder component; server-side ADMIN_ONLY gate unchanged
├── rote/
│   ├── adapter.py                  # voice/adaptation for any newly-emitted component; windows/android already full-capability
│   └── capabilities.py             # (unchanged) windows/android profiles already interactive + all types
└── tests/ (per-module)             # pytest: components() builders, chrome_surface branch, handler reuse, admin gate

# astralprims (first-party package — Astral-Primitives repo, consumed as a wheel)
#   ParamPicker: additive `submit_action`/`submit_payload` (action-submit mode) + optional password/textarea field kinds; documented, version-gated publish.

windows-client/
└── astral_client/
    ├── renderer.py                 # ADD color_picker + theme_apply builders; honor ParamPicker action-submit; expose a surface-render entry for a modal
    ├── chrome.py                   # ADD a settings-surface host: render a chrome_surface component list into a modal via the existing renderer; retire the "not available" notice
    ├── app.py                      # _open_surface: route the four ported surfaces to the SDUI host instead of the QMessageBox placeholder; consume the chrome_surface frame in _on_message
    └── theme.py                    # (P2) make palette tokens dynamic + re-apply stylesheet on a chosen preset

android-client/
├── core/ (:core, pure Kotlin, JVM-tested, Kover ≥90%)
│   ├── sdui/Component.kt           # (unchanged decoder) — already tolerant, keeps full attributes
│   └── protocol/                   # ADD Inbound.ChromeSurface variant + Wire.decode mapping (twin of ChromeMenu)
└── app/ (:app, Compose — thin)
    ├── render/Renderer.kt          # ADD color_picker/theme_apply composables; honor ParamPicker action-submit
    ├── ui/                         # surface host: replace SurfacePlaceholderScreen for the five with a Screen.Surface that renders the delivered components via the existing Renderer; route openMenuItem to it
    └── ui/theme/Theme.kt           # (P2) AstralTheme takes a dynamic ColorScheme from the chosen preset

.github/workflows/                  # ci.yml + android-ci.yml stay green; no structural change expected
```

**Structure Decision**: Multi-client SDUI system, extending feature 042. The **single source of truth per surface** is that surface module's new `components(...)` builder in `backend/webrender/chrome/surfaces/*.py`; the orchestrator renders/adapts it, and Windows (`renderer.py`/`chrome.py`) and Android (`render/Renderer.kt` + surface host) are thin consumers that reuse their existing component renderers. Per clarification, each surface's **web `render()` HTML is left unchanged** and `components()` serves the native targets only (no web convergence), so the web cannot regress (SC-006); the only web-layer change is `client.js` honoring the `ParamPicker` action-submit with no visual change.

## Architecture & Phasing

### Phase 0 — Research (see research.md)
Resolve: (a) the `chrome_surface` delivery frame + where `_render_surface`/re-render branches on device target; (b) **the interactive-input vocabulary** — how a savable form/toggle/select is expressed in SDUI given only `Button` carries an action today (the pivotal decision); (c) the native surface-host shape on each client + placeholder replacement; (d) theme application natively (dynamic palette from a preset's channels); (e) removing the `tour` item from the native menu channels (web-only, per clarification); (f) `color_picker`/`theme_apply` native rendering; (g) per-surface conversion order; (h) verification tooling; (i) migrations; (j) dependencies.

### Phase 1 — Design (data-model.md, contracts/chrome-surface.md, quickstart.md)
Define the `chrome_surface` payload + the per-surface component vocabulary + the `ParamPicker` action-submit extension + the theme-channel model; the `chrome_surface` delivery + `components()` surface-module contract + the settings action round-trip; and the cross-client verification quickstart per surface.

### Phase 2 — Tasks (tasks.md via /speckit-tasks)
Dependency-ordered, grouped by the spec's user stories (US1 render, US2 actions, US3 theme), each task independently testable, each surface independently shippable + production-ready, verified on every affected client.

### Implementation order (matches spec priorities + incremental delivery)
- **Foundational** — the `chrome_surface` frame + the `_render_surface`/re-render device branch + the `_sdui.py` helpers + the native surface hosts on both clients + the interactive-vocabulary foundation (`ParamPicker` action-submit + `color_picker`/`theme_apply` renderers) + the menu-model change omitting `tour` from the native channels. A not-yet-converted surface returns a single labeled placeholder component on native (never the old text placeholder). **Blocks all surface work.**
- **US1 + US2 per surface, simplest first** — each surface gains `components()` (US1 render) and its actions wired end-to-end (US2), delivered and verified together before the next: **guide** (static, existing vocab) → **theme** (presets on existing vocab; fine-tune color pickers) → **llm** (ParamPicker form + 4 actions) → **personalization** (5 tabs, 10 actions — largest). Each replaces its placeholder on both native clients. **Each surface independently shippable.**
- **US3 (P2) — theme applies natively** — make the Windows Qt palette and the Android Compose color scheme dynamic; a chosen preset restyles the app live and every client honors the saved preset on next load.

## Complexity Tracking

No constitution violations — table intentionally omitted.
