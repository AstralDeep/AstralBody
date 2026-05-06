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
Persists to PostgreSQL via the agent_scopes table.

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
    """Manages per-user, per-agent scope-based permissions backed by PostgreSQL.

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

    def __init__(self, db=None, data_dir: str = None, database_url: str = None):
        if db is not None:
            self.db = db
        elif data_dir is not None or database_url is not None:
            import sys
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
            from shared.database import Database
            self.db = Database(database_url)
        else:
            raise ValueError("Either db, data_dir, or database_url must be provided")

        self.data_dir = data_dir
        # In-memory tool→scope mapping populated by orchestrator on agent registration
        # Structure: { agent_id: { tool_name: scope_string } }
        self._tool_scope_map: Dict[str, Dict[str, str]] = {}
        self._migrate_from_json()

    def _migrate_from_json(self):
        """One-time migration from legacy JSON file to database."""
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
                """INSERT INTO agent_scopes
                   (user_id, agent_id, scope, enabled, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (user_id, agent_id, scope)
                   DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = EXCLUDED.updated_at""",
                (user_id, agent_id, scope, bool(enabled), now)
            )
        logger.info(
            f"Scopes updated: user={user_id} agent={agent_id} "
            f"scopes={scopes}"
        )

    # ── Per-Tool Overrides ──────────────────────────────────────────────

    def get_tool_overrides(self, user_id: str, agent_id: str) -> Dict[str, bool]:
        """Get per-tool enable/disable overrides for a user/agent.

        Returns a dict of {tool_name: enabled} only for tools that have
        an explicit override. Tools not in this dict follow scope default.
        """
        rows = self.db.fetch_all(
            "SELECT tool_name, enabled FROM tool_overrides WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
        return {row['tool_name']: bool(row['enabled']) for row in rows}

    def set_tool_overrides(self, user_id: str, agent_id: str, overrides: Dict[str, bool]):
        """Set per-tool enable/disable overrides.

        Args:
            overrides: Dict of {tool_name: enabled}. Only tools explicitly
                       toggled off need entries — scope-enabled tools default to on.
        """
        now = int(time.time() * 1000)
        for tool_name, enabled in overrides.items():
            if enabled:
                # Remove override — tool follows scope default (enabled)
                self.db.execute(
                    "DELETE FROM tool_overrides WHERE user_id = ? AND agent_id = ? AND tool_name = ?",
                    (user_id, agent_id, tool_name)
                )
            else:
                # Store disable override
                self.db.execute(
                    """INSERT INTO tool_overrides
                       (user_id, agent_id, tool_name, enabled, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT (user_id, agent_id, tool_name)
                       DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = EXCLUDED.updated_at""",
                    (user_id, agent_id, tool_name, False, now)
                )
        logger.info(
            f"Tool overrides updated: user={user_id} agent={agent_id} "
            f"overrides={overrides}"
        )

    # ── Tool-Level Authorization (used by orchestrator) ─────────────────

    def is_tool_allowed(self, user_id: str, agent_id: str, tool_name: str) -> bool:
        """Check if a specific tool is allowed for this user/agent.

        Resolution order (Feature 013 / FR-013):
          1. If a per-(tool, permission_kind) row exists for the tool's
             required kind, that explicit row decides — return its value.
          2. Else, if a legacy tool-wide override row (permission_kind IS
             NULL) exists and is False, the tool is blocked.
          3. Else, fall back to the agent-wide scope (`agent_scopes`).
        """
        required_scope = self.get_tool_scope(agent_id, tool_name)
        # 1. Per-(tool, kind) row takes priority
        kind_row = self.db.fetch_one(
            """SELECT enabled FROM tool_overrides
               WHERE user_id = ? AND agent_id = ? AND tool_name = ?
                 AND permission_kind = ?""",
            (user_id, agent_id, tool_name, required_scope),
        )
        if kind_row is not None:
            return bool(kind_row["enabled"])
        # 2. Legacy tool-wide override (permission_kind IS NULL) can still block
        legacy_row = self.db.fetch_one(
            """SELECT enabled FROM tool_overrides
               WHERE user_id = ? AND agent_id = ? AND tool_name = ?
                 AND permission_kind IS NULL""",
            (user_id, agent_id, tool_name),
        )
        if legacy_row is not None and not bool(legacy_row["enabled"]):
            return False
        # 3. Fall back to scope
        return self.is_scope_enabled(user_id, agent_id, required_scope)

    # ── Per-Tool Permissions (Feature 013) ──────────────────────────────

    def get_effective_tool_permissions(
        self, user_id: str, agent_id: str
    ) -> Dict[str, Dict[str, bool]]:
        """Return the resolved per-tool, per-permission-kind permission map.

        Output shape:
            { tool_name: { permission_kind: enabled } }

        Only the kinds that apply to each tool (i.e., the tool's required
        scope from the agent's tool→scope map) are included — satisfies
        FR-014 (no greyed-out toggles for inapplicable kinds).

        Resolution per tool:
          - If a per-kind row exists, use that boolean.
          - Else fall back to the agent-wide scope value.
          - A legacy tool-wide override (permission_kind IS NULL, enabled=False)
            forces the kind to False.
        """
        scope_map = self._tool_scope_map.get(agent_id, {})
        if not scope_map:
            return {}
        scope_state = self.get_agent_scopes(user_id, agent_id)
        # Pull per-kind rows for this user/agent in one query
        kind_rows = self.db.fetch_all(
            """SELECT tool_name, permission_kind, enabled FROM tool_overrides
               WHERE user_id = ? AND agent_id = ? AND permission_kind IS NOT NULL""",
            (user_id, agent_id),
        )
        kind_lookup: Dict[str, Dict[str, bool]] = {}
        for row in kind_rows:
            kind_lookup.setdefault(row["tool_name"], {})[row["permission_kind"]] = bool(
                row["enabled"]
            )
        legacy_rows = self.db.fetch_all(
            """SELECT tool_name, enabled FROM tool_overrides
               WHERE user_id = ? AND agent_id = ? AND permission_kind IS NULL""",
            (user_id, agent_id),
        )
        legacy_disabled = {
            row["tool_name"] for row in legacy_rows if not bool(row["enabled"])
        }
        result: Dict[str, Dict[str, bool]] = {}
        for tool_name, required_scope in scope_map.items():
            if tool_name in legacy_disabled:
                effective = False
            elif tool_name in kind_lookup and required_scope in kind_lookup[tool_name]:
                effective = kind_lookup[tool_name][required_scope]
            else:
                effective = bool(scope_state.get(required_scope, False))
            result[tool_name] = {required_scope: effective}
        return result

    def set_tool_permission(
        self,
        user_id: str,
        agent_id: str,
        tool_name: str,
        permission_kind: str,
        enabled: bool,
    ) -> None:
        """Set a single per-tool, per-permission-kind permission (Feature 013).

        Args:
            user_id: The user's identifier.
            agent_id: The agent's identifier.
            tool_name: The tool's identifier (must exist on the agent).
            permission_kind: One of VALID_SCOPES.
            enabled: True to allow, False to block.

        Raises:
            ValueError: If ``permission_kind`` is not a valid scope.
        """
        if permission_kind not in VALID_SCOPES:
            raise ValueError(
                f"Invalid permission_kind {permission_kind!r}; must be one of {VALID_SCOPES}"
            )
        now = int(time.time() * 1000)
        # Use the (user_id, agent_id, tool_name, COALESCE(permission_kind, ''))
        # unique index added by the migration. ON CONFLICT requires explicit
        # constraint targeting; use the index-based form.
        self.db.execute(
            """INSERT INTO tool_overrides
               (user_id, agent_id, tool_name, permission_kind, enabled, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (user_id, agent_id, tool_name, COALESCE(permission_kind, ''))
               DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = EXCLUDED.updated_at""",
            (user_id, agent_id, tool_name, permission_kind, bool(enabled), now),
        )
        logger.info(
            "Per-tool permission updated: user=%s agent=%s tool=%s kind=%s enabled=%s",
            user_id,
            agent_id,
            tool_name,
            permission_kind,
            bool(enabled),
        )

    def backfill_per_tool_rows(self, user_id: str, agent_id: str) -> int:
        """Idempotent 1:1 carry-forward from agent_scopes to per-tool rows (FR-015).

        For every tool the agent exposes, if a per-(tool, kind) row does
        not yet exist, insert one with ``enabled`` equal to the agent-wide
        scope state for that tool's required kind. Returns the number of
        rows inserted (zero on subsequent runs).

        Safe to call repeatedly — subsequent calls are no-ops because
        rows already exist. Called from the per-tool permissions
        endpoints on first read so users don't have to re-toggle.
        """
        scope_map = self._tool_scope_map.get(agent_id, {})
        if not scope_map:
            return 0
        scope_state = self.get_agent_scopes(user_id, agent_id)
        existing = self.db.fetch_all(
            """SELECT tool_name, permission_kind FROM tool_overrides
               WHERE user_id = ? AND agent_id = ? AND permission_kind IS NOT NULL""",
            (user_id, agent_id),
        )
        existing_pairs = {(r["tool_name"], r["permission_kind"]) for r in existing}
        now = int(time.time() * 1000)
        inserted = 0
        for tool_name, required_scope in scope_map.items():
            if (tool_name, required_scope) in existing_pairs:
                continue
            enabled = bool(scope_state.get(required_scope, False))
            self.db.execute(
                """INSERT INTO tool_overrides
                   (user_id, agent_id, tool_name, permission_kind, enabled, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (user_id, agent_id, tool_name, COALESCE(permission_kind, ''))
                   DO NOTHING""",
                (user_id, agent_id, tool_name, required_scope, enabled, now),
            )
            inserted += 1
        if inserted:
            logger.info(
                "Backfilled %d per-tool permission rows for user=%s agent=%s",
                inserted,
                user_id,
                agent_id,
            )
        return inserted

    def get_allowed_tools(
        self, user_id: str, agent_id: str, available_tools: list
    ) -> list:
        """Return the subset of available tools that the user has allowed.

        Uses :meth:`is_tool_allowed` per-tool so per-(tool, kind) rows
        added in Feature 013 are honored consistently with the
        orchestrator's per-turn filter loop.
        """
        return [
            tool for tool in available_tools
            if self.is_tool_allowed(user_id, agent_id, tool)
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
        """Get effective permissions for all tools (per-tool, per-kind aware).

        Returns ``{tool_name: allowed}`` using :meth:`is_tool_allowed` so
        per-(tool, kind) rows added in Feature 013 are honored.
        """
        return {
            tool: self.is_tool_allowed(user_id, agent_id, tool)
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
        """Remove all scope permissions and tool overrides for a user."""
        self.db.execute(
            "DELETE FROM agent_scopes WHERE user_id = ?",
            (user_id,)
        )
        self.db.execute(
            "DELETE FROM tool_overrides WHERE user_id = ?",
            (user_id,)
        )

    def remove_agent_permissions(self, user_id: str, agent_id: str):
        """Remove all scope permissions and tool overrides for a specific agent under a user."""
        self.db.execute(
            "DELETE FROM agent_scopes WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
        self.db.execute(
            "DELETE FROM tool_overrides WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id)
        )
