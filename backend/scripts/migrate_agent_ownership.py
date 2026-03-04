"""
Migration script: Assign all existing agents to sam.armstrong@uky.edu.

Run from the backend directory:
    python -m scripts.migrate_agent_ownership

This script:
1. Ensures the agent_ownership table exists
2. Queries the running orchestrator REST API for currently connected agents
3. Falls back to scanning tool_permissions/user_credentials for any known agent_ids
4. Assigns each agent to sam.armstrong@uky.edu as a private agent
"""
import os
import sys
import time

# Ensure backend root is on the path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, backend_dir)

from shared.database import Database

OWNER_EMAIL = "sam.armstrong@uky.edu"
DB_PATH = os.path.join(backend_dir, "data", "astral.db")


def get_connected_agent_ids():
    """Query the running orchestrator API for connected agent IDs."""
    import requests
    port = os.getenv("ORCHESTRATOR_PORT", "9001")
    try:
        resp = requests.get(
            f"http://localhost:{port}/api/agents",
            headers={"Authorization": "Bearer mock"},
            timeout=5
        )
        if resp.ok:
            data = resp.json()
            return {a["id"] for a in data.get("agents", [])}
    except Exception as e:
        print(f"  (Could not reach orchestrator API: {e})")
    return set()


def migrate():
    db = Database(DB_PATH)
    now = int(time.time() * 1000)

    # Collect agent IDs from multiple sources
    agent_ids = set()

    # 1. From running orchestrator
    connected = get_connected_agent_ids()
    if connected:
        print(f"  Found {len(connected)} agent(s) via orchestrator API")
        agent_ids.update(connected)

    # 2. From tool_permissions
    rows = db.fetch_all("SELECT DISTINCT agent_id FROM tool_permissions")
    agent_ids.update(row["agent_id"] for row in rows)

    # 3. From user_credentials
    rows = db.fetch_all("SELECT DISTINCT agent_id FROM user_credentials")
    agent_ids.update(row["agent_id"] for row in rows)

    if not agent_ids:
        print("No agents found from API, tool_permissions, or user_credentials.")
        print("Make sure the orchestrator is running, or agents have been used at least once.")
        return

    assigned = 0
    skipped = 0
    for agent_id in sorted(agent_ids):
        existing = db.get_agent_ownership(agent_id)
        if existing:
            print(f"  SKIP  {agent_id} (already owned by {existing['owner_email']})")
            skipped += 1
        else:
            db.execute(
                "INSERT INTO agent_ownership (agent_id, owner_email, is_public, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (agent_id, OWNER_EMAIL, False, now, now)
            )
            print(f"  SET   {agent_id} -> {OWNER_EMAIL} (private)")
            assigned += 1

    print(f"\nDone: {assigned} assigned, {skipped} skipped.")


if __name__ == "__main__":
    print(f"Migrating agent ownership to {OWNER_EMAIL}")
    print(f"Database: {DB_PATH}\n")
    migrate()
