"""
Start the full system: Orchestrator + General Agent.
"""
import subprocess
import time
import sys
import os

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

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
    agent_script = os.path.join(base_dir, "agents", "general_agent.py")
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
                    agent_scripts = [f for f in os.listdir(item_path) if f.endswith("_agent.py")]
                    if agent_scripts:
                        valid_agents.append(item)
        
        # Set MAX_AGENTS based on what we found, defaulting to 1 if none found to avoid errors
        max_agents = max(1, len(valid_agents))
        env = os.environ.copy()
        env["MAX_AGENTS"] = str(max_agents)

        print(f"Starting Orchestrator on port 8001 (expecting {max_agents} agents)...")
        p_orch = subprocess.Popen([python_exe, orchestrator_script], env=env)
        processes.append(p_orch)
        time.sleep(2)

        next_port = 8003
        for item in os.listdir(agents_dir):
            item_path = os.path.join(agents_dir, item)
            if os.path.isdir(item_path) and not item.startswith("__"):
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
                    time.sleep(1)

        print()
        print("-" * 60)
        print(" System started!")
        print("  Orchestrator WS: ws://localhost:8001")
        print("  Agent APIs start at: http://localhost:8003")
        print("-" * 60)
        print()
        print("Press Ctrl+C to stop.")
        print()

        while True:
            time.sleep(1)
            if p_orch.poll() is not None:
                print(" Orchestrator died!")
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
