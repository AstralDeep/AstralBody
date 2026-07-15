"""BYO agent host: supervise the user's own agents as child processes (058 T012).

This is the desktop half of `specs/058-byo-agents-runtime/contracts/host-bundle.md`.
The orchestrator generates a self-contained 3-file bundle and pushes it down the
owner's authenticated UI socket; this module writes it to disk, runs it as a
**separate child process**, and pumps frames between that child and the socket:

    orchestrator ──ws(agent_tunnel)──► client ──stdin (json lines)──► child
                 ◄─ws(agent_tunnel)───        ◄─stdout (json lines)──

The client is a **dumb pipe**. It does not parse, rewrite or validate agent
frames (beyond "is this one JSON object?"): the agent is untrusted, and every
gate that matters — owner binding, permissions, delegation, PHI — is re-applied
at the orchestrator, which is where the trust boundary actually is. Doing
"security" here would only move the check to the machine the attacker owns.

Why a child process and not a thread (unlike `win_agent/agent.py`, the built-in
Windows tools agent, which is an in-process aiohttp server the orchestrator
dials INTO): the code is LLM-written and user-owned. It gets its own process so
a crash, a `sys.exit()`, a runaway loop or a blocking C call cannot take the GUI
with it, and so termination is a real kill rather than a cooperative request.

No Qt in this module — the child pump runs on plain threads, so it is testable
without a QApplication and cannot touch a widget from the wrong thread. Callers
pass a `notify` callable that marshals to the GUI thread (a Qt signal's `.emit`).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("astral.client.byo")

#: The frame types this host owns on the inbound UI socket.
HOST_FRAME_TYPES = ("agent_bundle_deliver", "agent_tunnel", "agent_stop", "agent_offline")

#: How long to wait for the server's `agent_registered` ack after starting a
#: child. THE SILENCE TRAP (contract §6): a REFUSED registration produces no
#: frame at all — the orchestrator closes a `TunnelSocket`, whose `close()` is a
#: parity no-op, and there is no NAK in the protocol. Waiting forever on a frame
#: that will never come would leave a zombie child and a permanently "starting"
#: agent, so silence is treated as failure.
REGISTER_TIMEOUT_S = float(os.getenv("BYO_REGISTER_TIMEOUT_S", "20"))

#: An agent_id is used as a DIRECTORY NAME under the agents root, so the charset
#: alone is not enough: `.` and `..` match it and would escape (or clobber) the
#: root. Anything starting with a dot is refused, and the resolved path is
#: re-checked against the root before a single byte is written (`_agent_dir`).
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}$")


def agents_root() -> str:
    """`%LOCALAPPDATA%/AstralDeep/agents` (contract §5); `~/.astraldeep/agents`
    where LOCALAPPDATA is absent, so the module imports and tests on any OS."""
    base = os.getenv("BYO_AGENTS_DIR") or os.getenv("LOCALAPPDATA")
    if base:
        return os.path.join(base, "AstralDeep", "agents")
    return os.path.join(os.path.expanduser("~"), ".astraldeep", "agents")


def worker_argv(agent_dir: str) -> List[str]:
    """The command that re-invokes THIS application as a worker (contract §4).

    Frozen (PyInstaller onefile, `console=False`), `sys.executable` IS
    AstralDeep.exe, so the flag goes straight to it — and `main.py` must branch
    on it before Qt loads or every worker would raise a second GUI. Run from
    source, `sys.executable` is python.exe, which would treat `--byo-worker` as
    its own (unknown) option, so the script path has to be passed explicitly.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "--byo-worker", agent_dir]
    main_py = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"
    )
    return [sys.executable, main_py, "--byo-worker", agent_dir]


def _spawn(argv: List[str]) -> subprocess.Popen:
    return subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,  # line-buffered: a frame is relayed as soon as it is written
        # Keep a console window from flashing up behind the GUI on Windows.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class _Child:
    """One supervised user agent."""

    def __init__(self, agent_id: str, proc, directory: str) -> None:
        self.agent_id = agent_id
        self.proc = proc
        self.dir = directory
        self.registered = False
        #: Last `register_agent` the child emitted — replayed on socket
        #: reconnect, because the server pops `self.agents[agent_id]` on teardown
        #: and would otherwise never route to this (still running) child again.
        self.register_frame: Optional[str] = None
        self.timer: Optional[threading.Timer] = None
        self.threads: List[threading.Thread] = []

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None


