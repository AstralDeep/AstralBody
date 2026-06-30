"""Integrity verifier for the Windows desktop client (feature 039).

Before a freshly-downloaded ``AstralBody.exe`` is ever executed, this module:

  1. resolves the latest GitHub Release (api.github.com/repos/<repo>/releases/latest),
  2. downloads the exe + ``SHA256SUMS`` + ``cosign.bundle`` assets,
  3. verifies ``sha256(exe) ==`` the manifest entry for the exe,
  4. verifies the sigstore ``cosign.bundle`` against the exe — asserting the
     signing certificate's OIDC identity is the AstralDeep/AstralBody GitHub
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
import urllib.request
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("astral.integrity")

_REPO = os.getenv("DESKTOP_RELEASE_REPO", "AstralDeep/AstralBody")
_EXE_NAME = "AstralBody.exe"
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
    "https://github.com/AstralDeep/AstralBody/.github/workflows/release-windows.yml"
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


@dataclass
class VerifyResult:
    ok: bool
    reason: str = ""
    exe_path: str = ""
    version: str = ""


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
    assets = {a.get("name"): a for a in (data.get("assets") or [])}
    exe = assets.get(_EXE_NAME, {}).get("browser_download_url", "")
    sha = assets.get(_SHA_NAME, {}).get("browser_download_url", "")
    bundle = assets.get(_BUNDLE_NAME, {}).get("browser_download_url", "")
    if not exe or not sha or not bundle:
        logger.info("release missing required assets (exe/sha/bundle)")
        return None
    return ReleaseAssets(
        version=(data.get("name") or data.get("tag_name") or "").strip(),
        exe_url=exe,
        sha_url=sha,
        bundle_url=bundle,
        html_url=data.get("html_url", ""),
        tag=(data.get("tag_name") or "").strip(),
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
        return VerifyResult(ok=False, reason="Download of AstralBody.exe failed.")
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
            ok=False, reason="SHA256SUMS has no hash for AstralBody.exe."
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
                ok=False, reason="SHA256SUMS has no hash for AstralBody.exe."
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


def _norm_version(v: str) -> str:
    return (v or "").strip().lstrip("vV")


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
        latest = rel.version or rel.tag or ""
        if _norm_version(latest) == _norm_version(current_version):
            res = verify_running(exe_path, workdir=workdir)
            if res.ok:
                return {
                    "status": "verified",
                    "level": "success",
                    "version": latest,
                    "message": f"✓ Integrity verified — {latest} (SHA-256 + sigstore)",
                }
            return {
                "status": "unverified",
                "level": "error",
                "version": latest,
                "message": f"⚠ This build's signature did not verify ({res.reason})",
            }
        # Running build differs from the latest release → a newer release exists.
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
