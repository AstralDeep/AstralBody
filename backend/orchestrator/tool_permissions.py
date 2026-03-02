"""
Tool Permission Manager — Per-user, per-agent tool authorization.

Provides fine-grained control over which MCP tools each agent can
execute on behalf of a specific user. Persists permissions to a
JSON file alongside chat history.

Part of the RFC 8693 Delegated Authorization framework.
"""
import os
import json
import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger("ToolPermissions")


class ToolPermissionManager:
    """Manages per-user, per-agent tool permissions.

    Structure:
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

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.permissions_file = os.path.join(data_dir, "tool_permissions.json")
        self._lock = threading.Lock()
        self._permissions: Dict[str, Dict[str, Dict[str, bool]]] = {}
        self._load()

    def _load(self):
        """Load permissions from disk."""
        if os.path.exists(self.permissions_file):
            try:
                with open(self.permissions_file, "r", encoding="utf-8") as f:
                    self._permissions = json.load(f)
                logger.info(f"Loaded tool permissions for {len(self._permissions)} users")
            except Exception as e:
                logger.error(f"Failed to load tool permissions: {e}")
                self._permissions = {}
        else:
            self._permissions = {}

    def _save(self):
        """Persist permissions to disk."""
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.permissions_file, "w", encoding="utf-8") as f:
                json.dump(self._permissions, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save tool permissions: {e}")

    def get_permissions(self, user_id: str, agent_id: str) -> Dict[str, bool]:
        """Get tool permissions for a specific user and agent.

        Returns a dict of {tool_name: allowed}. If no permissions are stored
        yet, returns an empty dict (meaning 'use defaults').
        """
        with self._lock:
            user_perms = self._permissions.get(user_id, {})
            return dict(user_perms.get(agent_id, {}))

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
        result = {}
        for tool in available_tools:
            # Default to True (allowed) if not explicitly set
            result[tool] = stored.get(tool, True)
        return result

    def set_permission(
        self, user_id: str, agent_id: str, tool_name: str, allowed: bool
    ):
        """Set permission for a single tool."""
        with self._lock:
            if user_id not in self._permissions:
                self._permissions[user_id] = {}
            if agent_id not in self._permissions[user_id]:
                self._permissions[user_id][agent_id] = {}
            self._permissions[user_id][agent_id][tool_name] = allowed
            self._save()
        logger.info(
            f"Permission set: user={user_id} agent={agent_id} "
            f"tool={tool_name} allowed={allowed}"
        )

    def set_bulk_permissions(
        self, user_id: str, agent_id: str, permissions: Dict[str, bool]
    ):
        """Set permissions for multiple tools at once."""
        with self._lock:
            if user_id not in self._permissions:
                self._permissions[user_id] = {}
            if agent_id not in self._permissions[user_id]:
                self._permissions[user_id][agent_id] = {}
            self._permissions[user_id][agent_id].update(permissions)
            self._save()
        logger.info(
            f"Bulk permissions set: user={user_id} agent={agent_id} "
            f"count={len(permissions)}"
        )

    def is_tool_allowed(self, user_id: str, agent_id: str, tool_name: str) -> bool:
        """Check if a specific tool is allowed for the user/agent combination.

        Returns True if no permissions are stored (default = all allowed).
        """
        with self._lock:
            user_perms = self._permissions.get(user_id, {})
            agent_perms = user_perms.get(agent_id, {})
            # Default to True (allowed) if not explicitly set
            return agent_perms.get(tool_name, True)

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
        with self._lock:
            return dict(self._permissions.get(user_id, {}))

    def remove_user_permissions(self, user_id: str):
        """Remove all permissions for a user."""
        with self._lock:
            if user_id in self._permissions:
                del self._permissions[user_id]
                self._save()

    def remove_agent_permissions(self, user_id: str, agent_id: str):
        """Remove all permissions for a specific agent under a user."""
        with self._lock:
            if user_id in self._permissions and agent_id in self._permissions[user_id]:
                del self._permissions[user_id][agent_id]
                self._save()
