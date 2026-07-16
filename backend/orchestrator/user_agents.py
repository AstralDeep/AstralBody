"""User-agent registry accessors (feature 057).

The durable ``user_agent`` table — one row per user-authored, client-hosted
agent. Canonical owner key is ``owner_user_id`` (the OIDC ``sub``); the boundary
binds to it and never to a card field or email. ``status`` is the durable
lifecycle (authoring|validated|live|disabled); running/offline is DERIVED from
socket presence and is never stored here.

Also home to ``can_user_use_agent`` — the owner-isolation predicate the boundary
enforces in three places (grant endpoint, dispatch gate, tool-list build) so a
private user agent is invisible/unusable to non-owners (FR-016/019).
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
import json
from pathlib import PurePosixPath
import re
import time
from types import MappingProxyType
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence
import uuid

from psycopg2.extras import Json

from orchestrator.work_admission import (
    ExecutionFence,
    OperationState,
    PostgresWorkAdmissionRepository,
    StaleExecutionFenceError,
)
from shared.protocol import RuntimeFence


def _now_ms() -> int:
    return int(time.time() * 1000)


_STRICT_SEMVER_RE = re.compile(
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SAFE_CODE_RE = re.compile(r"[a-z][a-z0-9_]{0,127}")
_RUNTIME_TERMINAL_STATES = frozenset({"stopped", "failed", "offline", "superseded"})
_REQUEST_TERMINAL_STATES = frozenset(
    {"completed", "failed", "cancelled", "retryable"}
)
_MAX_GENERATION = (1 << 63) - 1


class PersonalAgentRuntimeError(RuntimeError):
    """Base class for safe personal-agent runtime repository failures."""


class HostRegistrationRefused(PersonalAgentRuntimeError):
    """Structured, non-sensitive host-registration refusal."""

    def __init__(self, code: str, details: Mapping[str, Any]) -> None:
        self.code = code
        self.details = MappingProxyType(dict(details))
        super().__init__(code)


class PersonalAgentNotFoundError(PersonalAgentRuntimeError):
    """The owner-scoped personal agent or runtime identity does not exist."""


class UserAgentOwnershipConflict(PersonalAgentRuntimeError):
    """An immutable agent ID is already bound to a different owner."""


class AgentDeletedError(PersonalAgentRuntimeError):
    """The durable agent tombstone prevents the requested mutation."""


class AgentOfflineError(PersonalAgentRuntimeError):
    """No exact current online authoritative runtime can accept the request."""


class StaleRuntimeGenerationError(PersonalAgentRuntimeError):
    """One or more immutable runtime/request fence fields are stale."""

    code = "stale_runtime_generation"


@dataclass(frozen=True)
class RuntimeCompatibilityPolicy:
    """Injected candidate-owned BYO runtime compatibility policy."""

    runtime_contract_version: int
    runtime_lock_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.runtime_contract_version) is not int
            or self.runtime_contract_version <= 0
        ):
            raise ValueError("runtime contract version must be a positive integer")
        if not _SHA256_RE.fullmatch(self.runtime_lock_sha256):
            raise ValueError("runtime lock digest must be 64 lowercase hex characters")


@dataclass(frozen=True)
class HostSessionFence:
    owner_user_id: str
    host_id: str
    host_session_id: str
    connection_scope_id: str
    host_generation: int


@dataclass(frozen=True)
class HostSessionRecord:
    host_session_id: str
    host_id: str
    owner_user_id: str
    connection_scope_id: str
    platform: str
    client_version: str
    host_generation: int
    supersedes_session_id: Optional[str]
    supported_runtime_contract_versions: tuple[int, ...]
    runtime_contract_version: int
    release_lock_digest: str
    state: str
    inventory_state: str
    eligible_since: Any
    accepted_at: Any
    last_seen_at: Any
    disconnected_at: Any
    inventory_reconciled_at: Any
    failure_code: Optional[str]

    @property
    def fence(self) -> HostSessionFence:
        return HostSessionFence(
            owner_user_id=self.owner_user_id,
            host_id=self.host_id,
            host_session_id=self.host_session_id,
            connection_scope_id=self.connection_scope_id,
            host_generation=self.host_generation,
        )


@dataclass(frozen=True)
class AgentRevisionRecord:
    revision_id: str
    agent_id: str
    owner_user_id: str
    revision_number: int
    parent_revision_id: Optional[str]
    previous_good_revision_id: Optional[str]
    artifact_digest: str
    manifest: Mapping[str, Any]
    artifact_relative_path: str
    runtime_contract_version: int
    release_lock_digest: str
    compatibility_state: str
    state: str
    promotion_token: str
    state_revision: int


@dataclass(frozen=True)
class RuntimeInstanceRecord:
    fence: RuntimeFence
    operation_id: Optional[str]
    operation_execution_generation: int
    state: str
    is_authoritative: bool
    state_revision: int
    created_at: Any
    started_at: Any
    registered_at: Any
    last_heartbeat_sequence: Optional[int]
    ready_at: Any
    last_liveness_at: Any
    terminal_at: Any
    failure_code: Optional[str]
    # Reconnect/client lifecycle projection context.  Ordinary transition
    # methods may return a row without these joined user-agent pointers; the
    # latest-runtime hydration query includes them so host-facing ``ready`` can
    # never be mistaken for invocable public ``online``.
    active_revision_id: Optional[str] = field(default=None, compare=False)
    authoritative_instance_id: Optional[str] = field(default=None, compare=False)


@dataclass(frozen=True)
class RuntimeRequestFence:
    runtime: RuntimeFence
    request_id: str
    request_generation: str
    operation_id: str
    operation_execution_generation: int
    operation_execution_lease_token: Optional[str]


@dataclass(frozen=True)
class RuntimeRequestRecord:
    fence: RuntimeRequestFence
    state: str
    state_revision: int
    assigned_at: Any
    terminal_at: Any
    terminal_code: Optional[str]
    result_digest: Optional[str]


@dataclass(frozen=True)
class HostSelection:
    session: Optional[HostSessionRecord]
    previous_session_id: Optional[str]
    changed: bool
    lifecycle_generation: int


@dataclass(frozen=True)
class SelectedSessionRevision:
    """The exact selected host and active immutable revision for one agent."""

    host: HostSessionRecord
    revision: AgentRevisionRecord
    lifecycle_generation: int


@dataclass(frozen=True)
class HostInventoryEntry:
    agent_id: str
    revision_id: str
    bundle_sha256: str
    runtime_contract_version: int
    required_runtime_lock_sha256: str


@dataclass(frozen=True)
class HostInventorySelectedDelivery:
    delivery_id: str
    runtime_instance_id: str
    lifecycle_generation: int
    runtime_contract_version: int
    required_runtime_lock_sha256: str
    bundle_sha256: str


@dataclass(frozen=True)
class HostInventoryAction:
    agent_id: str
    revision_id: str
    action: str
    reason_code: Optional[str]
    selected_delivery: Optional[HostInventorySelectedDelivery]


@dataclass(frozen=True)
class HostInventoryReconciliation:
    host: HostSessionRecord
    inventory_id: str
    actions: tuple[HostInventoryAction, ...]
    reconciled_at: Any


@dataclass(frozen=True)
class SelectedRecoveryDelivery:
    host: HostSessionRecord
    revision: AgentRevisionRecord
    instance: RuntimeInstanceRecord


@dataclass(frozen=True)
class RuntimeSettlement:
    instance: RuntimeInstanceRecord
    settled_request_ids: tuple[str, ...]


@dataclass(frozen=True)
class HostDisconnectResult:
    settled_request_ids: tuple[str, ...]
    settlements: tuple[RuntimeSettlement, ...]
    selected_sessions: Mapping[str, Optional[str]]


@dataclass(frozen=True)
class AgentTombstone:
    agent_id: str
    owner_user_id: str
    lifecycle_generation: int
    state_revision: int
    deleted_at: int


@dataclass(frozen=True)
class AgentTombstoneCleanup:
    tombstone: AgentTombstone
    settlements: tuple[RuntimeSettlement, ...]
    settled_request_ids: tuple[str, ...]


def _uuid4_text(value: Any, field_name: str) -> str:
    try:
        parsed = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a UUID4") from exc
    if parsed.version != 4 or parsed.variant != uuid.RFC_4122:
        raise ValueError(f"{field_name} must be a UUID4")
    return str(parsed)


def _required_text(value: Any, field_name: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{field_name} must be a bounded non-empty string")
    return value


def _sha256(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be 64 lowercase hex characters")
    return value


def _safe_code(value: Any, field_name: str = "failure_code") -> str:
    if not isinstance(value, str) or not _SAFE_CODE_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a safe canonical code")
    return value


def _plain_json(value: Any) -> Any:
    """Detach immutable JSON containers without weakening type validation."""

    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _frozen_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _frozen_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_frozen_json(item) for item in value)
    return value


def _optional_uuid_text(value: Any) -> Optional[str]:
    return None if value is None else str(value)


def create_user_agent(db, *, agent_id: str, owner_user_id: str, display_name: str,
                      owner_email: Optional[str] = None, draft_id: Optional[str] = None,
                      declared_tools: Optional[List[str]] = None,
                      declared_scopes: Optional[List[str]] = None,
                      declared_egress: Optional[List[str]] = None) -> None:
    """Insert or same-owner update a user-agent registry row.

    ``agent_id`` ownership is immutable. A conflicting owner or durable
    tombstone is explicit and cannot be overwritten by the legacy authoring
    helper while the feature-060 repository is being integrated.
    """
    now = _now_ms()
    connection = db._get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO user_agent (
                agent_id, owner_user_id, owner_email, display_name, status,
                declared_tools, declared_scopes, declared_egress, draft_id,
                is_public, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, 'authoring', %s, %s, %s, %s, FALSE, %s, %s
            )
            ON CONFLICT (agent_id) DO UPDATE SET
                owner_email = EXCLUDED.owner_email,
                display_name = EXCLUDED.display_name,
                draft_id = EXCLUDED.draft_id,
                declared_tools = EXCLUDED.declared_tools,
                declared_scopes = EXCLUDED.declared_scopes,
                declared_egress = EXCLUDED.declared_egress,
                updated_at = EXCLUDED.updated_at
            WHERE user_agent.owner_user_id = EXCLUDED.owner_user_id
              AND user_agent.deleted_at IS NULL
            RETURNING owner_user_id
            """,
            (
                agent_id,
                owner_user_id,
                owner_email,
                display_name,
                json.dumps(declared_tools or []),
                json.dumps(declared_scopes or []),
                json.dumps(declared_egress) if declared_egress is not None else None,
                draft_id,
                now,
                now,
            ),
        )
        if cursor.fetchone() is None:
            cursor.execute(
                "SELECT owner_user_id, deleted_at FROM user_agent "
                "WHERE agent_id = %s FOR SHARE",
                (agent_id,),
            )
            existing = cursor.fetchone()
            if existing is not None and existing["deleted_at"] is not None:
                raise AgentDeletedError("agent_deleted")
            if existing is not None and existing["owner_user_id"] != owner_user_id:
                raise UserAgentOwnershipConflict(
                    "agent id is already bound to a different owner"
                )
            raise PersonalAgentRuntimeError("user-agent create conflict")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        try:
            cursor.close()
        finally:
            connection.close()


def _update_non_deleted_agent(
    db: Any, query: str, params: Sequence[Any], *, agent_id: str
) -> Dict[str, Any]:
    """Execute one legacy lifecycle CAS and classify a missing row safely."""

    connection = db._get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(query, tuple(params))
        updated = cursor.fetchone()
        if updated is None:
            cursor.execute(
                "SELECT agent_id, deleted_at FROM user_agent "
                "WHERE agent_id = %s FOR SHARE",
                (agent_id,),
            )
            existing = cursor.fetchone()
            if existing is None:
                raise PersonalAgentNotFoundError("personal agent not found")
            if existing["deleted_at"] is not None:
                raise AgentDeletedError("agent_deleted")
            raise StaleRuntimeGenerationError("legacy lifecycle CAS is stale")
        connection.commit()
        return dict(updated)
    except BaseException:
        connection.rollback()
        raise
    finally:
        try:
            cursor.close()
        finally:
            connection.close()


def get_user_agent(db, agent_id: str) -> Optional[Dict[str, Any]]:
    row = db.fetch_one("SELECT * FROM user_agent WHERE agent_id = ?", (agent_id,))
    return dict(row) if row else None


def is_user_agent(db, agent_id: str) -> bool:
    return get_user_agent(db, agent_id) is not None


def list_user_agents(db, owner_user_id: str) -> List[Dict[str, Any]]:
    """The owner's agents, most-recent first, excluding soft-deleted rows."""
    rows = db.fetch_all(
        "SELECT * FROM user_agent WHERE owner_user_id = ? AND deleted_at IS NULL "
        "ORDER BY updated_at DESC",
        (owner_user_id,),
    )
    return [dict(r) for r in rows]


def mark_validated(db, agent_id: str, constitution_version: Optional[str],
                   *, declared_tools: Optional[List[str]] = None,
                   declared_scopes: Optional[List[str]] = None) -> None:
    """Analyze passed: record the constitution version and move to ``validated``."""
    now = _now_ms()
    sets = ["status = 'validated'", "constitution_version = %s", "validated_at = %s",
            "revalidation_required = FALSE", "updated_at = %s"]
    params: List[Any] = [constitution_version, now, now]
    if declared_tools is not None:
        sets.append("declared_tools = %s")
        params.append(json.dumps(declared_tools))
    if declared_scopes is not None:
        sets.append("declared_scopes = %s")
        params.append(json.dumps(declared_scopes))
    params.append(agent_id)
    _update_non_deleted_agent(
        db,
        f"UPDATE user_agent SET {', '.join(sets)} "
        "WHERE agent_id = %s AND deleted_at IS NULL RETURNING *",
        params,
        agent_id=agent_id,
    )


def go_live(db, agent_id: str, *, host_client_id: Optional[str] = None,
            host_session_id: Optional[str] = None) -> None:
    """The delivered agent registered inward: mark ``live``, stamp the host, and
    insert the companion ``agent_ownership`` row (is_public FALSE) so the existing
    routing/permission stack treats it uniformly (FR-007)."""
    now = _now_ms()
    row = _update_non_deleted_agent(
        db,
        "UPDATE user_agent SET status = 'live', host_client_id = %s, "
        "host_session_id = %s, host_last_seen_at = %s, updated_at = %s "
        "WHERE agent_id = %s AND deleted_at IS NULL RETURNING *",
        (host_client_id, host_session_id, now, now, agent_id),
        agent_id=agent_id,
    )
    # Companion ownership row — private by construction.
    db.set_agent_ownership(agent_id, row.get("owner_email") or row.get("owner_user_id"),
                           is_public=False)


