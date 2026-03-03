"""
Tool Permission Manager — Per-user, per-agent tool authorization.

Provides fine-grained control over which MCP tools each agent can
execute on behalf of a specific user. Persists permissions to SQLite.

Part of the RFC 8693 Delegated Authorization framework.
"""
import os
import json
import time
import logging
from typing import Dict

logger = logging.getLogger("ToolPermissions")


class ToolPermissionManager:
    """Manages per-user, per-agent tool permissions backed by SQLite.

    Structure (logical):
        {
            "<user_id>": {
                "<agent_id>": {
                    "tool_name": true/false,
                    ...
                }
            }
        }

    Default: all tools enabled for new agents (user must explicitly revoke).
    """

    def __init__(self, db=None, data_dir: str = None):
        if db is not None:
            self.db = db
        elif data_dir is not None:
            import sys
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
            from shared.database import Database
            db_path = os.path.join(data_dir, "chats.db")
            self.db = Database(db_path)
        else:
            raise ValueError("Either db or data_dir must be provided")

        self.data_dir = data_dir
        self._migrate_from_json()

    def _migrate_from_json(self):
        """One-time migration from legacy JSON file to SQLite."""
        if not self.data_dir:
            return
        json_path = os.path.join(self.data_dir, "tool_permissions.json")
        if not os.path.exists(json_path):
            return
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                permissions = json.load(f)
            now = int(time.time() * 1000)
            for user_id, agents in permissions.items():
                for agent_id, tools in agents.items():
                    for tool_name, allowed in tools.items():
                        self.db.execute(
                            """INSERT OR REPLACE INTO tool_permissions
                               (user_id, agent_id, tool_name, allowed, updated_at)
                               VALUES (?, ?, ?, ?, ?)""",
                            (user_id, agent_id, tool_name, 1 if allowed else 0, now)
                        )
            os.rename(json_path, json_path + ".bak")
            logger.info("Migrated tool permissions from JSON to SQLite")
        except Exception as e:
            logger.error(f"Failed to migrate tool permissions from JSON: {e}")

    def get_permissions(self, user_id: str, agent_id: str) -> Dict[str, bool]:
        """Get tool permissions for a specific user and agent.

        Returns a dict of {tool_name: allowed}. If no permissions are stored
        yet, returns an empty dict (meaning 'use defaults').
        """
        rows = self.db.fetch_all(
            "SELECT tool_name, allowed FROM tool_permissions WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
        return {row['tool_name']: bool(row['allowed']) for row in rows}

    def get_effective_permissions(
        self, user_id: str, agent_id: str, available_tools: list
    ) -> Dict[str, bool]:
        """Get effective permissions, defaulting to True for tools not yet stored.

        Args:
            user_id: The user's ID.
            agent_id: The agent's ID.
            available_tools: List of tool names the agent provides.

        Returns:
            Dict of {tool_name: allowed} for every available tool.
        """
        stored = self.get_permissions(user_id, agent_id)
        return {tool: stored.get(tool, True) for tool in available_tools}

    def set_permission(
        self, user_id: str, agent_id: str, tool_name: str, allowed: bool
    ):
        """Set permission for a single tool."""
        now = int(time.time() * 1000)
        self.db.execute(
            """INSERT OR REPLACE INTO tool_permissions
               (user_id, agent_id, tool_name, allowed, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, agent_id, tool_name, 1 if allowed else 0, now)
        )
        logger.info(
            f"Permission set: user={user_id} agent={agent_id} "
            f"tool={tool_name} allowed={allowed}"
        )

    def set_bulk_permissions(
        self, user_id: str, agent_id: str, permissions: Dict[str, bool]
    ):
        """Set permissions for multiple tools at once."""
        now = int(time.time() * 1000)
        for tool_name, allowed in permissions.items():
            self.db.execute(
                """INSERT OR REPLACE INTO tool_permissions
                   (user_id, agent_id, tool_name, allowed, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, agent_id, tool_name, 1 if allowed else 0, now)
            )
        logger.info(
            f"Bulk permissions set: user={user_id} agent={agent_id} "
            f"count={len(permissions)}"
        )

    def is_tool_allowed(self, user_id: str, agent_id: str, tool_name: str) -> bool:
        """Check if a specific tool is allowed for the user/agent combination.

        Returns True if no permissions are stored (default = all allowed).
        """
        row = self.db.fetch_one(
            "SELECT allowed FROM tool_permissions WHERE user_id = ? AND agent_id = ? AND tool_name = ?",
            (user_id, agent_id, tool_name)
        )
        if row is None:
            return True
        return bool(row['allowed'])

    def get_allowed_tools(
        self, user_id: str, agent_id: str, available_tools: list
    ) -> list:
        """Return the subset of available tools that the user has allowed.

        Args:
            user_id: The user's ID.
            agent_id: The agent's ID.
            available_tools: Full list of tool names the agent provides.

        Returns:
            List of tool names that are allowed.
        """
        return [
            tool for tool in available_tools
            if self.is_tool_allowed(user_id, agent_id, tool)
        ]

    def get_all_agent_permissions(self, user_id: str) -> Dict[str, Dict[str, bool]]:
        """Get permissions for all agents for a given user.

        Returns:
            Dict of {agent_id: {tool_name: allowed}}
        """
        rows = self.db.fetch_all(
            "SELECT agent_id, tool_name, allowed FROM tool_permissions WHERE user_id = ?",
            (user_id,)
        )
        result: Dict[str, Dict[str, bool]] = {}
        for row in rows:
            agent_id = row['agent_id']
            if agent_id not in result:
                result[agent_id] = {}
            result[agent_id][row['tool_name']] = bool(row['allowed'])
        return result

    def remove_user_permissions(self, user_id: str):
        """Remove all permissions for a user."""
        self.db.execute(
            "DELETE FROM tool_permissions WHERE user_id = ?",
            (user_id,)
        )

    def remove_agent_permissions(self, user_id: str, agent_id: str):
        """Remove all permissions for a specific agent under a user."""
        self.db.execute(
            "DELETE FROM tool_permissions WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
