"""Cross-client top-bar parity (Constitution XII).

The top bar is ONE shared, server-owned definition: "No client may add, omit,
rename, reorder, or otherwise diverge from those shared definitions"
(`.specify/memory/constitution.md`), and
`specs/044-native-client-parity/contracts/chrome-parity.md` pins "Ordering and
presence follow the model verbatim".

Web, Android and Apple all lay the bar out as

    brand · New chat · Recent chats · <server-model actions> · Settings

The Windows client shipped the server-model action cluster (Pulse, Workspace
timeline) BEFORE the client-local New/Recent buttons — visibly out of order next
to the web app on the same desktop, which is the constitution's own example. This
file is the drift guard so it cannot silently regress.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


def _bar(qapp):
    from astral_client.app import TopBar

    return TopBar("u", lambda: None, lambda: None, lambda s, ln: None, lambda: None)


def _order(tb):
    """The widgets of the top-bar row, in visual (layout) order."""
    lay = tb.layout()
    out = []
    for i in range(lay.count()):
        item = lay.itemAt(i)
        w = item.widget()
        out.append(w if w is not None else "stretch")
    return out


def test_topbar_widget_order_matches_the_shared_model(qapp):
    tb = _bar(qapp)
    order = _order(tb)

    # brand < (stretch) < new < recent < server-model actions < settings
    assert order[0] is tb._mark
    assert order[1] == "stretch"
    assert order[2:] == [tb.new_btn, tb.recent_btn, tb._actions_holder, tb.settings_btn]


def test_server_model_actions_sit_between_recent_and_settings(qapp):
    """The specific defect: the actions holder must NOT precede New/Recent."""
    tb = _bar(qapp)
    order = _order(tb)

    assert order.index(tb._actions_holder) > order.index(tb.recent_btn)
    assert order.index(tb._actions_holder) > order.index(tb.new_btn)
    assert order.index(tb._actions_holder) < order.index(tb.settings_btn)


def test_recent_chats_does_not_use_the_clock_glyph(qapp):
    """The clock belongs to the server 'Workspace timeline' control, which now
    sits immediately beside Recent chats — two clocks side by side is the drift
    android's RootScaffold explicitly warns about."""
    tb = _bar(qapp)
    assert "🕓" not in tb.recent_btn.text()
    assert "Recent chats" in tb.recent_btn.text()
