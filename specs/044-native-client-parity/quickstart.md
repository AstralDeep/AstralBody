# Quickstart — Running & Verifying Cross-Client Parity (044)

**Environment note**: the dev machine already runs Docker Desktop (backend) and an Android
emulator; the Windows client runs directly on the host (Python 3.10 is fine for the client —
it is the *backend* that needs 3.11, which lives in the container).

## 1. Backend (dev posture)

```bash
docker compose up -d                    # postgres + astraldeep on :8001
# Canonical suite run — unset the local research FF_* flags first (the local
# .env enables ~58 experimental flags CI never sets; see defect D-031):
docker exec astraldeep bash -c "cd /app/backend && for v in \$(env | grep -E '^FF_' | cut -d= -f1); do unset \$v; done && python -m pytest -q -m 'not integration'"
# sync an edit (source is baked; agents/ + knowledge/ are bind mounts):
docker cp backend/<path> astraldeep:/app/backend/<path>   # then restart if orchestrator code
```

`.env` must have `ASTRAL_ENV=development`. For headless E2E flip `USE_MOCK_AUTH=true`
temporarily (dev token `dev-token`, user `test_user`); interactive verification uses real
Keycloak (https://iam.ai.uky.edu).

## 2. Web client (baseline)

Open `http://localhost:8001/` in Chrome (server-rendered shell; OIDC login or mock). This is
the behavioral baseline for every parity scenario.

## 3. Windows client (host)

```powershell
cd windows-client
pip install -r requirements.txt          # PySide6, websockets, …
python main.py --url ws://127.0.0.1:8001/ws          # + --token dev-token under mock auth
# real auth: KEYCLOAK_AUTHORITY=https://iam.ai.uky.edu/realms/Astral (PKCE loopback, client astral-desktop)
python -m pytest tests -q               # headless-safe suite (QT_QPA_PLATFORM=offscreen)
```

## 4. Android client (emulator)

```powershell
cd android-client
.\gradlew :app:assembleDebug :core:test :app:testDebugUnitTest
.\gradlew :app:installDebug             # emulator must be running; debug flavor targets ws://10.0.2.2:8001/ws
adb shell am start -n com.personalailabs.astraldeep/.app.MainActivity
adb exec-out screencap -p > specs/044-native-client-parity/verification/android/<scenario>-android.png
```

## 5. Guard suites (drift protection — run per PR in CI)

```bash
# backend: manifest ↔ code equality + send-site sweep
docker exec astraldeep bash -c "cd /app/backend && python -m pytest tests/test_ui_protocol_manifest.py -q"
# windows: frame classification + vocabulary vs manifest
cd windows-client && python -m pytest tests/test_protocol_manifest.py tests/test_renderer.py -q
# android: classification + vocabulary vs manifest
cd android-client && .\gradlew :core:test :app:testDebugUnitTest
```

## 6. Regenerating the verification bundle (SC-007/SC-010)

1. Backend up (dev posture), all three clients connected as above.
2. Push the canonical 35-type gallery through the real WS path:
   `docker exec astraldeep bash -c "cd /app/backend && python -m verification.gallery_driver --user <id>"`
   (delivers every component type + interactive variants to each connected client per its
   declared vocabulary).
3. Walk the scripted scenarios in `verification/results.md` (US1–US6: error injection, socket
   drop, expired token, sign-out + SC-004 refresh-rejection check, settings round-trips with
   one forced failure, attachments lifecycle, pagination, theme presets, history reload).
4. Capture per client:
   - **Web**: browser screenshots.
   - **Windows**: `python tests/screenshot.py --live` on the real Windows platform (the
     harness now *fails* if no requested font family resolves — tofu output is impossible by
     construction).
   - **Android**: `adb exec-out screencap -p` per scenario.
5. Drop captures into `verification/{web,windows,android}/`, fill `results.md`, link evidence
   from [parity-matrix.md](parity-matrix.md) cells, update
   [defect-register.md](defect-register.md) dispositions.

## 7. Success gates before merge

- All pre-existing suites green (backend in-container, windows pytest, android unit) +
  new guards green (SC-009).
- Parity matrix: zero `pending` evidence cells; defect register: every entry `fixed` or
  `deferred` with rationale (SC-008).
- ruff clean from repo root; CI workflows (ci.yml + android-ci.yml + new windows job) green.