def touch_liveness(db, agent_id: str) -> None:
    """Heartbeat: update ``host_last_seen_at`` (derived running/offline reads it)."""
    _update_non_deleted_agent(
        db,
        "UPDATE user_agent SET host_last_seen_at = %s "
        "WHERE agent_id = %s AND deleted_at IS NULL RETURNING *",
        (_now_ms(), agent_id),
        agent_id=agent_id,
    )


def mark_revalidation_required(db, agent_id: str, required: bool = True) -> None:
    _update_non_deleted_agent(
        db,
        "UPDATE user_agent SET revalidation_required = %s, updated_at = %s "
        "WHERE agent_id = %s AND deleted_at IS NULL RETURNING *",
        (required, _now_ms(), agent_id),
        agent_id=agent_id,
    )


def soft_delete(db, agent_id: str) -> None:
    """Soft delete (finding I1): disable + stamp ``deleted_at``; retain the row and
    its audit trail (Constitution VII). Routing/visibility removal is done by the
    caller (stop host, drop registry socket)."""
    now = _now_ms()
    db.execute(
        "UPDATE user_agent SET status = 'disabled', deleted_at = ?, updated_at = ? "
        "WHERE agent_id = ?",
        (now, now, agent_id),
    )


#: Reserved id prefixes/stems a user agent may never register as (Constitution H).
_RESERVED_PREFIXES = ("__",)


def authorize_registration(db, owner_sub: str, agent_id: str, *,
                           reserved_ids: Optional[frozenset] = None):
    """Owner-binding decision for a user-agent tunnel registration (058 T002,
    FR-002/FR-015). Returns ``(ok, reason)``, fail-closed.

    The owner is the authenticated session ``sub`` (never a card field). A
    registration is admitted ONLY when the ``user_agent`` row exists, is owned by
    ``owner_sub``, is in a runnable ``status`` (``validated``/``live``), and is not
    flagged ``revalidation_required``. Reserved/colliding ids are refused
    (Constitution H). This is the single security decision the tunnel registration
    path depends on; it derives authority solely from the orchestrator's own
    record."""
    if not owner_sub or not agent_id:
        return False, "missing owner or agent id"
    if agent_id.startswith(_RESERVED_PREFIXES):
        return False, "reserved agent id"
    if reserved_ids and agent_id in reserved_ids:
        return False, "agent id collides with a built-in or reserved agent"
    try:
        ua = get_user_agent(db, agent_id)
    except Exception:
        return False, "registry lookup failed"
    if ua is None:
        return False, "no user-agent registry record for this agent id"
    if ua.get("owner_user_id") != owner_sub:
        return False, "agent is owned by a different user"
    if ua.get("deleted_at") is not None:
        return False, "agent is deleted"
    if ua.get("status") not in ("validated", "live"):
        return False, f"agent is not ready to run (status={ua.get('status')})"
    if ua.get("revalidation_required"):
        return False, "agent must re-pass Analyze before it can run again"
    return True, ""


def can_user_use_agent(db, user_id: str, agent_id: str) -> bool:
    """User-agent owner-isolation predicate.

    A **user agent** (feature 057 — private, client-hosted, owner-scoped) is
    usable/manageable ONLY by its owner (``user_agent.owner_user_id``). For any
    **non-user-agent** (built-in agents, the public catalog, drafts) this returns
    ``True`` and the normal per-user permission gate governs access — this
    predicate is NOT a general access check, it only enforces user-agent owner
    isolation, so it never blocks a user from managing their own permissions on a
    shared/built-in agent (including private built-ins usable via the safe-agent
    baseline). Enforced at the grant endpoint, the dispatch gate, and tool-list
    build (FR-016/019). Fail-closed: an unreadable owner on a known user agent
    denies non-owners."""
    if not user_id or not agent_id:
        return False
    try:
        ua = get_user_agent(db, agent_id)
    except Exception:
        # Fail closed only for a definite user-agent id; an errored lookup on an
        # unknown id must not lock out built-ins, so treat unknown as allowed.
        return True
    if ua is None:
        return True   # not a user agent → existing gates apply
    if ua.get("deleted_at") is not None:
        return False
    return ua.get("owner_user_id") == user_id


