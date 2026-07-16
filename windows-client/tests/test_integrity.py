"""Tests for the desktop client integrity verifier (feature 039).

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

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astral_client import integrity


@pytest.mark.parametrize(
    "value",
    [
        "v0.4.0",
        " 0.4.0",
        "0.4.0 ",
        "0.4.0\n",
        "0.4.0\r",
        "0.4.0\t",
        "0.4.0\u2028",
        "01.4.0",
        "0.04.0",
        "0.4.00",
        "0.4.0-01",
        "0.4.0-alpha.01",
    ],
)
def test_strict_semver_rejects_prefix_whitespace_and_leading_zeroes(value):
    with pytest.raises(ValueError):
        integrity.parse_semver(value)


@pytest.mark.parametrize(
    "value",
    [
        "0.4.0",
        "0.4.0-alpha",
        "0.4.0-alpha.1",
        "0.4.0-0.3.7",
        "0.4.0-x.7.z.92",
        "0.4.0+build.5",
        "0.4.0-alpha+build.5",
    ],
)
def test_strict_semver_accepts_legal_prerelease_and_build(value):
    assert str(integrity.parse_semver(value)) == value


def test_semver_precedence_and_upgrade_from_0_3_0():
    assert integrity.is_newer_version("0.4.0", "0.3.0") is True
    assert integrity.is_newer_version("0.4.0-alpha.1", "0.4.0-alpha") is True
    assert integrity.is_newer_version("0.4.0", "0.4.0-rc.1") is True
    assert integrity.is_newer_version("0.3.0", "0.4.0") is False
    assert integrity.is_newer_version("0.4.0+build.2", "0.4.0+build.1") is False


def test_release_assets_require_immutable_distinct_asset_identities(monkeypatch):
    payload = {
        "id": 42,
        "name": "0.4.0",
        "tag_name": "v0.4.0",
        "html_url": "https://github.invalid/releases/42",
        "assets": [
            {"id": 101, "name": "AstralDeep.exe", "browser_download_url": "u/exe"},
            {"id": 102, "name": "SHA256SUMS", "browser_download_url": "u/sha"},
            {"id": 103, "name": "cosign.bundle", "browser_download_url": "u/bundle"},
        ],
    }
    monkeypatch.setattr(integrity, "_api_get", lambda _path: payload)
    release = integrity.latest_release()
    assert release is not None
    assert release.version == "0.4.0"
    assert release.release_id == 42
    assert release.asset_ids == (101, 102, 103)

    payload["assets"][2]["id"] = 102
    assert integrity.latest_release() is None


def _make_release(exe_url="u/exe", sha_url="u/sha", bundle_url="u/bundle"):
    return integrity.ReleaseAssets(
        version="v1",
        exe_url=exe_url,
        sha_url=sha_url,
        bundle_url=bundle_url,
        html_url="h",
    )


def test_extract_sha_for_exe_picks_the_exe_line():
    body = f"{'a' * 64}  AstralDeep.exe\n{'b' * 64}  cosign.bundle\n"
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
        integrity, "_download_text", lambda url: f"{'0' * 64}  AstralDeep.exe\n"
    )
    # sigstore must not even be reached (sha check fails first).
    res = integrity.verify_latest(str(tmp_path))
    assert not res.ok
    assert "SHA-256 mismatch" in res.reason
    assert not os.path.exists(os.path.join(str(tmp_path), "AstralDeep.exe"))


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
        integrity, "_download_text", lambda url: f"{sha}  AstralDeep.exe\n"
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
    assert not os.path.exists(os.path.join(str(tmp_path), "AstralDeep.exe"))


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
        integrity, "_download_text", lambda url: f"{sha}  AstralDeep.exe\n"
    )
    monkeypatch.setattr(
        integrity, "_verify_sigstore", lambda exe, bundle, **kw: (True, "verified")
    )
    res = integrity.verify_latest(str(tmp_path))
    assert res.ok, res.reason
    assert res.exe_path.endswith("AstralDeep.exe")
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
        integrity, "_download_text", lambda url: f"{sha}  AstralDeep.exe\n"
    )
    monkeypatch.setattr(
        integrity,
        "_verify_sigstore",
        lambda exe, bundle, **kw: (False, "sigstore verification failed: bad sig"),
    )
    res = integrity.verify_latest(str(tmp_path))
    assert not res.ok
    assert "bad sig" in res.reason
    assert not os.path.exists(os.path.join(str(tmp_path), "AstralDeep.exe"))


def test_latest_release_none_when_asset_missing(monkeypatch):
    monkeypatch.setattr(
        integrity,
        "_api_get",
        lambda path: {
            "id": 1,
            "tag_name": "v1.2.3",
            "assets": [
                {"id": 2, "name": "AstralDeep.exe", "browser_download_url": "u"}
            ],  # no sha/bundle
        },
    )
    assert integrity.latest_release() is None


def test_latest_release_parses(monkeypatch):
    monkeypatch.setattr(
        integrity,
        "_api_get",
        lambda path: {
            "id": 11,
            "name": "1.2.3",
            "tag_name": "v1.2.3",
            "html_url": "h",
            "assets": [
                {"id": 21, "name": "AstralDeep.exe", "browser_download_url": "u/exe"},
                {"id": 22, "name": "SHA256SUMS", "browser_download_url": "u/sha"},
                {"id": 23, "name": "cosign.bundle", "browser_download_url": "u/bundle"},
            ],
        },
    )
    rel = integrity.latest_release()
    assert rel is not None
    assert rel.version == "1.2.3"
    assert rel.tag == "v1.2.3"
    assert rel.release_id == 11
    assert rel.asset_ids == (21, 22, 23)
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
            "https://github.com/AstralDeep/AstralDeep/.github/workflows/"
            "release-windows.yml@refs/tags/v0.1.0"
        )
    finally:
        os.remove(exe_path)
        os.remove(bundle_path)


# --------------------------------------------------------------------------- #
# verify_running_exe — verify the on-disk running binary (no exe re-download)
# --------------------------------------------------------------------------- #

def _rel(version="0.2.0"):
    return integrity.ReleaseAssets(
        version=version, exe_url="e", sha_url="s", bundle_url="b",
        html_url="h", tag=f"v{version}",
    )


def test_verify_running_exe_happy(monkeypatch, tmp_path):
    exe = tmp_path / "AstralDeep.exe"
    exe.write_bytes(b"running payload")
    sha = hashlib.sha256(b"running payload").hexdigest()
    monkeypatch.setattr(integrity, "_download_text", lambda url: f"{sha}  AstralDeep.exe\n")
    monkeypatch.setattr(
        integrity, "_download", lambda url, dest, **k: (open(dest, "wb").write(b"{}"), True)[1]
    )
    monkeypatch.setattr(integrity, "_verify_sigstore", lambda e, b, **kw: (True, "verified"))
    res = integrity.verify_running_exe(str(exe), workdir=str(tmp_path), _release=_rel)
    assert res.ok, res.reason
    assert res.exe_path == str(exe)
    assert res.version == "0.2.0"
    # the tiny bundle is cleaned up; the running exe is NEVER deleted.
    assert not os.path.exists(os.path.join(str(tmp_path), "cosign.bundle"))
    assert os.path.exists(str(exe))


def test_verify_running_exe_sha_mismatch_does_not_delete_exe(monkeypatch, tmp_path):
    exe = tmp_path / "AstralDeep.exe"
    exe.write_bytes(b"running payload")
    monkeypatch.setattr(integrity, "_download_text", lambda url: f"{'0' * 64}  AstralDeep.exe\n")
    monkeypatch.setattr(
        integrity, "_download", lambda url, dest, **k: (open(dest, "wb").write(b"{}"), True)[1]
    )
    monkeypatch.setattr(integrity, "_verify_sigstore", lambda e, b, **kw: (True, "verified"))
    res = integrity.verify_running_exe(str(exe), workdir=str(tmp_path), _release=_rel)
    assert not res.ok and "SHA-256 mismatch" in res.reason
    # never delete the user's running binary, even on mismatch.
    assert os.path.exists(str(exe))


def test_verify_running_exe_missing_file(tmp_path):
    res = integrity.verify_running_exe(
        str(tmp_path / "nope.exe"), workdir=str(tmp_path), _release=_rel
    )
    assert not res.ok and "running exe not found" in res.reason


def test_verify_running_exe_offline(tmp_path):
    exe = tmp_path / "AstralDeep.exe"
    exe.write_bytes(b"x")
    res = integrity.verify_running_exe(
        str(exe), workdir=str(tmp_path), _release=lambda: None
    )
    assert not res.ok and "release" in res.reason.lower()


# --------------------------------------------------------------------------- #
# check_at_launch — launch-time integrity/update decision (fully injected)
# --------------------------------------------------------------------------- #

def _verok(*a, **k):
    return integrity.VerifyResult(ok=True, reason="verified", exe_path="e", version="v0.2.0")


def _verbad(reason="bad sig"):
    def _f(*a, **k):
        return integrity.VerifyResult(ok=False, reason=reason)
    return _f


def test_check_at_launch_dev_not_frozen():
    n = integrity.check_at_launch("0.2.0", "", frozen=False, workdir="/tmp")
    assert n["status"] == "dev" and n["level"] == "muted"


def test_check_at_launch_verified_same_version():
    n = integrity.check_at_launch(
        "0.2.0", "C:/AstralDeep.exe", frozen=True, workdir="/tmp",
        _release=lambda: _rel("0.2.0"), _verify_running=_verok,
    )
    assert n["status"] == "verified" and n["level"] == "success"
    assert "0.2.0" in n["message"]


def test_check_at_launch_unverified_same_version():
    n = integrity.check_at_launch(
        "0.2.0", "C:/AstralDeep.exe", frozen=True, workdir="/tmp",
        _release=lambda: _rel("0.2.0"), _verify_running=_verbad("bad sig"),
    )
    assert n["status"] == "unverified" and n["level"] == "error"
    assert "bad sig" in n["message"]


def test_check_at_launch_offline():
    n = integrity.check_at_launch(
        "0.2.0", "C:/AstralDeep.exe", frozen=True, workdir="/tmp", _release=lambda: None
    )
    assert n["status"] == "offline" and n["level"] == "muted"


def test_check_at_launch_update_available():
    n = integrity.check_at_launch(
        "0.1.0", "C:/AstralDeep.exe", frozen=True, workdir="/tmp",
        _release=lambda: _rel("0.2.0"), _verify_latest=_verok,
    )
    assert n["status"] == "update_available" and "0.2.0" in n["message"]


def test_check_at_launch_update_unverified_is_ignored():
    n = integrity.check_at_launch(
        "0.1.0", "C:/AstralDeep.exe", frozen=True, workdir="/tmp",
        _release=lambda: _rel("0.2.0"), _verify_latest=_verbad("nope"),
    )
    assert n["status"] == "update_unverified" and n["level"] == "warning"


def test_check_at_launch_never_raises_on_error():
    def boom():
        raise RuntimeError("net down")

    n = integrity.check_at_launch("0.2.0", "C:/AstralDeep.exe", frozen=True,
                                  workdir="/tmp", _release=boom)
    assert n["status"] == "error" and n["message"] == ""
