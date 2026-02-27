# Flutter Environment Configuration Sync

## Problem

The Flutter web app was failing with error:
```
Flutter Web engine failed to fetch "assets/.env". HTTP request succeeded, but the server responded with HTTP status 404.
```

The Flutter app needed environment variables from the root `.env` file but couldn't access it.

## Solution

Created a sync script that:
1. Reads the root `.env` file
2. Merges it with Flutter-specific defaults
3. Generates `flutter/.env` and `flutter/assets/.env`
4. Updates `pubspec.yaml` to include `.env` as an asset

## Files Created/Modified

1. **`sync_flutter_env.py`** - Python script to sync environment variables
2. **`flutter/.env`** - Merged environment file for Flutter (auto-generated)
3. **`flutter/assets/.env`** - Environment file for web builds (auto-generated)
4. **`flutter/pubspec.yaml`** - Updated to include `assets/.env` in assets section

## Usage

### Manual Sync
Run the sync script before building:
```bash
python sync_flutter_env.py
```

Or using the project's virtual environment:
```bash
.venv\Scripts\python sync_flutter_env.py
```

### Integration with Build Process
Consider adding the sync script to your build process:
- Before `flutter build web`
- Before `flutter run -d chrome`
- In CI/CD pipelines

## How It Works

The script:
1. Parses the root `.env` file
2. Merges with Flutter defaults (VITE_BFF_URL, VITE_WS_URL, etc.)
3. Root values override Flutter defaults
4. Writes merged values to both Flutter `.env` files

## Key Variables Synced

From root `.env` → Flutter:
- `VITE_KEYCLOAK_AUTHORITY`
- `VITE_KEYCLOAK_CLIENT_ID`
- `VITE_USE_MOCK_AUTH`
- `DEBUG`

Flutter-specific defaults:
- `VITE_BFF_URL=http://localhost:8001`
- `VITE_WS_URL=ws://localhost:8001/ws`
- `VITE_KEYCLOAK_REDIRECT_URI=astralbody://callback`
- `VITE_KEYCLOAK_SCOPES=openid profile email`

## Verification

The fix is verified when:
1. Flutter web app starts without "failed to fetch assets/.env" error
2. App logs "App configuration loaded" with correct values
3. Configuration values match those in root `.env`
