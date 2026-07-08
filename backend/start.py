"""
Start the full system: Orchestrator + General Agent.
"""
import subprocess
import time
import sys
import os
import urllib.request

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass


def _wait_for_orchestrator(port: int, process, timeout_s: float = 60.0,
                           interval_s: float = 0.5) -> bool:
    """Poll the orchestrator's /healthz until it answers, dies, or times out.

    Proceeds on the first successful response (fast path); stops early if
    the orchestrator process exits so the supervisor loop can propagate its
    exit code. Returns True when healthy, False otherwise — callers always
    continue either way (feature 052, FR-029).
    """
    url = f"http://localhost:{port}/healthz"
    started = time.monotonic()
    deadline = started + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            print(" Orchestrator exited before reporting healthy.")
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    elapsed = time.monotonic() - started
                    print(f" Orchestrator healthy after {elapsed:.1f}s.")
                    return True
        except Exception:
            pass
        time.sleep(interval_s)
    print(f" Orchestrator /healthz not ready after {timeout_s:.0f}s; continuing anyway.")
    return False


def main():
    # Force UTF-8 encoding for stdout/stderr to avoid Windows cp1252 errors
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except AttributeError:
            pass  # older python versions might not have reconfigure

    base_dir = os.path.dirname(os.path.abspath(__file__))
    orchestrator_script = os.path.join(base_dir, "orchestrator", "orchestrator.py")
    os.path.join(base_dir, "agents", "general_agent.py")
    python_exe = sys.executable

    processes = []

    try:
        print("=" * 60)
        print("  AstralBody  ")
        print("=" * 60)
        print()

        # Auto-discover agents created in the agents/ folder to determine how many ports to scan
        agents_dir = os.path.join(base_dir, "agents")
        valid_agents = []
        if os.path.exists(agents_dir):
            for item in os.listdir(agents_dir):
                item_path = os.path.join(agents_dir, item)
                if os.path.isdir(item_path) and not item.startswith("__"):
                    # Skip draft agents from port count
                    if os.path.exists(os.path.join(item_path, ".draft")):
                        continue
                    agent_scripts = [f for f in os.listdir(item_path) if f.endswith("_agent.py")]
                    if agent_scripts:
                        valid_agents.append(item)
        
        # Assign DEFAULT_AGENT_OWNER to any agents (live or draft) without an owner
        default_owner = os.environ.get("DEFAULT_AGENT_OWNER")
        if default_owner:
            all_agents = []
            if os.path.exists(agents_dir):
                for item in os.listdir(agents_dir):
                    item_path = os.path.join(agents_dir, item)
                    if os.path.isdir(item_path) and not item.startswith("__"):
                        agent_scripts = [f for f in os.listdir(item_path) if f.endswith("_agent.py")]
                        if agent_scripts:
                            all_agents.append(item)
            if all_agents:
                from shared.database import Database
                db = Database()
                for agent_name in all_agents:
                    ownership = db.get_agent_ownership(agent_name)
                    if not ownership:
                        # Feature 030: bundled (non-draft) agents default to
                        # public so they are discoverable in the Agents
                        # surface; drafts stay private until approved.
                        is_draft = os.path.exists(os.path.join(agents_dir, agent_name, ".draft"))
                        db.set_agent_ownership(agent_name, default_owner, is_public=not is_draft)
                        print(f"  Assigned owner '{default_owner}' to agent: {agent_name}")
                db.close()

        # Set MAX_AGENTS based on what we found, defaulting to 1 if none found to avoid errors
        max_agents = max(1, len(valid_agents))
        env = os.environ.copy()
        env["MAX_AGENTS"] = str(max_agents)

        orch_port = int(os.environ.get("ORCHESTRATOR_PORT", 8001))
        print(f"Starting Orchestrator on port {orch_port} (expecting {max_agents} agents)...")
        p_orch = subprocess.Popen([python_exe, orchestrator_script], env=env)
        processes.append(p_orch)
        _wait_for_orchestrator(orch_port, p_orch)

        # Feature 040 (US1): when in-process agents are enabled (default), the
        # orchestrator runs the bundled first-party agents itself — don't spawn
        # a separate process/port for them. Drafts + any non-built-in agent are
        # unaffected.
        inprocess_enabled = os.environ.get("FF_INPROCESS_AGENTS", "True").lower() in ("true", "1", "yes")
        try:
            from orchestrator.local_agents import BUILT_IN_AGENT_DIRS
        except Exception:
            BUILT_IN_AGENT_DIRS = ()

        next_port = int(os.environ.get("AGENT_PORT", 8003))
        for item in os.listdir(agents_dir):
            item_path = os.path.join(agents_dir, item)
            if os.path.isdir(item_path) and not item.startswith("__"):
                # Skip draft agents — they are started on-demand via the UI
                if os.path.exists(os.path.join(item_path, ".draft")):
                    print(f"Skipping draft agent: {item}")
                    continue
                # Feature 040: bundled built-ins run in-process — no subprocess.
                if inprocess_enabled and item in BUILT_IN_AGENT_DIRS:
                    print(f"Running {item} in-process (no port)")
                    continue
                agent_scripts = [f for f in os.listdir(item_path) if f.endswith("_agent.py")]
                if agent_scripts:
                    custom_agent_script = os.path.join(item_path, agent_scripts[0])
                    print(f"Starting {item} agent on port {next_port}...")
                    p_custom_agent = subprocess.Popen(
                        [python_exe, custom_agent_script, "--port", str(next_port)],
                        cwd=item_path
                    )
                    processes.append(p_custom_agent)
                    next_port += 1

        print()
        print("-" * 60)
        print(" System started!")
        print(f"  Orchestrator WS: ws://localhost:{orch_port}")
        agent_start_port = int(os.environ.get("AGENT_PORT", 8003))
        print(f"  Agent APIs start at: http://localhost:{agent_start_port}")
        print("-" * 60)
        print()
        print("Press Ctrl+C to stop.")
        print()

        while True:
            time.sleep(1)
            if p_orch.poll() is not None:
                print(" Orchestrator died!")
                # Propagate the orchestrator's exit code (e.g. EX_CONFIG 78 from
                # the fail-closed boot gate) instead of masking it as a clean
                # supervisor exit. The finally block still runs (process cleanup)
                # before this SystemExit propagates to the container exit code.
                _rc = p_orch.returncode
                if _rc:
                    raise SystemExit(_rc)
                break

    except KeyboardInterrupt:
        print("\n Stopping...")
    finally:
        for p in processes:
            if p.poll() is None:
                if os.name == 'nt':
                    try:
                        subprocess.run(
                            ['taskkill', '/F', '/T', '/PID', str(p.pid)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False
                        )
                    except Exception:
                        p.terminate()
                else:
                    p.terminate()
                    try:
                        p.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        p.kill()
                # Wait a bit for process to terminate
                for _ in range(10):
                    if p.poll() is not None:
                        break
                    time.sleep(0.2)
        print(" System stopped.")


if __name__ == "__main__":
    main()
