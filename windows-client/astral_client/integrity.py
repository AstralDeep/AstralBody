"""Integrity verifier for the Windows desktop client (feature 039).

Before a freshly-downloaded ``AstralDeep.exe`` is ever executed, this module:

  1. resolves the latest GitHub Release (api.github.com/repos/<repo>/releases/latest),
  2. downloads the exe + ``SHA256SUMS`` + ``cosign.bundle`` assets,
  3. verifies ``sha256(exe) ==`` the manifest entry for the exe,
  4. verifies the sigstore ``cosign.bundle`` against the exe — asserting the
     signing certificate's OIDC identity is the AstralDeep/AstralDeep GitHub
     Actions workflow (issuer https://token.actions.githubusercontent.com),
  5. only then returns the verified exe path for the caller to launch/replace.

**Fail-closed:** any mismatch or unverifiable signature ⇒ ``VerifyResult(ok=False)``
and the downloaded binary is deleted. **Offline-tolerant:** an unreachable GitHub
on an *update check* keeps the current already-verified binary (the caller never
runs an unverified download); integrity is checked before every run of a
freshly-downloaded binary, not just on first install.

``sigstore`` is a CLIENT-ONLY dependency (frozen into the PyInstaller bundle) —
it never enters the orchestrator image (Constitution V preserved). If ``sigstore``
is unavailable, the verifier fail-closes (refuses) rather than skipping the
signature check.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass
from functools import total_ordering
from typing import Optional

logger = logging.getLogger("astral.integrity")

_REPO = os.getenv("DESKTOP_RELEASE_REPO", "AstralDeep/AstralDeep")
_EXE_NAME = "AstralDeep.exe"
_SHA_NAME = "SHA256SUMS"
_BUNDLE_NAME = "cosign.bundle"
# The OIDC identity the signing workflow MUST present (keyless sigstore).
_EXPECTED_ISSUER = "https://token.actions.githubusercontent.com"
# The signing workflow's OIDC subject (the SAN on the sigstore cert). The
# keyless ``sigstore sign --identity <this>@refs/tags/<tag>`` in
# release-windows.yml produces a SAN exactly equal to this path + the tag ref,
# so the verifier rebuilds that exact string from the release's tag. Pinning the
# workflow path means only THIS repo's release workflow can sign a binary the
# client will accept.
_SIGNING_WORKFLOW = (
    "https://github.com/AstralDeep/AstralDeep/.github/workflows/release-windows.yml"
)
_MAX_BYTES = 200 * 1024 * 1024  # 200 MB cap on the exe download


@dataclass
class ReleaseAssets:
    version: str
    exe_url: str
    sha_url: str
    bundle_url: str
    html_url: str
    tag: str = ""
    release_id: int = 0
    asset_ids: tuple[int, int, int] = (0, 0, 0)


@dataclass
class VerifyResult:
    ok: bool
    reason: str = ""
    exe_path: str = ""
    version: str = ""


_SEMVER_RE = re.compile(
    r"\A(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z"
)


@total_ordering
@dataclass(frozen=True)
class SemVer:
    """Strict Semantic Version 2.0 identity and precedence value."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    def __str__(self) -> str:
        value = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            value += "-" + ".".join(self.prerelease)
        if self.build:
            value += "+" + ".".join(self.build)
        return value

    def _compare_precedence(self, other: "SemVer") -> int:
        left_core = (self.major, self.minor, self.patch)
        right_core = (other.major, other.minor, other.patch)
        if left_core != right_core:
            return -1 if left_core < right_core else 1
        if not self.prerelease and not other.prerelease:
            return 0
        if not self.prerelease:
            return 1
        if not other.prerelease:
            return -1
        for left, right in zip(self.prerelease, other.prerelease):
            if left == right:
                continue
            left_numeric = left.isdigit()
            right_numeric = right.isdigit()
            if left_numeric and right_numeric:
                return -1 if int(left) < int(right) else 1
            if left_numeric != right_numeric:
                return -1 if left_numeric else 1
            return -1 if left < right else 1
        if len(self.prerelease) == len(other.prerelease):
            return 0
        return -1 if len(self.prerelease) < len(other.prerelease) else 1

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._compare_precedence(other) < 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return False
        # Build metadata does not participate in SemVer precedence/equality.
        return self._compare_precedence(other) == 0


