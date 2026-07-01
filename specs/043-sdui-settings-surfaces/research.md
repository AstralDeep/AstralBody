# Phase 0 Research: Native SDUI Settings Surfaces

All decisions are grounded in the current code. Source-of-truth anchors found during discovery:
- **Surfaces (HTML-first)**: `backend/webrender/chrome/__init__.py:1-14` (chrome is intentionally web-specific HTML, not primitives); the four ported modules `backend/webrender/chrome/surfaces/{theme,guide,llm,personalization}.py` (plus `tour.py`, which stays web-only per D5); registry + handler aggregation `surfaces/__init__.py:28-68`.
- **Delivery**: `backend/shared/protocol.py:189-215` (`ChromeRender` HTML + `ChromeMenu` model frames — no surface-content frame for native); dispatch `backend/orchestrator/chrome_events.py:62-177`; native menu delivery `orchestrator/orchestrator.py:1161-1180` + `api.py:1504-1519`.
- **Primitives / render / ROTE**: `backend/webrender/renderer.py:1105-1166` (`PRIMITIVE_RENDERERS`, `render_one`, `allowed_primitive_types`); `astralprims` `primitives.py` (`Button` is the only action-carrier; `Input` is a binding-less stub; no `Select`/`Toggle`); `backend/rote/adapter.py` + `capabilities.py:49-172` (`windows`/`android` full-capability, per-connection `supported_types`, fallback ladder).
- **Native clients**: Windows `windows-client/astral_client/{renderer.py,chrome.py,app.py,theme.py}`; Android `android-client/core/**` + `app/**` (renderer registries, `SurfacePlaceholderScreen`, `AstralTheme`).

## D1 — How is a settings surface's *content* delivered to a native client?

**Decision**: Add a third chrome frame **`chrome_surface`** to `shared/protocol.py`, beside `ChromeRender` and `ChromeMenu`:
`{type:"chrome_surface", region:"modal", surface_key, title, admin_only, components:[…]}`. In `chrome_events.py`, `_render_surface` (and the handler re-render path at `chrome_events.py:140-165`) branch on the connecting device target resolved from `orch.ui_sessions[websocket]`: **web (`browser`)** keeps the existing `ChromeRender(region:"modal", html=…)` path unchanged; **native (`windows`/`android`)** calls the surface's new `components(orch, user_id, roles, params)`, ROTE-adapts the component dicts for that device's `supported_types`, and pushes them as `chrome_surface`. A surface that has no `components()` yet returns a single labeled placeholder component on native (never the old text placeholder).

**Rationale**: Mirrors the feature-042 pattern (a structured native twin of a web-HTML channel) and the contract 042 already drafted (`042/contracts/chrome-menu.md §3`). The `HANDLERS` dispatch + persistence layer already takes a `payload` dict and returns `(surface, params, notice)` (`chrome_events.py:140-165`), so it is transport-agnostic — only the *render/re-render output* needs the branch. The `chrome_menu` delivery already keys off `device_type in ("windows","android")` (`orchestrator.py:1161-1180`), so the target signal is established.

**Alternatives rejected**: (i) Reuse `chrome_render` and have native clients parse HTML — both clients are web-view-free by design (no QtWebEngine, no Android WebView) and cannot consume trusted HTML. (ii) A REST `GET /api/chrome/surface/{key}` only — adds a round trip and a second code path; the WS push matches how the surface opens today (`ui_event{chrome_open}` → push).

## D2 — How is a savable settings control expressed in SDUI? *(pivotal)*

**Context**: `astralprims` has exactly **one** action-carrying primitive — `Button` (`action`+`payload`, rendered `<button class="astral-action" data-action data-payload>`). `Input` has no submit/action binding (the web renderer calls it a stub, `renderer.py:202-208`); there is **no** `Select`/`Toggle`/`Switch`/`Checkbox` primitive. The web chrome surfaces avoid this entirely by hand-building raw HTML `<input>/<select>/<checkbox>` collected client-side (`client.js` `data-ui-collect` → `collectChromeFields` → `payload.fields`) — a path that cannot cross to native. So a savable native form/toggle/select has no SDUI representation today.

**Decision**: Express interactive settings with the **smallest additive vocabulary**, reusing what both native clients already render:
1. **Actions and toggles-as-buttons** → existing **`Button`** (already rendered + action-wired on both clients). Theme presets (`chrome_theme_preset`), per-row skill/job/memory actions (`chrome_skill_toggle`, `chrome_job_pause`, `chrome_memory_delete`, …), guide TOC nav (`chrome_open`) are all Buttons carrying their row's id in `payload`.
2. **Multi-field forms** → extend the existing **`ParamPicker`** (already rendered on both clients: Windows `renderer.py:507-513`, Android `Input.kt:61-76`; field kinds text/number/boolean/select/checklist) with an **action-submit mode**: additive `submit_action` (+ optional `submit_payload`) so submit posts `ui_event{action:"chrome_*", payload:{fields, …submit_payload}}` instead of interpolating `submit_message_template` into a chat message. Add `password` and `textarea` field kinds for the API key and the profile textareas. One `ParamPicker` maps cleanly to the LLM form and to each personalization tab's form.
3. **Color controls** → the existing **`color_picker`** / **`theme_apply`** primitives (already used by `theme.py`); add the two missing native renderers (neither Windows nor Android renders them yet). Theme *presets* ship first as Buttons; the 7 fine-tune `color_picker`s follow once the native renderer lands.

