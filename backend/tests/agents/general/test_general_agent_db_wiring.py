"""Regression: the General Agent process wires the file_tools DB on startup.

The general agent runs as its OWN process (start.py subprocess), so the
orchestrator's register_database() never reaches it. If GeneralAgent.__init__
doesn't wire file_tools, every file reader (read_document/read_spreadsheet/…)
fast-fails with "no Database wired" — the upload parses fine but the reader tool
errors. This guards that wiring.
"""
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _can_connect():
    try:
        import psycopg2
        from shared.database import _build_database_url
        psycopg2.connect(_build_database_url()).close()
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _can_connect(), reason="Postgres unavailable")


@needs_db
def test_general_agent_init_wires_file_tools_db():
    from agents.general import file_tools

    # Simulate a fresh process: no DB wired yet.
    saved_resolved, saved_override = file_tools._RESOLVED_DB, file_tools._DB_OVERRIDE
    file_tools._RESOLVED_DB = None
    file_tools._DB_OVERRIDE = None
    try:
        from agents.general.general_agent import GeneralAgent
        GeneralAgent(port=18091)  # __init__ must wire file_tools as a side effect
        # _get_database() must now resolve without raising (the bug raised here).
        assert file_tools._get_database() is not None
    finally:
        file_tools._RESOLVED_DB, file_tools._DB_OVERRIDE = saved_resolved, saved_override
