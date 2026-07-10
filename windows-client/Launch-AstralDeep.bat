@echo off
REM ============================================================================
REM  AstralDeep — native Windows client launcher
REM  Double-click this file to start the desktop app against your deployment.
REM  It sets the orchestrator URL + Keycloak realm so the app runs the real
REM  OIDC sign-in (dedicated public client "astral-desktop") on launch.
REM ============================================================================

REM --- Orchestrator WebSocket endpoint (local Docker default) ------------------
if not defined ASTRAL_WS_URL set "ASTRAL_WS_URL=ws://127.0.0.1:8001/ws"

REM --- Keycloak realm (the app signs in with the astral-desktop public client) -
if not defined KEYCLOAK_AUTHORITY set "KEYCLOAK_AUTHORITY=https://iam.ai.uky.edu/realms/Astral"

REM --- Optional: match the orchestrator's AGENT_API_KEY so the in-app Windows
REM     tools agent (system info, clipboard, notify, open, ls) can register.
REM     Leave unset if the orchestrator runs keyless (ASTRAL_ENV=development).
REM set "AGENT_API_KEY=<paste the orchestrator's AGENT_API_KEY here>"

"%~dp0dist\AstralDeep.exe" %*
