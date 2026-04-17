"""Dispatcher: ownership enforcement and basic resolution."""

from __future__ import annotations

import uuid

from agents.general.file_tools import resolve_attachment
from conftest import _persist, make_png


def test_resolve_requires_user_id(repo, upload_root):
    aid = _persist(repo, user_id="alice", filename="x.png",
                   category="image", extension="png",
                   content_type="image/png", upload_root=upload_root,
                   payload=make_png())
    att, path, err = resolve_attachment(aid, user_id=None)
    assert att is None and path is None
    assert err["error"]["code"] == "not_found"


def test_resolve_rejects_foreign_user(repo, upload_root):
    aid = _persist(repo, user_id="alice", filename="x.png",
                   category="image", extension="png",
                   content_type="image/png", upload_root=upload_root,
                   payload=make_png())
    att, path, err = resolve_attachment(aid, user_id="bob")
    assert att is None and err["error"]["code"] == "not_found"


def test_resolve_unknown_id(repo, upload_root):
    att, path, err = resolve_attachment(str(uuid.uuid4()), user_id="alice")
    assert att is None and err["error"]["code"] == "not_found"


def test_resolve_happy_path(repo, upload_root):
    aid = _persist(repo, user_id="alice", filename="x.png",
                   category="image", extension="png",
                   content_type="image/png", upload_root=upload_root,
                   payload=make_png())
    att, path, err = resolve_attachment(aid, user_id="alice")
    assert err is None
    assert att.attachment_id == aid
    assert path.exists()
