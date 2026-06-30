"""Feature 040 (US3) — etf_tracker_1 retirement.

Verifies the agent is removed from every surface (directory, first-party public
catalog, retirement sets, history glyphs, knowledge index) and that the
idempotent ``_init_db`` cleanup purges orphaned permission/ownership rows for
the retired id without error on re-run.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Static surface checks (no DB) — FR-017
# ---------------------------------------------------------------------------

def test_etf_agent_directory_removed():
    assert not (BACKEND_DIR / "agents" / "etf_tracker_1").exists()


def test_etf_not_in_first_party_public_catalog():
    from shared.database import Database
    assert "etf-tracker-1-1" not in Database._FIRST_PARTY_PUBLIC_AGENT_IDS


def test_etf_in_retired_agent_ids():
    from orchestrator.orchestrator import RETIRED_AGENT_IDS
    assert "etf-tracker-1-1" in RETIRED_AGENT_IDS
    assert "etf_tracker_1" in RETIRED_AGENT_IDS


def test_etf_knowledge_stem_retired():
    from orchestrator.knowledge_synthesis import RETIRED_KNOWLEDGE_STEMS
    assert "etf_tracker" in RETIRED_KNOWLEDGE_STEMS


def test_etf_history_icon_removed():
    from orchestrator.history_surface import _AGENT_ICONS
    assert "etf_tracker_1" not in _AGENT_ICONS


# ---------------------------------------------------------------------------
# DB-backed idempotent cleanup — FR-018
# ---------------------------------------------------------------------------

def _can_connect_to_db() -> bool:
    try:
        import psycopg2
        from shared.database import _build_database_url

        conn = psycopg2.connect(_build_database_url())
        conn.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _can_connect_to_db(), reason="Postgres unavailable in this environment")
def test_etf_orphan_rows_purged_idempotently():
    from orchestrator.history import HistoryManager

    history = HistoryManager(data_dir=f"/tmp/etf-test-{uuid.uuid4().hex[:8]}")
    db = history.db

    # Seed an orphaned ownership row for the retired agent.
    db.set_agent_ownership("etf-tracker-1-1", "pytest-etf@example.com", is_public=True)
    assert db.get_agent_ownership("etf-tracker-1-1"), "precondition: row seeded"

    # First boot runs _cleanup_retired_agents_040 → row purged.
    db._init_db()
    assert not db.get_agent_ownership("etf-tracker-1-1"), "orphan row purged on boot"

    # Re-run is a no-op (Constitution IX idempotency).
    db._init_db()
    assert not db.get_agent_ownership("etf-tracker-1-1"), "idempotent on re-run"
