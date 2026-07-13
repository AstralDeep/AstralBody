"""Feature 055 (US4 T040 + US5 T045) — canvas component context menu.

Right-click on a canvas component offers Refine… (emits ``component_refine``
per wire-contract §3; disabled while viewing history) plus the export entries
(CSV for tables, canvas HTML) that open the session-authed export URLs in the
system browser. No versions submenu: no native frame carries the version
list, so restore stays a web affordance (declared parity carve-out).
"""
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint  # noqa: E402

from astral_client import app as appmod  # noqa: E402
from astral_client import rest  # noqa: E402
from astral_client.app import Canvas  # noqa: E402
from astral_client.renderer import RenderContext  # noqa: E402


def _canvas(emit=None, chat_id="c1", http_base="http://127.0.0.1:8001"):
    c = Canvas(RenderContext(emit=emit or (lambda *a: None), chat_id=chat_id))
    c.http_base = http_base
    return c


def _card(cid):
    return {"type": "card", "component_id": cid, "title": "Card", "content": []}


def _table(cid):
    return {"type": "table", "component_id": cid, "headers": ["A"], "rows": [["1"]]}


def _labels(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def _action(menu, label):
    return next(a for a in menu.actions() if a.text() == label)


# --- URL builders (pure) ------------------------------------------------------

def test_export_component_csv_url():
    assert rest.export_component_csv_url("http://h:8001/", "wc_a", "c1") == (
        "http://h:8001/api/export/component/wc_a.csv?chat_id=c1"
    )


def test_export_csv_url_quotes_unsafe_segments():
    url = rest.export_component_csv_url("http://h", "a b/c", "c 1")
    assert "/api/export/component/a%20b%2Fc.csv?" in url
    assert "chat_id=c+1" in url


def test_export_canvas_html_url():
    assert rest.export_canvas_html_url("http://h:8001", "c1") == (
        "http://h:8001/api/export/canvas/c1.html"
    )


# --- menu composition ---------------------------------------------------------

def test_menu_on_table_offers_refine_and_both_exports(qapp):
    c = _canvas()
    c.set_components([_table("wc_t")])
    menu = c.component_menu("wc_t", c._rendered["wc_t"])
    assert _labels(menu) == ["Refine…", "Export data (CSV)", "Export canvas (HTML)"]


def test_menu_on_non_table_has_no_csv_entry(qapp):
    c = _canvas()
    c.set_components([_card("wc_a")])
    menu = c.component_menu("wc_a", c._rendered["wc_a"])
    assert _labels(menu) == ["Refine…", "Export canvas (HTML)"]


def test_menu_on_bare_canvas_offers_canvas_export_only(qapp):
    menu = _canvas().component_menu(None, None)
    assert _labels(menu) == ["Export canvas (HTML)"]


def test_menu_without_chat_or_component_is_none(qapp):
    assert _canvas(chat_id=None).component_menu(None, None) is None


def test_menu_without_chat_still_offers_refine(qapp):
    c = _canvas(chat_id=None)
    c.set_components([_table("wc_t")])
    # No chat context → no export URLs; refine (id-scoped) remains.
    assert _labels(c.component_menu("wc_t", c._rendered["wc_t"])) == ["Refine…"]


def test_refine_disabled_in_timeline_mode(qapp):
    c = _canvas()
    c.set_components([_card("wc_a")])
    c.timeline_mode = True
    menu = c.component_menu("wc_a", c._rendered["wc_a"])
    assert not _action(menu, "Refine…").isEnabled()


# --- export actions open the system browser ------------------------------------

def test_csv_export_opens_url(qapp):
    opened = []
    c = _canvas()
    c.open_url = opened.append
    c.set_components([_table("wc_t")])
    _action(c.component_menu("wc_t", c._rendered["wc_t"]), "Export data (CSV)").trigger()
    assert opened == ["http://127.0.0.1:8001/api/export/component/wc_t.csv?chat_id=c1"]


def test_canvas_export_opens_url(qapp):
    opened = []
    c = _canvas()
    c.open_url = opened.append
    _action(c.component_menu(None, None), "Export canvas (HTML)").trigger()
    assert opened == ["http://127.0.0.1:8001/api/export/canvas/c1.html"]


# --- refine emit path -----------------------------------------------------------

def test_refine_emits_component_refine(qapp, monkeypatch):
    seen = []
    monkeypatch.setattr(appmod, "_ask_refine_instruction",
                        lambda parent, title: "make it blue")
    c = _canvas(emit=lambda a, p: seen.append((a, p)))
    c.set_components([_card("wc_a")])
    _action(c.component_menu("wc_a", c._rendered["wc_a"]), "Refine…").trigger()
    assert seen == [("component_refine", {
        "component_id": "wc_a", "instruction": "make it blue", "chat_id": "c1"})]


def test_refine_without_chat_omits_chat_id(qapp, monkeypatch):
    seen = []
    monkeypatch.setattr(appmod, "_ask_refine_instruction", lambda *a: "shorter")
    c = _canvas(emit=lambda a, p: seen.append((a, p)), chat_id=None)
    c.request_refine("wc_a")
    assert seen == [("component_refine",
                     {"component_id": "wc_a", "instruction": "shorter"})]


def test_refine_cancelled_prompt_sends_nothing(qapp, monkeypatch):
    seen = []
    monkeypatch.setattr(appmod, "_ask_refine_instruction", lambda *a: "")
    c = _canvas(emit=lambda a, p: seen.append((a, p)))
    c.request_refine("wc_a")
    assert seen == []


def test_refine_refused_in_timeline_mode(qapp, monkeypatch):
    seen = []
    # The prompt must not even open on a read-only historical view.
    monkeypatch.setattr(appmod, "_ask_refine_instruction",
                        lambda *a: pytest.fail("prompt opened in timeline mode"))
    c = _canvas(emit=lambda a, p: seen.append((a, p)))
    c.timeline_mode = True
    c.request_refine("wc_a")
    assert seen == []


# --- hit-testing: only canvas-tracked identities are targeted -------------------

def test_component_at_resolves_top_level_identity(qapp):
    c = _canvas()
    c.set_components([_card("wc_a")])
    inner_label = c._by_id["wc_a"].findChildren(appmod.QLabel)[0]
    c._inner.childAt = lambda pos: inner_label  # offscreen: no real geometry
    cid, comp = c._component_at(QPoint(1, 1))
    assert cid == "wc_a" and comp["component_id"] == "wc_a"


def test_component_at_skips_nested_author_ids(qapp):
    c = _canvas()
    comp = _card("wc_a")
    comp["content"] = [{"type": "text", "id": "author-child", "content": "x"}]
    c.set_components([comp])
    # The nested child's widget carries the author id property, but it is not a
    # workspace identity — the walk must land on the top-level component.
    child = next(w for w in c._by_id["wc_a"].findChildren(appmod.QLabel)
                 if w.property("component_id") == "author-child")
    c._inner.childAt = lambda pos: child
    cid, _ = c._component_at(QPoint(1, 1))
    assert cid == "wc_a"


def test_component_at_misses_return_none(qapp):
    c = _canvas()
    c._inner.childAt = lambda pos: None
    assert c._component_at(QPoint(1, 1)) == (None, None)
