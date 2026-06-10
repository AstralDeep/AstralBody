"""Env-name compatibility: the VITE_ prefix was dropped from the auth vars
in .env (2026-06-10); ``shared/__init__`` aliases both directions so every
legacy read site keeps working. Exercised in a clean subprocess because the
normalization runs at first import of ``shared``."""
import os
import subprocess
import sys
from pathlib import Path

BACKEND = str(Path(__file__).resolve().parents[1])

_PROBE = (
    "import shared, os;"
    "print(os.getenv('VITE_USE_MOCK_AUTH'), os.getenv('USE_MOCK_AUTH'),"
    "      os.getenv('VITE_KEYCLOAK_AUTHORITY'), os.getenv('KEYCLOAK_CLIENT_ID'))"
)


def _probe(env_overrides):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("VITE_", "USE_MOCK", "KEYCLOAK"))}
    env.update(env_overrides)
    env["PYTHONPATH"] = BACKEND
    out = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True,
                         text=True, env=env, cwd=BACKEND)
    assert out.returncode == 0, out.stderr
    return out.stdout.split()


def test_new_names_backfill_legacy_readers():
    vals = _probe({"USE_MOCK_AUTH": "true",
                   "KEYCLOAK_AUTHORITY": "https://kc.example/realms/x",
                   "KEYCLOAK_CLIENT_ID": "astral-frontend"})
    assert vals[0] == "true"            # VITE_USE_MOCK_AUTH backfilled
    assert vals[2] == "https://kc.example/realms/x"


def test_legacy_names_backfill_new_readers():
    vals = _probe({"VITE_USE_MOCK_AUTH": "true",
                   "VITE_KEYCLOAK_AUTHORITY": "https://old.example",
                   "VITE_KEYCLOAK_CLIENT_ID": "legacy-client"})
    assert vals[1] == "true"            # USE_MOCK_AUTH backfilled
    assert vals[3] == "legacy-client"   # KEYCLOAK_CLIENT_ID backfilled


def test_new_name_wins_when_both_set():
    vals = _probe({"USE_MOCK_AUTH": "false", "VITE_USE_MOCK_AUTH": "true"})
    assert vals[0] == "false" and vals[1] == "false"
