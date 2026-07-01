"""Feature 044 (US4, T043–T046) — Windows chat attachments.

Covers the stdlib multipart upload helper, the parser-status → chip-glyph
mapping, staging a chip via `attach_existing`, the upload-result signal handler,
mapping ready chips into the chat payload on send, and transcript rehydration.

Uses the `win` fixture pattern from test_message_routing (stub OrchestratorClient
+ _start_integrity_check + _init_workspace) so no socket/thread/workspace runs.
"""
import os
import urllib.error

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ASTRAL_WIN_AGENT"] = "0"  # don't spawn the client-hosted tools agent

from astral_client import app as appmod  # noqa: E402
from astral_client.app import MainWindow, parser_status_glyph  # noqa: E402
from astral_client.rest import RestError, upload_attachment  # noqa: E402


class _FakeResp:
    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n: int = -1) -> bytes:
        return self._data


class _RecordingClient:
    """Stands in for OrchestratorClient — records send_event / send_chat."""

    def __init__(self, *a, **k):
        self.events = []
        self.chats = []

    class _Sig:
        def connect(self, *_a):
            pass

    message = _Sig()
    status = _Sig()

    def start(self):
        pass

    def stop(self):
        pass

    def send_event(self, action, payload, session_id=None):
        self.events.append((action, payload, session_id))

    def send_chat(self, message, chat_id=None, attachments=None):
        self.chats.append({"message": message, "chat_id": chat_id, "attachments": attachments})


@pytest.fixture
def win(qapp, monkeypatch):
    monkeypatch.setattr(appmod, "OrchestratorClient", _RecordingClient)
    monkeypatch.setattr(MainWindow, "_start_integrity_check", lambda self: None)
    monkeypatch.setattr(MainWindow, "_init_workspace", lambda self: None)
    w = MainWindow("ws://127.0.0.1:9/ws", "dev-token")
    yield w
    w.close()


# --- T043: upload_attachment (stdlib multipart, injected opener) ------------

def test_upload_attachment_multipart_and_parse():
    seen = {}

    def opener(req, timeout=None):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        seen["ctype"] = req.get_header("Content-type")
        seen["body"] = req.data
        return _FakeResp(
            b'{"attachment_id":"att-1","filename":"a.csv",'
            b'"category":"data","parser_status":"preparing"}'
        )

    out = upload_attachment("http://h:8001/", "TOK", "a.csv", "text/csv",
                            b"col\n1\n", opener=opener)
    assert out["attachment_id"] == "att-1"
    assert out["category"] == "data" and out["parser_status"] == "preparing"
    assert seen["url"] == "http://h:8001/api/upload"
    assert seen["auth"] == "Bearer TOK"
    assert seen["ctype"].startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="a.csv"' in seen["body"]


def test_upload_attachment_error_raises():
    def opener(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 415, "Unsupported", {}, None)

    with pytest.raises(RestError) as ei:
        upload_attachment("http://h", "T", "f.bin", "application/octet-stream",
                          b"x", opener=opener)
    assert ei.value.status == 415


# --- T044: parser_status → chip glyph mapping -------------------------------

def test_parser_status_glyph_mapping():
    assert parser_status_glyph("covered") == ("✓", "ready")
    assert parser_status_glyph("preparing")[0] == "⏳"
    assert parser_status_glyph("pending_admin_approval")[0] == "⏳"
    assert "approval" in parser_status_glyph("pending_admin_approval")[1]
    assert parser_status_glyph("unavailable")[0] == "✗"
    assert parser_status_glyph(None) == ("•", "staged")


# --- T045: attach_existing stages a chip locally (never forwarded) ----------

def test_attach_existing_stages_chip_locally(win):
    win._emit("attach_existing",
              {"attachment_id": "att-9", "filename": "notes.txt", "category": "text"})
    assert len(win._attachments) == 1
    rec = win._attachments[0]
    assert rec["attachment_id"] == "att-9" and rec["status"] == "staged"
    assert not win._chips_bar.isHidden()          # strip is shown when non-empty
    # It is a client-side stage — NOT sent to the server.
    assert all(e[0] != "attach_existing" for e in win.client.events)


