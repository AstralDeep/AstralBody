"""
Tool Permission Manager — Scope-based agent authorization.

Provides scope-level control over which MCP tools each agent can
execute on behalf of a specific user. Four scopes map to Keycloak
client scopes on the astral-agent-service client:

  - tools:read   — Read/retrieve data, generate visualizations, analyze
  - tools:write  — Create, modify, delete data; post to external services
  - tools:search — Query external APIs/databases for information
  - tools:system — Access system resources (CPU, memory, disk)

By default, all scopes are DISABLED. Users must explicitly grant scopes.
Persists to SQLite via the agent_scopes table.

Part of the RFC 8693 Delegated Authorization framework.
"""
import os
import json
import time
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("ToolPermissions")

# The four canonical scopes aligned with Keycloak astral-agent-service client
VALID_SCOPES = ["tools:read", "tools:write", "tools:search", "tools:system"]


class ToolPermissionManager:
    """Manages per-user, per-agent scope-based permissions backed by SQLite.

    Structure (logical):
        {
            "<user_id>": {
                "<agent_id>": {
                    "tools:read": true/false,
                    "tools:write": true/false,
                    "tools:search": true/false,
                    "tools:system": true/false,
                }
            }
        }

    Default: all scopes DISABLED for new agents (user must explicitly grant).
    """

    def __init__(self, db=None, data_dir: str = None):
        if db is not None:
            self.db = db
        elif data_dir is not None:
            import sys
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
            from shared.database import Database
            db_path = os.path.join(data_dir, "astral.db")
            self.db = Database(db_path)
        else:
            raise ValueError("Either db or data_dir must be provided")

        self.data_dir = data_dir
        # In-memory tool→scope mapping populated by orchestrator on agent registration
        # Structure: { agent_id: { tool_name: scope_string } }
        self._tool_scope_map: Dict[str, Dict[str, str]] = {}
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
            # Legacy format was per-tool; we can't auto-migrate to scopes meaningfully
            # Just rename the file so migration doesn't re-run
            os.rename(json_path, json_path + ".bak")
            logger.info("Archived legacy tool_permissions.json (scope-based model now active)")
        except Exception as e:
            logger.error(f"Failed to archive legacy tool permissions: {e}")

    # ── Tool→Scope Mapping ──────────────────────────────────────────────

    def register_tool_scopes(self, agent_id: str, tool_scope_map: Dict[str, str]):
        """Register the tool→scope mapping for an agent (called on agent registration).

        Args:
            agent_id: The agent's identifier.
            tool_scope_map: Dict of {tool_name: scope} e.g. {"modify_data": "tools:write"}.
        """
        self._tool_scope_map[agent_id] = tool_scope_map
        logger.info(f"Registered tool scopes for agent={agent_id}: {len(tool_scope_map)} tools")

    def get_tool_scope(self, agent_id: str, tool_name: str) -> str:
        """Get the required scope for a specific tool.

        Returns the scope string or "tools:read" as default.
        """
        agent_map = self._tool_scope_map.get(agent_id, {})
        return agent_map.get(tool_name, "tools:read")

    def get_tool_scope_map(self, agent_id: str) -> Dict[str, str]:
        """Get the full tool→scope mapping for an agent."""
        return self._tool_scope_map.get(agent_id, {})

    # ── Scope Queries ───────────────────────────────────────────────────

    def get_agent_scopes(self, user_id: str, agent_id: str) -> Dict[str, bool]:
        """Get scope permissions for a specific user and agent.

        Returns a dict of {scope: enabled} for all 4 scopes.
        Default: all scopes disabled (False).
        """
        rows = self.db.fetch_all(
            "SELECT scope, enabled FROM agent_scopes WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
        stored = {row['scope']: bool(row['enabled']) for row in rows}
        # Fill in defaults for any missing scopes
        return {scope: stored.get(scope, False) for scope in VALID_SCOPES}

    def is_scope_enabled(self, user_id: str, agent_id: str, scope: str) -> bool:
        """Check if a specific scope is enabled for the user/agent combination.

        Returns False if no record exists (default = disabled).
        """
        row = self.db.fetch_one(
            "SELECT enabled FROM agent_scopes WHERE user_id = ? AND agent_id = ? AND scope = ?",
            (user_id, agent_id, scope)
        )
        if row is None:
            return False
        return bool(row['enabled'])

    def set_agent_scopes(self, user_id: str, agent_id: str, scopes: Dict[str, bool]):
        """Set scope permissions for a user/agent combination.

        Args:
            user_id: The user's ID.
            agent_id: The agent's ID.
            scopes: Dict of {scope: enabled} for each scope to set.
        """
        now = int(time.time() * 1000)
        for scope, enabled in scopes.items():
            if scope not in VALID_SCOPES:
                logger.warning(f"Ignoring invalid scope: {scope}")
                continue
            self.db.execute(
                """INSERT OR REPLACE INTO agent_scopes
                   (user_id, agent_id, scope, enabled, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, agent_id, scope, 1 if enabled else 0, now)
            )
        logger.info(
            f"Scopes updated: user={user_id} agent={agent_id} "
            f"scopes={scopes}"
        )

    # ── Tool-Level Authorization (used by orchestrator) ─────────────────

    def is_tool_allowed(self, user_id: str, agent_id: str, tool_name: str) -> bool:
        """Check if a specific tool is allowed based on scope authorization.

        Looks up the tool's required scope, then checks if the user has
        enabled that scope for the agent.

        Returns False if the required scope is not enabled (default = denied).
        """
        required_scope = self.get_tool_scope(agent_id, tool_name)
        return self.is_scope_enabled(user_id, agent_id, required_scope)

    def get_allowed_tools(
        self, user_id: str, agent_id: str, available_tools: list
    ) -> list:
        """Return the subset of available tools that the user has allowed via scopes.

        Args:
            user_id: The user's ID.
            agent_id: The agent's ID.
            available_tools: Full list of tool names the agent provides.

        Returns:
            List of tool names whose required scope is enabled.
        """
        # Get enabled scopes once (1 query) instead of per-tool
        enabled_scopes = self.get_agent_scopes(user_id, agent_id)
        agent_map = self._tool_scope_map.get(agent_id, {})
        return [
            tool for tool in available_tools
            if enabled_scopes.get(agent_map.get(tool, "tools:read"), False)
        ]

    def get_enabled_scope_names(self, user_id: str, agent_id: str) -> List[str]:
        """Return list of enabled scope names for the user/agent.

        Used when building delegation tokens.
        """
        scopes = self.get_agent_scopes(user_id, agent_id)
        return [scope for scope, enabled in scopes.items() if enabled]

    # ── Backward Compatibility ──────────────────────────────────────────

    def get_effective_permissions(
        self, user_id: str, agent_id: str, available_tools: list
    ) -> Dict[str, bool]:
        """Get effective permissions for all tools based on scope model.

        Returns a dict of {tool_name: allowed} for every available tool.
        A tool is allowed if its required scope is enabled.
        """
        enabled_scopes = self.get_agent_scopes(user_id, agent_id)
        agent_map = self._tool_scope_map.get(agent_id, {})
        return {
            tool: enabled_scopes.get(agent_map.get(tool, "tools:read"), False)
            for tool in available_tools
        }

    # ── Cleanup ─────────────────────────────────────────────────────────

    def get_all_agent_permissions(self, user_id: str) -> Dict[str, Dict[str, bool]]:
        """Get scope permissions for all agents for a given user.

        Returns:
            Dict of {agent_id: {scope: enabled}}
        """
        rows = self.db.fetch_all(
            "SELECT agent_id, scope, enabled FROM agent_scopes WHERE user_id = ?",
            (user_id,)
        )
        result: Dict[str, Dict[str, bool]] = {}
        for row in rows:
            agent_id = row['agent_id']
            if agent_id not in result:
                result[agent_id] = {s: False for s in VALID_SCOPES}
            result[agent_id][row['scope']] = bool(row['enabled'])
        return result

    def remove_user_permissions(self, user_id: str):
        """Remove all scope permissions for a user."""
        self.db.execute(
            "DELETE FROM agent_scopes WHERE user_id = ?",
            (user_id,)
        )

    def remove_agent_permissions(self, user_id: str, agent_id: str):
        """Remove all scope permissions for a specific agent under a user."""
        self.db.execute(
            "DELETE FROM agent_scopes WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
