"""Headless screenshot harness: drives the real MainWindow against a running
(mock-auth) orchestrator and grabs the window to PNGs at each stage, so the UI
can be verified without a display. Offscreen Qt + QWidget.grab().

Usage:  python tests/screenshot.py --prompt "roll 3 dice"
Outputs: shot_welcome.png, shot_chat.png in the cwd.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication  # noqa: E402

from astral_client.app import MainWindow, configure  # noqa: E402


def pump(app: QApplication, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def grab(win: MainWindow, path: str) -> None:
    win.grab().save(path)
    status = win._status.text().encode("ascii", "replace").decode()
    print("saved", path, "| status:", status)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://127.0.0.1:8001/ws")
    ap.add_argument("--token", default="dev-token")
    ap.add_argument("--prompt", default="roll 3 dice and show the results")
    ap.add_argument("--out", default=".")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    configure(app)
    win = MainWindow(args.url, args.token)
    win.resize(1300, 860)
    win.show()

    pump(app, 5)                       # connect + welcome canvas
    grab(win, os.path.join(args.out, "shot_welcome.png"))

    win._input.setText(args.prompt)    # ask a question
    win._send()
    pump(app, float(os.getenv("SHOT_WAIT", "28")))   # ReAct loop + designer + components
    grab(win, os.path.join(args.out, "shot_chat.png"))

    win.client.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
