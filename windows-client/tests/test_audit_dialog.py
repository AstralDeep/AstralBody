"""Tests for the native AuditDialog (read-only audit-log viewer).

Needs Qt -> uses the offscreen ``qapp`` fixture (skips when PySide6 is absent).
The dialog owns no I/O; these exercise population (``add_page``), the reset/
append semantics of ``begin_load``, the filter round-trip, cursor pagination,
and the error path.
"""


def _row(**kw):
    base = {
        "recorded_at": "2026-06-30 12:00:00",
        "event_class": "auth",
        "action_type": "auth.ws_register",
        "outcome": "success",
        "description": "registered",
    }
    base.update(kw)
    return base


def test_add_page_appends_rows_and_toggles_load_more(qapp):
    from astral_client.app import AuditDialog

    d = AuditDialog(None, lambda f, reset: None)
    d.add_page([_row(), _row(outcome="failure")], "NEXT")
    assert d._table.rowCount() == 2
    # isVisibleTo(dialog) reflects the explicit flag without needing the dialog
    # to be actually shown on screen.
    assert d._more_btn.isVisibleTo(d)
    # A second page appends; a None cursor hides "Load more".
    d.add_page([_row(event_class="file")], None)
    assert d._table.rowCount() == 3
    assert not d._more_btn.isVisibleTo(d)


def test_begin_load_reset_clears_table(qapp):
    from astral_client.app import AuditDialog

    d = AuditDialog(None, lambda f, reset: None)
    d.add_page([_row()], None)
    assert d._table.rowCount() == 1
    d.begin_load(reset=True)
    assert d._table.rowCount() == 0


def test_begin_load_without_reset_keeps_rows(qapp):
    from astral_client.app import AuditDialog

    d = AuditDialog(None, lambda f, reset: None)
    d.add_page([_row()], "NEXT")
    d.begin_load(reset=False)
    assert d._table.rowCount() == 1


def test_apply_invokes_on_query_with_filters_and_reset(qapp):
    from astral_client.app import AuditDialog

    calls = []
    d = AuditDialog(None, lambda f, reset: calls.append((f, reset)))
    d._class.setCurrentIndex(d._class.findData("auth"))
    d._outcome.setCurrentIndex(d._outcome.findData("failure"))
    d._search.setText("login")
    d._apply()
    assert calls == [({"event_class": "auth", "outcome": "failure", "q": "login"}, True)]


def test_load_more_passes_cursor_and_reset_false(qapp):
    from astral_client.app import AuditDialog

    calls = []
    d = AuditDialog(None, lambda f, reset: calls.append((f, reset)))
    d.add_page([_row()], "CUR")   # sets the next cursor
    d._load_more()
    assert calls[-1][1] is False
    assert calls[-1][0]["cursor"] == "CUR"


def test_set_error_surfaces_message(qapp):
    from astral_client.app import AuditDialog

    d = AuditDialog(None, lambda f, reset: None)
    d.set_error("401: Unauthorized")
    assert "401" in d._status_lbl.text()
