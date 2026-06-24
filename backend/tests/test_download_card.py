"""Feature 067 — desktop codegen download-card tests.

Covers:
  - the ``download_card`` webrender primitive (registry, renderer structure,
    URL-validation defense-in-depth, escaping, unavailable variant)
  - ROTE adaptation per device (browser/tv passthrough, mobile compaction,
    watch collapse, voice speech)
  - the ``desktop_codegen`` meta-tool: tool definition, injection gate,
    build_download_card (available + unavailable), release-info cache +
    fail-open last-good + SHA256 extraction, and handle_meta_tool end-to-end
    with the GitHub API mocked.

Pure Python — no DB. The GitHub Releases API is monkeypatched so no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rote.adapter import ComponentAdapter  # noqa: E402
from rote.capabilities import DeviceProfile  # noqa: E402
from webrender.renderer import allowed_primitive_types, render_one  # noqa: E402


def _profile(device_type: str) -> DeviceProfile:
    return DeviceProfile.from_dict({"device_type": device_type})


# --------------------------------------------------------------------------- #
# Primitive / renderer
# --------------------------------------------------------------------------- #

def test_download_card_registered():
    assert "download_card" in allowed_primitive_types()


def _card(**kw):
    base = {"type": "download_card", "variant": "available",
            "title": "Astral desktop app", "description": "Install me",
            "download_url": "https://github.com/AstralDeep/AstralBody/releases/download/v1/AstralBody.exe",
            "sha256": "a" * 64, "sigstore_bundle_url": "https://github.com/AstralDeep/AstralBody/releases/download/v1/cosign.bundle",
            "version": "1.2.3", "platform": "windows-x64",
            "html_url": "https://github.com/AstralDeep/AstralBody/releases/latest"}
    base.update(kw)
    return base


def test_render_available_has_github_link_and_hash():
    html = render_one(_card())
    assert "https://github.com/AstralDeep/AstralBody/releases/download/v1/AstralBody.exe" in html
    assert "a" * 64 in html  # sha256 shown
    assert "Download for Windows" in html
    assert "v1.2.3" in html


def test_render_refuses_non_github_url():
    # A crafted non-GitHub URL must NOT become a clickable download link.
    html = render_one(_card(download_url="https://evil.example/a.exe", variant="available"))
    assert "evil.example" not in html
    assert "Download temporarily unavailable" in html


def test_render_unavailable_variant():
    html = render_one(_card(variant="unavailable", download_url="", sha256=""))
    assert "Download temporarily unavailable" in html
    assert "GitHub Releases" in html  # link to releases page still present


def test_render_escapes_title():
    html = render_one(_card(title="<script>x</script>"))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# --------------------------------------------------------------------------- #
# ROTE adaptation
# --------------------------------------------------------------------------- #

def test_rote_browser_passthrough():
    c = _card()
    out = ComponentAdapter.adapt([c], _profile("browser"))
    assert out[0]["type"] == "download_card"
    assert out[0].get("sha256") == "a" * 64  # full card preserved


def test_rote_mobile_drops_sha_and_note():
    out = ComponentAdapter.adapt([_card()], _profile("mobile"))
    assert out[0]["type"] == "download_card"
    assert "sha256" not in out[0]
    assert "description" not in out[0]
    assert out[0]["download_url"]  # link still present


def test_rote_watch_collapses_to_button():
    out = ComponentAdapter.adapt([_card()], _profile("watch"))
    assert out[0]["type"] == "button"
    assert "v1.2.3" in out[0]["label"]


def test_rote_voice_speaks():
    out = ComponentAdapter.adapt([_card()], _profile("voice"))
    assert out[0]["type"] == "text"
    assert "GitHub" in out[0]["content"]
    assert "SHA-256" in out[0]["content"]


# --------------------------------------------------------------------------- #
# desktop_codegen meta-tool (GitHub API mocked)
# --------------------------------------------------------------------------- #

from orchestrator import desktop_codegen as dc  # noqa: E402


def test_meta_tool_definition():
    defs = dc.meta_tool_definitions()
    assert defs[0]["function"]["name"] == "offer_desktop_codegen"
    assert "code" in defs[0]["function"]["parameters"]["required"]


def test_should_inject_respects_flag_and_draft(monkeypatch):
    from shared.feature_flags import flags
    monkeypatch.setitem(flags._flags, "desktop_codegen", True)
    assert dc.should_inject(None) is True
    assert dc.should_inject("draft-1") is False  # draft-test exclusion
    monkeypatch.setitem(flags._flags, "desktop_codegen", False)
    assert dc.should_inject(None) is False


def test_build_card_available():
    info = {"exe_url": "https://github.com/AstralDeep/AstralBody/releases/download/v1/AstralBody.exe",
            "sha256": "b" * 64, "bundle_url": "u", "version": "1.0.0", "html_url": "h",
            "sha_url": "s"}
    card = dc.build_download_card(info)
    assert card["variant"] == "available"
    assert card["sha256"] == "b" * 64
    assert card["download_url"].startswith("https://github.com/")


def test_build_card_unavailable_when_no_info():
    card = dc.build_download_card(None)
    assert card["variant"] == "unavailable"
    assert card["download_url"] == ""


def _mock_release(monkeypatch, *, sha="c" * 64):
    def fake_fetch():
        return {"version": "v9.9.9", "tag": "v9.9.9",
                "exe_url": "https://github.com/AstralDeep/AstralBody/releases/download/v9.9.9/AstralBody.exe",
                "sha_url": "https://github.com/AstralDeep/AstralBody/releases/download/v9.9.9/SHA256SUMS",
                "bundle_url": "https://github.com/AstralDeep/AstralBody/releases/download/v9.9.9/cosign.bundle",
                "html_url": "https://github.com/AstralDeep/AstralBody/releases/latest"}
    monkeypatch.setattr(dc, "_fetch_release_info", fake_fetch)
    monkeypatch.setattr(dc, "_fetch_sha256", lambda url: sha)


def test_get_release_info_caches_and_fails_open(monkeypatch):
    dc._CACHE.clear()
    _mock_release(monkeypatch)
    info = dc.get_release_info()
    assert info["sha256"] == "c" * 64
    # Second call within TTL must not re-fetch: make the fetcher raise.
    monkeypatch.setattr(dc, "_fetch_release_info", lambda: None)
    info2 = dc.get_release_info()
    assert info2 is info or info2["sha256"] == "c" * 64  # last-good kept


def test_get_release_info_none_when_no_cache_and_fetch_fails(monkeypatch):
    dc._CACHE.clear()
    monkeypatch.setattr(dc, "_fetch_release_info", lambda: None)
    assert dc.get_release_info() is None


def test_fetch_sha256_extracts_hash(monkeypatch):
    body = f"{'d' * 64}  AstralBody.exe\n{'e' * 64}  cosign.bundle\n"

    class _Resp:
        status_code = 200
        def iter_content(self, chunk_size=0):
            yield body.encode()

    import requests
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _Resp())
    h = dc._fetch_sha256("https://github.com/AstralDeep/AstralBody/releases/download/v1/SHA256SUMS")
    assert h == "d" * 64


def test_handle_meta_tool_returns_code_and_card(monkeypatch):
    import asyncio
    _mock_release(monkeypatch)
    dc._CACHE.clear()
    res = asyncio.run(dc.handle_meta_tool(
        None, "offer_desktop_codegen",
        {"language": "python", "code": "print('hi')", "summary": "sorts files"},
        user_id="u1", chat_id="c1", websocket=None))
    assert res.error is None
    types = [c["type"] for c in res.ui_components]
    assert "code" in types and "download_card" in types
    assert res.result["status"] == "offered"


def test_handle_meta_tool_needs_code(monkeypatch):
    import asyncio
    res = asyncio.run(dc.handle_meta_tool(
        None, "offer_desktop_codegen", {"language": "python", "code": ""},
        user_id="u1", chat_id="c1", websocket=None))
    assert res.error is not None


def test_handle_meta_tool_unavailable_when_no_release(monkeypatch):
    import asyncio
    dc._CACHE.clear()
    monkeypatch.setattr(dc, "_fetch_release_info", lambda: None)
    res = asyncio.run(dc.handle_meta_tool(
        None, "offer_desktop_codegen",
        {"language": "python", "code": "x"}, user_id="u1", chat_id="c1", websocket=None))
    types = [c["type"] for c in res.ui_components]
    assert "download_card" in types
    assert res.result["status"] == "unavailable"