def parse_semver(value: str) -> SemVer:
    """Parse exact SemVer without trimming, prefix removal, or line tolerance."""

    if not isinstance(value, str) or any(character.isspace() for character in value):
        raise ValueError("version must be strict SemVer without whitespace")
    match = _SEMVER_RE.fullmatch(value)
    if match is None:
        raise ValueError("version must be strict SemVer")
    prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
    build = tuple(match.group(5).split(".")) if match.group(5) else ()
    return SemVer(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        prerelease,
        build,
    )


def is_newer_version(candidate: str, current: str) -> bool:
    """Return whether ``candidate`` has greater strict SemVer precedence."""

    return parse_semver(candidate) > parse_semver(current)


def _api_get(path: str) -> Optional[dict]:
    url = f"https://api.github.com/{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    token = os.getenv("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read(2 * 1024 * 1024).decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        logger.info("github API %s failed: %s", path, exc)
        return None


def latest_release() -> Optional[ReleaseAssets]:
    data = _api_get(f"repos/{_REPO}/releases/latest")
    if not data:
        return None
    release_id = data.get("id")
    tag = data.get("tag_name")
    if isinstance(release_id, bool) or not isinstance(release_id, int) or release_id <= 0:
        logger.info("release missing immutable numeric identity")
        return None
    if not isinstance(tag, str) or not tag.startswith("v"):
        logger.info("release tag is not v<strict-semver>")
        return None
    try:
        version = str(parse_semver(tag[1:]))
    except ValueError:
        logger.info("release tag is not v<strict-semver>")
        return None
    asset_rows = data.get("assets") or []
    required_names = (_EXE_NAME, _SHA_NAME, _BUNDLE_NAME)
    if any(sum(row.get("name") == name for row in asset_rows) != 1 for name in required_names):
        logger.info("release does not contain exactly one of every required asset")
        return None
    assets = {a.get("name"): a for a in asset_rows}
    exe = assets.get(_EXE_NAME, {}).get("browser_download_url", "")
    sha = assets.get(_SHA_NAME, {}).get("browser_download_url", "")
    bundle = assets.get(_BUNDLE_NAME, {}).get("browser_download_url", "")
    asset_ids = tuple(assets[name].get("id") for name in required_names)
    if (
        not exe
        or not sha
        or not bundle
        or len({exe, sha, bundle}) != 3
        or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in asset_ids)
        or len(set(asset_ids)) != 3
    ):
        logger.info("release missing required assets (exe/sha/bundle)")
        return None
    return ReleaseAssets(
        version=version,
        exe_url=exe,
        sha_url=sha,
        bundle_url=bundle,
        html_url=data.get("html_url", ""),
        tag=tag,
        release_id=release_id,
        asset_ids=asset_ids,
    )


def _download(url: str, dest: str, *, max_bytes: int = _MAX_BYTES) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
            total = 0
            while True:
                chunk = r.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    f.close()
                    os.remove(dest)
                    logger.warning("download exceeded %d bytes: %s", max_bytes, url)
                    return False
                f.write(chunk)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("download failed %s: %s", url, exc)
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except OSError:
                pass
        return False


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_sha_for_exe(sha_text: str) -> Optional[str]:
    for line in sha_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].endswith(_EXE_NAME):
            h = parts[0].lower()
            if len(h) == 64:
                return h
    for line in sha_text.splitlines():
        h = line.strip().lower()
        if len(h) == 64:
            return h
    return None


def _download_text(url: str) -> Optional[str]:
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.read(64 * 1024).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        logger.warning("text download failed %s: %s", url, exc)
        return None


