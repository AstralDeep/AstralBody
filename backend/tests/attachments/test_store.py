"""Filesystem store: write/read/delete round-trips, oversize, collisions."""

from __future__ import annotations

import pytest

from orchestrator.attachments import store


def _chunks(data: bytes, n: int = 16):
    for i in range(0, len(data), n):
        yield data[i : i + n]


def test_write_creates_canonical_layout(upload_root, tmp_path):
    path, size, sha = store.write(
        user_id="user-A",
        attachment_id="aid-1",
        filename="hello.txt",
        chunks=_chunks(b"hello world"),
        max_bytes=1024,
        root=upload_root,
    )
    assert path == upload_root / "user-A" / "aid-1" / "hello.txt"
    assert path.read_bytes() == b"hello world"
    assert size == len(b"hello world")
    assert len(sha) == 64


def test_write_rejects_oversize_and_cleans_up(upload_root):
    with pytest.raises(ValueError):
        store.write(
            user_id="u", attachment_id="aid-2", filename="big.bin",
            chunks=_chunks(b"x" * 1000),
            max_bytes=100,
            root=upload_root,
        )
    # Partial blob and empty attachment dir should be gone.
    assert not (upload_root / "u" / "aid-2").exists()


def test_collision_safe_via_attachment_dir(upload_root):
    """Same filename, different attachment_id, same user: no collision."""
    store.write(user_id="u", attachment_id="a", filename="report.pdf",
                chunks=_chunks(b"first"), max_bytes=1024, root=upload_root)
    store.write(user_id="u", attachment_id="b", filename="report.pdf",
                chunks=_chunks(b"second"), max_bytes=1024, root=upload_root)
    assert (upload_root / "u" / "a" / "report.pdf").read_bytes() == b"first"
    assert (upload_root / "u" / "b" / "report.pdf").read_bytes() == b"second"


def test_read_path_raises_when_missing(upload_root):
    with pytest.raises(FileNotFoundError):
        store.read_path("u", "missing", "x.txt", root=upload_root)


def test_delete_is_idempotent(upload_root):
    store.write(user_id="u", attachment_id="a", filename="x.txt",
                chunks=_chunks(b"hi"), max_bytes=1024, root=upload_root)
    store.delete("u", "a", root=upload_root)
    assert not (upload_root / "u" / "a").exists()
    # Second call is a no-op.
    store.delete("u", "a", root=upload_root)


def test_delete_user_purges_all(upload_root):
    store.write(user_id="u", attachment_id="a", filename="x.txt",
                chunks=_chunks(b"hi"), max_bytes=1024, root=upload_root)
    store.write(user_id="u", attachment_id="b", filename="y.txt",
                chunks=_chunks(b"bye"), max_bytes=1024, root=upload_root)
    store.delete_user("u", root=upload_root)
    assert not (upload_root / "u").exists()