class ByoAgentHost:
    """Supervises the user's BYO agents for one client session."""

    def __init__(
        self,
        send_event: Callable[[str, dict], None],
        notify: Optional[Callable[[str, str], None]] = None,
        base_dir: Optional[str] = None,
        spawn: Callable[[List[str]], object] = _spawn,
        register_timeout: float = REGISTER_TIMEOUT_S,
    ) -> None:
        self._send_event = send_event
        self._notify = notify or (lambda text, level="info": None)
        self._base_dir = base_dir or agents_root()
        self._spawn = spawn
        self._register_timeout = register_timeout
        # Identifies this host process to the server for the life of the client
        # (stamped on `user_agent.host_session_id` at registration).
        self.host_session_id = uuid.uuid4().hex
        self._children: Dict[str, _Child] = {}
        self._lock = threading.Lock()
        self._rehydrated = False

    def _agent_dir(self, agent_id: str) -> Optional[str]:
        """The on-disk directory for one agent, or None if the id cannot own one.

        Defence in depth: the delivering server is trusted and namespaces the id,
        but this path is the one place a bad id turns into a WRITE — so the id is
        charset+dot checked AND the resolved target is asserted to sit under the
        agents root before anything is created.
        """
        if not _SAFE_ID.match(agent_id or ""):
            return None
        base = os.path.realpath(self._base_dir)
        target = os.path.realpath(os.path.join(self._base_dir, agent_id))
        try:
            if target == base or os.path.commonpath([base, target]) != base:
                return None
        except ValueError:  # different drives on Windows: not under the root
            return None
        return os.path.join(self._base_dir, agent_id)

    # --- inbound (server -> host) ----------------------------------------- #

    def handle_frame(self, msg: dict) -> bool:
        """Route one server frame. Returns True if this host consumed it."""
        t = msg.get("type")
        if t == "agent_bundle_deliver":
            self.deliver(
                msg.get("agent_id") or "",
                msg.get("files") or {},
                msg.get("constitution_version"),
            )
        elif t == "agent_tunnel":
            self._to_child(msg.get("agent_id") or "", msg.get("frame"))
        elif t == "agent_stop":
            # A SERVER stop is terminal (the agent was deleted/deauthorized), so
            # the bundle leaves the disk too: LLM-written source must not sit at
            # rest under %LOCALAPPDATA% after the agent is gone — and with
            # rehydrate-on-connect below, a leftover directory would resurrect it.
            self.remove(msg.get("agent_id") or "")
        elif t == "agent_offline":
            # The server dropped routing for one of this owner's agents (its host
            # socket went away). Informational here — another device may have
            # been hosting it; our own children are supervised locally.
            logger.info("server reports agent offline: %s", msg.get("agent_id"))
        else:
            return False
        return True

    def on_agent_registered(self, agent_id: str) -> None:
        """The server accepted the child's registration — disarm the silence
        timeout (see REGISTER_TIMEOUT_S)."""
        with self._lock:
            child = self._children.get(agent_id)
            if child is None or child.registered:
                return
            child.registered = True
            timer, child.timer = child.timer, None
        if timer is not None:
            timer.cancel()
        logger.info("byo agent %s registered", agent_id)
        self._notify(f"Your agent “{agent_id}” is running on this PC.", "info")

    def on_ui_connected(self) -> None:
        """Re-send every running child's `register_agent` after a (re)connect —
        the server pops its `agents` entry on socket teardown, so without this
        the child stays alive but unreachable (contract §5).

        On the FIRST connect of a process there are no children yet: the bundles
        are on disk from an earlier session and nothing re-delivers them (the
        server only pushes `agent_bundle_deliver` from the generation path), so
        without `rehydrate()` every agent the user ever made would be permanently
        offline after the client restarts."""
        self.rehydrate()
        with self._lock:
            children = [c for c in self._children.values() if c.alive() and c.register_frame]
        for child in children:
            child.registered = False
            self._arm_register_timeout(child.agent_id)
            self._tunnel_out(child.agent_id, child.register_frame)
        if children:
            logger.info("re-registered %d byo agent(s) after reconnect", len(children))

    def rehydrate(self) -> List[str]:
        """Start every bundle already on disk (once per host process).

        The host does NOT decide whether an agent is still allowed to run: the
        server re-authorizes at registration, so a soft-deleted or deauthorized
        agent is simply refused, goes silent, and the REGISTER_TIMEOUT_S reaper
        removes the child. That is the safe direction — refuse-by-server, not
        trust-the-disk.

        Once only: after a mid-session reconnect a child that has already exited
        must stay offline (contract §5 — "do not auto-respawn"), and a child that
        is still running is re-registered by `on_ui_connected` above.
        """
        with self._lock:
            if self._rehydrated:
                return []
            self._rehydrated = True
            known = set(self._children)

        started: List[str] = []
        try:
            entries = sorted(os.listdir(self._base_dir))
        except OSError:
            return started  # no agents root yet: nothing was ever delivered
        for agent_id in entries:
            if agent_id in known:
                continue
            directory = self._agent_dir(agent_id)
            if not directory or not os.path.isfile(os.path.join(directory, "agent_main.py")):
                continue
            self._start(agent_id, directory)
            started.append(agent_id)
        if started:
            logger.info("rehydrated %d byo agent(s) from disk: %s", len(started), started)
        return started

    # --- lifecycle --------------------------------------------------------- #

    def deliver(self, agent_id: str, files: dict, constitution_version=None) -> Optional[str]:
        """Write a delivered bundle and start it. Returns the agent dir, or None."""
        directory = self._agent_dir(agent_id)
        if directory is None:
            logger.warning("refusing bundle with unusable agent_id %r", agent_id)
            return None
        if not isinstance(files, dict) or not files:
            logger.warning("refusing empty bundle for %s", agent_id)
            return None

        self.stop(agent_id)  # a redelivery (revision) replaces the running child
        try:
            os.makedirs(directory, exist_ok=True)
            for name, source in files.items():
                # The bundle is a FLAT {filename: source} map; anything that
                # tries to escape the agent's own directory is not a filename.
                if not isinstance(name, str) or not isinstance(source, str):
                    continue
                if os.path.basename(name) != name or name in (".", ".."):
                    logger.warning("skipping bundle entry with a path in it: %r", name)
                    continue
                with open(os.path.join(directory, name), "w", encoding="utf-8") as fh:
                    fh.write(source)
        except OSError:
            logger.exception("could not write the bundle for %s", agent_id)
            self._notify(f"Couldn't save your agent “{agent_id}” to this PC.", "error")
            return None

        logger.info("wrote %d bundle file(s) for %s -> %s", len(files), agent_id, directory)
        self._start(agent_id, directory)
        return directory

    def _start(self, agent_id: str, directory: str) -> None:
        try:
            proc = self._spawn(worker_argv(directory))
        except Exception:  # noqa: BLE001 — a failed spawn is a user-visible failure
            logger.exception("could not start the worker for %s", agent_id)
            self._notify(f"Couldn't start your agent “{agent_id}”.", "error")
            return

        child = _Child(agent_id, proc, directory)
        with self._lock:
            self._children[agent_id] = child

        for name, stream, pump in (
            ("stdout", proc.stdout, self._pump_stdout),
            ("stderr", proc.stderr, self._pump_stderr),
        ):
            if stream is None:
                continue
            th = threading.Thread(
                target=pump, args=(child, stream), name=f"byo-{name}-{agent_id}", daemon=True
            )
            th.start()
            child.threads.append(th)

        # Armed at spawn, not at the first stdout frame: a child that dies before
        # it ever writes `register_agent` must fail here too, not hang forever.
        self._arm_register_timeout(agent_id)
        logger.info("started byo agent %s (pid=%s)", agent_id, getattr(proc, "pid", "?"))

    def stop(self, agent_id: str) -> bool:
        """Terminate one child and forget it. Idempotent."""
        with self._lock:
            child = self._children.pop(agent_id, None)
        if child is None:
            return False
        self._kill(child)
        logger.info("stopped byo agent %s", agent_id)
        return True

    def remove(self, agent_id: str) -> bool:
        """Terminate one child AND delete its bundle from disk (server `agent_stop`).

        Distinct from `stop()`, which is the internal "replace this child" used by
        re-delivery and by client shutdown — those must KEEP the bundle.
        """
        stopped = self.stop(agent_id)
        directory = self._agent_dir(agent_id)
        if directory and os.path.isdir(directory):
            try:
                shutil.rmtree(directory)
                logger.info("removed the bundle for %s", agent_id)
            except OSError:
                logger.exception("could not remove the bundle dir for %s", agent_id)
        return stopped

    def stop_all(self) -> None:
        """Client is closing: every user agent dies with it (contract §5) — the
        server sees the socket drop and takes them honestly offline."""
        with self._lock:
            children = list(self._children.values())
            self._children.clear()
        for child in children:
            self._kill(child)
        if children:
            logger.info("stopped %d byo agent(s) on client close", len(children))

    def running(self) -> List[str]:
        with self._lock:
            return [a for a, c in self._children.items() if c.alive()]

    # --- pipes ------------------------------------------------------------- #

    def _pump_stdout(self, child: _Child, stream) -> None:
        """child stdout (json lines) -> agent_tunnel over the UI socket."""
        for line in iter(stream.readline, ""):
            line = line.strip()
            if not line:
                continue
            try:
                frame = json.loads(line)
            except (ValueError, TypeError):
                # A stray print() in LLM-written tool code must not corrupt the
                # channel (contract §3): discard the line, keep the agent up.
                logger.warning("byo %s: discarding non-JSON stdout line: %.120s",
                               child.agent_id, line)
                continue
            if not isinstance(frame, dict):
                logger.warning("byo %s: discarding non-object stdout frame", child.agent_id)
                continue
            if frame.get("type") == "register_agent":
                # The envelope is stamped with the id we SPAWNED, but the server
                # keys the tunnel by the envelope id and then ROUTES by the id in
                # the card. If they disagree, `agents[<card id>]` ends up pointing
                # at a socket that teardown (keyed by the envelope id) never
                # clears — invocations then hang instead of answering
                # honest-offline. The host knows what it started: refuse the frame.
                card = frame.get("agent_card")
                card_id = card.get("agent_id") if isinstance(card, dict) else None
                if card_id != child.agent_id:
                    logger.warning(
                        "byo %s: dropping register_agent for a different agent_id %r",
                        child.agent_id, card_id,
                    )
                    continue
                child.register_frame = json.dumps(frame)
            self._tunnel_out(child.agent_id, json.dumps(frame))
        self._on_child_exit(child)

    def _pump_stderr(self, child: _Child, stream) -> None:
        """stderr is diagnostics only — logged, never relayed (contract §3)."""
        for line in iter(stream.readline, ""):
            if line.strip():
                logger.info("byo %s: %s", child.agent_id, line.rstrip())

    def _to_child(self, agent_id: str, frame) -> None:
        """An inbound `agent_tunnel` push -> the child's stdin, one JSON line."""
        with self._lock:
            child = self._children.get(agent_id)
        if child is None or not child.alive() or child.proc.stdin is None:
            logger.warning("agent_tunnel for %s with no running child — dropped", agent_id)
            return
        if frame is None:
            return
        text = frame if isinstance(frame, str) else json.dumps(frame)
        try:
            child.proc.stdin.write(text.rstrip("\n") + "\n")
            child.proc.stdin.flush()
        except (OSError, ValueError):
            logger.warning("byo %s: stdin closed — dropping frame", agent_id)

    def _tunnel_out(self, agent_id: str, frame: str) -> None:
        """Wrap one agent frame in the C->S `agent_tunnel` ui_event (contract §7)."""
        try:
            self._send_event("agent_tunnel", {
                "agent_id": agent_id,
                "frame": frame,
                "host_session_id": self.host_session_id,
            })
        except Exception:  # noqa: BLE001 — a dead socket must not kill the pump
            logger.debug("agent_tunnel send failed for %s", agent_id, exc_info=True)

    # --- failure handling --------------------------------------------------- #

    def _arm_register_timeout(self, agent_id: str) -> None:
        timer = threading.Timer(
            self._register_timeout, self._registration_timed_out, args=(agent_id,)
        )
        timer.daemon = True
        with self._lock:
            child = self._children.get(agent_id)
            if child is None:
                return
            child.timer = timer
        timer.start()

    def _registration_timed_out(self, agent_id: str) -> None:
        with self._lock:
            child = self._children.get(agent_id)
            if child is None or child.registered:
                return
            self._children.pop(agent_id, None)
        self._kill(child)
        logger.warning("byo %s: no agent_registered ack — reaped the child", agent_id)
        self._notify(
            f"Your agent “{agent_id}” couldn't start: the server didn't accept it. "
            "Open your agents and try again.",
            "error",
        )

    def _on_child_exit(self, child: _Child) -> None:
        """stdout closed: the child is gone. No auto-respawn in v1 — an agent
        that is not running should look offline, not flap (contract §5)."""
        with self._lock:
            known = self._children.get(child.agent_id)
            if known is not child:
                return  # already stopped/replaced deliberately
            self._children.pop(child.agent_id, None)
            timer, child.timer = child.timer, None
        if timer is not None:
            timer.cancel()
        code = child.proc.poll()
        logger.warning("byo agent %s exited (code=%s)", child.agent_id, code)
        if child.registered:
            self._notify(f"Your agent “{child.agent_id}” stopped running.", "warning")

    def _kill(self, child: _Child) -> None:
        if child.timer is not None:
            child.timer.cancel()
            child.timer = None
        proc = child.proc
        try:
            if proc.stdin is not None:
                proc.stdin.close()  # EOF: the runner's stdin loop exits cleanly
        except (OSError, ValueError):
            pass
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:  # noqa: BLE001 — already dead / no such process
            logger.debug("terminate failed for %s", child.agent_id, exc_info=True)
