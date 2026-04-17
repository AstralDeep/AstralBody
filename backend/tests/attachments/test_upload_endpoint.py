"""HTTP contract tests for /api/upload and /api/attachments.

We mount the attachments_router into a fresh FastAPI app, stub out the
``require_user_id`` dependency to return a configurable test user, and stub the
repository factory to return a StubDatabase-backed repo. This exercises the
real router code (validation, sniffing-aware path, JSON shapes) without
needing a running PostgreSQL or Keycloak.
"""

from __future__ import annotations

import io
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator.attachments import router as attachments_router_module
from orchestrator.attachments.repository import AttachmentRepository
from orchestrator.attachments.router import attachments_router
from orchestrator.auth import require_user_id

from .conftest import StubDatabase


@pytest.fixture
def app(monkeypatch, tmp_path, stub_db: StubDatabase) -> FastAPI:
    """A minimal FastAPI app wired only with the attachments router."""
    monkeypatch.setenv("ATTACHMENT_UPLOAD_ROOT", str(tmp_path))

    app = FastAPI()
    app.include_router(attachments_router)

    # Stub repo factory to bypass the orchestrator dependency.
    repo = AttachmentRepository(stub_db)
    monkeypatch.setattr(
        attachments_router_module, "_get_repository", lambda request: repo,
    )

    # Default user override (per-test can re-override).
    app.dependency_overrides[require_user_id] = lambda: "user-A"

    return app


def _client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_upload_returns_201_with_attachment_id(app):
    client = _client(app)
    res = client.post(
        "/api/upload",
        files={"file": ("notes.md", b"# hi\nthere", "text/markdown")},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["filename"] == "notes.md"
    assert body["category"] == "text"
    assert body["extension"] == "md"
    assert body["size_bytes"] == len(b"# hi\nthere")
    assert len(body["sha256"]) == 64
    assert body["attachment_id"]


def test_upload_then_list_then_get_then_delete(app):
    client = _client(app)
    up = client.post(
        "/api/upload",
        files={"file": ("a.txt", b"hello", "text/plain")},
    ).json()
    aid = up["attachment_id"]

    listed = client.get("/api/attachments").json()
    assert len(listed["attachments"]) == 1
    assert listed["attachments"][0]["attachment_id"] == aid

    one = client.get(f"/api/attachments/{aid}")
    assert one.status_code == 200
    assert one.json()["attachment_id"] == aid

    deleted = client.delete(f"/api/attachments/{aid}")
    assert deleted.status_code == 204
    assert client.get(f"/api/attachments/{aid}").status_code == 404
    assert client.get("/api/attachments").json()["attachments"] == []


# ---------------------------------------------------------------------------
# Negative paths
# ---------------------------------------------------------------------------


def test_upload_unsupported_extension_returns_415(app):
    client = _client(app)
    res = client.post("/api/upload", files={"file": ("blueprint.dwg", b"\x00\x01", "application/octet-stream")})
    assert res.status_code == 415
    assert "dwg" in res.json()["detail"].lower()


def test_upload_legacy_binary_format_returns_415(app):
    client = _client(app)
    # .doc is in LEGACY_BINARY_FORMATS — must be rejected at upload time.
    res = client.post("/api/upload", files={"file": ("legacy.doc", b"some bytes", "application/msword")})
    assert res.status_code == 415


def test_upload_oversize_returns_413(app, monkeypatch):
    """A file larger than the per-category cap is rejected with 413."""
    from orchestrator.attachments import content_type as ct

    monkeypatch.setitem(ct.MAX_BYTES_BY_CATEGORY, "text", 100)
    client = _client(app)
    res = client.post("/api/upload", files={"file": ("big.txt", b"x" * 200, "text/plain")})
    assert res.status_code == 413
    assert "upload limit" in res.json()["detail"].lower()


def test_upload_oversize_respects_per_category_caps(app, monkeypatch):
    """A medical-size file (>30 MB) that fits under the medical cap is accepted;
    the same size uploaded as a text file is rejected."""
    from orchestrator.attachments import content_type as ct

    # Shrink medical cap to make the test fast but still larger than the text cap.
    monkeypatch.setitem(ct.MAX_BYTES_BY_CATEGORY, "text", 1000)
    monkeypatch.setitem(ct.MAX_BYTES_BY_CATEGORY, "medical", 100_000)

    client = _client(app)
    payload = b"x" * 5000  # 5 KB: > text cap (1 KB), < medical cap (100 KB)

    # .txt (text category) → 413
    res_text = client.post(
        "/api/upload", files={"file": ("big.txt", payload, "text/plain")},
    )
    assert res_text.status_code == 413, res_text.text

    # .nii (medical category) → bypasses the smaller text cap.
    # We can't easily satisfy the libmagic sniff for NIfTI in a 5KB blob, but
    # the size check runs before the sniff so it'll pass the 413 gate. If it
    # fails, it must fail with 415 (mismatch), NOT 413 (oversize).
    res_med = client.post(
        "/api/upload", files={"file": ("big.nii", payload, "application/octet-stream")},
    )
    assert res_med.status_code != 413, res_med.text


def test_get_foreign_attachment_returns_404_not_403(app):
    """Non-owners must not be able to confirm existence."""
    client = _client(app)
    aid = client.post("/api/upload", files={"file": ("a.txt", b"hi", "text/plain")}).json()["attachment_id"]

    # Switch to a different user and try to read it.
    app.dependency_overrides[require_user_id] = lambda: "user-B"
    res = client.get(f"/api/attachments/{aid}")
    assert res.status_code == 404


def test_delete_foreign_attachment_returns_404(app):
    client = _client(app)
    aid = client.post("/api/upload", files={"file": ("a.txt", b"hi", "text/plain")}).json()["attachment_id"]
    app.dependency_overrides[require_user_id] = lambda: "user-B"
    assert client.delete(f"/api/attachments/{aid}").status_code == 404


def test_listing_is_per_user(app):
    """Same endpoint, two users — each only sees their own."""
    client = _client(app)
    client.post("/api/upload", files={"file": ("a.txt", b"hi", "text/plain")})
    app.dependency_overrides[require_user_id] = lambda: "user-B"
    client.post("/api/upload", files={"file": ("b.txt", b"yo", "text/plain")})

    bob = client.get("/api/attachments").json()
    assert len(bob["attachments"]) == 1
    assert bob["attachments"][0]["filename"] == "b.txt"

    app.dependency_overrides[require_user_id] = lambda: "user-A"
    alice = client.get("/api/attachments").json()
    assert len(alice["attachments"]) == 1
    assert alice["attachments"][0]["filename"] == "a.txt"