def _verify_sigstore(
    exe_path: str, bundle_path: str, *, tag: str = ""
) -> tuple[bool, str]:
    """Verify the cosign bundle against the exe; assert the OIDC identity.

    Returns (ok, reason). Fail-closed if sigstore isn't importable.

    The expected SAN is the signing workflow's OIDC subject, rebuilt from the
    release tag so it exactly matches the cert GitHub issued for that tag
    (sigstore's Identity policy is an exact match, not a prefix). An explicit
    ``DESKTOP_SIGSTORE_IDENTITY`` env override wins (for testing/branch builds).
    """
    try:
        from sigstore.verify import Verifier
        from sigstore.verify.policy import Identity
        from sigstore.models import Bundle
    except Exception as exc:  # noqa: BLE001
        return False, f"sigstore not available: {exc}"
    if tag:
        expected = f"{_SIGNING_WORKFLOW}@refs/tags/{tag}"
    else:
        expected = _SIGNING_WORKFLOW
    expected = os.getenv("DESKTOP_SIGSTORE_IDENTITY", expected)
    try:
        with open(bundle_path, "rb") as f:
            bundle = Bundle.from_json(f.read())
        identity = Identity(issuer=_EXPECTED_ISSUER, identity=expected)
        verifier = Verifier.production()
        with open(exe_path, "rb") as f:
            verifier.verify_artifact(input_=f.read(), bundle=bundle, policy=identity)
        return True, "verified"
    except Exception as exc:  # noqa: BLE001
        return False, f"sigstore verification failed: {exc}"


def verify_latest(workdir: str) -> VerifyResult:
    """Download + verify the latest released exe into ``workdir``.

    Returns a :class:`VerifyResult`; on failure the downloaded files are
    deleted. The caller launches ``exe_path`` only when ``ok`` is True.
    """
    rel = latest_release()
    if rel is None:
        return VerifyResult(
            ok=False, reason="Could not resolve the latest GitHub release."
        )
    exe_path = os.path.join(workdir, _EXE_NAME)
    bundle_path = os.path.join(workdir, _BUNDLE_NAME)

    if not _download(rel.exe_url, exe_path):
        return VerifyResult(ok=False, reason="Download of AstralDeep.exe failed.")
    sha_text = _download_text(rel.sha_url)
    if not sha_text:
        _cleanup(exe_path)
        return VerifyResult(ok=False, reason="Download of SHA256SUMS failed.")
    if not _download(rel.bundle_url, bundle_path):
        _cleanup(exe_path)
        return VerifyResult(ok=False, reason="Download of cosign.bundle failed.")

    # 1. SHA-256
    expected = _extract_sha_for_exe(sha_text)
    if not expected:
        _cleanup(exe_path, bundle_path)
        return VerifyResult(
            ok=False, reason="SHA256SUMS has no hash for AstralDeep.exe."
        )
    actual = _sha256_file(exe_path)
    if actual != expected:
        _cleanup(exe_path, bundle_path)
        return VerifyResult(
            ok=False,
            reason=f"SHA-256 mismatch (expected {expected[:12]}…, got {actual[:12]}…).",
        )

    # 2. sigstore
    ok, reason = _verify_sigstore(exe_path, bundle_path, tag=rel.tag)
    if not ok:
        _cleanup(exe_path, bundle_path)
        return VerifyResult(ok=False, reason=reason)

    return VerifyResult(
        ok=True, reason="verified", exe_path=exe_path, version=rel.version
    )


