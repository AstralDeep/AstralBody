"""Account-deletion hook: soft-deletes rows and removes blob dirs."""

from __future__ import annotations

import os

from orchestrator.attachments import store
from orchestrator.attachments.account_lifecycle import purge_user_attachments
from orchestrator.attachments.repository import AttachmentRepository


def _chunks(b: bytes):
    yield b


def test_purge_user_attachments_removes_rows_and_blobs(tmp_path, monkeypatch, stub_db):
    monkeypatch.setenv("ATTACHMENT_UPLOAD_ROOT", str(tmp_path))
    repo = AttachmentRepository(stub_db)

    # Insert two for alice, one for bob.
    for _ in range(2):
        repo.insert(
            attachment_id=f"alice-{_}",
            user_id="alice",
            filename="x.txt", content_type="text/plain", category="text",
            extension="txt", size_bytes=2, sha256="0" * 64,
            storage_path=f"alice/alice-{_}/x.txt",
        )
    repo.insert(
        attachment_id="bob-1", user_id="bob",
        filename="y.txt", content_type="text/plain", category="text",
        extension="txt", size_bytes=2, sha256="0" * 64,
        storage_path="bob/bob-1/y.txt",
    )

    # And a blob for alice on disk.
    store.write(user_id="alice", attachment_id="alice-0", filename="x.txt",
                chunks=_chunks(b"hi"), max_bytes=10, root=tmp_path)

    purged = purge_user_attachments(stub_db, "alice")
    assert purged == 2

    # Alice's rows are gone from the live view.
    assert repo.get_by_id("alice-0", "alice") is None
    # Bob is untouched.
    assert repo.get_by_id("bob-1", "bob") is not None
    # Alice's blob directory is removed.
    assert not (tmp_path / "alice").exists()
