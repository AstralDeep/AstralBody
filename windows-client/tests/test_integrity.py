"""Tests for the desktop client integrity verifier (feature 067).

Covers:
  - SHA256SUMS parsing (extracts the exe's hash)
  - SHA-256 mismatch ⇒ refuse + delete
  - missing sigstore module ⇒ fail-closed (refuse)
  - bad sigstore signature ⇒ refuse
  - happy path (good hash + good signature) ⇒ ok
  - latest_release missing any asset ⇒ None

Network is fully mocked (urllib + sigstore). Pure Python, no PySide6.
"""

from __future__ import annotations

import hashlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astral_client import integrity


def _make_release(exe_url="u/exe", sha_url="u/sha", bundle_url="u/bundle"):
    return integrity.ReleaseAssets(
        version="v1",
        exe_url=exe_url,
        sha_url=sha_url,
        bundle_url=bundle_url,
        html_url="h",
    )


def test_extract_sha_for_exe_picks_the_exe_line():
    body = f"{'a' * 64}  AstralBody.exe\n{'b' * 64}  cosign.bundle\n"
    assert integrity._extract_sha_for_exe(body) == "a" * 64


def test_extract_sha_falls_back_to_single_hash_line():
    assert integrity._extract_sha_for_exe("c" * 64) == "c" * 64


def test_extract_sha_returns_none_when_no_hash():
    assert integrity._extract_sha_for_exe("nothing here") is None


