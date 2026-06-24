"""Test bootstrap — path setup + (optional) headless Qt.

The Qt import is guarded so pure-Python tests (the codegen tools, phi_gate,
audit_log) can run without PySide6 installed. Tests that actually need Qt use
the ``qapp`` fixture, which skips gracefully when PySide6 is unavailable.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest  # noqa: E402

try:
    from PySide6.QtWidgets import QApplication  # noqa: E402
    _HAS_QT = True
except Exception:  # noqa: BLE001 — Qt is optional for non-renderer tests
    QApplication = None  # type: ignore[assignment]
    _HAS_QT = False


@pytest.fixture(scope="session")
def qapp():
    if not _HAS_QT:
        pytest.skip("PySide6 not installed")
    app = QApplication.instance() or QApplication([])
    yield app