The extension lives in `astralprims` (define) → `webrender/renderer.py` + `static/client.js` (render, web parity) → `rote/adapter.py` (voice) → each native renderer, documented before use. Per the feature-029 dashboard-primitive precedent, the orchestrator MAY emit the extended `param_picker` dict immediately (renderers honor the new fields) while the `astralprims` class change follows the version-gated publish.

**Rationale**: `ParamPicker` is *already* a "collect a set of typed fields and submit them together" control rendered on every client — semantically a settings form — so an action-submit mode is a minimal, localized change that reuses the fully-built native renderers, versus introducing and cross-implementing three new primitives. It keeps the primitive surface (and the wire contract) small and satisfies Constitution II/VIII (composed from astralprims; extension added + documented before use).

**Alternatives rejected**: (i) **Net-new `TextInput`/`Select`/`Toggle` primitives, each action-bound** — the "cleanest" vocabulary but the largest churn: three classes × orchestrator renderer × ROTE voice × two native renderers × docs, for controls `ParamPicker` already expresses. Kept on the table only if a surface needs a control `ParamPicker` genuinely cannot represent. (ii) **A bespoke non-primitive "surface schema"** — reintroduces a parallel per-surface vocabulary the clients must special-case, violating Constitution II ("composed from astralprims … exactly like any other SDUI") and XII (drift). (iii) **Keep collecting fields via client-specific form code** — that is the HTML `collectChromeFields` path; duplicating it natively is exactly the divergence 042/043 exist to kill.

## D3 — The native surface host + placeholder replacement

**Decision**: Each native client gains a **settings-surface host** that renders a delivered `chrome_surface.components` list through its existing component renderer into a modal/sheet, and the placeholder branch is rerouted to it:
- **Windows**: `app.py::_open_surface` (`app.py:924-941`) currently routes `agents`/`audit`/`workspace_timeline` to native dialogs and everything else to a `QMessageBox` "coming soon" (`app.py:937-941`). The four ported surfaces instead emit `ui_event{chrome_open}` and render the returned `chrome_surface` in a modal built by a new host in `chrome.py` that calls the existing `renderer.py` builders; retire the `chrome.py::chrome_render_notice` "not available" path (`chrome.py:29-45`).
- **Android**: `AppViewModel.openMenuItem` (`AppViewModel.kt:317-328`) routes `agents`/`audit` to native screens and everything else to `SurfacePlaceholderScreen` (`Screens.kt:222-241`). Replace the `else` with a new `Screen.Surface` that holds the decoded `chrome_surface` and renders it via the existing `render/Renderer.kt`; consume a new `Inbound.ChromeSurface` in the reducer (twin of `Inbound.ChromeMenu` at `AppViewModel.kt:501`).

Both renderers already degrade an unknown component to a labeled placeholder (Windows `_r_fallback` `renderer.py:799-811`; Android `Placeholder` `Renderer.kt:53-61`), satisfying FR-014 with no new code.

**Rationale**: Reuses the fully-built canvas renderers and the existing `ui_event` round-trip on each client — the host is a thin shell (open a modal, pass the component list to the renderer, wire `emit`). No per-surface native UI.