def test_sha256_file(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello")
    assert integrity._sha256_file(str(p)) == hashlib.sha256(b"hello").hexdigest()


def test_verify_refuses_on_sha_mismatch(monkeypatch, tmp_path):
    # Real exe bytes, but a SHA256SUMS that claims a different hash.
    exe_bytes = b"real binary content"
    monkeypatch.setattr(
        integrity,
        "latest_release",
        lambda: _make_release(exe_url="exe", sha_url="sha", bundle_url="bundle"),
    )
    monkeypatch.setattr(
        integrity,
        "_download",
        lambda url, dest, **k: (open(dest, "wb").write(exe_bytes), True)[1],
    )
    monkeypatch.setattr(
        integrity, "_download_text", lambda url: f"{'0' * 64}  AstralBody.exe\n"
    )
    # sigstore must not even be reached (sha check fails first).
    res = integrity.verify_latest(str(tmp_path))
    assert not res.ok
    assert "SHA-256 mismatch" in res.reason
    assert not os.path.exists(os.path.join(str(tmp_path), "AstralBody.exe"))


def test_verify_fail_closed_when_sigstore_missing(monkeypatch, tmp_path):
    exe_bytes = b"real binary content"
    sha = hashlib.sha256(exe_bytes).hexdigest()
    monkeypatch.setattr(integrity, "latest_release", lambda: _make_release())
    monkeypatch.setattr(
        integrity,
        "_download",
        lambda url, dest, **k: (open(dest, "wb").write(exe_bytes), True)[1],
    )
    monkeypatch.setattr(
        integrity, "_download_text", lambda url: f"{sha}  AstralBody.exe\n"
    )

    # Force the sigstore import to fail → fail-closed.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("sigstore"):
            raise ImportError("no sigstore")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    res = integrity.verify_latest(str(tmp_path))
    assert not res.ok
    assert "sigstore" in res.reason
    assert not os.path.exists(os.path.join(str(tmp_path), "AstralBody.exe"))


def test_verify_happy_path(monkeypatch, tmp_path):
    exe_bytes = b"the real exe payload"
    sha = hashlib.sha256(exe_bytes).hexdigest()
    monkeypatch.setattr(integrity, "latest_release", lambda: _make_release())
    monkeypatch.setattr(
        integrity,
        "_download",
        lambda url, dest, **k: (open(dest, "wb").write(exe_bytes), True)[1],
    )
    monkeypatch.setattr(
        integrity, "_download_text", lambda url: f"{sha}  AstralBody.exe\n"
    )
    monkeypatch.setattr(
        integrity, "_verify_sigstore", lambda exe, bundle, **kw: (True, "verified")
    )
    res = integrity.verify_latest(str(tmp_path))
    assert res.ok, res.reason
    assert res.exe_path.endswith("AstralBody.exe")
    assert os.path.exists(res.exe_path)
    assert res.version == "v1"


def test_verify_refuses_on_bad_signature(monkeypatch, tmp_path):
    exe_bytes = b"exe"
    sha = hashlib.sha256(exe_bytes).hexdigest()
    monkeypatch.setattr(integrity, "latest_release", lambda: _make_release())
    monkeypatch.setattr(
        integrity,
        "_download",
        lambda url, dest, **k: (open(dest, "wb").write(exe_bytes), True)[1],
    )
    monkeypatch.setattr(
        integrity, "_download_text", lambda url: f"{sha}  AstralBody.exe\n"
    )
    monkeypatch.setattr(
        integrity,
        "_verify_sigstore",
        lambda exe, bundle, **kw: (False, "sigstore verification failed: bad sig"),
    )
    res = integrity.verify_latest(str(tmp_path))
    assert not res.ok
    assert "bad sig" in res.reason
    assert not os.path.exists(os.path.join(str(tmp_path), "AstralBody.exe"))


def test_latest_release_none_when_asset_missing(monkeypatch):
    monkeypatch.setattr(
        integrity,
        "_api_get",
        lambda path: {
            "assets": [
                {"name": "AstralBody.exe", "browser_download_url": "u"}
            ],  # no sha/bundle
        },
    )
    assert integrity.latest_release() is None


def test_latest_release_parses(monkeypatch):
    monkeypatch.setattr(
        integrity,
        "_api_get",
        lambda path: {
            "name": "v1.2.3",
            "tag_name": "v1.2.3",
            "html_url": "h",
            "assets": [
                {"name": "AstralBody.exe", "browser_download_url": "u/exe"},
                {"name": "SHA256SUMS", "browser_download_url": "u/sha"},
                {"name": "cosign.bundle", "browser_download_url": "u/bundle"},
            ],
        },
    )
    rel = integrity.latest_release()
    assert rel is not None
    assert rel.version == "v1.2.3"
    assert rel.tag == "v1.2.3"
    assert rel.exe_url == "u/exe" and rel.bundle_url == "u/bundle"


def test_verify_sigstore_builds_identity_from_tag(monkeypatch):
    """The expected SAN is the workflow path + the release's tag (exact match).

    Regression: the old verifier pinned a prefix identity that could never
    exactly match the tag-specific SAN GitHub issues, so every release would
    fail-closed. Now the identity is rebuilt from the tag.
    """
    captured = {}

    class FakeIdentity:
        def __init__(self, issuer, identity):
            captured["issuer"] = issuer
            captured["identity"] = identity

    class FakeVerifier:
        @staticmethod
        def production():
            class V:
                def verify_artifact(self, *, input_, bundle, policy):
                    return True

            return V()

    class FakeBundle:
        @staticmethod
        def from_json(_):
            return object()

    import sys

    monkeypatch.setitem(sys.modules, "sigstore", type("M", (), {}))
    monkeypatch.setitem(
        sys.modules,
        "sigstore.verify",
        type(
            "M",
            (),
            {
                "Verifier": FakeVerifier,
                "policy": type("P", (), {"Identity": FakeIdentity}),
            },
        ),
    )
    monkeypatch.setitem(
        sys.modules, "sigstore.verify.policy", type("P", (), {"Identity": FakeIdentity})
    )
    monkeypatch.setitem(
        sys.modules, "sigstore.models", type("M", (), {"Bundle": FakeBundle})
    )

    # _verify_sigstore opens both files before verifying; use real temp paths.
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as ef:
        ef.write(b"exe")
        exe_path = ef.name
    with tempfile.NamedTemporaryFile(suffix=".bundle", delete=False) as bf:
        bf.write(b"{}")
        bundle_path = bf.name
    try:
        ok, reason = integrity._verify_sigstore(exe_path, bundle_path, tag="v0.1.0")
        assert ok, reason
        assert captured["issuer"] == integrity._EXPECTED_ISSUER
        assert captured["identity"] == (
            "https://github.com/AstralDeep/AstralBody/.github/workflows/"
            "release-windows.yml@refs/tags/v0.1.0"
        )
    finally:
        os.remove(exe_path)
        os.remove(bundle_path)
