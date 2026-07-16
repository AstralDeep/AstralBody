"""Pre-Qt PyInstaller/run entry point for the AstralDeep Windows client.

The `--byo-worker` branch must come BEFORE `astral_client.app` (and therefore Qt)
is imported: the BYO agent host re-invokes `sys.executable` to run a delivered
agent in a child process, and under PyInstaller onefile `sys.executable` IS
AstralDeep.exe — so without this branch every user agent would raise a second,
invisible GUI (`console=False`) instead of a stdio worker.
See specs/058-byo-agents-runtime/contracts/host-bundle.md §4.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys


def _restore_frozen_standard_streams() -> bool:
    """Rebuild redirected pipe streams hidden by PyInstaller windowed mode.

    ``console=False`` deliberately gives an ordinary GUI launch no console and
    sets Python's standard streams to ``None``. A frozen BYO worker is different:
    its supervising parent supplies real anonymous-pipe Windows handles. Duplicate
    and wrap only those inherited handles before importing the worker module.
    """

    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        return True
    if all(stream is not None for stream in (sys.stdin, sys.stdout, sys.stderr)):
        return True
    try:
        import ctypes
        from ctypes import wintypes
        import msvcrt
    except ImportError:
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.DuplicateHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    kernel32.DuplicateHandle.restype = wintypes.BOOL
    current_process = kernel32.GetCurrentProcess()
    invalid_handle = ctypes.c_void_p(-1).value

    def _open_stream(std_handle_id: int, *, reading: bool):
        source = kernel32.GetStdHandle(ctypes.c_ulong(std_handle_id).value)
        if not source or source == invalid_handle:
            return None
        duplicate = wintypes.HANDLE()
        if not kernel32.DuplicateHandle(
            current_process,
            source,
            current_process,
            ctypes.byref(duplicate),
            0,
            False,
            0x00000002,  # DUPLICATE_SAME_ACCESS
        ):
            return None
        flags = os.O_BINARY | (os.O_RDONLY if reading else os.O_WRONLY)
        try:
            descriptor = msvcrt.open_osfhandle(duplicate.value, flags)
            raw = os.fdopen(
                descriptor,
                "rb" if reading else "wb",
                buffering=0,
            )
            return io.TextIOWrapper(
                raw,
                encoding="utf-8",
                errors="replace" if reading else "backslashreplace",
                newline=None if reading else "\n",
                line_buffering=not reading,
                write_through=not reading,
            )
        except Exception:  # noqa: BLE001 - startup must fail closed below
            kernel32.CloseHandle(duplicate)
            return None

    if sys.stdin is None:
        sys.stdin = _open_stream(-10, reading=True)
    if sys.stdout is None:
        sys.stdout = _open_stream(-11, reading=False)
    if sys.stderr is None:
        sys.stderr = _open_stream(-12, reading=False)
    return all(stream is not None for stream in (sys.stdin, sys.stdout, sys.stderr))


def _resource_root() -> Path:
    """Return the PyInstaller extraction root or the source client directory."""

    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def main(argv=None) -> int:
    """Resolve one deployment, validate if requested, then import/start Qt."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if (
        "--byo-worker" in arguments or "--validate-deployment" in arguments
    ) and not _restore_frozen_standard_streams():
        return 78
    if "--byo-worker" in arguments:
        from win_agent.byo_worker import main as worker_main

        return worker_main([sys.argv[0], *arguments])

    from astral_client import __version__
    from astral_client.deployment import DeploymentProfileError, resolve_startup

    try:
        startup = resolve_startup(
            arguments,
            resource_root=_resource_root(),
            expected_client_version=__version__,
            frozen=bool(getattr(sys, "frozen", False)),
        )
    except DeploymentProfileError as exc:
        if sys.stderr is not None:
            print(f"AstralDeep deployment validation failed: {exc}", file=sys.stderr)
        return 78
    if startup.validation_report is not None:
        print(json.dumps(startup.validation_report, sort_keys=True))
        return 0

    # Deliberately imported only after the immutable profile has resolved.
    from astral_client.app import main as app_main

    return app_main(
        effective_profile=startup.effective_profile,
        argv=list(startup.remaining_args),
    )

if __name__ == "__main__":
    raise SystemExit(main())