**Alternatives rejected**: Per-surface native screens (what Android's removed duplicate Settings did) — the drift XII forbids and the maintenance this feature removes.

## D4 — Theme application on native clients (US3 / P2)

**Decision**: The theme *surface* and its *save* (US1/US2) ship first: preset Buttons post `chrome_theme_preset`, whose handler already persists `{"theme":{"preset":name}}` to `user_preferences` (`theme.py:179`) and returns a re-render. Live **application** (US3) makes each client's palette dynamic and drives it from the chosen preset's 7 channels (bg/surface/primary/secondary/text/muted/accent, the `PRESETS` map in `theme.py:29-45`): **Windows** `theme.py` currently exposes static module constants applied once (`app.py:1454-1466`) — make the tokens a runtime object and re-apply `APP_STYLESHEET` on preset change; **Android** `AstralTheme` wraps a fixed `AstralDarkColors` (`Theme.kt:37-57`) — make it take a dynamic `ColorScheme` the VM holds. The user's active theme is included in the register bootstrap so a client themes correctly on connect. Channels ship to native either in the `chrome_theme_preset` re-render side-effect (a `theme_apply`-style payload) or the register bootstrap — not CSS.

**Rationale**: Reuses the existing preset model + persistence; ships tokens, not CSS, to native; genuinely native work (both clients are dark-only today) → correctly scheduled as P2, after the surface renders and saves.

**Alternatives rejected**: A native light/dark toggle in the chrome — the web has none; adding one breaks parity (spec Assumptions, Constitution XII). Rendering `theme_apply` as a visible component — it is a side-effect signal, not UI; natively the client applies channels to its own palette.

## D5 — "Take the tour" on native: removed (web-only)

**Decision** (clarified): Do **not** port the tour to native. Remove "Take the tour" and its options from the Windows and Android clients — the server omits the `tour` item from the native menu channels (the `chrome_menu` WS frame at `orchestrator.py:1161-1180` + `GET /api/chrome/menu` at `api.py:1504-1519`), mirroring how 042 keeps admin tools web-only (`include_admin=False`). The web keeps the tour surface unchanged. So no `tour` `components()` is built and no native tour runtime is needed; the native HELP group shows **User guide only**.

**Rationale**: The web tour is a bespoke client engine that closes the modal and highlights `[data-tour-target]` DOM nodes (`tour.py:154-158`); it has no native analog, and the user's explicit decision is to drop it from native rather than invent one. Filtering it out of the native menu (vs. delivering a placeholder) is the honest representation — the capability genuinely does not exist on native, like the admin surfaces. `tour.py` (its web `render()`/`HANDLERS`) stays for the web.

**Alternatives rejected**: A native paged-walkthrough equivalent, or native coach-marks anchored to native views — both were on the table but the user chose removal; not built. Leaving the tour item in the native menu opening a placeholder — the user asked for the item itself gone, not a stub.

## D6 — Web parity: converted surfaces leave the web unchanged

**Decision** (clarified): Keep every surface's web `render()` HTML **exactly as-is**; add `components()` for the **native targets only**. No surface's web path is converged onto `components()` in this feature. The one web-layer change is `client.js` honoring the `ParamPicker` action-submit (D2), which has no visual effect on existing web usage.

**Rationale**: "Web unchanged" is a hard success criterion (SC-006). Not touching the web `render()` paths makes web regression structurally impossible; the single-source (web-rendered-from-`components()`) convergence is a possible later cleanup once native has proven the vocabulary, not worth any web-diff risk now. This is the user's explicit choice.

**Alternatives rejected**: Converging the simple surfaces (theme/guide) onto `components()` for a single source — small duplication savings, non-zero web-regression risk; deferred. Converging all surfaces — highest risk, rejected.

## D7 — Re-render + notices on native

**Decision**: The handler contract `fn(...) → (surface_key, params, notice_html)` triggers a re-render-with-notice (`chrome_events.py:140-165`). On native, the re-render goes back through `_render_surface`'s native branch (fresh `components()`), and the `notice_html` becomes an **`Alert` component** prepended to the surface (the `_sdui.py` helper maps success/error notices → `Alert`), not HTML. Handlers that push their own output and return `None` (e.g. `tour`'s `_handle_tour_event`) are unchanged; the native tour surface interprets the lifecycle client-side like the web does. Action failures (network/refusal) surface as an in-surface `Alert` and leave the client usable (FR edge case).

**Rationale**: Keeps the handler signatures and the FR-016 explicit-save→notice contract intact; only the notice *rendering* is retargeted to a primitive.

## D8 — Verification tooling on this host

**Decision**: Backend via `docker compose up` (`:8001`). Web via a real browser (claude-in-chrome / puppeteer) against `http://localhost:8001`. Windows via `pip install -r windows-client/requirements.txt` + `python windows-client/main.py`, screenshotted per surface. Android via the committed Gradle wrapper + local Android SDK + JDK: `:core`/`:app` JVM tests always; `:app:assembleDebug` + emulator screenshots per surface where an AVD with acceleration is available, else the CI `instrumented` job (`workflow_dispatch` on `android-ci.yml`). Device-independent logic (component builders, host-mapping, decoders) is covered by tests that need no device (FR-018).

**Rationale**: Uses the requested per-surface screenshot path where the host supports it and degrades to the pipeline where it does not, while keeping the feature CI-verifiable. Matches 042's D6 (that round confirmed the SDK/JDK/wrapper are present; emulator availability is re-confirmed at verification time).

## D9 — Migrations / schema

**Decision**: No new tables. Surfaces are computed; the theme preset persists in the existing `user_preferences.theme`. If any preference key is added (e.g. explicit theme channels), it ships as an idempotent guarded `_init_db` delta with a documented rollback (Constitution IX).

## D10 — Dependencies

**Decision**: Zero new third-party runtime dependencies on the server or either client. All work reuses FastAPI/websockets/astralprims/webrender/rote (backend), Compose/OkHttp/kotlinx.serialization (Android), PySide6 (Windows). The only package change is the additive first-party `astralprims` extension (D2), documented in the PR and version-gated (Constitution V, first-party clause).
