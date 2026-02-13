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
        print("  Final Product -- Multi-Agent Platform")
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
                p.terminate()
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()
        print(" System stopped.")


if __name__ == "__main__":
    main()