def verify_running_exe(exe_path: str, *, workdir: str, _release=None) -> VerifyResult:
    """Verify an already-installed exe (e.g. ``sys.executable``) against the
    latest release's ``SHA256SUMS`` + ``cosign.bundle`` — WITHOUT re-downloading
    the 68 MB exe. The launch-time check uses this to confirm the binary the user
    is *actually running* is the signed one. Only the tiny manifest + bundle are
    fetched; the local exe is hashed in place. Fail-closed; never raises.
    """
    if not exe_path or not os.path.exists(exe_path):
        return VerifyResult(ok=False, reason="running exe not found")
    rel = (_release or latest_release)()
    if rel is None:
        return VerifyResult(
            ok=False, reason="Could not resolve the latest GitHub release."
        )
    bundle_path = os.path.join(workdir, _BUNDLE_NAME)
    try:
        sha_text = _download_text(rel.sha_url)
        if not sha_text:
            return VerifyResult(ok=False, reason="Download of SHA256SUMS failed.")
        if not _download(rel.bundle_url, bundle_path):
            return VerifyResult(ok=False, reason="Download of cosign.bundle failed.")
        expected = _extract_sha_for_exe(sha_text)
        if not expected:
            return VerifyResult(
                ok=False, reason="SHA256SUMS has no hash for AstralDeep.exe."
            )
        actual = _sha256_file(exe_path)
        if actual != expected:
            return VerifyResult(
                ok=False,
                reason=f"SHA-256 mismatch (expected {expected[:12]}…, got {actual[:12]}…).",
            )
        ok, reason = _verify_sigstore(exe_path, bundle_path, tag=rel.tag)
        if not ok:
            return VerifyResult(ok=False, reason=reason)
        return VerifyResult(
            ok=True, reason="verified", exe_path=exe_path, version=rel.version
        )
    finally:
        _cleanup(bundle_path)


def check_at_launch(
    current_version: str,
    exe_path: str,
    *,
    frozen: bool,
    workdir: str,
    _release=None,
    _verify_running=None,
    _verify_latest=None,
) -> dict:
    """Launch-time integrity + update check. **Never raises; offline-tolerant.**

    Returns a notice dict ``{status, level, message, version}`` for a status
    line. When the app is a packaged build (``frozen``), the running exe is
    verified against the signed release manifest + sigstore bundle on *every*
    launch — the honest realisation of the spec's "integrity checked before run"
    (B.5). In a source/dev run there is no signed artifact on disk, so the check
    is a benign no-op notice. A newer signed release surfaces as a verified
    update notice; an unverifiable update is ignored (never offered).

    All I/O is injectable (``_release``/``_verify_running``/``_verify_latest``)
    so the decision logic is unit-testable without network or a real exe.
    """
    release = _release or latest_release
    verify_running = _verify_running or verify_running_exe
    verify_latest_fn = _verify_latest or verify_latest
    try:
        if not (frozen and exe_path):
            return {
                "status": "dev",
                "level": "muted",
                "version": current_version,
                "message": (
                    f"Astral {current_version} (dev) — integrity verification "
                    "runs on the packaged app"
                ),
            }
        rel = release()
        if rel is None:
            return {
                "status": "offline",
                "level": "muted",
                "version": current_version,
                "message": f"Astral {current_version} — integrity check skipped (offline)",
            }
        try:
            current = parse_semver(current_version)
            latest = parse_semver(rel.version)
        except ValueError:
            return {
                "status": "invalid_version",
                "level": "warning",
                "version": rel.version,
                "message": "Release metadata has an invalid semantic version; update ignored.",
            }
        if latest == current:
            res = verify_running(exe_path, workdir=workdir)
            if res.ok:
                return {
                    "status": "verified",
                    "level": "success",
                    "version": rel.version,
                    "message": f"✓ Integrity verified — {rel.version} (SHA-256 + sigstore)",
                }
            return {
                "status": "unverified",
                "level": "error",
                "version": rel.version,
                "message": f"⚠ This build's signature did not verify ({res.reason})",
            }
        if latest < current:
            return {
                "status": "current_newer",
                "level": "muted",
                "version": current_version,
                "message": f"Astral {current_version}",
            }
        # A strictly greater release exists.
        # Verify that release's artifact before offering it as an update.
        res = verify_latest_fn(workdir)
        if res.ok:
            return {
                "status": "update_available",
                "level": "success",
                "version": rel.version,
                "message": f"A verified update is available: {rel.version}",
            }
        return {
            "status": "update_unverified",
            "level": "warning",
            "version": rel.version,
            "message": (
                f"Update {rel.version} found but its signature did not verify — ignored."
            ),
        }
    except Exception as exc:  # noqa: BLE001 — launch must never crash here
        logger.info("launch integrity check failed: %s", exc)
        return {
            "status": "error",
            "level": "muted",
            "version": current_version,
            "message": "",
        }


def _cleanup(*paths: str) -> None:
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
