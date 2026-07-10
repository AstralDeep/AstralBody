"""Legacy env-name shim: the React-era VITE_ aliases are retired (054
cleanup) — every backend read site uses the unprefixed names. A deployment
whose .env still sets a VITE_-prefixed value gets it copied one-way to the
real name with a deprecation warning. Exercised in a clean subprocess
because the shim runs at first import of ``shared``."""
import os
import subprocess
import sys
from pathlib import Path

BACKEND = str(Path(__file__).resolve().parents[1])

_PROBE = (
    "import shared, os;"
    "print(os.getenv('USE_MOCK_AUTH'), os.getenv('KEYCLOAK_AUTHORITY'),"
    "      os.getenv('KEYCLOAK_CLIENT_ID'), os.getenv('VITE_USE_MOCK_AUTH'))"
)


def _probe(env_overrides):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("VITE_", "USE_MOCK", "KEYCLOAK"))}
    env.update(env_overrides)
    env["PYTHONPATH"] = BACKEND
    out = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True,
                         text=True, env=env, cwd=BACKEND)
    assert out.returncode == 0, out.stderr
    return out.stdout.split(), out.stderr


def test_unprefixed_names_pass_through_untouched():
    vals, stderr = _probe({"USE_MOCK_AUTH": "true",
                           "KEYCLOAK_AUTHORITY": "https://kc.example/realms/x",
                           "KEYCLOAK_CLIENT_ID": "astral-frontend"})
    assert vals[0] == "true"
    assert vals[1] == "https://kc.example/realms/x"
    assert vals[2] == "astral-frontend"
    assert vals[3] == "None"          # no reverse backfill of the VITE_ alias
    assert "deprecated" not in stderr


def test_legacy_vite_names_backfill_with_deprecation_warning():
    vals, stderr = _probe({"VITE_USE_MOCK_AUTH": "true",
                           "VITE_KEYCLOAK_AUTHORITY": "https://old.example",
                           "VITE_KEYCLOAK_CLIENT_ID": "legacy-client"})
    assert vals[0] == "true"           # USE_MOCK_AUTH backfilled from alias
    assert vals[1] == "https://old.example"
    assert vals[2] == "legacy-client"
    assert "deprecated" in stderr      # operator told to rename


def test_unprefixed_name_wins_when_both_set():
    vals, _ = _probe({"USE_MOCK_AUTH": "false", "VITE_USE_MOCK_AUTH": "true"})
    assert vals[0] == "false"
