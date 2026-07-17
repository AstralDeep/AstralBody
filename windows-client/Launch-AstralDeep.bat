@echo off
REM ============================================================================
REM  AstralDeep — native Windows client launcher
REM  Double-click this file to start the official app with its reviewed bundled
REM  production profile. Pass --deployment-profile with one complete JSON file
REM  for an explicitly managed or generic/developer override.
REM ============================================================================

"%~dp0dist\AstralDeep.exe" %*
