# Verification bundle — feature 051 (Apple native clients)

044 conventions: legible captures (readable text), per-client subdirectories,
a dated `results.md` with per-scenario outcomes, regenerable from a clean
checkout via [../quickstart.md](../quickstart.md).

## Contents

- `results.md` — dated per-scenario outcomes with environment details.
- `ios/` — iPhone simulator captures (`xcrun simctl io <device> screenshot`).
- `macos/` — macOS app captures (requires Screen Recording permission for
  the capturing terminal; see results.md for the launch evidence recorded
  without it).
- `watch/` — watch simulator captures.

## Regeneration

1. `docker compose up -d` with `.env` per quickstart (dev posture,
   `FF_DEVICE_LOGIN=true`).
2. Build all three targets:
   `xcodebuild -project apple-clients/AstralApp/AstralApp.xcodeproj -scheme {AstralApp|AstralWatch} …`
3. `xcrun simctl install/launch` on a booted iPhone + watch simulator;
   `open …/Debug/AstralDeep.app` for macOS.
4. Screenshot per scenario; the watch QR path additionally needs the realm's
   device grant enabled on `astral-watch`
   (docs/keycloak-realm-settings.md §051).
