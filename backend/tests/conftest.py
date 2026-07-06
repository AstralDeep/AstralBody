"""Shared fixtures for backend/tests.

Hermeticity guard: a dev container's ``.env`` may export feature flags
globally (FF_UI_DESIGNER_* pass flags, FF_MOA_DEBATE, FF_HOOK_SYSTEM, ...),
but these suites assume the in-code defaults and monkeypatch only the flag
under test. CI sets none of them, so ambient values are stripped for the
whole session to make in-container runs behave identically to CI. Flag
values can also be cached by module-level state on first read, so the strip
must happen once up front, not per-test. Note the ui_designer prefix is
``FF_UI_DESIGNER_`` (trailing underscore): the master ``FF_UI_DESIGNER``
kill-switch is left alone.
"""
from __future__ import annotations

import os

_AMBIENT_FLAG_PREFIXES = ("FF_UI_DESIGNER_",)
_AMBIENT_FLAGS = (
    "FF_ADAPTIVE_OBJECTIVES",
    "FF_MOA_DEBATE",
    "FF_HITL_HIGHRISK",
    "FF_HOOK_SYSTEM",
)


def _strip_ambient_flags() -> None:
    for name in list(os.environ):
        if name.startswith(_AMBIENT_FLAG_PREFIXES) or name in _AMBIENT_FLAGS:
            del os.environ[name]


# Run at collection import time (before any test module import can cache a
# flag read); tests that need a flag set it explicitly via monkeypatch.
_strip_ambient_flags()
