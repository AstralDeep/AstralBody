# Quickstart: Native Apple Clients (051)

## Backend (dev)

```bash
docker compose up -d                    # postgres + astralbody as usual
# .env additions:
#   FF_DEVICE_LOGIN=1                                  # default on; explicit for clarity
#   KEYCLOAK_ALLOWED_AZP=astral-desktop,astral-mobile,astral-ios,astral-macos,astral-watch
docker exec astralbody bash -c "cd /app/backend && python -m pytest -q tests/test_qr.py tests/test_apple_profiles.py tests/test_device_login.py tests/test_watch_speech.py"
```

## Keycloak realm (one-time)

1. Create public clients `astral-ios`, `astral-macos` (Standard flow + PKCE S256; redirect
   URIs `astral://oauth2redirect` and `http://127.0.0.1:*` loopback respectively — final
   values in docs/keycloak-realm-settings.md).
2. Create public client `astral-watch` with **OAuth 2.0 Device Authorization Grant** enabled
   (Capability config → "OAuth 2.0 Device Authorization Grant" toggle).
3. Confirm the realm well-known advertises `device_authorization_endpoint`; the backend
   discovers it from `KEYCLOAK_AUTHORITY` and fails closed if absent.

## Apple clients

```bash
cd apple-clients/AstralCore && swift test        # core logic + manifest drift guard (any Mac)
```

App targets (Xcode 15+ on the Mac):

- **Canonical**: follow `apple-clients/README.md` § "Creating the Xcode project" — one
  multiplatform app target (iOS+macOS) from `AstralApp/`, one watchOS app target from
  `AstralWatch/`, both depending on the local `AstralCore` package.
- **Convenience**: `brew install xcodegen && cd apple-clients && xcodegen` (optional,
  dev-machine only).

Point the app at the backend via the in-app server field (default `http://127.0.0.1:8001`,
simulators reach the host directly; devices need the Mac's LAN address).

## Watch sign-in demo (US3)

1. Run the watch app in the simulator, signed out → QR + short code appear.
2. Scan with a phone camera (or open the `verification_uri` and type the code in any
   browser), sign in, approve.
3. Watch flips to signed-in home within one poll interval; try a voice message and listen.
