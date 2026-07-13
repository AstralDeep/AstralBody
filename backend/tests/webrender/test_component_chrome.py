"""Feature 055 (US4 T039 + US5 T045, web lane) — per-component chrome row.

The renderer emits a small affordance row after the provenance footer of every
identified, non-decorative component on an interactive host profile: refine +
version history (FF_COMPONENT_REFINE), a CSV export link for tables
(FF_ARTIFACT_EXPORT), and share (FF_ARTIFACT_SHARING, fail-closed default
off). Each entry is server-side flag-gated so every off state is
byte-identical to pre-055 markup; ``render_workspace`` additionally stamps the
export/share data-flags on the canvas root for the client's toolbar.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from webrender.renderer import (  # noqa: E402
    render_component_fragment,
    render_workspace,
)


def _profile(device_type="browser", interactive=True):
    return types.SimpleNamespace(
        device_type=types.SimpleNamespace(value=device_type),
        supports_interactivity=interactive,
    )


def _table(**extra):
    comp = {"type": "table", "component_id": "wc_t1",
            "headers": ["a"], "rows": [["1"]]}
    comp.update(extra)
    return comp


@pytest.fixture(autouse=True)
def default_flags(monkeypatch):
    # Pin the shipped defaults regardless of the ambient environment.
    monkeypatch.delenv("FF_COMPONENT_REFINE", raising=False)
    monkeypatch.delenv("FF_ARTIFACT_EXPORT", raising=False)
    monkeypatch.delenv("FF_ARTIFACT_SHARING", raising=False)


# ───────────────────────── default-flag chrome ───────────────────────────────

def test_table_gets_refine_history_and_csv():
    out = render_component_fragment(_table(), _profile())
    assert "astral-component-chrome" in out
    assert "astral-refine-btn" in out
    assert "astral-vhistory-btn" in out
    assert 'href="/api/export/component/wc_t1.csv"' in out
    # sharing is fail-closed default OFF
    assert "astral-share-btn" not in out


def test_non_table_gets_no_csv_link():
    comp = {"type": "metric", "component_id": "wc_m1", "title": "M", "value": "1"}
    out = render_component_fragment(comp, _profile())
    assert "astral-refine-btn" in out
    assert "astral-export-csv" not in out


def test_share_appears_only_when_flag_on(monkeypatch):
    monkeypatch.setenv("FF_ARTIFACT_SHARING", "true")
    out = render_component_fragment(_table(), _profile())
    assert 'class="astral-share-btn' in out
    assert 'data-share-scope="component"' in out


# ───────────────────────── flag-off byte parity ──────────────────────────────

def test_all_flags_off_is_byte_identical_to_chromeless(monkeypatch):
    monkeypatch.setenv("FF_COMPONENT_REFINE", "false")
    monkeypatch.setenv("FF_ARTIFACT_EXPORT", "false")
    monkeypatch.setenv("FF_ARTIFACT_SHARING", "false")
    comp = _table()
    with_profile = render_component_fragment(comp, _profile())
    assert "astral-component-chrome" not in with_profile
    # identical to the pre-055 fragment (chrome never rendered for None).
    assert with_profile == render_component_fragment(comp, None)


def test_refine_flag_off_drops_refine_and_history(monkeypatch):
    monkeypatch.setenv("FF_COMPONENT_REFINE", "false")
    out = render_component_fragment(_table(), _profile())
    assert "astral-refine-btn" not in out
    assert "astral-vhistory-btn" not in out
    assert "astral-export-csv" in out  # export flag still default-on


def test_export_flag_off_drops_csv(monkeypatch):
    monkeypatch.setenv("FF_ARTIFACT_EXPORT", "false")
    out = render_component_fragment(_table(), _profile())
    assert "astral-export-csv" not in out
    assert "astral-refine-btn" in out


# ───────────────────────── host gating ───────────────────────────────────────

def test_no_profile_means_no_chrome():
    # Static renditions (exports, share snapshots, legacy calls) stay bare.
    assert "astral-component-chrome" not in render_component_fragment(_table())


def test_non_interactive_host_strips_chrome():
    out = render_component_fragment(_table(), _profile(interactive=False))
    assert "astral-component-chrome" not in out


def test_watch_and_voice_get_no_chrome():
    for dt in ("watch", "voice"):
        out = render_component_fragment(_table(), _profile(device_type=dt))
        assert "astral-component-chrome" not in out


# ───────────────────────── identity gating ───────────────────────────────────

def test_no_component_id_means_no_chrome():
    comp = {"type": "table", "headers": ["a"], "rows": [["1"]]}
    assert "astral-component-chrome" not in render_component_fragment(comp, _profile())


@pytest.mark.parametrize("cid", ["dg_note1", "wel_hero", "ly_key1"])
def test_ephemeral_identity_prefixes_get_no_chrome(cid):
    out = render_component_fragment(_table(component_id=cid), _profile())
    assert "astral-component-chrome" not in out


def test_decorative_type_gets_no_chrome():
    out = render_component_fragment(
        {"type": "divider", "component_id": "wc_d1"}, _profile())
    assert "astral-component-chrome" not in out


def test_csv_href_encodes_hostile_id():
    hostile = 'a/b"?x=1'
    out = render_component_fragment(_table(component_id=hostile), _profile())
    assert 'href="/api/export/component/a%2Fb%22%3Fx%3D1.csv"' in out
    assert 'href="/api/export/component/a/b' not in out


# ───────────────────────── version history payload ───────────────────────────

def test_versions_attr_bounded_and_whitelisted():
    versions = [{"version_no": i, "reason": "refine",
                 "created_at": f"2026-07-1{i}T00:00:00",
                 "title": f"T{i}", "junk": "<script>"} for i in range(1, 8)]
    out = render_component_fragment(_table(versions=versions), _profile())
    assert "data-versions=" in out
    assert "<script>" not in out
    assert "junk" not in out  # only whitelisted fields survive
    # bounded to the newest-5 retain window (first five list entries)
    assert "&quot;version_no&quot;: 5" in out
    assert "&quot;version_no&quot;: 6" not in out


def test_versions_attr_absent_for_junk_values():
    for versions in ("hax", {"a": 1}, [{"version_no": "x"}], []):
        out = render_component_fragment(_table(versions=versions), _profile())
        assert "data-versions" not in out


# ───────────────────────── canvas root data-flags ────────────────────────────

def test_workspace_root_stamps_export_flag_for_interactive_profile():
    out = render_workspace([_table()], _profile())
    assert out.startswith('<div class="dynamic-renderer space-y-3" data-astral-export="1">')
    assert "data-astral-share" not in out  # sharing default off


def test_workspace_root_stamps_share_flag_when_on(monkeypatch):
    monkeypatch.setenv("FF_ARTIFACT_SHARING", "true")
    out = render_workspace([], _profile())
    assert 'data-astral-export="1"' in out
    assert 'data-astral-share="1"' in out


def test_workspace_root_bare_without_profile_or_when_off(monkeypatch):
    assert render_workspace([]) == '<div class="dynamic-renderer space-y-3"></div>'
    monkeypatch.setenv("FF_ARTIFACT_EXPORT", "false")
    assert render_workspace([], _profile()) == '<div class="dynamic-renderer space-y-3"></div>'


def test_workspace_root_bare_on_watch_and_noninteractive():
    assert render_workspace([], _profile(device_type="watch")) == \
        '<div class="dynamic-renderer space-y-3"></div>'
    assert render_workspace([], _profile(interactive=False)) == \
        '<div class="dynamic-renderer space-y-3"></div>'
