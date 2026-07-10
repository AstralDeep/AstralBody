# Quickstart: Verify Cross-Client Chrome Parity

Goal: confirm the web, Windows, and Android clients render the **same** top bar + Settings menu from the one server-owned model, that Android shows no duplicated options, that admin-gating works, and that sign-out ends the session.

## 0. Backend up

```bash
docker compose up -d                 # postgres + astraldeep on :8001 (ASTRAL_ENV=development ⇒ mock auth ⇒ roles [admin,user])
curl -fsS localhost:8001/healthz && curl -fsS localhost:8001/readyz
curl -fsS localhost:8001/api/chrome/menu | python -m json.tool   # the served model (admin, since dev mock auth)
```

## 1. Menu-model contract (fast, no client)

```bash
docker exec astraldeep bash -c "cd /app/backend && python -m pytest webrender/tests/test_menu_model.py orchestrator/tests/test_chrome_menu.py -q"
```
Asserts: builder order/labels match the source of truth; admin vs non-admin filtering; REST body == WS frame; every item surface resolves; Pulse present only when `FF_PULSE_DIGEST`.

## 2. Web (source of truth)

Open `http://localhost:8001`, sign in, click the gear. Confirm: top bar = brand · status · [pulse if flag] · timeline (history icon) · Settings; dropdown = ACCOUNT (Agents & permissions, LLM settings, Personalization, Audit log, Theme) · HELP (Take the tour, User guide) · ADMIN TOOLS (Tool quality, Tutorial admin — admin only) · red Sign out. Screenshot for the parity comparison.

## 3. Windows client

```bash
python -m pip install -r windows-client/requirements.txt   # PySide6 etc.
python windows-client/main.py                              # point at ws://127.0.0.1:8001/ws
```
Confirm the flat button row is gone; the gear opens the same grouped dropdown; Agents/Audit are inside it; Sign out is red at the bottom; ADMIN TOOLS appears only for an admin token. Screenshot.

## 4. Android client

```bash
cd android-client
./gradlew :core:test :app:testDebugUnitTest    # device-independent logic incl. ChromeMenu decode + gating
./gradlew :app:assembleDebug                    # APK
# If an emulator/AVD is available:
adb devices                                     # confirm a running emulator
./gradlew :app:installDebug
# drive + screenshot the top bar and Settings dropdown; confirm no duplicated options and no separate Settings page
```
If no emulator is available on the host, rely on the JVM unit tests here plus the CI `instrumented` job (`workflow_dispatch` on `android-ci.yml`).

## 5. Cross-client parity check (SC-001..SC-007)

Place the three screenshots side by side. Same groups, same items, same order, zero duplicates. Sign in as a non-admin (a non-mock token) and confirm ADMIN TOOLS is absent on all three and an admin surface open is refused + audited. Change one label in `menu_model.py`, restart, and confirm all three reflect it with no client code change (SC-005).

## 6. CI

```bash
# Backend gates (run the same invocations CI runs):
docker exec astraldeep bash -c "cd /app/backend && python -m ruff check . && python -m pytest -q -m 'not integration'"
# Android gates:
cd android-client && ./gradlew ktlintCheck :app:lintDebug :core:test :app:testDebugUnitTest :core:koverVerify :app:assembleDebug
```
Then push the branch and confirm `CI` and `android-ci` are green on the PR; trigger the Android `instrumented` job via `workflow_dispatch` for the emulator UI tests.