class PersonalAgentRuntimeRepository:
    """PostgreSQL authority for feature-060 personal-agent runtime truth.

    Every state transition borrows one connection and commits one explicit
    transaction.  PostgreSQL receipt time, owner/agent locks, exact immutable
    fences, and the shared operation repository are used together; no mutable
    process-local map is an authority for selection, liveness, or settlement.
    """

    def __init__(
        self,
        database: Any,
        *,
        compatibility_policy: RuntimeCompatibilityPolicy,
        operation_repository: Optional[PostgresWorkAdmissionRepository] = None,
        operation_retention: timedelta = timedelta(hours=24),
        uuid_factory: Any = uuid.uuid4,
    ) -> None:
        if database is None or not callable(getattr(database, "_get_connection", None)):
            raise TypeError("database must provide _get_connection()")
        if not isinstance(compatibility_policy, RuntimeCompatibilityPolicy):
            raise TypeError("compatibility_policy must be RuntimeCompatibilityPolicy")
        if operation_retention <= timedelta(0):
            raise ValueError("operation_retention must be positive")
        if not callable(uuid_factory):
            raise TypeError("uuid_factory must be callable")
        self._database = database
        self._policy = compatibility_policy
        self._operations = operation_repository or PostgresWorkAdmissionRepository(
            database
        )
        self._operation_retention = operation_retention
        self._uuid_factory = uuid_factory

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        connection = self._database._get_connection()
        cursor = connection.cursor()
        try:
            yield cursor
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            try:
                cursor.close()
            finally:
                connection.close()

    def _new_uuid(self, field_name: str) -> str:
        return _uuid4_text(self._uuid_factory(), field_name)

    @staticmethod
    def _lock_owner(cursor: Any, owner_user_id: str) -> None:
        """Serialize host/pointer/runtime transitions for one authenticated owner."""

        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"personal-agent-owner:{owner_user_id}",),
        )

    def _lock_runtime_owner(self, cursor: Any, runtime_instance_id: str) -> str:
        cursor.execute(
            "SELECT owner_user_id FROM agent_runtime_instance "
            "WHERE runtime_instance_id = %s",
            (runtime_instance_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise StaleRuntimeGenerationError("runtime fence is stale")
        owner_user_id = str(row["owner_user_id"])
        self._lock_owner(cursor, owner_user_id)
        return owner_user_id

    def _lock_request_owner(self, cursor: Any, request_id: str) -> str:
        cursor.execute(
            "SELECT owner_user_id FROM agent_runtime_request WHERE request_id = %s",
            (request_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise StaleRuntimeGenerationError("request fence is stale")
        owner_user_id = str(row["owner_user_id"])
        self._lock_owner(cursor, owner_user_id)
        return owner_user_id

    @staticmethod
    def _host_from_row(row: Mapping[str, Any]) -> HostSessionRecord:
        return HostSessionRecord(
            host_session_id=str(row["host_session_id"]),
            host_id=str(row["host_id"]),
            owner_user_id=str(row["owner_user_id"]),
            connection_scope_id=str(row["connection_scope_id"]),
            platform=str(row["platform"]),
            client_version=str(row["client_version"]),
            host_generation=int(row["host_generation"]),
            supersedes_session_id=_optional_uuid_text(row["supersedes_session_id"]),
            supported_runtime_contract_versions=tuple(
                int(item) for item in row["supported_runtime_contract_versions"]
            ),
            runtime_contract_version=int(row["runtime_contract_version"]),
            release_lock_digest=str(row["release_lock_digest"]),
            state=str(row["state"]),
            inventory_state=str(row["inventory_state"]),
            eligible_since=row["eligible_since"],
            accepted_at=row["accepted_at"],
            last_seen_at=row["last_seen_at"],
            disconnected_at=row["disconnected_at"],
            inventory_reconciled_at=row["inventory_reconciled_at"],
            failure_code=row["failure_code"],
        )

    @staticmethod
    def _revision_from_row(row: Mapping[str, Any]) -> AgentRevisionRecord:
        manifest = row["manifest_json"]
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        return AgentRevisionRecord(
            revision_id=str(row["revision_id"]),
            agent_id=str(row["agent_id"]),
            owner_user_id=str(row["owner_user_id"]),
            revision_number=int(row["revision_number"]),
            parent_revision_id=_optional_uuid_text(row["parent_revision_id"]),
            previous_good_revision_id=_optional_uuid_text(
                row["previous_good_revision_id"]
            ),
            artifact_digest=str(row["artifact_digest"]),
            manifest=_frozen_json(manifest),
            artifact_relative_path=str(row["artifact_relative_path"]),
            runtime_contract_version=int(row["runtime_contract_version"]),
            release_lock_digest=str(row["release_lock_digest"]),
            compatibility_state=str(row["compatibility_state"]),
            state=str(row["state"]),
            promotion_token=str(row["promotion_token"]),
            state_revision=int(row["state_revision"]),
        )

    @staticmethod
    def _runtime_from_row(row: Mapping[str, Any]) -> RuntimeInstanceRecord:
        fence = RuntimeFence(
            agent_id=str(row["agent_id"]),
            host_id=str(row["host_id"]),
            host_session_id=str(row["host_session_id"]),
            delivery_id=str(row["delivery_id"]),
            revision_id=str(row["revision_id"]),
            runtime_instance_id=str(row["runtime_instance_id"]),
            process_id=_optional_uuid_text(row["process_id"]),
            lifecycle_generation=int(row["lifecycle_generation"]),
        )
        fence.validate(allow_prelaunch=fence.process_id is None)
        return RuntimeInstanceRecord(
            fence=fence,
            operation_id=_optional_uuid_text(row["operation_id"]),
            operation_execution_generation=int(
                row["operation_execution_generation"]
            ),
            state=str(row["state"]),
            is_authoritative=bool(row["is_authoritative"]),
            state_revision=int(row["state_revision"]),
            created_at=row["created_at"],
            started_at=row["started_at"],
            registered_at=row["registered_at"],
            last_heartbeat_sequence=(
                None
                if row["last_heartbeat_sequence"] is None
                else int(row["last_heartbeat_sequence"])
            ),
            ready_at=row["ready_at"],
            last_liveness_at=row["last_liveness_at"],
            terminal_at=row["terminal_at"],
            failure_code=row["failure_code"],
            active_revision_id=_optional_uuid_text(
                row.get("active_revision_id")
            ),
            authoritative_instance_id=_optional_uuid_text(
                row.get("authoritative_instance_id")
            ),
        )

    @classmethod
    def _request_from_row(cls, row: Mapping[str, Any]) -> RuntimeRequestRecord:
        runtime = cls._runtime_from_row(row)
        token = row.get("operation_execution_lease_token")
        fence = RuntimeRequestFence(
            runtime=runtime.fence,
            request_id=str(row["request_id"]),
            request_generation=str(row["request_generation"]),
            operation_id=str(row["request_operation_id"]),
            operation_execution_generation=int(
                row["request_operation_execution_generation"]
            ),
            operation_execution_lease_token=_optional_uuid_text(token),
        )
        return RuntimeRequestRecord(
            fence=fence,
            state=str(row["request_state"]),
            state_revision=int(row["request_state_revision"]),
            assigned_at=row["assigned_at"],
            terminal_at=row["request_terminal_at"],
            terminal_code=row["terminal_code"],
            result_digest=row["result_digest"],
        )

    @staticmethod
    def _validate_host_registration(
        *,
        owner_user_id: Any,
        connection_scope_id: Any,
        host_id: Any,
        platform: Any,
        client_version: Any,
        supported_runtime_contract_versions: Any,
        runtime_lock_sha256: Any,
    ) -> tuple[str, str, str, str, str, tuple[int, ...], str]:
        fields = (
            ("owner_user_id", lambda: _required_text(owner_user_id, "owner_user_id")),
            (
                "connection_scope_id",
                lambda: _uuid4_text(connection_scope_id, "connection_scope_id"),
            ),
            ("host_id", lambda: _uuid4_text(host_id, "host_id")),
        )
        validated: list[str] = []
        for field_name, validator in fields:
            try:
                validated.append(validator())
            except ValueError as exc:
                raise HostRegistrationRefused(
                    "invalid_host_registration", {"field": field_name}
                ) from exc
        if platform not in {"windows", "macos"}:
            raise HostRegistrationRefused(
                "invalid_host_registration", {"field": "platform"}
            )
        if (
            not isinstance(client_version, str)
            or len(client_version) > 128
            or not _STRICT_SEMVER_RE.fullmatch(client_version)
        ):
            raise HostRegistrationRefused(
                "invalid_host_registration", {"field": "client_version"}
            )
        versions = supported_runtime_contract_versions
        if (
            not isinstance(versions, Sequence)
            or isinstance(versions, (str, bytes))
            or not versions
            or any(type(item) is not int or item <= 0 for item in versions)
            or len(set(versions)) != len(versions)
            or len(versions) > 32
        ):
            raise HostRegistrationRefused(
                "invalid_host_registration",
                {"field": "supported_runtime_contract_versions"},
            )
        try:
            lock_digest = _sha256(runtime_lock_sha256, "runtime_lock_sha256")
        except ValueError as exc:
            raise HostRegistrationRefused(
                "invalid_host_registration", {"field": "runtime_lock_sha256"}
            ) from exc
        return (
            validated[0],
            validated[1],
            validated[2],
            platform,
            client_version,
            tuple(sorted(versions)),
            lock_digest,
        )

    def register_host_session(
        self,
        *,
        owner_user_id: str,
        connection_scope_id: str,
        host_id: str,
        platform: str,
        client_version: str,
        supported_runtime_contract_versions: Sequence[int],
        runtime_lock_sha256: str,
    ) -> HostSessionRecord:
        """Validate first, then allocate and persist one server-owned session."""

        (
            owner_user_id,
            connection_scope_id,
            host_id,
            platform,
            client_version,
            versions,
            runtime_lock_sha256,
        ) = self._validate_host_registration(
            owner_user_id=owner_user_id,
            connection_scope_id=connection_scope_id,
            host_id=host_id,
            platform=platform,
            client_version=client_version,
            supported_runtime_contract_versions=supported_runtime_contract_versions,
            runtime_lock_sha256=runtime_lock_sha256,
        )
        required_version = self._policy.runtime_contract_version
        if required_version not in versions:
            raise HostRegistrationRefused(
                "runtime_contract_unsupported",
                {
                    "required_runtime_contract_version": required_version,
                    "supported_runtime_contract_versions": list(versions),
                },
            )
        if runtime_lock_sha256 != self._policy.runtime_lock_sha256:
            raise HostRegistrationRefused(
                "runtime_lock_mismatch",
                {
                    "expected_sha256_prefix": self._policy.runtime_lock_sha256[:12],
                    "actual_sha256_prefix": runtime_lock_sha256[:12],
                },
            )

        session_id = self._new_uuid("host_session_id")
        with self._transaction() as cursor:
            self._lock_owner(cursor, owner_user_id)
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"personal-agent-host:{owner_user_id}:{host_id}",),
            )
            cursor.execute(
                """
                SELECT *
                FROM agent_host_session
                WHERE owner_user_id = %s AND host_id = %s
                ORDER BY host_generation DESC
                FOR UPDATE
                """,
                (owner_user_id, host_id),
            )
            prior_rows = list(cursor.fetchall())
            previous = prior_rows[0] if prior_rows else None
            generation = int(previous["host_generation"]) + 1 if previous else 1
            if generation > _MAX_GENERATION:
                raise PersonalAgentRuntimeError("host generation exhausted")
            cursor.execute("SELECT clock_timestamp() AS current_time")
            current_time = cursor.fetchone()["current_time"]
            eligible_since = (
                min(row["eligible_since"] for row in prior_rows)
                if previous
                else current_time
            )
            prior_session_ids = [
                str(row["host_session_id"])
                for row in prior_rows
                if row["state"] == "connected"
            ]
            if prior_session_ids:
                cursor.execute(
                    """
                    UPDATE agent_host_session
                    SET state = 'disconnected', disconnected_at = %s,
                        last_seen_at = %s, failure_code = 'host_lost'
                    WHERE host_session_id = ANY(%s::uuid[]) AND state = 'connected'
                    """,
                    (current_time, current_time, prior_session_ids),
                )
            cursor.execute(
                """
                INSERT INTO agent_host_session (
                    host_session_id, host_id, owner_user_id, connection_scope_id,
                    platform, client_version, host_generation,
                    supersedes_session_id, supported_runtime_contract_versions,
                    runtime_contract_version, release_lock_digest, state,
                    inventory_state, eligible_since, accepted_at, last_seen_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    'connected', 'pending', %s, %s, %s
                ) RETURNING *
                """,
                (
                    session_id,
                    host_id,
                    owner_user_id,
                    connection_scope_id,
                    platform,
                    client_version,
                    generation,
                    str(previous["host_session_id"]) if previous else None,
                    list(versions),
                    required_version,
                    runtime_lock_sha256,
                    eligible_since,
                    current_time,
                    current_time,
                ),
            )
            accepted = cursor.fetchone()

            # Superseding the same stable host is a host-loss boundary for its
            # old sessions. Settle those exact runtimes before rebinding sticky
            # agent pointers to the new, inventory-pending server session.
            if prior_session_ids:
                self._terminalize_session_instances_locked(
                    cursor,
                    owner_user_id=owner_user_id,
                    host_session_ids=prior_session_ids,
                    failure_code="host_lost",
                )
                cursor.execute(
                    """
                    SELECT * FROM user_agent
                    WHERE owner_user_id = %s
                      AND selected_host_session_id = ANY(%s::uuid[])
                    ORDER BY agent_id
                    FOR UPDATE
                    """,
                    (owner_user_id, prior_session_ids),
                )
                for agent_row in cursor.fetchall():
                    self._set_selected_session_locked(
                        cursor, agent_row, selected_session_id=session_id
                    )
        return self._host_from_row(accepted)

    def _locked_host_session(
        self, cursor: Any, fence: HostSessionFence
    ) -> Mapping[str, Any]:
        owner_user_id = _required_text(fence.owner_user_id, "owner_user_id")
        host_id = _uuid4_text(fence.host_id, "host_id")
        session_id = _uuid4_text(fence.host_session_id, "host_session_id")
        connection_scope_id = _uuid4_text(
            fence.connection_scope_id, "connection_scope_id"
        )
        if type(fence.host_generation) is not int or fence.host_generation <= 0:
            raise ValueError("host_generation must be positive")
        cursor.execute(
            "SELECT * FROM agent_host_session WHERE host_session_id = %s FOR UPDATE",
            (session_id,),
        )
        row = cursor.fetchone()
        if row is None or not (
            str(row["owner_user_id"]) == owner_user_id
            and str(row["host_id"]) == host_id
            and str(row["connection_scope_id"]) == connection_scope_id
            and int(row["host_generation"]) == fence.host_generation
        ):
            raise StaleRuntimeGenerationError("host session fence is stale")
        return row

    @staticmethod
    def _inventory_entry(value: Any) -> HostInventoryEntry:
        if isinstance(value, HostInventoryEntry):
            raw = {
                "agent_id": value.agent_id,
                "revision_id": value.revision_id,
                "bundle_sha256": value.bundle_sha256,
                "runtime_contract_version": value.runtime_contract_version,
                "required_runtime_lock_sha256": value.required_runtime_lock_sha256,
            }
        elif isinstance(value, Mapping):
            raw = dict(value)
        else:
            raise ValueError("inventory entry must be an object")
        required = {
            "agent_id",
            "revision_id",
            "bundle_sha256",
            "runtime_contract_version",
            "required_runtime_lock_sha256",
        }
        if set(raw) != required:
            raise ValueError("inventory entry fields are invalid")
        agent_id = _required_text(raw["agent_id"], "agent_id", maximum=255)
        revision_id = _uuid4_text(raw["revision_id"], "revision_id")
        bundle_sha256 = _sha256(raw["bundle_sha256"], "bundle_sha256")
        runtime_contract_version = raw["runtime_contract_version"]
        if type(runtime_contract_version) is not int or runtime_contract_version <= 0:
            raise ValueError("runtime_contract_version must be a positive integer")
        required_runtime_lock_sha256 = _sha256(
            raw["required_runtime_lock_sha256"],
            "required_runtime_lock_sha256",
        )
        return HostInventoryEntry(
            agent_id=agent_id,
            revision_id=revision_id,
            bundle_sha256=bundle_sha256,
            runtime_contract_version=runtime_contract_version,
            required_runtime_lock_sha256=required_runtime_lock_sha256,
        )

    @classmethod
    def _inventory_entries(
        cls, entries: Sequence[Any]
    ) -> tuple[HostInventoryEntry, ...]:
        if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
            raise ValueError("inventory entries must be an array")
        if len(entries) > 1_000:
            raise ValueError("inventory exceeds 1000 entries")
        validated = tuple(cls._inventory_entry(value) for value in entries)
        keys = {(entry.agent_id, entry.revision_id) for entry in validated}
        if len(keys) != len(validated):
            raise ValueError("inventory entries must have unique agent/revision pairs")
        return validated

    @staticmethod
    def _inventory_action_without_delivery(
        entry: HostInventoryEntry, *, action: str, reason_code: str
    ) -> HostInventoryAction:
        return HostInventoryAction(
            agent_id=entry.agent_id,
            revision_id=entry.revision_id,
            action=action,
            reason_code=reason_code,
            selected_delivery=None,
        )

    def reconcile_host_inventory(
        self,
        fence: HostSessionFence,
        *,
        inventory_id: str,
        entries: Sequence[Any],
        delivery_operation_fences: Optional[
            Mapping[tuple[str, str], ExecutionFence]
        ] = None,
    ) -> HostInventoryReconciliation:
        """Validate, decide, allocate selected deliveries, and commit as one unit.

        A start action is possible only for an exact retained active revision on
        this selected server-issued session.  Its running delivery operation
        must be supplied under the same ``(agent_id, revision_id)`` key.  Any
        malformed entry, missing/extra operation fence, stale pointer, or failed
        allocation rolls the whole transaction back and leaves inventory
        pending, so the host cannot start a partial response.
        """

        inventory_id = _uuid4_text(inventory_id, "inventory_id")
        validated_entries = self._inventory_entries(entries)
        supplied_operations = dict(delivery_operation_fences or {})
        for key, operation_fence in supplied_operations.items():
            if (
                not isinstance(key, tuple)
                or len(key) != 2
                or not isinstance(key[0], str)
                or not isinstance(key[1], str)
                or not isinstance(operation_fence, ExecutionFence)
            ):
                raise ValueError("delivery operation fence mapping is invalid")

        with self._transaction() as cursor:
            self._lock_owner(cursor, fence.owner_user_id)
            host = self._locked_host_session(cursor, fence)
            if host["state"] != "connected":
                raise StaleRuntimeGenerationError("host session is disconnected")
            if host["inventory_state"] != "pending":
                raise StaleRuntimeGenerationError("host inventory is not pending")
            if not (
                int(host["runtime_contract_version"])
                == self._policy.runtime_contract_version
                and host["release_lock_digest"] == self._policy.runtime_lock_sha256
            ):
                raise StaleRuntimeGenerationError("host compatibility fence is stale")

            agent_ids = sorted({entry.agent_id for entry in validated_entries})
            agents: dict[str, Mapping[str, Any]] = {}
            if agent_ids:
                cursor.execute(
                    """
                    SELECT * FROM user_agent
                    WHERE owner_user_id = %s AND agent_id = ANY(%s::text[])
                    ORDER BY agent_id
                    FOR UPDATE
                    """,
                    (fence.owner_user_id, agent_ids),
                )
                agents = {str(row["agent_id"]): row for row in cursor.fetchall()}

            revision_ids = sorted(
                {entry.revision_id for entry in validated_entries}
            )
            revisions: dict[str, Mapping[str, Any]] = {}
            if revision_ids:
                cursor.execute(
                    """
                    SELECT * FROM user_agent_revision
                    WHERE revision_id = ANY(%s::uuid[])
                    ORDER BY revision_id
                    FOR SHARE
                    """,
                    (revision_ids,),
                )
                revisions = {
                    str(row["revision_id"]): row for row in cursor.fetchall()
                }

            decisions: list[
                tuple[HostInventoryEntry, HostInventoryAction, Optional[Mapping[str, Any]]]
            ] = []
            start_keys: set[tuple[str, str]] = set()
            for entry in validated_entries:
                agent = agents.get(entry.agent_id)
                revision = revisions.get(entry.revision_id)
                if agent is None:
                    action = self._inventory_action_without_delivery(
                        entry, action="delete", reason_code="agent_unknown"
                    )
                elif agent["deleted_at"] is not None:
                    action = self._inventory_action_without_delivery(
                        entry, action="delete", reason_code="agent_deleted"
                    )
                elif revision is None or not (
                    str(revision["owner_user_id"]) == fence.owner_user_id
                    and str(revision["agent_id"]) == entry.agent_id
                ):
                    action = self._inventory_action_without_delivery(
                        entry, action="delete", reason_code="revision_unknown"
                    )
                elif revision["artifact_digest"] != entry.bundle_sha256:
                    action = self._inventory_action_without_delivery(
                        entry, action="delete", reason_code="bundle_digest_mismatch"
                    )
                elif (
                    int(revision["runtime_contract_version"] or 0)
                    != entry.runtime_contract_version
                    or entry.runtime_contract_version
                    != self._policy.runtime_contract_version
                ):
                    action = self._inventory_action_without_delivery(
                        entry,
                        action="delete",
                        reason_code="runtime_contract_unsupported",
                    )
                elif (
                    revision["release_lock_digest"]
                    != entry.required_runtime_lock_sha256
                    or entry.required_runtime_lock_sha256
                    != self._policy.runtime_lock_sha256
                ):
                    action = self._inventory_action_without_delivery(
                        entry, action="delete", reason_code="runtime_lock_mismatch"
                    )
                elif revision["compatibility_state"] != "compatible":
                    action = self._inventory_action_without_delivery(
                        entry, action="delete", reason_code="revision_incompatible"
                    )
                elif revision["state"] in {"failed", "retired", "legacy_pending"}:
                    action = self._inventory_action_without_delivery(
                        entry, action="delete", reason_code="revision_obsolete"
                    )
                elif (
                    _optional_uuid_text(agent["active_revision_id"])
                    != entry.revision_id
                    or revision["state"] != "active"
                ):
                    action = self._inventory_action_without_delivery(
                        entry, action="keep_stopped", reason_code="revision_not_active"
                    )
                elif (
                    _optional_uuid_text(agent["selected_host_session_id"])
                    != fence.host_session_id
                ):
                    action = self._inventory_action_without_delivery(
                        entry, action="keep_stopped", reason_code="host_not_selected"
                    )
                else:
                    key = (entry.agent_id, entry.revision_id)
                    start_keys.add(key)
                    action = HostInventoryAction(
                        agent_id=entry.agent_id,
                        revision_id=entry.revision_id,
                        action="start",
                        reason_code=None,
                        selected_delivery=None,
                    )
                decisions.append((entry, action, revision))

            if set(supplied_operations) != start_keys:
                raise ValueError(
                    "delivery operations must exactly match inventory start actions"
                )
            for key in sorted(start_keys):
                self._assert_operation_locked(
                    cursor,
                    supplied_operations[key],
                    owner_user_id=fence.owner_user_id,
                )

            actions: list[HostInventoryAction] = []
            for entry, action, revision in decisions:
                if action.action != "start":
                    actions.append(action)
                    continue
                agent = agents[entry.agent_id]
                if revision is None:  # pragma: no cover - decision invariant
                    raise RuntimeError("start action has no revision")
                instance = self._create_prelaunch_instance_locked(
                    cursor,
                    agent_row=agent,
                    host_row=host,
                    revision_row=revision,
                    operation_fence=supplied_operations[
                        (entry.agent_id, entry.revision_id)
                    ],
                    allow_inventory_pending=True,
                    operation_already_validated=True,
                )
                actions.append(
                    HostInventoryAction(
                        agent_id=entry.agent_id,
                        revision_id=entry.revision_id,
                        action="start",
                        reason_code=None,
                        selected_delivery=HostInventorySelectedDelivery(
                            delivery_id=instance.fence.delivery_id,
                            runtime_instance_id=instance.fence.runtime_instance_id,
                            lifecycle_generation=instance.fence.lifecycle_generation,
                            runtime_contract_version=self._policy.runtime_contract_version,
                            required_runtime_lock_sha256=self._policy.runtime_lock_sha256,
                            bundle_sha256=entry.bundle_sha256,
                        ),
                    )
                )

            cursor.execute(
                """
                UPDATE agent_host_session
                SET inventory_state = 'reconciled',
                    inventory_reconciled_at = clock_timestamp(),
                    last_seen_at = clock_timestamp(), failure_code = NULL
                WHERE host_session_id = %s AND state = 'connected'
                  AND inventory_state = 'pending'
                RETURNING *
                """,
                (fence.host_session_id,),
            )
            reconciled_host = cursor.fetchone()
            if reconciled_host is None:
                raise StaleRuntimeGenerationError("host inventory fence is stale")
        host_record = self._host_from_row(reconciled_host)
        return HostInventoryReconciliation(
            host=host_record,
            inventory_id=inventory_id,
            actions=tuple(actions),
            reconciled_at=host_record.inventory_reconciled_at,
        )

    def mark_inventory_reconciled(
        self, fence: HostSessionFence
    ) -> HostSessionRecord:
        """Commit an explicitly empty inventory (compatibility convenience)."""

        result = self.reconcile_host_inventory(
            fence,
            inventory_id=self._new_uuid("inventory_id"),
            entries=(),
        )
        return result.host

    @staticmethod
    def _set_selected_session_locked(
        cursor: Any,
        agent_row: Mapping[str, Any],
        *,
        selected_session_id: Optional[str],
    ) -> tuple[int, bool]:
        previous = _optional_uuid_text(agent_row["selected_host_session_id"])
        if previous == selected_session_id:
            return int(agent_row["lifecycle_generation"]), False
        generation = max(
            int(agent_row["generation_counter"]),
            int(agent_row["lifecycle_generation"]),
        ) + 1
        if generation > _MAX_GENERATION:
            raise PersonalAgentRuntimeError("agent lifecycle generation exhausted")
        cursor.execute(
            """
            UPDATE user_agent
            SET selected_host_session_id = %s,
                generation_counter = %s,
                lifecycle_generation = %s,
                state_revision = state_revision + 1,
                updated_at = (extract(epoch from clock_timestamp()) * 1000)::bigint
            WHERE agent_id = %s AND owner_user_id = %s
              AND state_revision = %s
            RETURNING lifecycle_generation
            """,
            (
                selected_session_id,
                generation,
                generation,
                agent_row["agent_id"],
                agent_row["owner_user_id"],
                agent_row["state_revision"],
            ),
        )
        updated = cursor.fetchone()
        if updated is None:
            raise StaleRuntimeGenerationError("agent selection revision is stale")
        return int(updated["lifecycle_generation"]), True

    def _select_host_locked(
        self, cursor: Any, agent_row: Mapping[str, Any]
    ) -> HostSelection:
        previous_session_id = _optional_uuid_text(
            agent_row["selected_host_session_id"]
        )
        selected_row = None
        if previous_session_id is not None:
            cursor.execute(
                "SELECT * FROM agent_host_session WHERE host_session_id = %s",
                (previous_session_id,),
            )
            previous_host = cursor.fetchone()
            if (
                previous_host is not None
                and previous_host["owner_user_id"] == agent_row["owner_user_id"]
            ):
                cursor.execute(
                    """
                    SELECT * FROM agent_host_session
                    WHERE owner_user_id = %s AND host_id = %s
                      AND state = 'connected'
                    ORDER BY host_generation DESC
                    LIMIT 1
                    """,
                    (agent_row["owner_user_id"], previous_host["host_id"]),
                )
                selected_row = cursor.fetchone()
        if selected_row is None:
            cursor.execute(
                """
                SELECT * FROM agent_host_session
                WHERE owner_user_id = %s AND state = 'connected'
                ORDER BY eligible_since, host_id::text, host_session_id::text
                LIMIT 1
                """,
                (agent_row["owner_user_id"],),
            )
            selected_row = cursor.fetchone()
        selected_session_id = (
            None if selected_row is None else str(selected_row["host_session_id"])
        )
        lifecycle_generation, changed = self._set_selected_session_locked(
            cursor,
            agent_row,
            selected_session_id=selected_session_id,
        )
        return HostSelection(
            session=(
                None if selected_row is None else self._host_from_row(selected_row)
            ),
            previous_session_id=previous_session_id,
            changed=changed,
            lifecycle_generation=lifecycle_generation,
        )

    def select_host_for_agent(
        self, *, owner_user_id: str, agent_id: str
    ) -> HostSelection:
        owner_user_id = _required_text(owner_user_id, "owner_user_id")
        agent_id = _required_text(agent_id, "agent_id", maximum=255)
        with self._transaction() as cursor:
            self._lock_owner(cursor, owner_user_id)
            agent_row = self._locked_agent(
                cursor, owner_user_id=owner_user_id, agent_id=agent_id
            )
            return self._select_host_locked(cursor, agent_row)

    def get_selected_session_revision(
        self,
        fence: HostSessionFence,
        *,
        agent_id: str,
    ) -> SelectedSessionRevision:
        """Return the active revision only when ``fence`` is the exact selection.

        This lookup intentionally permits either pending or reconciled inventory
        so the host-frame adapter can determine which retained entries need
        delivery-operation fences before committing one inventory transaction.
        It never makes the session delivery eligible by itself.
        """

        agent_id = _required_text(agent_id, "agent_id", maximum=255)
        with self._transaction() as cursor:
            self._lock_owner(cursor, fence.owner_user_id)
            host = self._locked_host_session(cursor, fence)
            if host["state"] != "connected" or host["inventory_state"] not in {
                "pending",
                "reconciled",
            }:
                raise StaleRuntimeGenerationError("host session is not selectable")
            agent = self._locked_agent(
                cursor,
                owner_user_id=fence.owner_user_id,
                agent_id=agent_id,
            )
            if (
                _optional_uuid_text(agent["selected_host_session_id"])
                != fence.host_session_id
            ):
                raise AgentOfflineError("host session is not selected for this agent")
            active_revision_id = _optional_uuid_text(agent["active_revision_id"])
            if active_revision_id is None:
                raise AgentOfflineError("personal agent has no active revision")
            cursor.execute(
                """
                SELECT * FROM user_agent_revision
                WHERE revision_id = %s AND agent_id = %s AND owner_user_id = %s
                FOR SHARE
                """,
                (active_revision_id, agent_id, fence.owner_user_id),
            )
            revision = cursor.fetchone()
            if not (
                revision is not None
                and revision["state"] == "active"
                and revision["compatibility_state"] == "compatible"
                and int(revision["runtime_contract_version"])
                == self._policy.runtime_contract_version
                and revision["release_lock_digest"]
                == self._policy.runtime_lock_sha256
            ):
                raise AgentOfflineError("personal agent has no compatible active revision")
            return SelectedSessionRevision(
                host=self._host_from_row(host),
                revision=self._revision_from_row(revision),
                lifecycle_generation=int(agent["lifecycle_generation"]),
            )

    @staticmethod
    def _locked_agent(
        cursor: Any, *, owner_user_id: str, agent_id: str
    ) -> Mapping[str, Any]:
        cursor.execute(
            """
            SELECT * FROM user_agent
            WHERE agent_id = %s AND owner_user_id = %s
            FOR UPDATE
            """,
            (agent_id, owner_user_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise PersonalAgentNotFoundError("personal agent not found")
        if row["deleted_at"] is not None:
            raise AgentDeletedError("agent_deleted")
        return row

    @staticmethod
    def _validate_manifest(manifest: Any) -> tuple[Mapping[str, Any], str]:
        if not isinstance(manifest, Mapping):
            raise ValueError("manifest must be an object")
        try:
            detached = _plain_json(manifest)
            canonical = json.dumps(
                detached,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("manifest must be bounded canonical JSON") from exc
        if len(canonical.encode("utf-8")) > 64 * 1024:
            raise ValueError("manifest exceeds 64 KiB")
        return _frozen_json(json.loads(canonical)), canonical

    def create_revision(
        self,
        *,
        owner_user_id: str,
        agent_id: str,
        artifact_digest: str,
        manifest: Mapping[str, Any],
        artifact_relative_path: str,
        runtime_contract_version: int,
        release_lock_digest: str,
        parent_revision_id: Optional[str] = None,
    ) -> AgentRevisionRecord:
        """Insert one immutable compatible revision under the owner/agent lock."""

        owner_user_id = _required_text(owner_user_id, "owner_user_id")
        agent_id = _required_text(agent_id, "agent_id", maximum=255)
        artifact_digest = _sha256(artifact_digest, "artifact_digest")
        release_lock_digest = _sha256(
            release_lock_digest, "release_lock_digest"
        )
        if runtime_contract_version != self._policy.runtime_contract_version:
            raise ValueError("revision runtime contract is incompatible")
        if release_lock_digest != self._policy.runtime_lock_sha256:
            raise ValueError("revision runtime lock is incompatible")
        if (
            not isinstance(artifact_relative_path, str)
            or not artifact_relative_path
            or "\\" in artifact_relative_path
            or PurePosixPath(artifact_relative_path).is_absolute()
            or ".." in PurePosixPath(artifact_relative_path).parts
            or len(artifact_relative_path) > 1024
        ):
            raise ValueError("artifact_relative_path must remain beneath revision root")
        immutable_manifest, canonical_manifest = self._validate_manifest(manifest)
        parent_revision_id = (
            None
            if parent_revision_id is None
            else _uuid4_text(parent_revision_id, "parent_revision_id")
        )
        revision_id = self._new_uuid("revision_id")
        promotion_token = self._new_uuid("promotion_token")
        with self._transaction() as cursor:
            self._lock_owner(cursor, owner_user_id)
            agent_row = self._locked_agent(
                cursor, owner_user_id=owner_user_id, agent_id=agent_id
            )
            if parent_revision_id is not None:
                cursor.execute(
                    """
                    SELECT 1 FROM user_agent_revision
                    WHERE revision_id = %s AND agent_id = %s AND owner_user_id = %s
                    """,
                    (parent_revision_id, agent_id, owner_user_id),
                )
                if cursor.fetchone() is None:
                    raise StaleRuntimeGenerationError("parent revision is stale")
            cursor.execute(
                "SELECT COALESCE(max(revision_number), -1) + 1 AS next_revision "
                "FROM user_agent_revision WHERE agent_id = %s",
                (agent_id,),
            )
            revision_number = int(cursor.fetchone()["next_revision"])
            cursor.execute(
                """
                INSERT INTO user_agent_revision (
                    revision_id, agent_id, owner_user_id, revision_number,
                    parent_revision_id, previous_good_revision_id,
                    artifact_digest, manifest_json, artifact_relative_path,
                    runtime_contract_version, release_lock_digest,
                    compatibility_state, state, promotion_token
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    'compatible', 'prepared', %s
                ) RETURNING *
                """,
                (
                    revision_id,
                    agent_id,
                    owner_user_id,
                    revision_number,
                    parent_revision_id,
                    agent_row["active_revision_id"],
                    artifact_digest,
                    Json(json.loads(canonical_manifest)),
                    artifact_relative_path,
                    runtime_contract_version,
                    release_lock_digest,
                    promotion_token,
                ),
            )
            row = cursor.fetchone()
        record = self._revision_from_row(row)
        if record.manifest != immutable_manifest:
            raise RuntimeError("persisted revision manifest changed")
        return record

    @staticmethod
    def _runtime_join_sql(*, lock: bool) -> str:
        suffix = " FOR UPDATE OF ri, ua, hs" if lock else ""
        return (
            "SELECT ri.*, ua.selected_host_session_id, "
            "ua.authoritative_instance_id, ua.active_revision_id, "
            "ua.deleted_at AS agent_deleted_at, ua.state_revision AS agent_state_revision, "
            "ua.lifecycle_generation AS agent_lifecycle_generation, "
            "ua.generation_counter AS agent_generation_counter, "
            "hs.owner_user_id AS host_owner_user_id, "
            "hs.host_id AS session_host_id, hs.connection_scope_id, "
            "hs.state AS host_state, hs.inventory_state AS host_inventory_state, "
            "hs.runtime_contract_version AS host_runtime_contract_version, "
            "hs.release_lock_digest AS host_release_lock_digest, "
            "rev.artifact_digest AS revision_artifact_digest, "
            "rev.release_lock_digest AS revision_lock_digest, "
            "rev.runtime_contract_version AS revision_runtime_contract_version, "
            "rev.compatibility_state AS revision_compatibility_state, "
            "rev.state AS revision_state "
            "FROM agent_runtime_instance ri "
            "JOIN user_agent ua ON ua.agent_id = ri.agent_id "
            "  AND ua.owner_user_id = ri.owner_user_id "
            "JOIN agent_host_session hs ON hs.host_session_id = ri.host_session_id "
            "JOIN user_agent_revision rev ON rev.revision_id = ri.revision_id "
            "  AND rev.agent_id = ri.agent_id AND rev.owner_user_id = ri.owner_user_id "
            "WHERE ri.runtime_instance_id = %s" + suffix
        )

    @staticmethod
    def _runtime_fence_matches(
        row: Mapping[str, Any], fence: RuntimeFence, *, allow_prelaunch: bool
    ) -> bool:
        fence.validate(allow_prelaunch=allow_prelaunch)
        process_id = _optional_uuid_text(row["process_id"])
        return (
            str(row["agent_id"]) == fence.agent_id
            and str(row["host_id"]) == fence.host_id
            and str(row["host_session_id"]) == fence.host_session_id
            and str(row["delivery_id"]) == fence.delivery_id
            and str(row["revision_id"]) == fence.revision_id
            and str(row["runtime_instance_id"]) == fence.runtime_instance_id
            and process_id == fence.process_id
            and int(row["lifecycle_generation"]) == fence.lifecycle_generation
        )

    def _locked_runtime(
        self,
        cursor: Any,
        fence: RuntimeFence,
        *,
        allow_prelaunch: bool,
        require_current_host: bool,
    ) -> Mapping[str, Any]:
        self._lock_runtime_owner(cursor, fence.runtime_instance_id)
        cursor.execute(self._runtime_join_sql(lock=True), (fence.runtime_instance_id,))
        row = cursor.fetchone()
        if row is None or not self._runtime_fence_matches(
            row, fence, allow_prelaunch=allow_prelaunch
        ):
            raise StaleRuntimeGenerationError("runtime fence is stale")
        if row["agent_deleted_at"] is not None:
            raise AgentDeletedError("agent_deleted")
        if not (
            str(row["host_owner_user_id"]) == str(row["owner_user_id"])
            and str(row["session_host_id"]) == str(row["host_id"])
        ):
            raise StaleRuntimeGenerationError("runtime host binding is stale")
        if require_current_host and not (
            row["host_state"] == "connected"
            and str(row["selected_host_session_id"]) == str(row["host_session_id"])
        ):
            raise StaleRuntimeGenerationError("selected host session is stale")
        return row

    def _assert_operation_locked(
        self,
        cursor: Any,
        fence: ExecutionFence,
        *,
        owner_user_id: str,
    ) -> Any:
        try:
            operation = self._operations.assert_current_execution(
                fence, transaction=cursor
            )
        except StaleExecutionFenceError as exc:
            raise StaleRuntimeGenerationError(
                "operation execution fence is stale"
            ) from exc
        if operation.owner_user_id != owner_user_id:
            raise StaleRuntimeGenerationError("operation owner fence is stale")
        return operation

    def _assert_runtime_operation_locked(
        self, cursor: Any, row: Mapping[str, Any]
    ) -> ExecutionFence:
        operation_id = row["operation_id"]
        if operation_id is None:
            raise StaleRuntimeGenerationError("runtime operation fence is absent")
        cursor.execute(
            """
            SELECT operation_id, owner_user_id, state, execution_generation,
                   execution_lease_token
            FROM operation_record WHERE operation_id = %s
            FOR UPDATE
            """,
            (operation_id,),
        )
        operation = cursor.fetchone()
        if not (
            operation is not None
            and operation["state"] == "running"
            and operation["owner_user_id"] == row["owner_user_id"]
            and int(operation["execution_generation"])
            == int(row["operation_execution_generation"])
            and operation["execution_lease_token"] is not None
        ):
            raise StaleRuntimeGenerationError("runtime operation fence is stale")
        return ExecutionFence(
            operation_id=uuid.UUID(str(operation["operation_id"])),
            execution_generation=int(operation["execution_generation"]),
            execution_lease_token=uuid.UUID(str(operation["execution_lease_token"])),
        )

    def _create_prelaunch_instance_locked(
        self,
        cursor: Any,
        *,
        agent_row: Mapping[str, Any],
        host_row: Mapping[str, Any],
        revision_row: Mapping[str, Any],
        operation_fence: ExecutionFence,
        allow_inventory_pending: bool,
        operation_already_validated: bool,
    ) -> RuntimeInstanceRecord:
        owner_user_id = str(agent_row["owner_user_id"])
        agent_id = str(agent_row["agent_id"])
        host_session_id = str(host_row["host_session_id"])
        revision_id = str(revision_row["revision_id"])
        allowed_inventory_states = (
            {"pending", "reconciled"}
            if allow_inventory_pending
            else {"reconciled"}
        )
        if not (
            _optional_uuid_text(agent_row["selected_host_session_id"])
            == host_session_id
            and str(host_row["owner_user_id"]) == owner_user_id
            and host_row["state"] == "connected"
            and host_row["inventory_state"] in allowed_inventory_states
            and int(host_row["runtime_contract_version"])
            == self._policy.runtime_contract_version
            and host_row["release_lock_digest"]
            == self._policy.runtime_lock_sha256
        ):
            raise StaleRuntimeGenerationError("host session is not delivery eligible")
        if not (
            str(revision_row["agent_id"]) == agent_id
            and str(revision_row["owner_user_id"]) == owner_user_id
            and revision_row["compatibility_state"] == "compatible"
            and revision_row["state"] in {"prepared", "ready", "active"}
            and int(revision_row["runtime_contract_version"])
            == self._policy.runtime_contract_version
            and revision_row["release_lock_digest"]
            == self._policy.runtime_lock_sha256
        ):
            raise StaleRuntimeGenerationError("revision is not delivery eligible")
        if not operation_already_validated:
            self._assert_operation_locked(
                cursor, operation_fence, owner_user_id=owner_user_id
            )

        runtime_instance_id = self._new_uuid("runtime_instance_id")
        delivery_id = self._new_uuid("delivery_id")
        lifecycle_generation = max(
            int(agent_row["generation_counter"]),
            int(agent_row["lifecycle_generation"]),
        ) + 1
        if lifecycle_generation > _MAX_GENERATION:
            raise PersonalAgentRuntimeError("agent lifecycle generation exhausted")
        cursor.execute(
            """
            UPDATE user_agent
            SET generation_counter = %s, state_revision = state_revision + 1,
                updated_at = (extract(epoch from clock_timestamp()) * 1000)::bigint
            WHERE agent_id = %s AND owner_user_id = %s AND state_revision = %s
            """,
            (
                lifecycle_generation,
                agent_id,
                owner_user_id,
                agent_row["state_revision"],
            ),
        )
        if cursor.rowcount != 1:
            raise StaleRuntimeGenerationError("agent generation allocator is stale")
        cursor.execute(
            """
            INSERT INTO agent_runtime_instance (
                runtime_instance_id, agent_id, owner_user_id, host_id,
                host_session_id, delivery_id, revision_id, process_id,
                lifecycle_generation, runtime_contract_version, operation_id,
                operation_execution_generation, state, is_authoritative
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s,
                'delivering', FALSE
            ) RETURNING *
            """,
            (
                runtime_instance_id,
                agent_id,
                owner_user_id,
                host_row["host_id"],
                host_session_id,
                delivery_id,
                revision_id,
                lifecycle_generation,
                self._policy.runtime_contract_version,
                str(operation_fence.operation_id),
                operation_fence.execution_generation,
            ),
        )
        row = cursor.fetchone()
        if row is None:  # pragma: no cover - INSERT RETURNING invariant
            raise RuntimeError("runtime insert returned no row")
        return self._runtime_from_row(row)

    def create_prelaunch_instance(
        self,
        *,
        owner_user_id: str,
        agent_id: str,
        host_session_id: str,
        revision_id: str,
        operation_fence: ExecutionFence,
    ) -> RuntimeInstanceRecord:
        owner_user_id = _required_text(owner_user_id, "owner_user_id")
        agent_id = _required_text(agent_id, "agent_id", maximum=255)
        host_session_id = _uuid4_text(host_session_id, "host_session_id")
        revision_id = _uuid4_text(revision_id, "revision_id")
        if not isinstance(operation_fence, ExecutionFence):
            raise TypeError("operation_fence must be ExecutionFence")
        with self._transaction() as cursor:
            self._lock_owner(cursor, owner_user_id)
            agent_row = self._locked_agent(
                cursor, owner_user_id=owner_user_id, agent_id=agent_id
            )
            cursor.execute(
                "SELECT * FROM agent_host_session WHERE host_session_id = %s FOR UPDATE",
                (host_session_id,),
            )
            host = cursor.fetchone()
            cursor.execute(
                """
                SELECT * FROM user_agent_revision
                WHERE revision_id = %s AND agent_id = %s AND owner_user_id = %s
                FOR SHARE
                """,
                (revision_id, agent_id, owner_user_id),
            )
            revision = cursor.fetchone()
            if host is None or revision is None:
                raise StaleRuntimeGenerationError("delivery identity is stale")
            return self._create_prelaunch_instance_locked(
                cursor,
                agent_row=agent_row,
                host_row=host,
                revision_row=revision,
                operation_fence=operation_fence,
                allow_inventory_pending=False,
                operation_already_validated=False,
            )

    def create_selected_recovery_instance(
        self,
        *,
        owner_user_id: str,
        agent_id: str,
        operation_fence: ExecutionFence,
    ) -> SelectedRecoveryDelivery:
        """Allocate one fresh recovery runtime for the durable selected standby.

        This is the post-disconnect/failover seam. It resolves the current
        selected reconciled host and already-active revision under the same
        owner transaction that allocates the delivery/runtime generation. A
        current authority or another non-terminal recovery makes the request
        stale, preventing duplicate starts from concurrent disconnect handlers.
        """

        owner_user_id = _required_text(owner_user_id, "owner_user_id")
        agent_id = _required_text(agent_id, "agent_id", maximum=255)
        if not isinstance(operation_fence, ExecutionFence):
            raise TypeError("operation_fence must be ExecutionFence")
        with self._transaction() as cursor:
            self._lock_owner(cursor, owner_user_id)
            agent = self._locked_agent(
                cursor,
                owner_user_id=owner_user_id,
                agent_id=agent_id,
            )
            host_session_id = _optional_uuid_text(
                agent["selected_host_session_id"]
            )
            revision_id = _optional_uuid_text(agent["active_revision_id"])
            if host_session_id is None or revision_id is None:
                raise AgentOfflineError(
                    "personal agent has no selected host and active revision"
                )
            if agent["authoritative_instance_id"] is not None:
                raise StaleRuntimeGenerationError(
                    "personal agent already has an authoritative runtime"
                )
            cursor.execute(
                "SELECT * FROM agent_host_session "
                "WHERE host_session_id = %s FOR UPDATE",
                (host_session_id,),
            )
            host = cursor.fetchone()
            cursor.execute(
                """
                SELECT * FROM user_agent_revision
                WHERE revision_id = %s AND agent_id = %s AND owner_user_id = %s
                FOR SHARE
                """,
                (revision_id, agent_id, owner_user_id),
            )
            revision = cursor.fetchone()
            if not (
                host is not None
                and host["state"] == "connected"
                and host["inventory_state"] == "reconciled"
                and str(host["owner_user_id"]) == owner_user_id
                and revision is not None
                and revision["state"] == "active"
                and revision["compatibility_state"] == "compatible"
            ):
                raise AgentOfflineError(
                    "selected standby is not eligible for active revision recovery"
                )
            cursor.execute(
                """
                SELECT runtime_instance_id
                FROM agent_runtime_instance
                WHERE agent_id = %s AND owner_user_id = %s
                  AND host_session_id = %s AND revision_id = %s
                  AND state NOT IN ('stopped', 'failed', 'offline', 'superseded')
                ORDER BY created_at, runtime_instance_id
                FOR UPDATE
                """,
                (agent_id, owner_user_id, host_session_id, revision_id),
            )
            if cursor.fetchone() is not None:
                raise StaleRuntimeGenerationError(
                    "selected recovery runtime is already pending"
                )
            instance = self._create_prelaunch_instance_locked(
                cursor,
                agent_row=agent,
                host_row=host,
                revision_row=revision,
                operation_fence=operation_fence,
                allow_inventory_pending=False,
                operation_already_validated=False,
            )
            return SelectedRecoveryDelivery(
                host=self._host_from_row(host),
                revision=self._revision_from_row(revision),
                instance=instance,
            )

    def bind_runtime_process(
        self,
        fence: RuntimeFence,
        *,
        process_id: str,
        expected_state_revision: int,
    ) -> RuntimeInstanceRecord:
        """Bind the host's logical process UUID exactly once on ``starting``."""

        if fence.process_id is not None:
            raise ValueError("prelaunch fence process_id must be null")
        fence.validate(allow_prelaunch=True)
        process_id = _uuid4_text(process_id, "process_id")
        if type(expected_state_revision) is not int or expected_state_revision < 0:
            raise ValueError("expected_state_revision must be non-negative")
        with self._transaction() as cursor:
            self._lock_runtime_owner(cursor, fence.runtime_instance_id)
            cursor.execute(
                self._runtime_join_sql(lock=True), (fence.runtime_instance_id,)
            )
            row = cursor.fetchone()
            if row is None:
                raise StaleRuntimeGenerationError("prelaunch runtime fence is stale")
            row_fence = RuntimeFence(
                agent_id=str(row["agent_id"]),
                host_id=str(row["host_id"]),
                host_session_id=str(row["host_session_id"]),
                delivery_id=str(row["delivery_id"]),
                revision_id=str(row["revision_id"]),
                runtime_instance_id=str(row["runtime_instance_id"]),
                process_id=None,
                lifecycle_generation=int(row["lifecycle_generation"]),
            )
            if row_fence != fence:
                raise StaleRuntimeGenerationError("prelaunch runtime fence is stale")
            if row["agent_deleted_at"] is not None:
                raise AgentDeletedError("agent_deleted")
            if not (
                str(row["host_owner_user_id"]) == str(row["owner_user_id"])
                and str(row["session_host_id"]) == str(row["host_id"])
                and row["host_state"] == "connected"
                and row["host_inventory_state"] == "reconciled"
                and str(row["selected_host_session_id"])
                == str(row["host_session_id"])
            ):
                raise StaleRuntimeGenerationError("selected host session is stale")
            existing_process_id = _optional_uuid_text(row["process_id"])
            if existing_process_id is not None:
                if existing_process_id == process_id and row["state"] in {
                    "starting",
                    "ready",
                    "online",
                    "updating",
                    "stopping",
                    "stopped",
                    "failed",
                    "offline",
                }:
                    return self._runtime_from_row(row)
                raise StaleRuntimeGenerationError("runtime process is already bound")
            if not (
                row["state"] == "delivering"
                and int(row["state_revision"]) == expected_state_revision
            ):
                raise StaleRuntimeGenerationError("prelaunch runtime revision is stale")
            self._assert_runtime_operation_locked(cursor, row)
            cursor.execute(
                "SELECT 1 FROM agent_runtime_instance "
                "WHERE host_id = %s AND process_id = %s",
                (row["host_id"], process_id),
            )
            if cursor.fetchone() is not None:
                raise StaleRuntimeGenerationError("process identity was already used")
            cursor.execute(
                """
                UPDATE agent_runtime_instance
                SET process_id = %s, state = 'starting', started_at = clock_timestamp(),
                    state_revision = state_revision + 1
                WHERE runtime_instance_id = %s AND agent_id = %s
                  AND owner_user_id = %s AND host_id = %s
                  AND host_session_id = %s AND delivery_id = %s
                  AND revision_id = %s AND lifecycle_generation = %s
                  AND process_id IS NULL AND state = 'delivering'
                  AND state_revision = %s
                RETURNING *
                """,
                (
                    process_id,
                    fence.runtime_instance_id,
                    fence.agent_id,
                    row["owner_user_id"],
                    fence.host_id,
                    fence.host_session_id,
                    fence.delivery_id,
                    fence.revision_id,
                    fence.lifecycle_generation,
                    expected_state_revision,
                ),
            )
            updated = cursor.fetchone()
            if updated is None:
                raise StaleRuntimeGenerationError("prelaunch bind CAS is stale")
        return self._runtime_from_row(updated)

    def accept_runtime_registration(
        self,
        fence: RuntimeFence,
        *,
        runtime_contract_version: int,
        bundle_sha256: str,
    ) -> RuntimeInstanceRecord:
        """Durably accept the exact bound child's first registration frame."""

        fence.validate(allow_prelaunch=False)
        bundle_sha256 = _sha256(bundle_sha256, "bundle_sha256")
        with self._transaction() as cursor:
            row = self._locked_runtime(
                cursor,
                fence,
                allow_prelaunch=False,
                require_current_host=True,
            )
            if not (
                runtime_contract_version == int(row["runtime_contract_version"])
                == self._policy.runtime_contract_version
                and bundle_sha256 == row["revision_artifact_digest"]
                and row["revision_lock_digest"] == self._policy.runtime_lock_sha256
                and int(row["revision_runtime_contract_version"])
                == self._policy.runtime_contract_version
            ):
                raise StaleRuntimeGenerationError(
                    "runtime registration compatibility fence is stale"
                )
            if row["registered_at"] is not None:
                return self._runtime_from_row(row)
            if row["state"] != "starting":
                raise StaleRuntimeGenerationError("runtime registration state is stale")
            self._assert_runtime_operation_locked(cursor, row)
            cursor.execute(
                """
                UPDATE agent_runtime_instance
                SET registered_at = clock_timestamp(), state_revision = state_revision + 1
                WHERE runtime_instance_id = %s AND process_id = %s
                  AND state = 'starting' AND registered_at IS NULL
                  AND state_revision = %s
                RETURNING *
                """,
                (
                    fence.runtime_instance_id,
                    fence.process_id,
                    row["state_revision"],
                ),
            )
            updated = cursor.fetchone()
            if updated is None:
                raise StaleRuntimeGenerationError("runtime registration CAS is stale")
        return self._runtime_from_row(updated)

    def record_runtime_heartbeat(
        self,
        fence: RuntimeFence,
        *,
        heartbeat_sequence: int,
    ) -> RuntimeInstanceRecord:
        """Advance durable liveness only for a strictly larger sequence."""

        fence.validate(allow_prelaunch=False)
        if (
            type(heartbeat_sequence) is not int
            or heartbeat_sequence <= 0
            or heartbeat_sequence > _MAX_GENERATION
        ):
            raise ValueError("heartbeat_sequence must be a positive BIGINT")
        with self._transaction() as cursor:
            row = self._locked_runtime(
                cursor,
                fence,
                allow_prelaunch=False,
                require_current_host=True,
            )
            if row["registered_at"] is None or row["state"] not in {
                "starting",
                "ready",
                "online",
                "updating",
            }:
                raise StaleRuntimeGenerationError(
                    "heartbeat arrived before accepted registration"
                )
            current_sequence = row["last_heartbeat_sequence"]
            if current_sequence is not None and heartbeat_sequence <= int(
                current_sequence
            ):
                return self._runtime_from_row(row)
            cursor.execute(
                """
                UPDATE agent_runtime_instance
                SET last_heartbeat_sequence = %s,
                    last_liveness_at = clock_timestamp()
                WHERE runtime_instance_id = %s AND process_id = %s
                  AND registered_at IS NOT NULL
                  AND state IN ('starting', 'ready', 'online', 'updating')
                  AND (last_heartbeat_sequence IS NULL
                       OR last_heartbeat_sequence < %s)
                RETURNING *
                """,
                (
                    heartbeat_sequence,
                    fence.runtime_instance_id,
                    fence.process_id,
                    heartbeat_sequence,
                ),
            )
            updated = cursor.fetchone()
            if updated is None:
                raise StaleRuntimeGenerationError("heartbeat CAS is stale")
        return self._runtime_from_row(updated)

    def mark_runtime_ready(self, fence: RuntimeFence) -> RuntimeInstanceRecord:
        """Accept ready only after durable registration and liveness proof."""

        fence.validate(allow_prelaunch=False)
        with self._transaction() as cursor:
            row = self._locked_runtime(
                cursor,
                fence,
                allow_prelaunch=False,
                require_current_host=True,
            )
            if row["state"] == "ready":
                return self._runtime_from_row(row)
            if not (
                row["state"] == "starting"
                and row["registered_at"] is not None
                and row["last_heartbeat_sequence"] is not None
                and row["last_liveness_at"] is not None
            ):
                raise StaleRuntimeGenerationError(
                    "runtime is not registered and live"
                )
            self._assert_runtime_operation_locked(cursor, row)
            cursor.execute(
                """
                UPDATE agent_runtime_instance
                SET state = 'ready', ready_at = clock_timestamp(),
                    state_revision = state_revision + 1
                WHERE runtime_instance_id = %s AND process_id = %s
                  AND state = 'starting' AND state_revision = %s
                  AND registered_at IS NOT NULL
                  AND last_heartbeat_sequence IS NOT NULL
                  AND last_liveness_at IS NOT NULL
                RETURNING *
                """,
                (
                    fence.runtime_instance_id,
                    fence.process_id,
                    row["state_revision"],
                ),
            )
            updated = cursor.fetchone()
            if updated is None:
                raise StaleRuntimeGenerationError("ready CAS is stale")
        return self._runtime_from_row(updated)

    def promote_recovered_runtime(
        self, fence: RuntimeFence
    ) -> RuntimeInstanceRecord:
        """Atomically restore authority for a retained already-active revision.

        Inventory recovery creates a fresh fenced runtime for the immutable
        revision already named by ``active_revision_id``.  Once that child has
        registered, proved liveness, and reached ready, this transition installs
        only the new runtime/lifecycle authority.  It deliberately does not
        mutate revision state or the last-known-good revision pointer.
        """

        fence.validate(allow_prelaunch=False)
        with self._transaction() as cursor:
            row = self._locked_runtime(
                cursor,
                fence,
                allow_prelaunch=False,
                require_current_host=True,
            )
            already_authoritative = (
                row["state"] == "online"
                and bool(row["is_authoritative"])
                and str(row["authoritative_instance_id"])
                == fence.runtime_instance_id
                and int(row["agent_lifecycle_generation"])
                == fence.lifecycle_generation
            )
            if already_authoritative:
                # New promotions settle atomically below. Repair a runtime
                # promoted by an older build only when its exact delivery
                # operation is still current; an already-terminal operation is
                # the normal idempotent replay path.
                try:
                    replay_operation = self._assert_runtime_operation_locked(
                        cursor, row
                    )
                except StaleRuntimeGenerationError:
                    return self._runtime_from_row(row)
                self._operations.terminalize(
                    replay_operation,
                    state=OperationState.COMPLETED,
                    terminal_code=None,
                    safe_summary=None,
                    retry_after_ms=None,
                    now=None,
                    retention=self._operation_retention,
                    transaction=cursor,
                )
                return self._runtime_from_row(row)
            if not (
                row["state"] == "ready"
                and not bool(row["is_authoritative"])
                and row["registered_at"] is not None
                and row["last_heartbeat_sequence"] is not None
                and row["last_liveness_at"] is not None
                and row["ready_at"] is not None
                and row["host_state"] == "connected"
                and row["host_inventory_state"] == "reconciled"
                and str(row["selected_host_session_id"])
                == fence.host_session_id
                and str(row["active_revision_id"]) == fence.revision_id
                and row["revision_state"] == "active"
                and row["revision_compatibility_state"] == "compatible"
                and int(row["agent_generation_counter"])
                == fence.lifecycle_generation
                and int(row["lifecycle_generation"])
                == fence.lifecycle_generation
                and row["authoritative_instance_id"] is None
            ):
                raise StaleRuntimeGenerationError(
                    "recovered runtime promotion fence is stale"
                )
            operation_fence = self._assert_runtime_operation_locked(cursor, row)
            cursor.execute(
                """
                UPDATE agent_runtime_instance
                SET state = 'online', is_authoritative = TRUE,
                    state_revision = state_revision + 1
                WHERE runtime_instance_id = %s AND process_id = %s
                  AND revision_id = %s AND lifecycle_generation = %s
                  AND state = 'ready' AND is_authoritative = FALSE
                  AND state_revision = %s
                RETURNING *
                """,
                (
                    fence.runtime_instance_id,
                    fence.process_id,
                    fence.revision_id,
                    fence.lifecycle_generation,
                    row["state_revision"],
                ),
            )
            promoted = cursor.fetchone()
            if promoted is None:
                raise StaleRuntimeGenerationError(
                    "recovered runtime promotion CAS is stale"
                )
            cursor.execute(
                """
                UPDATE user_agent
                SET authoritative_instance_id = %s,
                    lifecycle_generation = %s,
                    status = 'live', state_revision = state_revision + 1,
                    updated_at = (extract(epoch from clock_timestamp()) * 1000)::bigint
                WHERE agent_id = %s AND owner_user_id = %s
                  AND selected_host_session_id = %s
                  AND active_revision_id = %s
                  AND authoritative_instance_id IS NULL
                  AND generation_counter = %s
                  AND state_revision = %s
                  AND deleted_at IS NULL
                """,
                (
                    fence.runtime_instance_id,
                    fence.lifecycle_generation,
                    fence.agent_id,
                    row["owner_user_id"],
                    fence.host_session_id,
                    fence.revision_id,
                    fence.lifecycle_generation,
                    row["agent_state_revision"],
                ),
            )
            if cursor.rowcount != 1:
                raise StaleRuntimeGenerationError(
                    "recovered agent authority CAS is stale"
                )
            self._operations.terminalize(
                operation_fence,
                state=OperationState.COMPLETED,
                terminal_code=None,
                safe_summary=None,
                retry_after_ms=None,
                now=None,
                retention=self._operation_retention,
                transaction=cursor,
            )
        return self._runtime_from_row(promoted)

    def get_runtime_instance(self, runtime_instance_id: str) -> RuntimeInstanceRecord:
        runtime_instance_id = _uuid4_text(
            runtime_instance_id, "runtime_instance_id"
        )
        with self._transaction() as cursor:
            cursor.execute(
                "SELECT * FROM agent_runtime_instance WHERE runtime_instance_id = %s",
                (runtime_instance_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise PersonalAgentNotFoundError("runtime instance not found")
            return self._runtime_from_row(row)

    def list_latest_runtime_instances(
        self, *, owner_user_id: str
    ) -> tuple[RuntimeInstanceRecord, ...]:
        """Return the newest durable runtime generation for each live agent.

        This is the reconnect/hydration source for ``agent_lifecycle``.  Socket
        maps are intentionally excluded: a client that was absent for a child
        exit or host loss must still receive the committed terminal state.
        """

        owner_user_id = _required_text(owner_user_id, "owner_user_id")
        with self._transaction() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT ON (runtime.agent_id) runtime.*,
                       agent.active_revision_id,
                       agent.authoritative_instance_id
                FROM agent_runtime_instance AS runtime
                JOIN user_agent AS agent
                  ON agent.agent_id = runtime.agent_id
                 AND agent.owner_user_id = runtime.owner_user_id
                WHERE runtime.owner_user_id = %s
                  AND agent.deleted_at IS NULL
                ORDER BY runtime.agent_id,
                         runtime.lifecycle_generation DESC,
                         runtime.state_revision DESC
                """,
                (owner_user_id,),
            )
            return tuple(self._runtime_from_row(row) for row in cursor.fetchall())

    def get_current_online_authority(
        self, *, owner_user_id: str, agent_id: str
    ) -> RuntimeInstanceRecord:
        """Resolve the one exact routable runtime from durable pointers.

        Every owner, selected-session, active-revision, lifecycle, compatibility,
        and online-authority relation is checked in the same transaction.  The
        later request assignment repeats these checks under row locks before a
        frame is sent; this lookup never turns a process-local cache into an
        authority.
        """

        owner_user_id = _required_text(owner_user_id, "owner_user_id")
        agent_id = _required_text(agent_id, "agent_id", maximum=255)
        with self._transaction() as cursor:
            self._lock_owner(cursor, owner_user_id)
            cursor.execute(
                """
                SELECT authoritative_instance_id
                FROM user_agent
                WHERE agent_id = %s AND owner_user_id = %s
                  AND deleted_at IS NULL
                FOR SHARE
                """,
                (agent_id, owner_user_id),
            )
            agent = cursor.fetchone()
            if agent is None or agent["authoritative_instance_id"] is None:
                raise AgentOfflineError("personal agent has no online authority")
            runtime_instance_id = str(agent["authoritative_instance_id"])
            cursor.execute(self._runtime_join_sql(lock=False), (runtime_instance_id,))
            row = cursor.fetchone()
            if not (
                row is not None
                and str(row["agent_id"]) == agent_id
                and str(row["owner_user_id"]) == owner_user_id
                and row["agent_deleted_at"] is None
                and row["process_id"] is not None
                and row["state"] == "online"
                and bool(row["is_authoritative"])
                and str(row["authoritative_instance_id"])
                == runtime_instance_id
                and str(row["selected_host_session_id"])
                == str(row["host_session_id"])
                and str(row["active_revision_id"]) == str(row["revision_id"])
                and int(row["lifecycle_generation"])
                == int(row["agent_lifecycle_generation"])
                and str(row["host_owner_user_id"]) == owner_user_id
                and str(row["session_host_id"]) == str(row["host_id"])
                and row["host_state"] == "connected"
                and row["host_inventory_state"] == "reconciled"
                and int(row["host_runtime_contract_version"])
                == self._policy.runtime_contract_version
                and row["host_release_lock_digest"]
                == self._policy.runtime_lock_sha256
                and row["revision_state"] == "active"
                and row["revision_compatibility_state"] == "compatible"
                and int(row["revision_runtime_contract_version"])
                == self._policy.runtime_contract_version
                and row["revision_lock_digest"]
                == self._policy.runtime_lock_sha256
            ):
                raise AgentOfflineError("personal agent has no exact online authority")
            return self._runtime_from_row(row)

    @staticmethod
    def _request_join_sql(*, lock: bool) -> str:
        suffix = " FOR UPDATE OF rr, ri, ua" if lock else ""
        return (
            "SELECT ri.*, rr.request_id, rr.request_generation, "
            "rr.operation_id AS request_operation_id, "
            "rr.operation_execution_generation "
            "AS request_operation_execution_generation, "
            "rr.state AS request_state, rr.state_revision AS request_state_revision, "
            "rr.assigned_at, rr.terminal_at AS request_terminal_at, "
            "rr.terminal_code, rr.result_digest, "
            "op.execution_lease_token AS operation_execution_lease_token, "
            "ua.selected_host_session_id, ua.authoritative_instance_id, "
            "ua.active_revision_id, ua.lifecycle_generation AS agent_lifecycle_generation, "
            "ua.deleted_at AS agent_deleted_at "
            "FROM agent_runtime_request rr "
            "JOIN agent_runtime_instance ri "
            "  ON ri.runtime_instance_id = rr.runtime_instance_id "
            " AND ri.agent_id = rr.agent_id AND ri.owner_user_id = rr.owner_user_id "
            "JOIN user_agent ua ON ua.agent_id = ri.agent_id "
            " AND ua.owner_user_id = ri.owner_user_id "
            "LEFT JOIN operation_record op ON op.operation_id = rr.operation_id "
            "WHERE rr.request_id = %s" + suffix
        )

    @staticmethod
    def _request_fence_matches(
        row: Mapping[str, Any], fence: RuntimeRequestFence
    ) -> bool:
        return (
            PersonalAgentRuntimeRepository._runtime_fence_matches(
                row, fence.runtime, allow_prelaunch=False
            )
            and str(row["request_id"]) == fence.request_id
            and str(row["request_generation"]) == fence.request_generation
            and str(row["request_operation_id"]) == fence.operation_id
            and int(row["request_operation_execution_generation"])
            == fence.operation_execution_generation
        )

    def assign_request(
        self,
        runtime_fence: RuntimeFence,
        *,
        operation_fence: ExecutionFence,
        request_generation: Optional[str] = None,
    ) -> RuntimeRequestRecord:
        """Persist a call against the exact current online authority before send."""

        runtime_fence.validate(allow_prelaunch=False)
        if not isinstance(operation_fence, ExecutionFence):
            raise TypeError("operation_fence must be ExecutionFence")
        request_id = self._new_uuid("request_id")
        request_generation = (
            self._new_uuid("request_generation")
            if request_generation is None
            else _uuid4_text(request_generation, "request_generation")
        )
        with self._transaction() as cursor:
            row = self._locked_runtime(
                cursor,
                runtime_fence,
                allow_prelaunch=False,
                require_current_host=True,
            )
            if not (
                row["state"] == "online"
                and bool(row["is_authoritative"])
                and str(row["authoritative_instance_id"])
                == runtime_fence.runtime_instance_id
                and str(row["active_revision_id"]) == runtime_fence.revision_id
                and int(row["lifecycle_generation"])
                == runtime_fence.lifecycle_generation
                and row["registered_at"] is not None
                and row["last_heartbeat_sequence"] is not None
                and row["last_liveness_at"] is not None
            ):
                raise AgentOfflineError("agent_offline")
            operation = self._assert_operation_locked(
                cursor,
                operation_fence,
                owner_user_id=str(row["owner_user_id"]),
            )
            if operation.request_generation not in {
                None,
                uuid.UUID(request_generation),
            }:
                raise StaleRuntimeGenerationError(
                    "operation request generation is stale"
                )
            if operation.request_generation is None:
                cursor.execute(
                    """
                    UPDATE operation_record SET request_generation = %s
                    WHERE operation_id = %s AND state = 'running'
                      AND execution_generation = %s AND execution_lease_token = %s
                      AND request_generation IS NULL
                    """,
                    (
                        request_generation,
                        str(operation_fence.operation_id),
                        operation_fence.execution_generation,
                        str(operation_fence.execution_lease_token),
                    ),
                )
                if cursor.rowcount != 1:
                    raise StaleRuntimeGenerationError(
                        "operation request generation CAS is stale"
                    )
            cursor.execute(
                """
                INSERT INTO agent_runtime_request (
                    request_id, request_generation, operation_id,
                    operation_execution_generation, runtime_instance_id,
                    agent_id, owner_user_id, state
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'assigned')
                RETURNING *
                """,
                (
                    request_id,
                    request_generation,
                    str(operation_fence.operation_id),
                    operation_fence.execution_generation,
                    runtime_fence.runtime_instance_id,
                    runtime_fence.agent_id,
                    row["owner_user_id"],
                ),
            )
            cursor.fetchone()
            cursor.execute(self._request_join_sql(lock=False), (request_id,))
            assigned = cursor.fetchone()
        return self._request_from_row(assigned)

    def get_runtime_request(self, request_id: str) -> RuntimeRequestRecord:
        request_id = _uuid4_text(request_id, "request_id")
        with self._transaction() as cursor:
            cursor.execute(self._request_join_sql(lock=False), (request_id,))
            row = cursor.fetchone()
            if row is None:
                raise PersonalAgentNotFoundError("runtime request not found")
            return self._request_from_row(row)

    def settle_request(
        self,
        fence: RuntimeRequestFence,
        *,
        state: str,
        terminal_code: Optional[str] = None,
        result_digest: Optional[str] = None,
    ) -> RuntimeRequestRecord:
        """Settle one result and its operation atomically under the full fence."""

        if state not in _REQUEST_TERMINAL_STATES:
            raise ValueError("request terminal state is invalid")
        _uuid4_text(fence.request_id, "request_id")
        _uuid4_text(fence.request_generation, "request_generation")
        _uuid4_text(fence.operation_id, "operation_id")
        fence.runtime.validate(allow_prelaunch=False)
        if state == "completed":
            if terminal_code is not None:
                raise ValueError("completed requests cannot have a terminal code")
            if result_digest is not None:
                result_digest = _sha256(result_digest, "result_digest")
        else:
            terminal_code = _safe_code(terminal_code, "terminal_code")
            if result_digest is not None:
                raise ValueError("non-completed requests cannot have a result digest")
        with self._transaction() as cursor:
            self._lock_request_owner(cursor, fence.request_id)
            cursor.execute(self._request_join_sql(lock=True), (fence.request_id,))
            row = cursor.fetchone()
            if row is None or not self._request_fence_matches(row, fence):
                raise StaleRuntimeGenerationError("request fence is stale")
            if row["request_state"] in _REQUEST_TERMINAL_STATES:
                if (
                    row["request_state"] == state
                    and row["terminal_code"] == terminal_code
                    and row["result_digest"] == result_digest
                ):
                    return self._request_from_row(row)
                raise StaleRuntimeGenerationError("request is already terminal")
            if row["agent_deleted_at"] is not None:
                raise AgentDeletedError("agent_deleted")
            if not (
                row["state"] == "online"
                and bool(row["is_authoritative"])
                and str(row["authoritative_instance_id"])
                == fence.runtime.runtime_instance_id
                and str(row["selected_host_session_id"])
                == fence.runtime.host_session_id
                and str(row["active_revision_id"]) == fence.runtime.revision_id
                and int(row["agent_lifecycle_generation"])
                == fence.runtime.lifecycle_generation
            ):
                raise StaleRuntimeGenerationError("request runtime authority is stale")
            if fence.operation_execution_lease_token is None:
                raise StaleRuntimeGenerationError("operation lease fence is absent")
            operation_fence = ExecutionFence(
                operation_id=uuid.UUID(fence.operation_id),
                execution_generation=fence.operation_execution_generation,
                execution_lease_token=uuid.UUID(
                    fence.operation_execution_lease_token
                ),
            )
            self._assert_operation_locked(
                cursor,
                operation_fence,
                owner_user_id=str(row["owner_user_id"]),
            )
            cursor.execute(
                "SELECT request_generation FROM operation_record "
                "WHERE operation_id = %s",
                (fence.operation_id,),
            )
            operation_generation = cursor.fetchone()
            if (
                operation_generation is None
                or _optional_uuid_text(operation_generation["request_generation"])
                != fence.request_generation
            ):
                raise StaleRuntimeGenerationError(
                    "operation request generation is stale"
                )
            cursor.execute(
                """
                UPDATE agent_runtime_request
                SET state = %s, terminal_at = clock_timestamp(),
                    terminal_code = %s, result_digest = %s,
                    state_revision = state_revision + 1
                WHERE request_id = %s AND request_generation = %s
                  AND runtime_instance_id = %s
                  AND operation_execution_generation = %s
                  AND state IN ('assigned', 'running')
                """,
                (
                    state,
                    terminal_code,
                    result_digest,
                    fence.request_id,
                    fence.request_generation,
                    fence.runtime.runtime_instance_id,
                    fence.operation_execution_generation,
                ),
            )
            if cursor.rowcount != 1:
                raise StaleRuntimeGenerationError("request settlement CAS is stale")
            operation_state = {
                "completed": OperationState.COMPLETED,
                "failed": OperationState.FAILED,
                "cancelled": OperationState.CANCELLED,
                "retryable": OperationState.RETRYABLE,
            }[state]
            self._operations.terminalize(
                operation_fence,
                state=operation_state,
                terminal_code=terminal_code,
                safe_summary=None,
                retry_after_ms=(0 if state == "retryable" else None),
                now=None,
                retention=self._operation_retention,
                transaction=cursor,
            )
            cursor.execute(self._request_join_sql(lock=False), (fence.request_id,))
            settled = cursor.fetchone()
        return self._request_from_row(settled)

    def _terminalize_request_operations_locked(
        self,
        cursor: Any,
        request_rows: Sequence[Mapping[str, Any]],
        *,
        failure_code: str,
    ) -> None:
        for request in request_rows:
            operation_id = request["operation_id"]
            if operation_id is None:
                continue
            cursor.execute(
                """
                SELECT operation_id, owner_user_id, request_generation, state,
                       execution_generation, execution_lease_token
                FROM operation_record WHERE operation_id = %s
                FOR UPDATE
                """,
                (operation_id,),
            )
            operation = cursor.fetchone()
            if not (
                operation is not None
                and operation["state"] == "running"
                and operation["execution_lease_token"] is not None
                and operation["owner_user_id"] == request["owner_user_id"]
                and _optional_uuid_text(operation["request_generation"])
                == str(request["request_generation"])
                and int(operation["execution_generation"])
                == int(request["operation_execution_generation"])
            ):
                continue
            operation_fence = ExecutionFence(
                operation_id=uuid.UUID(str(operation["operation_id"])),
                execution_generation=int(operation["execution_generation"]),
                execution_lease_token=uuid.UUID(
                    str(operation["execution_lease_token"])
                ),
            )
            self._operations.terminalize(
                operation_fence,
                state=OperationState.RETRYABLE,
                terminal_code=failure_code,
                safe_summary=None,
                retry_after_ms=0,
                now=None,
                retention=self._operation_retention,
                transaction=cursor,
            )

    def _terminalize_runtime_operation_locked(
        self,
        cursor: Any,
        row: Mapping[str, Any],
        *,
        failure_code: str,
    ) -> None:
        operation_id = row["operation_id"]
        if operation_id is None:
            return
        cursor.execute(
            """
            SELECT operation_id, owner_user_id, state, execution_generation,
                   execution_lease_token
            FROM operation_record WHERE operation_id = %s
            FOR UPDATE
            """,
            (operation_id,),
        )
        operation = cursor.fetchone()
        if not (
            operation is not None
            and operation["state"] == "running"
            and operation["execution_lease_token"] is not None
            and operation["owner_user_id"] == row["owner_user_id"]
            and int(operation["execution_generation"])
            == int(row["operation_execution_generation"])
        ):
            return
        operation_fence = ExecutionFence(
            operation_id=uuid.UUID(str(operation["operation_id"])),
            execution_generation=int(operation["execution_generation"]),
            execution_lease_token=uuid.UUID(
                str(operation["execution_lease_token"])
            ),
        )
        self._operations.terminalize(
            operation_fence,
            state=OperationState.RETRYABLE,
            terminal_code=failure_code,
            safe_summary=None,
            retry_after_ms=0,
            now=None,
            retention=self._operation_retention,
            transaction=cursor,
        )

    def _terminalize_instance_row_locked(
        self,
        cursor: Any,
        row: Mapping[str, Any],
        *,
        failure_code: str,
    ) -> RuntimeSettlement:
        runtime_id = str(row["runtime_instance_id"])
        if row["state"] in _RUNTIME_TERMINAL_STATES:
            return RuntimeSettlement(
                instance=self._runtime_from_row(row), settled_request_ids=()
            )
        self._terminalize_runtime_operation_locked(
            cursor, row, failure_code=failure_code
        )
        cursor.execute(
            """
            SELECT * FROM agent_runtime_request
            WHERE runtime_instance_id = %s AND state IN ('assigned', 'running')
            ORDER BY assigned_at, request_id
            FOR UPDATE
            """,
            (runtime_id,),
        )
        request_rows = list(cursor.fetchall())
        self._terminalize_request_operations_locked(
            cursor, request_rows, failure_code=failure_code
        )
        if request_rows:
            cursor.execute(
                """
                UPDATE agent_runtime_request
                SET state = 'retryable', terminal_at = clock_timestamp(),
                    terminal_code = %s, result_digest = NULL,
                    state_revision = state_revision + 1
                WHERE runtime_instance_id = %s AND state IN ('assigned', 'running')
                """,
                (failure_code, runtime_id),
            )
        terminal_state = "failed" if row["process_id"] is None else "offline"
        cursor.execute(
            """
            UPDATE agent_runtime_instance
            SET state = %s, is_authoritative = FALSE,
                terminal_at = clock_timestamp(), failure_code = %s,
                state_revision = state_revision + 1
            WHERE runtime_instance_id = %s
              AND state NOT IN ('stopped', 'failed', 'offline', 'superseded')
            RETURNING *
            """,
            (terminal_state, failure_code, runtime_id),
        )
        terminal = cursor.fetchone()
        if terminal is None:
            raise StaleRuntimeGenerationError("runtime terminalization CAS is stale")
        cursor.execute(
            """
            UPDATE user_agent
            SET authoritative_instance_id = NULL,
                state_revision = state_revision + 1,
                updated_at = (extract(epoch from clock_timestamp()) * 1000)::bigint
            WHERE agent_id = %s AND owner_user_id = %s
              AND authoritative_instance_id = %s
            """,
            (row["agent_id"], row["owner_user_id"], runtime_id),
        )
        return RuntimeSettlement(
            instance=self._runtime_from_row(terminal),
            settled_request_ids=tuple(str(item["request_id"]) for item in request_rows),
        )

    def terminalize_runtime(
        self, fence: RuntimeFence, *, failure_code: str
    ) -> RuntimeSettlement:
        """Atomically fence one known failed instance and all assigned calls."""

        fence.validate(allow_prelaunch=fence.process_id is None)
        failure_code = _safe_code(failure_code)
        with self._transaction() as cursor:
            self._lock_runtime_owner(cursor, fence.runtime_instance_id)
            cursor.execute(
                self._runtime_join_sql(lock=True), (fence.runtime_instance_id,)
            )
            row = cursor.fetchone()
            if row is None or not self._runtime_fence_matches(
                row, fence, allow_prelaunch=fence.process_id is None
            ):
                raise StaleRuntimeGenerationError("runtime failure fence is stale")
            if row["state"] in _RUNTIME_TERMINAL_STATES:
                if row["failure_code"] == failure_code:
                    return RuntimeSettlement(
                        instance=self._runtime_from_row(row),
                        settled_request_ids=(),
                    )
                raise StaleRuntimeGenerationError("runtime is already terminal")
            if row["agent_deleted_at"] is not None:
                raise AgentDeletedError("agent_deleted")
            if not (
                str(row["host_owner_user_id"]) == str(row["owner_user_id"])
                and str(row["session_host_id"]) == str(row["host_id"])
            ):
                raise StaleRuntimeGenerationError("runtime host binding is stale")
            return self._terminalize_instance_row_locked(
                cursor, row, failure_code=failure_code
            )

    def terminalize_expired_startup(
        self,
        fence: RuntimeFence,
        *,
        timeout_seconds: float,
    ) -> RuntimeSettlement:
        """Atomically fail one still-starting runtime after its DB-time deadline.

        This covers both a pre-launch ``delivering`` recovery that never binds a
        process and a bound ``starting`` child that never becomes ready. The
        state/deadline recheck and runtime/delivery-operation settlement share
        one transaction, so a concurrent ready transition wins cleanly instead
        of being killed from a stale process-local timer.
        """

        fence.validate(allow_prelaunch=fence.process_id is None)
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 < float(timeout_seconds) <= 300
        ):
            raise ValueError("timeout_seconds must be in (0, 300]")
        with self._transaction() as cursor:
            self._lock_runtime_owner(cursor, fence.runtime_instance_id)
            cursor.execute(
                self._runtime_join_sql(lock=True), (fence.runtime_instance_id,)
            )
            row = cursor.fetchone()
            if row is None or not self._runtime_fence_matches(
                row, fence, allow_prelaunch=fence.process_id is None
            ):
                raise StaleRuntimeGenerationError("runtime startup fence is stale")
            if row["state"] in _RUNTIME_TERMINAL_STATES:
                if row["failure_code"] == "child_registration_timeout":
                    return RuntimeSettlement(
                        instance=self._runtime_from_row(row),
                        settled_request_ids=(),
                    )
                raise StaleRuntimeGenerationError("runtime is already terminal")
            if row["agent_deleted_at"] is not None:
                raise AgentDeletedError("agent_deleted")
            if row["state"] not in {"delivering", "starting"}:
                raise StaleRuntimeGenerationError(
                    "runtime is no longer awaiting startup"
                )
            cursor.execute(
                """
                SELECT clock_timestamp() >=
                    (COALESCE(%s, %s) + make_interval(secs => %s))
                    AS expired
                """,
                (
                    row["started_at"],
                    row["created_at"],
                    float(timeout_seconds),
                ),
            )
            if not bool(cursor.fetchone()["expired"]):
                raise StaleRuntimeGenerationError(
                    "runtime startup deadline has not elapsed"
                )
            return self._terminalize_instance_row_locked(
                cursor,
                row,
                failure_code="child_registration_timeout",
            )

    def terminalize_expired_liveness(
        self,
        fence: RuntimeFence,
        *,
        timeout_seconds: float = 5.0,
    ) -> RuntimeSettlement:
        """Atomically apply the DB-receipt-time child-hang boundary."""

        fence.validate(allow_prelaunch=False)
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0 < float(timeout_seconds) <= 60
        ):
            raise ValueError("timeout_seconds must be in (0, 60]")
        with self._transaction() as cursor:
            self._lock_runtime_owner(cursor, fence.runtime_instance_id)
            cursor.execute(
                self._runtime_join_sql(lock=True), (fence.runtime_instance_id,)
            )
            row = cursor.fetchone()
            if row is None or not self._runtime_fence_matches(
                row, fence, allow_prelaunch=False
            ):
                raise StaleRuntimeGenerationError("runtime liveness fence is stale")
            if row["state"] in _RUNTIME_TERMINAL_STATES:
                if row["failure_code"] == "child_hung":
                    return RuntimeSettlement(
                        instance=self._runtime_from_row(row),
                        settled_request_ids=(),
                    )
                raise StaleRuntimeGenerationError("runtime is already terminal")
            if row["agent_deleted_at"] is not None:
                raise AgentDeletedError("agent_deleted")
            if row["state"] not in {"ready", "online", "updating"} or row[
                "last_liveness_at"
            ] is None:
                raise StaleRuntimeGenerationError(
                    "runtime has no live heartbeat authority"
                )
            cursor.execute(
                """
                SELECT clock_timestamp() >=
                    (%s + make_interval(secs => %s)) AS expired
                """,
                (row["last_liveness_at"], float(timeout_seconds)),
            )
            if not bool(cursor.fetchone()["expired"]):
                raise StaleRuntimeGenerationError(
                    "runtime liveness deadline has not elapsed"
                )
            return self._terminalize_instance_row_locked(
                cursor,
                row,
                failure_code="child_hung",
            )

    def _terminalize_session_instances_locked(
        self,
        cursor: Any,
        *,
        owner_user_id: str,
        host_session_ids: Sequence[str],
        failure_code: str,
    ) -> tuple[RuntimeSettlement, ...]:
        if not host_session_ids:
            return ()
        cursor.execute(
            """
            SELECT ri.* FROM agent_runtime_instance ri
            WHERE ri.owner_user_id = %s
              AND ri.host_session_id = ANY(%s::uuid[])
              AND ri.state NOT IN ('stopped', 'failed', 'offline', 'superseded')
            ORDER BY ri.agent_id, ri.runtime_instance_id
            FOR UPDATE
            """,
            (owner_user_id, list(host_session_ids)),
        )
        rows = list(cursor.fetchall())
        settlements: list[RuntimeSettlement] = []
        for row in rows:
            result = self._terminalize_instance_row_locked(
                cursor, row, failure_code=failure_code
            )
            settlements.append(result)
        return tuple(settlements)

    def disconnect_host_session(
        self,
        fence: HostSessionFence,
        *,
        failure_code: str = "host_lost",
    ) -> HostDisconnectResult:
        """Persist host loss, settle its exact calls, then select standbys."""

        failure_code = _safe_code(failure_code)
        with self._transaction() as cursor:
            self._lock_owner(cursor, fence.owner_user_id)
            host = self._locked_host_session(cursor, fence)
            if host["state"] == "connected":
                cursor.execute(
                    """
                    UPDATE agent_host_session
                    SET state = 'disconnected', disconnected_at = clock_timestamp(),
                        last_seen_at = clock_timestamp(), failure_code = %s
                    WHERE host_session_id = %s AND state = 'connected'
                    """,
                    (failure_code, fence.host_session_id),
                )
                if cursor.rowcount != 1:
                    raise StaleRuntimeGenerationError(
                        "host disconnect CAS is stale"
                    )
            elif host["state"] != "disconnected":
                raise StaleRuntimeGenerationError("host session is incompatible")
            settlements = self._terminalize_session_instances_locked(
                cursor,
                owner_user_id=fence.owner_user_id,
                host_session_ids=(fence.host_session_id,),
                failure_code=failure_code,
            )
            cursor.execute(
                """
                SELECT * FROM user_agent
                WHERE owner_user_id = %s AND selected_host_session_id = %s
                ORDER BY agent_id
                FOR UPDATE
                """,
                (fence.owner_user_id, fence.host_session_id),
            )
            selections: dict[str, Optional[str]] = {}
            for agent_row in cursor.fetchall():
                if agent_row["deleted_at"] is not None:
                    continue
                selection = self._select_host_locked(cursor, agent_row)
                selections[str(agent_row["agent_id"])] = (
                    None
                    if selection.session is None
                    else selection.session.host_session_id
                )
        return HostDisconnectResult(
            settled_request_ids=tuple(
                request_id
                for settlement in settlements
                for request_id in settlement.settled_request_ids
            ),
            settlements=settlements,
            selected_sessions=MappingProxyType(selections),
        )

    def tombstone_agent(
        self,
        *,
        owner_user_id: str,
        agent_id: str,
        expected_state_revision: Optional[int] = None,
    ) -> AgentTombstone:
        """Commit the deletion generation and clear pointers before cleanup."""

        owner_user_id = _required_text(owner_user_id, "owner_user_id")
        agent_id = _required_text(agent_id, "agent_id", maximum=255)
        if expected_state_revision is not None and (
            type(expected_state_revision) is not int or expected_state_revision < 0
        ):
            raise ValueError("expected_state_revision must be non-negative")
        with self._transaction() as cursor:
            self._lock_owner(cursor, owner_user_id)
            cursor.execute(
                """
                SELECT * FROM user_agent
                WHERE agent_id = %s AND owner_user_id = %s
                FOR UPDATE
                """,
                (agent_id, owner_user_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise PersonalAgentNotFoundError("personal agent not found")
            if row["deleted_at"] is not None:
                return AgentTombstone(
                    agent_id=agent_id,
                    owner_user_id=owner_user_id,
                    lifecycle_generation=int(row["lifecycle_generation"]),
                    state_revision=int(row["state_revision"]),
                    deleted_at=int(row["deleted_at"]),
                )
            if (
                expected_state_revision is not None
                and int(row["state_revision"]) != expected_state_revision
            ):
                raise StaleRuntimeGenerationError("agent tombstone revision is stale")
            generation = max(
                int(row["generation_counter"]), int(row["lifecycle_generation"])
            ) + 1
            if generation > _MAX_GENERATION:
                raise PersonalAgentRuntimeError("agent lifecycle generation exhausted")
            cursor.execute(
                """
                UPDATE user_agent
                SET status = 'disabled',
                    deleted_at = (extract(epoch from clock_timestamp()) * 1000)::bigint,
                    updated_at = (extract(epoch from clock_timestamp()) * 1000)::bigint,
                    generation_counter = %s, lifecycle_generation = %s,
                    state_revision = state_revision + 1,
                    active_revision_id = NULL,
                    selected_host_session_id = NULL,
                    authoritative_instance_id = NULL,
                    host_client_id = NULL, host_session_id = NULL,
                    host_last_seen_at = NULL
                WHERE agent_id = %s AND owner_user_id = %s
                  AND state_revision = %s AND deleted_at IS NULL
                RETURNING lifecycle_generation, state_revision, deleted_at
                """,
                (
                    generation,
                    generation,
                    agent_id,
                    owner_user_id,
                    row["state_revision"],
                ),
            )
            updated = cursor.fetchone()
            if updated is None:
                raise StaleRuntimeGenerationError("agent tombstone CAS is stale")
            return AgentTombstone(
                agent_id=agent_id,
                owner_user_id=owner_user_id,
                lifecycle_generation=int(updated["lifecycle_generation"]),
                state_revision=int(updated["state_revision"]),
                deleted_at=int(updated["deleted_at"]),
            )

    def cleanup_tombstoned_agent(
        self, tombstone: AgentTombstone
    ) -> AgentTombstoneCleanup:
        """Settle every older runtime only after the exact tombstone committed.

        The tombstone generation/state revision/deletion timestamp and cleared
        pointers are rechecked before touching runtimes. This preserves the
        required delete-first ordering while avoiding ``_locked_runtime``'s
        intentional rejection of frames arriving after deletion.
        """

        if not isinstance(tombstone, AgentTombstone):
            raise TypeError("tombstone must be an AgentTombstone")
        owner_user_id = _required_text(
            tombstone.owner_user_id, "owner_user_id"
        )
        agent_id = _required_text(tombstone.agent_id, "agent_id", maximum=255)
        if (
            type(tombstone.lifecycle_generation) is not int
            or tombstone.lifecycle_generation <= 0
            or type(tombstone.state_revision) is not int
            or tombstone.state_revision <= 0
            or type(tombstone.deleted_at) is not int
            or tombstone.deleted_at <= 0
        ):
            raise ValueError("tombstone generations and timestamp must be positive")
        with self._transaction() as cursor:
            self._lock_owner(cursor, owner_user_id)
            cursor.execute(
                """
                SELECT * FROM user_agent
                WHERE agent_id = %s AND owner_user_id = %s
                FOR UPDATE
                """,
                (agent_id, owner_user_id),
            )
            agent = cursor.fetchone()
            if not (
                agent is not None
                and agent["status"] == "disabled"
                and agent["deleted_at"] is not None
                and int(agent["deleted_at"]) == tombstone.deleted_at
                and int(agent["lifecycle_generation"])
                == tombstone.lifecycle_generation
                and int(agent["generation_counter"])
                == tombstone.lifecycle_generation
                and int(agent["state_revision"]) == tombstone.state_revision
                and agent["active_revision_id"] is None
                and agent["selected_host_session_id"] is None
                and agent["authoritative_instance_id"] is None
            ):
                raise StaleRuntimeGenerationError(
                    "agent tombstone cleanup fence is stale"
                )
            cursor.execute(
                """
                SELECT * FROM agent_runtime_instance
                WHERE agent_id = %s AND owner_user_id = %s
                  AND lifecycle_generation < %s
                  AND state NOT IN ('stopped', 'failed', 'offline', 'superseded')
                ORDER BY lifecycle_generation, runtime_instance_id
                FOR UPDATE
                """,
                (
                    agent_id,
                    owner_user_id,
                    tombstone.lifecycle_generation,
                ),
            )
            settlements = tuple(
                self._terminalize_instance_row_locked(
                    cursor, row, failure_code="agent_deleted"
                )
                for row in cursor.fetchall()
            )
            settled_request_ids = tuple(
                request_id
                for settlement in settlements
                for request_id in settlement.settled_request_ids
            )
            return AgentTombstoneCleanup(
                tombstone=tombstone,
                settlements=settlements,
                settled_request_ids=settled_request_ids,
            )
