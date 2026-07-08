"""Feature 052 — every async twin runs its sync counterpart off the loop.

One await per ``a*`` facade method across WorkspaceManager, WebSessionStore
and the attachment repositories, against the live dev Postgres. All rows are
namespaced per-test and deleted on teardown. Sync setup happens in sync
fixtures (no running loop), so the suite's event-loop guard stays quiet even
in enforce mode.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import psycopg2  # noqa: F401
    from shared.database import Database
except Exception:  # pragma: no cover - import guard
    Database = None  # type: ignore


def _db_or_skip():
    """Return a connected Database or skip the test."""
    if Database is None:
        pytest.skip("psycopg2/shared.database unavailable")
    try:
        return Database()
    except Exception as exc:  # pragma: no cover - no DB in this env
        pytest.skip(f"database unreachable: {exc}")


@pytest.fixture()
def chat_env():
    """Real HistoryManager + unique user/chat, deleted on teardown."""
    _db_or_skip()
    from orchestrator.history import HistoryManager
    history = HistoryManager()
    user_id = f"twin-user-{uuid.uuid4()}"
    chat_id = history.create_chat(user_id=user_id)
    yield history, user_id, chat_id
    history.delete_chat(chat_id, user_id=user_id)


async def test_workspace_async_twins_cover_the_sync_surface(chat_env):
    from orchestrator.workspace import WorkspaceManager
    history, user_id, chat_id = chat_env
    ws = WorkspaceManager(history)
    comp = {"type": "metric", "title": "Twin", "value": "1",
            "_source_agent": "agent-t", "_source_tool": "tool-t",
            "_source_params": {}}

    ops = await ws.aupsert(chat_id, user_id, [comp])
    cid = ops[0]["component_id"]

    rows = await ws.alive_rows(chat_id, user_id)
    assert [r["component_id"] for r in rows] == [cid]
    comps = await ws.alive_components(chat_id, user_id)
    assert comps[0]["component_id"] == cid
    got = await ws.aget_by_component_id(chat_id, user_id, cid)
    assert got is not None

    assert await ws.aupsert_layout(
        chat_id, user_id, "lk_test",
        [{"type": "ref", "component_id": cid}]) is True
    layouts = await ws.alive_layouts(chat_id, user_id)
    assert layouts and layouts[0]["layout_key"] == "lk_test"

    snap_id = await ws.asnapshot(chat_id, user_id, "twin-test")
    assert snap_id is not None
    snaps = await ws.alist_snapshots(chat_id, user_id)
    assert any(s["id"] == snap_id for s in snaps)
    assert await ws.acount_snapshots(chat_id, user_id) >= 1
    snap = await ws.aget_snapshot(snap_id, user_id)
    assert snap is not None and snap["chat_id"] == chat_id

    assert await ws.aremove(chat_id, user_id, cid) is True
    assert await ws.alive_components(chat_id, user_id) == []


@pytest.fixture()
def session_env(monkeypatch):
    """A dev-mode WebSessionStore + namespaced ids, cleaned on teardown."""
    db = _db_or_skip()
    monkeypatch.setenv("ASTRAL_ENV", "development")
    from orchestrator.session_store import WebSessionStore
    store = WebSessionStore(db)
    sid = f"twin-sid-{uuid.uuid4()}"
    user_id = f"twin-user-{uuid.uuid4()}"
    yield store, sid, user_id
    db.execute("DELETE FROM web_session WHERE sid = ?", (sid,))
    db.execute("DELETE FROM auth_revocation_queue WHERE user_id = ?", (user_id,))


async def test_session_store_async_twins_cover_the_sync_surface(session_env):
    store, sid, user_id = session_env
    row = await store.acreate(
        sid, user_id=user_id, access_token="at", refresh_token="rt",
        hard_max_seconds=3600)
    assert row["sid"] == sid

    got = await store.aget(sid)
    assert got is not None and got["user_id"] == user_id

    await store.aupdate_tokens(sid, access_token="at2", refresh_token="rt2")
    await store.amark_resumed(sid, True)
    assert (await store.aget(sid))["resumed"] is True

    deleted = await store.adelete(sid)
    assert deleted is not None
    assert await store.adelete_for_user(user_id) == 0
    assert isinstance(await store.apurge_expired(), int)

    await store.aenqueue_revocation(user_id, "rt-orphan", client_id="astral-web")
    pending = await store.apending_revocations(limit=500)
    mine = [p for p in pending if p["user_id"] == user_id]
    assert mine and mine[0]["client_id"] == "astral-web"
    await store.aresolve_revocation(mine[0]["id"])


@pytest.fixture()
def attachment_env():
    """Live-DB attachment repositories + namespaced ids, cleaned on teardown."""
    db = _db_or_skip()
    user_id = f"twin-att-user-{uuid.uuid4()}"
    att_id = str(uuid.uuid4())
    yield db, user_id, att_id
    db.execute("DELETE FROM message_attachment WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM user_attachments WHERE user_id = ?", (user_id,))


async def test_attachment_repository_async_twins(attachment_env):
    from orchestrator.attachments.repository import AttachmentRepository
    db, user_id, att_id = attachment_env
    repo = AttachmentRepository(db)

    att = await repo.ainsert(
        attachment_id=att_id, user_id=user_id, filename="twin.md",
        content_type="text/markdown", category="text", extension="md",
        size_bytes=4, sha256="0" * 64, storage_path=f"{user_id}/twin.md")
    assert att.attachment_id == att_id

    got = await repo.aget_by_id(att_id, user_id)
    assert got is not None and got.filename == "twin.md"

    listed, cursor = await repo.alist_for_user(user_id, limit=10)
    assert [a.attachment_id for a in listed] == [att_id]

    assert await repo.asoft_delete(att_id, user_id) is True
    assert await repo.asoft_delete_all_for_user(user_id) == 0


async def test_message_attachment_repo_async_twins(attachment_env):
    from orchestrator.attachments.message_attachment_repo import (
        MessageAttachmentRepository,
    )
    db, user_id, att_id = attachment_env
    repo = MessageAttachmentRepository(db)
    chat_id = f"twin-chat-{uuid.uuid4()}"

    link_id = await repo.ainsert(
        chat_id=chat_id, attachment_id=att_id, user_id=user_id,
        message_id="m-twin-1")
    assert link_id

    for_chat = await repo.alist_for_chat(chat_id, user_id)
    assert [r["id"] for r in for_chat] == [link_id]
    for_message = await repo.alist_for_message("m-twin-1", user_id)
    assert [r["attachment_id"] for r in for_message] == [att_id]


@pytest.fixture()
def parser_env():
    """Live-DB parser registry repo + namespaced gap, cleaned on teardown."""
    db = _db_or_skip()
    gap = f"twin-gap-{uuid.uuid4()}"
    yield db, gap
    db.execute("DELETE FROM attachment_parser WHERE gap_fingerprint = ?", (gap,))


async def test_parser_repo_async_twins(parser_env):
    from orchestrator.attachments.parser_repo import (
        STATUS_FAILED,
        STATUS_LIVE,
        AttachmentParserRepository,
    )
    db, gap = parser_env
    repo = AttachmentParserRepository(db)
    draft_id = f"twin-draft-{uuid.uuid4().hex[:12]}"

    row = await repo.acreate_pending(
        gap_fingerprint=gap, category="data", extension="xyz",
        draft_agent_id=draft_id, source_attachment_id=None,
        source_chat_id=None, requested_by="twin-user")
    assert row["gap_fingerprint"] == gap

    assert (await repo.aget_by_gap(gap))["id"] == row["id"]
    assert (await repo.aget_by_draft(draft_id))["id"] == row["id"]

    await repo.amark_live(gap, live_agent_id="xyz-parser-1",
                          tool_name="read_xyz", approved_by="admin")
    assert (await repo.aget_by_gap(gap))["status"] == STATUS_LIVE

    await repo.amark_status(gap, STATUS_FAILED)
    failed = await repo.alist_by_status(STATUS_FAILED)
    assert any(r["gap_fingerprint"] == gap for r in failed)