def test_attach_existing_dedupes_same_id(win):
    payload = {"attachment_id": "att-9", "filename": "notes.txt", "category": "text"}
    win._emit("attach_existing", payload)
    win._emit("attach_existing", dict(payload))
    assert len(win._attachments) == 1


def test_remove_chip(win):
    win._emit("attach_existing", {"attachment_id": "att-1", "filename": "a", "category": "file"})
    cid = win._attachments[0]["chip_id"]
    win._remove_chip(cid)
    assert win._attachments == []
    assert win._chips_bar.isHidden()              # strip hidden when empty


# --- upload-result signal handler flips the chip staged / failed ------------

def test_upload_result_marks_chip_staged(win):
    win._attachments = [{"chip_id": "k1", "attachment_id": None, "filename": "a.csv",
                         "category": "file", "parser_status": None, "status": "uploading"}]
    win._on_attachment_uploaded({"chip_id": "k1", "error": None, "result": {
        "attachment_id": "att-1", "filename": "a.csv",
        "category": "data", "parser_status": "covered"}})
    rec = win._attachments[0]
    assert rec["status"] == "staged" and rec["attachment_id"] == "att-1"
    assert rec["parser_status"] == "covered"


def test_upload_failure_marks_chip_failed(win):
    win._attachments = [{"chip_id": "k1", "attachment_id": None, "filename": "a.csv",
                         "category": "file", "parser_status": None, "status": "uploading"}]
    win._on_attachment_uploaded({"chip_id": "k1", "error": "boom", "result": None})
    assert win._attachments[0]["status"] == "failed"


# --- T046 / send: ready chips flow into the chat payload --------------------

def test_send_maps_ready_chips_into_payload(win):
    win._attachments = [
        {"chip_id": "k1", "attachment_id": "att-1", "filename": "a.csv",
         "category": "data", "parser_status": "covered", "status": "staged"},
        {"chip_id": "k2", "attachment_id": None, "filename": "b.csv",
         "category": "file", "parser_status": None, "status": "uploading"},
    ]
    win._input.setText("read this")
    win._send()
    assert win.client.chats, "no chat was sent"
    sent = win.client.chats[-1]
    assert sent["message"] == "read this"
    # only the staged chip flows through; the still-uploading one is excluded
    assert sent["attachments"] == [
        {"attachment_id": "att-1", "filename": "a.csv", "category": "data"}]
    assert win._attachments == []                 # strip cleared after send


def test_send_attachment_only_turn(win):
    win._attachments = [{"chip_id": "k1", "attachment_id": "att-1", "filename": "a.csv",
                         "category": "data", "parser_status": "covered", "status": "staged"}]
    win._input.setText("")
    win._send()
    sent = win.client.chats[-1]
    assert sent["message"] == ""
    assert sent["attachments"] == [
        {"attachment_id": "att-1", "filename": "a.csv", "category": "data"}]


def test_send_noop_without_text_or_ready_chips(win):
    win._attachments = [{"chip_id": "k1", "attachment_id": None, "filename": "x",
                         "category": "file", "parser_status": None, "status": "uploading"}]
    win._input.setText("")
    win._send()
    assert win.client.chats == []                 # nothing sendable


# --- T046: transcript rehydration shows an attachment note ------------------

def test_replay_transcript_shows_attachment_note(win):
    from PySide6.QtWidgets import QLabel

    win._replay_transcript({"id": "c1", "messages": [
        {"role": "user", "content": "here it is", "attachments": [
            {"attachment_id": "a1", "filename": "report.pdf", "category": "document"}]}]})
    texts = [w.text() for w in win.rail.findChildren(QLabel)]
    assert any("report.pdf" in t for t in texts)
