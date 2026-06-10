# Shared modules for the orchestrator-agent system

import os as _os

# ---------------------------------------------------------------------------
# Env-name compatibility (2026-06-10): the auth variables lost their legacy
# VITE_ prefix in .env/.env.example (the React frontend that needed it is
# gone). Many backend call sites still read the old names — and some read
# them at import time — so normalize BOTH directions here, before any other
# backend module loads. New names win when both are set.
#   USE_MOCK_AUTH        <-> VITE_USE_MOCK_AUTH
#   KEYCLOAK_AUTHORITY   <-> VITE_KEYCLOAK_AUTHORITY
#   KEYCLOAK_CLIENT_ID   <-> VITE_KEYCLOAK_CLIENT_ID
# ---------------------------------------------------------------------------
for _new, _old in (
    ("USE_MOCK_AUTH", "VITE_USE_MOCK_AUTH"),
    ("KEYCLOAK_AUTHORITY", "VITE_KEYCLOAK_AUTHORITY"),
    ("KEYCLOAK_CLIENT_ID", "VITE_KEYCLOAK_CLIENT_ID"),
):
    if _os.getenv(_new):
        _os.environ[_old] = _os.environ[_new]
    elif _os.getenv(_old):
        _os.environ[_new] = _os.environ[_old]
del _new, _old, _os

from .progress import ProgressEvent, ProgressPhase, ProgressStep, ProgressEmitter, create_log_event  # noqa: E402
