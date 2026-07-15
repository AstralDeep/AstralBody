"""PyInstaller / run entry point for the AstralDeep Windows client.

The `--byo-worker` branch must come BEFORE `astral_client.app` (and therefore Qt)
is imported: the BYO agent host re-invokes `sys.executable` to run a delivered
agent in a child process, and under PyInstaller onefile `sys.executable` IS
AstralDeep.exe — so without this branch every user agent would raise a second,
invisible GUI (`console=False`) instead of a stdio worker.
See specs/058-byo-agents-runtime/contracts/host-bundle.md §4.
"""
import sys

if "--byo-worker" in sys.argv:
    from win_agent.byo_worker import main as worker_main

    raise SystemExit(worker_main())

from astral_client.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
