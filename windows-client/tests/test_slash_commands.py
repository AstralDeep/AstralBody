"""Feature 068 (US5) — slash-command discovery popup in the Windows client.

Verifies the QCompleter model: every command is present, the popup display
carries the description while the inserted value is the clean "/command "
token, and prefix filtering narrows correctly. Runs headlessly via the offscreen
``qapp`` fixture (skips when PySide6 is not installed).
"""
from astral_client.app import build_slash_completer, _SLASH_COMMANDS


def test_completer_lists_all_commands(qapp):
    from PySide6.QtCore import Qt

    comp = build_slash_completer()
    model = comp.model()
    assert model.rowCount() == len(_SLASH_COMMANDS) == 5

    displays = [model.data(model.index(i, 0), Qt.ItemDataRole.DisplayRole) for i in range(model.rowCount())]
    edits = [model.data(model.index(i, 0), Qt.ItemDataRole.EditRole) for i in range(model.rowCount())]

    # Popup display carries name + description; inserted value is the clean
    # "/command " token (ready for arguments).
    assert any(d.startswith("/help") and "show available commands" in d for d in displays)
    assert "/summarize " in edits
    assert "/weather " in edits


def test_completer_prefix_filtering(qapp):
    comp = build_slash_completer()

    # "/" surfaces every command.
    comp.setCompletionPrefix("/")
    assert comp.completionCount() == 5

    # "/sum" narrows to a single command and inserts the clean token.
    comp.setCompletionPrefix("/sum")
    assert comp.completionCount() == 1
    assert comp.currentCompletion() == "/summarize "

    # A non-slash prefix matches nothing (popup stays hidden for normal text).
    comp.setCompletionPrefix("hello")
    assert comp.completionCount() == 0
