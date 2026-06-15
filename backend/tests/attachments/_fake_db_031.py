"""In-memory fake Database for Feature 031 repository/wiring tests.

Recognizes exactly the queries issued by AttachmentRepository,
MessageAttachmentRepository, and AttachmentParserRepository (``?`` placeholder
dialect) and serves them from per-table lists of dicts. Mirrors the approach in
``conftest.StubDatabase`` but extends coverage to the two new tables.
"""

from __future__ import annotations

from typing import List, Optional, Tuple


class _Cursor:
    def __init__(self, rowcount: int = 0):
        self.rowcount = rowcount


class FakeDB:
    def __init__(self) -> None:
        self.user_attachments: List[dict] = []
        self.message_attachment: List[dict] = []
        self.attachment_parser: List[dict] = []

    # -- writes -------------------------------------------------------------
    def execute(self, query: str, params: Tuple = ()) -> _Cursor:
        q = " ".join(query.split()).lower()
        if q.startswith("insert into user_attachments"):
            (aid, uid, fn, ctype, cat, ext, size, sha, path, created) = params
            self.user_attachments.append({
                "attachment_id": aid, "user_id": uid, "filename": fn,
                "content_type": ctype, "category": cat, "extension": ext,
                "size_bytes": size, "sha256": sha, "storage_path": path,
                "created_at": created, "deleted_at": None,
            })
            return _Cursor(1)
        if q.startswith("insert into message_attachment"):
            (rid, chat_id, message_id, aid, uid, created) = params
            self.message_attachment.append({
                "id": rid, "chat_id": chat_id, "message_id": message_id,
                "attachment_id": aid, "user_id": uid, "created_at": created,
            })
            return _Cursor(1)
        if q.startswith("insert into attachment_parser"):
            (rid, ext, cat, gap, status, draft_id, src_att, src_chat,
             requested_by, created, updated) = params
            self.attachment_parser.append({
                "id": rid, "extension": ext, "category": cat,
                "gap_fingerprint": gap, "status": status,
                "draft_agent_id": draft_id, "live_agent_id": None,
                "tool_name": None, "source_attachment_id": src_att,
                "source_chat_id": src_chat, "requested_by": requested_by,
                "approved_by": None, "created_at": created, "updated_at": updated,
            })
            return _Cursor(1)
        if q.startswith("update attachment_parser") and "set status = ?, live_agent_id" in q:
            status, live_id, tool, approved, updated, gap = params
            for r in self.attachment_parser:
                if r["gap_fingerprint"] == gap:
                    r.update(status=status, live_agent_id=live_id, tool_name=tool,
                             approved_by=approved, updated_at=updated)
            return _Cursor(1)
        if q.startswith("update attachment_parser") and "set status = ?, updated_at" in q:
            status, updated, gap = params
            for r in self.attachment_parser:
                if r["gap_fingerprint"] == gap:
                    r.update(status=status, updated_at=updated)
            return _Cursor(1)
        raise NotImplementedError(query)

    # -- reads --------------------------------------------------------------
    def fetch_one(self, query: str, params: Tuple = ()) -> Optional[dict]:
        q = " ".join(query.split()).lower()
        if "from user_attachments where attachment_id = ? and user_id = ? and deleted_at is null" in q:
            aid, uid = params
            for r in self.user_attachments:
                if r["attachment_id"] == aid and r["user_id"] == uid and r["deleted_at"] is None:
                    return dict(r)
            return None
        if "from user_attachments where attachment_id = ?" in q:
            (aid,) = params
            for r in self.user_attachments:
                if r["attachment_id"] == aid:
                    return dict(r)
            return None
        if "from attachment_parser where gap_fingerprint = ?" in q:
            (gap,) = params
            for r in self.attachment_parser:
                if r["gap_fingerprint"] == gap:
                    return dict(r)
            return None
        if "from attachment_parser where draft_agent_id = ?" in q:
            (did,) = params
            for r in self.attachment_parser:
                if r["draft_agent_id"] == did:
                    return dict(r)
            return None
        raise NotImplementedError(query)

    def fetch_all(self, query: str, params: Tuple = ()) -> List[dict]:
        q = " ".join(query.split()).lower()
        if "from message_attachment where message_id = ? and user_id = ?" in q:
            mid, uid = params
            rows = [r for r in self.message_attachment if r["message_id"] == mid and r["user_id"] == uid]
            return [dict(r) for r in sorted(rows, key=lambda r: r["created_at"])]
        if "from message_attachment where chat_id = ? and user_id = ?" in q:
            cid, uid = params
            rows = [r for r in self.message_attachment if r["chat_id"] == cid and r["user_id"] == uid]
            return [dict(r) for r in sorted(rows, key=lambda r: r["created_at"])]
        if "from attachment_parser where status = ?" in q:
            (status,) = params
            rows = [r for r in self.attachment_parser if r["status"] == status]
            return [dict(r) for r in sorted(rows, key=lambda r: r["created_at"], reverse=True)]
        raise NotImplementedError(query)
