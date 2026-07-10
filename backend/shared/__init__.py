# Shared modules for the orchestrator-agent system

import os as _os

# ---------------------------------------------------------------------------
# Legacy env-name shim (054 cleanup): every backend call site now reads the
# unprefixed names — the React-era VITE_ aliases are retired. A deployment
# whose .env still sets a VITE_-prefixed value gets it copied to the real
# name (unprefixed wins when both are set) with a deprecation warning, so
# old host configs don't silently break. Remove the shim once no deployed
# .env carries the old names.
#   VITE_USE_MOCK_AUTH        -> USE_MOCK_AUTH
#   VITE_KEYCLOAK_AUTHORITY   -> KEYCLOAK_AUTHORITY
#   VITE_KEYCLOAK_CLIENT_ID   -> KEYCLOAK_CLIENT_ID
# ---------------------------------------------------------------------------
for _new, _old in (
    ("USE_MOCK_AUTH", "VITE_USE_MOCK_AUTH"),
    ("KEYCLOAK_AUTHORITY", "VITE_KEYCLOAK_AUTHORITY"),
    ("KEYCLOAK_CLIENT_ID", "VITE_KEYCLOAK_CLIENT_ID"),
):
    if not _os.getenv(_new) and _os.getenv(_old):
        import logging as _logging
        _logging.getLogger("shared.env").warning(
            "%s is deprecated — rename it to %s in your .env", _old, _new)
        _os.environ[_new] = _os.environ[_old]
del _new, _old, _os

from .progress import ProgressEvent, ProgressPhase, ProgressStep, ProgressEmitter, create_log_event  # noqa: E402

__all__ = [
    "ProgressEvent",
    "ProgressPhase",
    "ProgressStep",
    "ProgressEmitter",
    "create_log_event",
]
