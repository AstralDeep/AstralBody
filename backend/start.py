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

        print("Starting Orchestrator on port 8001...")
        p_orch = subprocess.Popen([python_exe, orchestrator_script])
        processes.append(p_orch)
        time.sleep(2)

        print("Starting General Agent on port 8003...")
        p_agent = subprocess.Popen([python_exe, agent_script, "--port", "8003"])
        processes.append(p_agent)
        time.sleep(2)

        # Auto-discover and start other agents created in the agents/ folder
        agents_dir = os.path.join(base_dir, "agents")
        next_port = 8004
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
        print("  Agent API:       http://localhost:8003")
        print("  Agent Card:      http://localhost:8003/.well-known/agent-card.json")
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
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)], capture_output=True)
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
