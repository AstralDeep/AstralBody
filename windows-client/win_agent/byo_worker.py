"""BYO agent worker entry — always the child side of the 058/060 host.

Runs ONE delivered bundle (`%LOCALAPPDATA%/AstralDeep/agents/<agent_id>/`) in a
process of its own. The versioned bundle's `agent_main.py` owns the stdio loop:
v2 reads the non-secret launch fence/runtime metadata supplied by its parent,
emits `agent_runtime_register`, then handles fully fenced request JSON lines.
This module's whole job is to make that file importable and hand it control.

**Imports no Qt.** Under PyInstaller onefile the worker's interpreter is
AstralDeep.exe itself, so anything imported here is imported into every agent
process; pulling in Qt would raise a second GUI (and cost ~100 MB of RSS per
agent). It also intentionally does not import or instantiate the process
supervisor: only the parent host owns process trees, pipes, deadlines, and
termination. `main.py` branches on `--byo-worker` before Qt loads for the same
reason.

Bundle entry contract (the seam T008's generator template must satisfy):
`agent_main.py` either runs its stdio loop at import time, or exposes a
`main()` / `run()` callable. Both are supported; anything else is a bad bundle
and is reported on stderr, which the supervisor logs.
"""
from __future__ import annotations

import importlib
import io
import os
import sys
import traceback


def _rebind_std_streams() -> bool:
    """Guarantee `sys.stdout`/`sys.stderr` are the real OS pipes. Returns False
    if stdout is unusable (in which case there is no channel and no agent).

    THE FROZEN-BUILD TRAP: the worker's interpreter is AstralDeep.exe itself and
    the spec builds it `console=False` — a windowed PyInstaller bootloader "may
    have no stdout" (the same hazard `astral_client/auth.py` already documents).
    If Python's `sys.stdout` came up as `None`, the bundle's `print(..., flush=True)`
    would raise, `register_agent` would never reach the parent, and EVERY BYO
    agent would fail in the SHIPPED product while working perfectly from source —
    with the traceback swallowed too, so undiagnosably.

    The parent always creates the pipes (`subprocess.PIPE` on fds 0/1/2), so the
    OS handles exist even when the Python-level objects don't: re-open the fds.
    """
    for fd, name, mode in ((1, "stdout", "w"), (2, "stderr", "w"), (0, "stdin", "r")):
        stream = getattr(sys, name, None)
        if stream is not None and callable(getattr(stream, "write", None) if mode == "w"
                                           else getattr(stream, "readline", None)):
            continue
        try:
            rebound = os.fdopen(
                fd, mode, buffering=1,  # line-buffered: one JSON frame per line
                encoding="utf-8", errors="replace", closefd=False,
            )
        except OSError:
            rebound = None
        if rebound is None and mode == "w":
            # No pipe at all on this fd. stderr can degrade to a sink; stdout is
            # the agent channel and its absence is fatal — say so, don't limp on.
            if name == "stderr":
                rebound = io.StringIO()
            else:
                return False
        setattr(sys, name, rebound)
    return getattr(sys, "stdout", None) is not None


def run_worker(agent_dir: str) -> int:
    """Import and run the delivered agent in this process. Returns an exit code."""
    if not _rebind_std_streams():
        return 3  # no stdout => no agent channel; nothing useful can happen
    directory = os.path.abspath(agent_dir or "")
    entry = os.path.join(directory, "agent_main.py")
    if not os.path.isfile(entry):
        print(f"byo-worker: no agent_main.py in {directory}", file=sys.stderr, flush=True)
        return 2

    # The bundle is self-contained and imports `mcp_tools` as a SIBLING module
    # (never `shared.*` / `agents.*` — contract §2), so its own directory has to
    # come first on the path.
    sys.path.insert(0, directory)
    try:
        module = importlib.import_module("agent_main")
    except Exception:  # noqa: BLE001 — LLM-written code; report, never crash silently
        traceback.print_exc()
        return 1

    entrypoint = getattr(module, "main", None) or getattr(module, "run", None)
    if not callable(entrypoint):
        # The module ran its loop at import and has now returned (EOF on stdin).
        return 0
    try:
        return int(entrypoint() or 0)
    except SystemExit as exc:  # a bundle that exits deliberately
        return int(exc.code or 0)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--byo-worker" not in argv:
        print("usage: --byo-worker <agent_dir>", file=sys.stderr, flush=True)
        return 2
    idx = argv.index("--byo-worker")
    if idx + 1 >= len(argv):
        print("byo-worker: missing <agent_dir>", file=sys.stderr, flush=True)
        return 2
    return run_worker(argv[idx + 1])


if __name__ == "__main__":
    raise SystemExit(main())
