# Quickstart: Verify Native SDUI Settings Surfaces

Goal: confirm each of the four ported surfaces (User guide, Theme, LLM settings, Personalization) opens as a **native SDUI screen** on Windows and Android — same content + actions as the web, no "coming soon" placeholder, no web view — that **Take the tour** no longer appears in the native menu (the web keeps it), and that the web is unchanged.

## 0. Backend up

```bash
docker compose up -d                 # postgres + astralbody on :8001 (ASTRAL_ENV=development ⇒ mock auth ⇒ roles [admin,user])
curl -fsS localhost:8001/healthz && curl -fsS localhost:8001/readyz
curl -fsS localhost:8001/api/chrome/menu | python -m json.tool   # the 042 menu (the five items live under ACCOUNT/HELP)
```

## 1. Surface contract (fast, no client)

```bash
docker exec astralbody bash -c "cd /app/backend && python -m pytest webrender/chrome/tests/ orchestrator/tests/test_chrome_surface.py -q"
```
Asserts: `chrome_open` on a `windows`/`android` session returns a `chrome_surface` with valid `astralprims` components; a `browser` session still returns `chrome_render` HTML; every emitted `chrome_*` action resolves in `collect_handlers()`; a `ParamPicker` action-submit yields the `payload.fields` shape each form handler accepts; admin surfaces stay refused+audited; the four in-scope surfaces render for a `user`; the native menu omits `tour`.

## 2. Web (source of truth — must be unchanged)

Open `http://localhost:8001`, sign in, gear → open **User guide / Theme / LLM settings / Personalization** (and confirm **Take the tour** is still present here on the web). Screenshot each for the parity comparison, and diff against a pre-branch build to confirm **no web change** (SC-006).

## 3. Windows client

```bash
python -m pip install -r windows-client/requirements.txt   # PySide6 etc.
python windows-client/main.py                              # point at ws://127.0.0.1:8001/ws
```
Open each of the four from the gear (Take the tour should NOT appear in the native menu). Confirm a **native modal** renders (not the old `QMessageBox` "coming to the desktop app soon"), with the same fields/sections/controls as the web. Perform each surface's primary action (below) and confirm it takes effect + a success/error `Alert` appears in the modal. Screenshot each.

## 4. Android client

```bash
cd android-client
./gradlew :core:test :app:testDebugUnitTest    # device-independent: component/ChromeSurface decode + surface-host mapping + action payloads
./gradlew :app:assembleDebug                    # APK
# If an emulator/AVD is available:
adb devices
./gradlew :app:installDebug
# open each of the four from Settings (no Take the tour); confirm a native surface (not SurfacePlaceholderScreen), drive its primary action, screenshot
```
If no emulator is available, rely on the JVM unit tests here plus the CI `instrumented` job (`workflow_dispatch` on `android-ci.yml`).

## 5. Primary action per surface (SC-003)

- **User guide** — navigate the TOC; each section's content renders. (No mutation.)
- **Theme** — pick a preset → saved to `user_preferences` and honored on re-open (US1/US2); (P2) the app restyles live and a second client opens with the preset (SC-004).
- **LLM settings** — Load models → Test → Save → re-open shows the saved base_url/model (api-key write-only); Clear.
- **Personalization** — soul: save profile; memory: edit + delete an item; skills: toggle a skill; schedule: pause/resume/run/delete a job; dreaming: toggle + trigger a sweep. Each reflected on re-open, matching the web.

## 6. Cross-client parity + degradation (SC-001, SC-002, SC-005)

Place the three screenshots of a surface side by side — same content + controls (SC-002). Confirm **zero** "coming soon" placeholders and **zero** web pages remain for the four, and that each opens within ~1s of selection (SC-001, FR-004). Change a surface's server composition (add a field/section in `components()`), restart, re-open on all three — the change appears with no client code change (SC-005). Point a client at a build missing one component renderer and confirm that component degrades to a labeled placeholder while the rest of the surface still works (FR-014).

## 7. CI

```bash
# Backend gates (same invocations CI runs):
docker exec astralbody bash -c "cd /app/backend && python -m ruff check . && python -m pytest -q -m 'not integration'"
# Android gates:
cd android-client && ./gradlew ktlintCheck :app:lintDebug :core:test :app:testDebugUnitTest :core:koverVerify :app:assembleDebug
```
Then push the branch; confirm `CI` and `android-ci` are green; trigger the Android `instrumented` job via `workflow_dispatch` for the emulator UI tests. Verify backend changed-line coverage ≥90% (diff-cover) and `:core` Kover ≥90%.
