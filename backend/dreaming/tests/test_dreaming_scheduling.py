"""030 — per-user recurring dreaming job registration (US4 / T028-T029)."""
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _can_connect():
    try:
        import psycopg2
        from shared.database import _build_database_url
        conn = psycopg2.connect(_build_database_url())
        conn.close()
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _can_connect(), reason="Postgres unavailable")


@pytest.fixture
def db():
    from shared.database import Database
    database = Database()
    user = f"pytest-dreaming-{uuid.uuid4().hex[:8]}"
    yield database, user
    try:
        database.execute("DELETE FROM scheduled_job WHERE user_id = ?", (user,))
    except Exception:
        pass


@needs_db
def test_ensure_creates_then_is_idempotent(db):
    from dreaming.scheduling import DREAMING_AGENT_ID, ensure_dreaming_job
    from scheduler.store import ScheduledJobStore
    database, user = db
    store = ScheduledJobStore(database)

    job = ensure_dreaming_job(database, user)
    assert job["agent_id"] == DREAMING_AGENT_ID
    assert job["schedule_kind"] == "cron"
    # idempotent: a second call returns the same active job (no duplicate)
    again = ensure_dreaming_job(database, user)
    assert again["id"] == job["id"]
    actives = [j for j in store.list_jobs(user)
               if j["agent_id"] == DREAMING_AGENT_ID and j["status"] == "active"]
    assert len(actives) == 1


@needs_db
def test_remove_then_resume(db):
    from dreaming.scheduling import (DREAMING_AGENT_ID, ensure_dreaming_job,
                                     remove_dreaming_job)
    from scheduler.store import ScheduledJobStore
    database, user = db
    store = ScheduledJobStore(database)

    created = ensure_dreaming_job(database, user)
    assert remove_dreaming_job(database, user) == 1
    actives = [j for j in store.list_jobs(user)
               if j["agent_id"] == DREAMING_AGENT_ID and j["status"] == "active"]
    assert actives == []
    # re-enable reactivates the SAME job rather than creating a duplicate
    resumed = ensure_dreaming_job(database, user)
    assert resumed["id"] == created["id"]
    assert resumed["status"] == "active"


@needs_db
def test_set_offline_grant(db):
    from scheduler.store import ScheduledJobStore
    database, user = db
    store = ScheduledJobStore(database)
    job = store.create_job(
        user, name="t", instruction="i", schedule_kind="interval", schedule_expr="1d",
        timezone="UTC", consented_scopes=[], agent_id=None, target_chat_id=None,
        next_run_at=None, offline_grant_id=None)
    assert job["offline_grant_id"] is None
    grant_id = str(uuid.uuid4())
    assert store.set_offline_grant(user, job["id"], grant_id) is True
    assert str(store.get_job(user, job["id"])["offline_grant_id"]) == grant_id
