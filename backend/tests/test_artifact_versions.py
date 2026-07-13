"""Feature 055 (US4) — component version history store (research D10, FR-024).

Exercises backend/orchestrator/artifact_versions.py against a real Postgres:
monotonic version numbering, archive-time pruning to the newest RETAIN rows,
bounded metadata listing, full-dict retrieval, (chat_id, user_id) ownership
scoping, the async twins, and the deletion cascades wired into
WorkspaceManager.remove, HistoryManager.delete_component and
HistoryManager.delete_chat.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from orchestrator import artifact_versions as av  # noqa: E402
from orchestrator.workspace import WorkspaceManager  # noqa: E402


def _can_connect_to_db() -> bool:
    try:
        import psycopg2
        from shared.database import _build_database_url

        conn = psycopg2.connect(_build_database_url())
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect_to_db(),
    reason="Postgres unavailable in this environment",
)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def history(tmp_path_factory):
    from orchestrator.history import HistoryManager

    return HistoryManager(data_dir=str(tmp_path_factory.mktemp("av-data")))


@pytest.fixture(scope="module")
def ws(history):
    return WorkspaceManager(history)


@pytest.fixture
def chat(history):
    """A fresh chat with a unique user per test; delete_chat sweeps versions."""
    user_id = f"pytest-av-{uuid.uuid4().hex[:12]}"
    chat_id = history.create_chat(user_id=user_id)
    yield chat_id, user_id
    history.delete_chat(chat_id, user_id)


def _comp(n: int, **extra):
    c = {"type": "card", "title": f"Version {n}", "body": f"content v{n}"}
    c.update(extra)
    return c


def _raw_count(db, chat_id: str, component_id: str | None = None) -> int:
    """Physical row count, unscoped by user — proves deletion, not filtering."""
    if component_id:
        row = db.fetch_one(
            "SELECT COUNT(*) AS count FROM component_version "
            "WHERE chat_id = ? AND component_id = ?",
            (chat_id, component_id),
        )
    else:
        row = db.fetch_one(
            "SELECT COUNT(*) AS count FROM component_version WHERE chat_id = ?",
            (chat_id,),
        )
    return int(row["count"])


# ----------------------------------------------------------------------
# archive()
# ----------------------------------------------------------------------


def test_archive_assigns_monotonic_version_numbers(history, chat):
    chat_id, user_id = chat
    cid = "wc_avtest000000001"
    assert av.archive(history.db, chat_id, user_id, cid, _comp(1)) == 1
    assert av.archive(history.db, chat_id, user_id, cid, _comp(2)) == 2
    assert av.archive(history.db, chat_id, user_id, cid, _comp(3), reason="restore") == 3


def test_archive_numbering_is_per_component(history, chat):
    chat_id, user_id = chat
    assert av.archive(history.db, chat_id, user_id, "wc_avtest_a", _comp(1)) == 1
    assert av.archive(history.db, chat_id, user_id, "wc_avtest_b", _comp(1)) == 1
    assert av.archive(history.db, chat_id, user_id, "wc_avtest_a", _comp(2)) == 2


def test_archive_rejects_invalid_args(history, chat):
    chat_id, user_id = chat
    with pytest.raises(ValueError):
        av.archive(history.db, "", user_id, "wc_x", _comp(1))
    with pytest.raises(ValueError):
        av.archive(history.db, chat_id, "", "wc_x", _comp(1))
    with pytest.raises(ValueError):
        av.archive(history.db, chat_id, user_id, "", _comp(1))
    with pytest.raises(ValueError):
        av.archive(history.db, chat_id, user_id, "wc_x", "not-a-dict")
    with pytest.raises(ValueError):
        av.archive(history.db, chat_id, user_id, "wc_x", _comp(1), reason="undo")


def test_retention_prunes_to_newest_five(history, chat):
    """FR-024: at most RETAIN (=5) versions survive per component."""
    chat_id, user_id = chat
    cid = "wc_avtest_prune01"
    for n in range(1, 8):
        av.archive(history.db, chat_id, user_id, cid, _comp(n))
    versions = av.list_versions(history.db, chat_id, user_id, cid)
    assert [v["version_no"] for v in versions] == [7, 6, 5, 4, 3]
    assert av.get_version(history.db, chat_id, user_id, cid, 1) is None
    assert av.get_version(history.db, chat_id, user_id, cid, 2) is None
    assert av.get_version(history.db, chat_id, user_id, cid, 3) is not None
    assert _raw_count(history.db, chat_id, cid) == av.RETAIN


# ----------------------------------------------------------------------
# list_versions() / get_version()
# ----------------------------------------------------------------------


def test_list_versions_metadata_only_and_bounded(history, chat):
    chat_id, user_id = chat
    cid = "wc_avtest_list001"
    av.archive(history.db, chat_id, user_id, cid, _comp(1))
    av.archive(history.db, chat_id, user_id, cid, _comp(2), reason="restore")
    versions = av.list_versions(history.db, chat_id, user_id, cid)
    assert len(versions) == 2
    newest = versions[0]
    assert newest["version_no"] == 2
    assert newest["reason"] == "restore"
    assert newest["title"] == "Version 2"
    assert newest["component_type"] == "card"
    assert isinstance(newest["created_at"], str)  # wire-ready ISO string
    assert "component" not in newest  # metadata only, no payloads
    # explicit limit respected; oversized/garbage limits clamp to RETAIN
    assert len(av.list_versions(history.db, chat_id, user_id, cid, limit=1)) == 1
    assert len(av.list_versions(history.db, chat_id, user_id, cid, limit=999)) == 2
    assert len(av.list_versions(history.db, chat_id, user_id, cid, limit="junk")) == 2
    assert av.list_versions(history.db, chat_id, user_id, "") == []


def test_get_version_roundtrips_component_dict(history, chat):
    chat_id, user_id = chat
    cid = "wc_avtest_get0001"
    original = _comp(1, component_id=cid, _source_agent="agentX", _source_tool="toolY")
    av.archive(history.db, chat_id, user_id, cid, original)
    got = av.get_version(history.db, chat_id, user_id, cid, 1)
    assert got is not None
    assert got["component"] == original
    assert got["version_no"] == 1
    assert got["reason"] == "refine"
    assert got["chat_id"] == chat_id
    assert got["component_id"] == cid
    assert av.get_version(history.db, chat_id, user_id, cid, 2) is None
    assert av.get_version(history.db, chat_id, user_id, cid, "junk") is None


def test_reads_and_deletes_are_user_scoped(history, chat):
    """Ownership: another user sees nothing and can delete nothing."""
    chat_id, user_id = chat
    cid = "wc_avtest_scope01"
    av.archive(history.db, chat_id, user_id, cid, _comp(1))
    intruder = f"pytest-av-intruder-{uuid.uuid4().hex[:8]}"
    assert av.list_versions(history.db, chat_id, intruder, cid) == []
    assert av.get_version(history.db, chat_id, intruder, cid, 1) is None
    assert av.delete_for_component(history.db, chat_id, intruder, cid) == 0
    assert av.delete_for_chat(history.db, chat_id, intruder) == 0
    assert av.get_version(history.db, chat_id, user_id, cid, 1) is not None


def test_delete_helpers_return_row_counts(history, chat):
    chat_id, user_id = chat
    av.archive(history.db, chat_id, user_id, "wc_avtest_del_a", _comp(1))
    av.archive(history.db, chat_id, user_id, "wc_avtest_del_a", _comp(2))
    av.archive(history.db, chat_id, user_id, "wc_avtest_del_b", _comp(1))
    assert av.delete_for_component(history.db, chat_id, user_id, "wc_avtest_del_a") == 2
    assert av.delete_for_component(history.db, chat_id, user_id, "wc_avtest_del_a") == 0
    assert av.delete_for_chat(history.db, chat_id, user_id) == 1
    assert _raw_count(history.db, chat_id) == 0


# ----------------------------------------------------------------------
# Deletion cascades
# ----------------------------------------------------------------------


def test_workspace_remove_cascades_versions(history, ws, chat):
    chat_id, user_id = chat
    ops = ws.upsert(chat_id, user_id, [{
        "type": "card", "title": "Live",
        "_source_agent": "agentX", "_source_tool": "toolY",
        "_source_params": {"q": 1},
    }])
    cid = ops[0]["component_id"]
    av.archive(history.db, chat_id, user_id, cid, _comp(1))
    av.archive(history.db, chat_id, user_id, cid, _comp(2))
    assert ws.remove(chat_id, user_id, cid) is True
    assert _raw_count(history.db, chat_id, cid) == 0


def test_history_delete_component_cascades_versions(history, ws, chat):
    """The WS/REST delete verb path (row-uuid keyed) sweeps version rows."""
    chat_id, user_id = chat
    ops = ws.upsert(chat_id, user_id, [{
        "type": "card", "title": "Live",
        "_source_agent": "agentX", "_source_tool": "toolZ",
        "_source_params": {"q": 2},
    }])
    cid = ops[0]["component_id"]
    av.archive(history.db, chat_id, user_id, cid, _comp(1))
    row = history.db.fetch_one(
        "SELECT id FROM saved_components WHERE chat_id = ? AND component_id = ? AND user_id = ?",
        (chat_id, cid, user_id),
    )
    assert history.delete_component(row["id"], user_id=user_id) is True
    assert _raw_count(history.db, chat_id, cid) == 0


def test_delete_chat_cascades_versions(history):
    user_id = f"pytest-av-{uuid.uuid4().hex[:12]}"
    chat_id = history.create_chat(user_id=user_id)
    av.archive(history.db, chat_id, user_id, "wc_avtest_chatdel", _comp(1))
    av.archive(history.db, chat_id, user_id, "wc_avtest_chatde2", _comp(1))
    assert _raw_count(history.db, chat_id) == 2
    history.delete_chat(chat_id, user_id)
    assert _raw_count(history.db, chat_id) == 0


# ----------------------------------------------------------------------
# Async twins (loop-guard-safe: only a*-functions touch the DB here)
# ----------------------------------------------------------------------


async def test_async_twins_cover_full_cycle(history, chat):
    chat_id, user_id = chat
    cid = "wc_avtest_async01"
    assert await av.aarchive(history.db, chat_id, user_id, cid, _comp(1)) == 1
    assert await av.aarchive(history.db, chat_id, user_id, cid, _comp(2), "restore") == 2
    versions = await av.alist_versions(history.db, chat_id, user_id, cid)
    assert [v["version_no"] for v in versions] == [2, 1]
    got = await av.aget_version(history.db, chat_id, user_id, cid, 1)
    assert got is not None and got["component"]["title"] == "Version 1"
    assert await av.adelete_for_component(history.db, chat_id, user_id, cid) == 2
    assert await av.adelete_for_chat(history.db, chat_id, user_id) == 0
    count = await asyncio.to_thread(_raw_count, history.db, chat_id, cid)
    assert count == 0
