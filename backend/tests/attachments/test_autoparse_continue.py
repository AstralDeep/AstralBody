"""031 T031 — auto-continue the original turn once a parser goes live."""
import asyncio
import sys
import types
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from orchestrator import attachment_autoparse  # noqa: E402


class _FakeDB:
    def __init__(self, link=True, content="summarize this file"):
        self._link = link
        self._content = content

    def fetch_one(self, query, params):
        if "message_attachment" in query:
            return {"message_id": "m1"} if self._link else None
        if "FROM messages" in query:
            return {"content": self._content}
        return None


class _Att:
    filename = "data.xyz"
    category = "data"
    attachment_id = "a1"


def _orch(db, calls):
    async def handle_chat_message(ws, message, chat_id, *, user_id=None, attachments=None, **kw):
        calls.append({"message": message, "chat_id": chat_id,
                      "user_id": user_id, "attachments": attachments})

    return types.SimpleNamespace(
        history=types.SimpleNamespace(db=db),
        handle_chat_message=handle_chat_message,
    )


def _patch_repo(monkeypatch):
    import orchestrator.attachments.repository as repo_mod
    monkeypatch.setattr(repo_mod, "AttachmentRepository",
                        lambda db: types.SimpleNamespace(get_by_id=lambda aid, uid: _Att()))


def test_auto_continue_replays_original_turn(monkeypatch):
    _patch_repo(monkeypatch)
    calls = []
    orch = _orch(_FakeDB(link=True), calls)
    ok = asyncio.run(attachment_autoparse.auto_continue_after_go_live(
        orch, requested_by="u1", source_chat_id="c1", source_attachment_id="a1",
        extension="xyz", category="data"))
    assert ok is True
    assert len(calls) == 1
    assert calls[0]["message"] == "summarize this file"  # original (un-augmented) text
    assert calls[0]["chat_id"] == "c1"
    assert calls[0]["user_id"] == "u1"
    assert calls[0]["attachments"][0]["attachment_id"] == "a1"


def test_auto_continue_returns_false_when_no_link(monkeypatch):
    _patch_repo(monkeypatch)
    calls = []
    orch = _orch(_FakeDB(link=False), calls)
    ok = asyncio.run(attachment_autoparse.auto_continue_after_go_live(
        orch, requested_by="u1", source_chat_id="c1", source_attachment_id="a1",
        extension="xyz", category="data"))
    assert ok is False
    assert calls == []


def test_auto_continue_returns_false_on_missing_args():
    ok = asyncio.run(attachment_autoparse.auto_continue_after_go_live(
        None, requested_by=None, source_chat_id=None, source_attachment_id=None,
        extension="x", category="data"))
    assert ok is False
