"""Transactional personal-agent runtime fencing tests for feature 060.

The suite creates a throwaway PostgreSQL database.  It never mutates the
configured development database and deliberately exercises repository
reconstruction so PostgreSQL, not process-local state, remains authoritative.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Iterator

import psycopg2
import pytest
from psycopg2 import sql

from orchestrator.agent_generator import AgentCodeGenerator
from orchestrator.agent_lifecycle import (
    CandidatePreparation,
    PostgresPersonalAgentRevisionStore,
    RevisionActivationError,
)
from orchestrator.user_agents import (
    AgentDeletedError,
    AgentOfflineError,
    HostRegistrationRefused,
    PersonalAgentRuntimeRepository,
    RuntimeCompatibilityPolicy,
    StaleRuntimeGenerationError,
    UserAgentOwnershipConflict,
    authorize_registration,
    can_user_use_agent,
    create_user_agent,
    go_live,
    mark_revalidation_required,
    mark_validated,
    soft_delete,
    touch_liveness,
)
from orchestrator.work_admission import ExecutionFence
from shared.database import Database, _build_database_url


_FIXTURE = json.loads(
    (
        Path(__file__).parent
        / "fixtures"
        / "runtime_reliability_060"
        / "runtime-lock-contract.json"
    ).read_text(encoding="utf-8")
)
_LOCK_DIGEST = str(_FIXTURE["lock_digest"])
_POLICY = RuntimeCompatibilityPolicy(
    runtime_contract_version=int(_FIXTURE["runtime_contract_version"]),
    runtime_lock_sha256=_LOCK_DIGEST,
)
_OWNER = "owner-us2"
_AGENT = "agent-us2"


@pytest.fixture(scope="module")
def postgres_database() -> Iterator[Database]:
    base_dsn = _build_database_url()
    try:
        params = psycopg2.extensions.parse_dsn(base_dsn)
        name = f"astraldeep_byo_runtime_{uuid.uuid4().hex}"
        admin = psycopg2.connect(**params)
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        admin.close()
    except Exception as exc:  # pragma: no cover - environment gate
        pytest.skip(f"cannot create isolated PostgreSQL database: {exc}")

    database_params = dict(params)
    database_params["dbname"] = name
    dsn = psycopg2.extensions.make_dsn(**database_params)
    prior_pool_setting = os.environ.get("DB_POOL_DISABLE")
    os.environ["DB_POOL_DISABLE"] = "1"
    try:
        yield Database(dsn)
    finally:
        if prior_pool_setting is None:
            os.environ.pop("DB_POOL_DISABLE", None)
        else:
            os.environ["DB_POOL_DISABLE"] = prior_pool_setting
        try:
            admin = psycopg2.connect(**params)
            admin.autocommit = True
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (name,),
                )
                cursor.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name))
                )
            admin.close()
        except Exception:
            pass


@pytest.fixture
def clean_database(postgres_database: Database) -> Database:
    connection = postgres_database._get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE user_agent SET active_revision_id = NULL, "
                "last_known_good_revision_id = NULL, selected_host_session_id = NULL, "
                "authoritative_instance_id = NULL"
            )
            cursor.execute("DELETE FROM agent_runtime_request")
            cursor.execute("DELETE FROM agent_runtime_instance")
            cursor.execute("DELETE FROM user_agent_revision")
            cursor.execute("DELETE FROM agent_host_session")
            cursor.execute("DELETE FROM user_agent")
            cursor.execute("DELETE FROM operation_submission_result")
            cursor.execute(
                "UPDATE operation_admission_slot SET operation_id = NULL, "
                "lease_token = NULL, lease_expires_at = NULL"
            )
            cursor.execute("DELETE FROM operation_record")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    return postgres_database


@pytest.fixture
def repository(clean_database: Database) -> PersonalAgentRuntimeRepository:
    return PersonalAgentRuntimeRepository(clean_database, compatibility_policy=_POLICY)


def _running_operation(
    db: Database,
    *,
    owner_user_id: str = _OWNER,
    operation_kind: str = "agent_runtime_request",
) -> ExecutionFence:
    operation_id = uuid.uuid4()
    lease_token = uuid.uuid4()
    db.execute(
        """
        INSERT INTO operation_record (
            operation_id, operation_kind, admission_class, owner_scope,
            owner_user_id, state, execution_generation,
            execution_lease_token, started_at
        ) VALUES (?, ?, 'interactive', 'user', ?, 'running', 1, ?, now())
        """,
        (str(operation_id), operation_kind, owner_user_id, str(lease_token)),
    )
    return ExecutionFence(operation_id, 1, lease_token)


def _host(
    repository: PersonalAgentRuntimeRepository,
    *,
    host_id: str | None = None,
    connection_scope_id: str | None = None,
):
    return repository.register_host_session(
        owner_user_id=_OWNER,
        connection_scope_id=connection_scope_id or str(uuid.uuid4()),
        host_id=host_id or str(uuid.uuid4()),
        platform="windows",
        client_version="0.4.0",
        supported_runtime_contract_versions=(2,),
        runtime_lock_sha256=_LOCK_DIGEST,
    )


def _agent_revision(
    repository: PersonalAgentRuntimeRepository,
    db: Database,
):
    create_user_agent(
        db,
        agent_id=_AGENT,
        owner_user_id=_OWNER,
        display_name="US2 Agent",
    )
    db.execute(
        "UPDATE user_agent SET status = 'validated' WHERE agent_id = ?",
        (_AGENT,),
    )
    return repository.create_revision(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
        artifact_digest=hashlib.sha256(b"us2-agent-bundle").hexdigest(),
        manifest={"runtime_contract_version": 2, "files": []},
        artifact_relative_path=f"{_AGENT}/revision-1",
        runtime_contract_version=2,
        release_lock_digest=_LOCK_DIGEST,
    )


def _runtime(
    repository: PersonalAgentRuntimeRepository,
    db: Database,
    *,
    online: bool,
):
    revision = _agent_revision(repository, db)
    host = _host(repository)
    host = repository.mark_inventory_reconciled(host.fence)
    selection = repository.select_host_for_agent(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
    )
    assert selection.session is not None
    assert selection.session.host_session_id == host.host_session_id
    delivery_operation = _running_operation(
        db,
        operation_kind="agent_runtime_delivery",
    )
    instance = repository.create_prelaunch_instance(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
        host_session_id=host.host_session_id,
        revision_id=revision.revision_id,
        operation_fence=delivery_operation,
    )
    process_id = str(uuid.uuid4())
    instance = repository.bind_runtime_process(
        instance.fence,
        process_id=process_id,
        expected_state_revision=instance.state_revision,
    )
    if online:
        instance = repository.accept_runtime_registration(
            instance.fence,
            runtime_contract_version=2,
            bundle_sha256=revision.artifact_digest,
        )
        instance = repository.record_runtime_heartbeat(
            instance.fence,
            heartbeat_sequence=1,
        )
        connection = db._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE user_agent_revision SET state = 'active', "
                    "confirmed_at = now(), promoted_at = now(), "
                    "state_revision = state_revision + 1 WHERE revision_id = %s",
                    (revision.revision_id,),
                )
                cursor.execute(
                    "UPDATE agent_runtime_instance SET state = 'online', "
                    "is_authoritative = TRUE, ready_at = now(), "
                    "last_liveness_at = now(), state_revision = state_revision + 1 "
                    "WHERE runtime_instance_id = %s",
                    (instance.fence.runtime_instance_id,),
                )
                cursor.execute(
                    "UPDATE user_agent SET active_revision_id = %s, "
                    "last_known_good_revision_id = %s, authoritative_instance_id = %s, "
                    "lifecycle_generation = %s, state_revision = state_revision + 1 "
                    "WHERE agent_id = %s AND owner_user_id = %s",
                    (
                        revision.revision_id,
                        revision.revision_id,
                        instance.fence.runtime_instance_id,
                        instance.fence.lifecycle_generation,
                        _AGENT,
                        _OWNER,
                    ),
                )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        instance = repository.get_runtime_instance(instance.fence.runtime_instance_id)
    return revision, host, instance


def test_latest_runtime_instances_are_owner_scoped_durable_hydration(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    revision, _host_record, online = _runtime(
        repository, clean_database, online=True
    )

    latest = repository.list_latest_runtime_instances(owner_user_id=_OWNER)

    assert latest == (online,)
    assert latest[0].active_revision_id == revision.revision_id
    assert (
        latest[0].authoritative_instance_id
        == online.fence.runtime_instance_id
    )
    assert repository.list_latest_runtime_instances(
        owner_user_id="different-owner"
    ) == ()


def test_registration_validates_before_allocating_and_persisting_session(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    invalid_cases = (
        ({"host_id": "not-a-uuid"}, "invalid_host_registration"),
        ({"platform": "linux"}, "invalid_host_registration"),
        ({"client_version": "0.4"}, "invalid_host_registration"),
        ({"supported_runtime_contract_versions": ()}, "invalid_host_registration"),
        ({"supported_runtime_contract_versions": (2, 2)}, "invalid_host_registration"),
        ({"supported_runtime_contract_versions": (1,)}, "runtime_contract_unsupported"),
        ({"runtime_lock_sha256": "0" * 64}, "runtime_lock_mismatch"),
    )
    base = {
        "owner_user_id": _OWNER,
        "connection_scope_id": str(uuid.uuid4()),
        "host_id": str(uuid.uuid4()),
        "platform": "windows",
        "client_version": "0.4.0",
        "supported_runtime_contract_versions": (2,),
        "runtime_lock_sha256": _LOCK_DIGEST,
    }
    for changes, expected_code in invalid_cases:
        with pytest.raises(HostRegistrationRefused) as raised:
            repository.register_host_session(**(base | changes))
        assert raised.value.code == expected_code

    assert clean_database.fetch_one(
        "SELECT count(*) AS count FROM agent_host_session"
    )["count"] == 0

    accepted = repository.register_host_session(**base)
    assert uuid.UUID(accepted.host_session_id).version == 4
    assert accepted.host_session_id not in {
        accepted.host_id,
        accepted.connection_scope_id,
    }
    assert accepted.state == "connected"
    assert accepted.inventory_state == "pending"
    assert accepted.runtime_contract_version == 2
    persisted = clean_database.fetch_one(
        "SELECT * FROM agent_host_session WHERE host_session_id = ?",
        (accepted.host_session_id,),
    )
    assert str(persisted["host_id"]) == accepted.host_id
    assert str(persisted["connection_scope_id"]) == accepted.connection_scope_id


def test_legacy_create_preserves_owner_and_rejects_cross_owner_overwrite(
    clean_database: Database,
) -> None:
    create_user_agent(
        clean_database,
        agent_id=_AGENT,
        owner_user_id=_OWNER,
        display_name="Original",
    )
    create_user_agent(
        clean_database,
        agent_id=_AGENT,
        owner_user_id=_OWNER,
        display_name="Same-owner update",
    )
    updated = clean_database.fetch_one(
        "SELECT owner_user_id, display_name FROM user_agent WHERE agent_id = ?",
        (_AGENT,),
    )
    assert updated == {
        "owner_user_id": _OWNER,
        "display_name": "Same-owner update",
    }

    with pytest.raises(UserAgentOwnershipConflict):
        create_user_agent(
            clean_database,
            agent_id=_AGENT,
            owner_user_id="different-owner",
            display_name="Stolen",
        )
    unchanged = clean_database.fetch_one(
        "SELECT owner_user_id, display_name FROM user_agent WHERE agent_id = ?",
        (_AGENT,),
    )
    assert unchanged == updated


def test_legacy_lifecycle_mutations_cannot_revive_a_tombstoned_agent(
    clean_database: Database,
) -> None:
    create_user_agent(
        clean_database,
        agent_id=_AGENT,
        owner_user_id=_OWNER,
        display_name="Deleted",
    )
    mark_validated(clean_database, _AGENT, "0.1.0")
    soft_delete(clean_database, _AGENT)

    with pytest.raises(AgentDeletedError):
        create_user_agent(
            clean_database,
            agent_id=_AGENT,
            owner_user_id=_OWNER,
            display_name="Resurrected",
        )
    with pytest.raises(AgentDeletedError):
        mark_validated(clean_database, _AGENT, "0.1.0")
    with pytest.raises(AgentDeletedError):
        go_live(clean_database, _AGENT, host_session_id="legacy-session")
    with pytest.raises(AgentDeletedError):
        touch_liveness(clean_database, _AGENT)
    with pytest.raises(AgentDeletedError):
        mark_revalidation_required(clean_database, _AGENT, True)

    accepted, reason = authorize_registration(clean_database, _OWNER, _AGENT)
    assert accepted is False
    assert reason == "agent is deleted"
    assert can_user_use_agent(clean_database, _OWNER, _AGENT) is False
    tombstone = clean_database.fetch_one(
        "SELECT status, deleted_at, display_name FROM user_agent WHERE agent_id = ?",
        (_AGENT,),
    )
    assert tombstone["status"] == "disabled"
    assert tombstone["deleted_at"] is not None
    assert tombstone["display_name"] == "Deleted"


def test_sticky_selection_same_host_rollover_then_deterministic_failover(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    _agent_revision(repository, clean_database)
    host_a_id = "11111111-1111-4111-8111-111111111111"
    host_b_id = "22222222-2222-4222-8222-222222222222"
    host_a1 = repository.mark_inventory_reconciled(
        _host(repository, host_id=host_a_id).fence
    )
    host_b = repository.mark_inventory_reconciled(
        _host(repository, host_id=host_b_id).fence
    )
    clean_database.execute(
        "UPDATE agent_host_session SET eligible_since = now() - interval '2 seconds' "
        "WHERE host_session_id = ?",
        (host_a1.host_session_id,),
    )
    selected = repository.select_host_for_agent(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
    )
    assert selected.session is not None
    assert selected.session.host_id == host_a_id

    host_a2 = repository.mark_inventory_reconciled(
        _host(repository, host_id=host_a_id).fence
    )
    assert host_a2.host_generation == host_a1.host_generation + 1
    assert host_a2.supersedes_session_id == host_a1.host_session_id
    selected = repository.select_host_for_agent(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
    )
    assert selected.session is not None
    assert selected.session.host_session_id == host_a2.host_session_id

    disconnected = repository.disconnect_host_session(
        host_a2.fence,
        failure_code="host_lost",
    )
    assert disconnected.selected_sessions[_AGENT] == host_b.host_session_id
    pointer = clean_database.fetch_one(
        "SELECT selected_host_session_id FROM user_agent WHERE agent_id = ?",
        (_AGENT,),
    )
    assert str(pointer["selected_host_session_id"]) == host_b.host_session_id


def test_inventory_reconciliation_is_all_or_nothing_and_allocates_exact_start(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    revision = _agent_revision(repository, clean_database)
    host = _host(repository)
    selection = repository.select_host_for_agent(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
    )
    assert selection.session is not None
    assert selection.session.host_session_id == host.host_session_id
    clean_database.execute(
        "UPDATE user_agent_revision SET state = 'active', promoted_at = now() "
        "WHERE revision_id = ?",
        (revision.revision_id,),
    )
    clean_database.execute(
        "UPDATE user_agent SET active_revision_id = ?, "
        "last_known_good_revision_id = ? WHERE agent_id = ?",
        (revision.revision_id, revision.revision_id, _AGENT),
    )
    selected = repository.get_selected_session_revision(
        host.fence,
        agent_id=_AGENT,
    )
    assert selected.host.inventory_state == "pending"
    assert selected.revision.revision_id == revision.revision_id

    entry = {
        "agent_id": _AGENT,
        "revision_id": revision.revision_id,
        "bundle_sha256": revision.artifact_digest,
        "runtime_contract_version": 2,
        "required_runtime_lock_sha256": _LOCK_DIGEST,
    }
    before = clean_database.fetch_one(
        "SELECT generation_counter FROM user_agent WHERE agent_id = ?",
        (_AGENT,),
    )
    with pytest.raises(
        ValueError,
        match="delivery operations must exactly match inventory start actions",
    ):
        repository.reconcile_host_inventory(
            host.fence,
            inventory_id=str(uuid.uuid4()),
            entries=(entry,),
        )
    still_pending = clean_database.fetch_one(
        "SELECT inventory_state FROM agent_host_session WHERE host_session_id = ?",
        (host.host_session_id,),
    )
    after = clean_database.fetch_one(
        "SELECT generation_counter FROM user_agent WHERE agent_id = ?",
        (_AGENT,),
    )
    assert still_pending["inventory_state"] == "pending"
    assert after["generation_counter"] == before["generation_counter"]
    assert clean_database.fetch_one(
        "SELECT count(*) AS count FROM agent_runtime_instance"
    )["count"] == 0

    operation = _running_operation(
        clean_database,
        operation_kind="agent_runtime_delivery",
    )
    inventory_id = str(uuid.uuid4())
    result = repository.reconcile_host_inventory(
        host.fence,
        inventory_id=inventory_id,
        entries=(entry,),
        delivery_operation_fences={
            (_AGENT, revision.revision_id): operation,
        },
    )
    assert result.inventory_id == inventory_id
    assert result.host.inventory_state == "reconciled"
    assert result.reconciled_at == result.host.inventory_reconciled_at
    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.action == "start"
    assert action.reason_code is None
    assert action.selected_delivery is not None
    assert action.selected_delivery.bundle_sha256 == revision.artifact_digest
    instance = repository.get_runtime_instance(
        action.selected_delivery.runtime_instance_id
    )
    assert instance.state == "delivering"
    assert instance.fence.process_id is None
    assert instance.fence.delivery_id == action.selected_delivery.delivery_id
    assert (
        instance.fence.lifecycle_generation
        == action.selected_delivery.lifecycle_generation
    )
    bound = repository.bind_runtime_process(
        instance.fence,
        process_id=str(uuid.uuid4()),
        expected_state_revision=instance.state_revision,
    )
    with pytest.raises(StaleRuntimeGenerationError):
        repository.promote_recovered_runtime(bound.fence)
    registered = repository.accept_runtime_registration(
        bound.fence,
        runtime_contract_version=2,
        bundle_sha256=revision.artifact_digest,
    )
    live = repository.record_runtime_heartbeat(
        registered.fence,
        heartbeat_sequence=1,
    )
    ready = repository.mark_runtime_ready(live.fence)
    promoted = repository.promote_recovered_runtime(ready.fence)
    assert promoted.state == "online"
    assert promoted.is_authoritative is True
    pointers = clean_database.fetch_one(
        "SELECT active_revision_id, last_known_good_revision_id, "
        "authoritative_instance_id, lifecycle_generation FROM user_agent "
        "WHERE agent_id = ?",
        (_AGENT,),
    )
    assert str(pointers["active_revision_id"]) == revision.revision_id
    assert str(pointers["last_known_good_revision_id"]) == revision.revision_id
    assert str(pointers["authoritative_instance_id"]) == (
        promoted.fence.runtime_instance_id
    )
    assert pointers["lifecycle_generation"] == promoted.fence.lifecycle_generation
    assert repository.promote_recovered_runtime(ready.fence) == promoted
    assert repository.get_current_online_authority(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
    ) == promoted
    settled_delivery = clean_database.fetch_one(
        "SELECT state, terminal_code FROM operation_record WHERE operation_id = ?",
        (str(operation.operation_id),),
    )
    assert settled_delivery["state"] == "completed"
    assert settled_delivery["terminal_code"] is None


def test_inventory_validation_and_stale_operation_leave_no_partial_commit(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    revision = _agent_revision(repository, clean_database)
    host = _host(repository)
    repository.select_host_for_agent(owner_user_id=_OWNER, agent_id=_AGENT)
    clean_database.execute(
        "UPDATE user_agent_revision SET state = 'active', promoted_at = now() "
        "WHERE revision_id = ?",
        (revision.revision_id,),
    )
    clean_database.execute(
        "UPDATE user_agent SET active_revision_id = ? WHERE agent_id = ?",
        (revision.revision_id, _AGENT),
    )
    entry = {
        "agent_id": _AGENT,
        "revision_id": revision.revision_id,
        "bundle_sha256": revision.artifact_digest,
        "runtime_contract_version": 2,
        "required_runtime_lock_sha256": _LOCK_DIGEST,
    }
    with pytest.raises(ValueError, match="unique agent/revision pairs"):
        repository.reconcile_host_inventory(
            host.fence,
            inventory_id=str(uuid.uuid4()),
            entries=(entry, entry),
        )

    stale_operation = _running_operation(
        clean_database,
        operation_kind="agent_runtime_delivery",
    )
    clean_database.execute(
        "UPDATE operation_record SET "
        "execution_generation = execution_generation + 1, "
        "execution_lease_token = ? WHERE operation_id = ?",
        (str(uuid.uuid4()), str(stale_operation.operation_id)),
    )
    with pytest.raises(StaleRuntimeGenerationError):
        repository.reconcile_host_inventory(
            host.fence,
            inventory_id=str(uuid.uuid4()),
            entries=(entry,),
            delivery_operation_fences={
                (_AGENT, revision.revision_id): stale_operation,
            },
        )
    persisted = clean_database.fetch_one(
        "SELECT inventory_state FROM agent_host_session WHERE host_session_id = ?",
        (host.host_session_id,),
    )
    assert persisted["inventory_state"] == "pending"
    assert clean_database.fetch_one(
        "SELECT count(*) AS count FROM agent_runtime_instance"
    )["count"] == 0


def test_inventory_returns_one_ordered_action_for_every_retained_entry(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    active = _agent_revision(repository, clean_database)
    clean_database.execute(
        "UPDATE user_agent_revision SET state = 'active', promoted_at = now() "
        "WHERE revision_id = ?",
        (active.revision_id,),
    )
    clean_database.execute(
        "UPDATE user_agent SET active_revision_id = ? WHERE agent_id = ?",
        (active.revision_id, _AGENT),
    )
    inactive = repository.create_revision(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
        artifact_digest=hashlib.sha256(b"inactive-retained-bundle").hexdigest(),
        manifest={"runtime_contract_version": 2, "files": []},
        artifact_relative_path=f"{_AGENT}/revision-2",
        runtime_contract_version=2,
        release_lock_digest=_LOCK_DIGEST,
        parent_revision_id=active.revision_id,
    )
    host = _host(repository)
    repository.select_host_for_agent(owner_user_id=_OWNER, agent_id=_AGENT)
    unknown_revision = str(uuid.uuid4())

    def entry(revision_id: str, digest: str) -> dict[str, object]:
        return {
            "agent_id": _AGENT,
            "revision_id": revision_id,
            "bundle_sha256": digest,
            "runtime_contract_version": 2,
            "required_runtime_lock_sha256": _LOCK_DIGEST,
        }

    result = repository.reconcile_host_inventory(
        host.fence,
        inventory_id=str(uuid.uuid4()),
        entries=(
            entry(active.revision_id, active.artifact_digest),
            entry(inactive.revision_id, inactive.artifact_digest),
            entry(unknown_revision, hashlib.sha256(b"unknown").hexdigest()),
        ),
        delivery_operation_fences={
            (active.agent_id, active.revision_id): _running_operation(
                clean_database,
                operation_kind="agent_runtime_delivery",
            )
        },
    )
    assert [
        (action.revision_id, action.action, action.reason_code)
        for action in result.actions
    ] == [
        (active.revision_id, "start", None),
        (inactive.revision_id, "keep_stopped", "revision_not_active"),
        (unknown_revision, "delete", "revision_unknown"),
    ]
    assert result.actions[0].selected_delivery is not None
    assert result.actions[1].selected_delivery is None
    assert result.actions[2].selected_delivery is None


def test_current_online_authority_requires_every_durable_pointer_relation(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    revision, host, online = _runtime(repository, clean_database, online=True)
    resolved = repository.get_current_online_authority(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
    )
    assert resolved == online
    selected = repository.get_selected_session_revision(
        host.fence,
        agent_id=_AGENT,
    )
    assert selected.revision.revision_id == revision.revision_id

    clean_database.execute(
        "UPDATE agent_host_session SET inventory_state = 'pending', "
        "inventory_reconciled_at = NULL WHERE host_session_id = ?",
        (host.host_session_id,),
    )
    with pytest.raises(AgentOfflineError):
        repository.get_current_online_authority(
            owner_user_id=_OWNER,
            agent_id=_AGENT,
        )


def test_prelaunch_process_binding_is_nullable_once_only_and_replay_safe(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    _, _, instance = _runtime(repository, clean_database, online=False)
    assert instance.state == "starting"
    assert instance.fence.process_id is not None

    replay = repository.bind_runtime_process(
        dataclasses.replace(instance.fence, process_id=None),
        process_id=instance.fence.process_id,
        expected_state_revision=0,
    )
    assert replay == instance

    with pytest.raises(StaleRuntimeGenerationError):
        repository.bind_runtime_process(
            dataclasses.replace(instance.fence, process_id=None),
            process_id=str(uuid.uuid4()),
            expected_state_revision=0,
        )
    persisted = repository.get_runtime_instance(instance.fence.runtime_instance_id)
    assert persisted.fence.process_id == instance.fence.process_id


def test_delivering_recovery_timeout_is_db_fenced_and_settles_delivery_operation(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    revision = _agent_revision(repository, clean_database)
    host = repository.mark_inventory_reconciled(_host(repository).fence)
    repository.select_host_for_agent(owner_user_id=_OWNER, agent_id=_AGENT)
    clean_database.execute(
        "UPDATE user_agent_revision SET state = 'active', promoted_at = now() "
        "WHERE revision_id = ?",
        (revision.revision_id,),
    )
    clean_database.execute(
        "UPDATE user_agent SET active_revision_id = ? WHERE agent_id = ?",
        (revision.revision_id, _AGENT),
    )
    operation = _running_operation(
        clean_database,
        operation_kind="agent_runtime_delivery",
    )
    recovery = repository.create_selected_recovery_instance(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
        operation_fence=operation,
    )
    assert recovery.host.host_session_id == host.host_session_id
    with pytest.raises(
        StaleRuntimeGenerationError,
        match="deadline has not elapsed",
    ):
        repository.terminalize_expired_startup(
            recovery.instance.fence,
            timeout_seconds=20,
        )
    clean_database.execute(
        "UPDATE agent_runtime_instance SET created_at = now() - interval '30 seconds' "
        "WHERE runtime_instance_id = ?",
        (recovery.instance.fence.runtime_instance_id,),
    )
    started = time.monotonic()
    settlement = repository.terminalize_expired_startup(
        recovery.instance.fence,
        timeout_seconds=20,
    )
    assert time.monotonic() - started < 2.0
    assert settlement.instance.state == "failed"
    assert settlement.instance.failure_code == "child_registration_timeout"
    delivery_operation = clean_database.fetch_one(
        "SELECT state, terminal_code FROM operation_record WHERE operation_id = ?",
        (str(operation.operation_id),),
    )
    assert delivery_operation == {
        "state": "retryable",
        "terminal_code": "child_registration_timeout",
    }
    replay = repository.terminalize_expired_startup(
        recovery.instance.fence,
        timeout_seconds=20,
    )
    assert replay.instance == settlement.instance
    assert replay.settled_request_ids == ()


def test_every_runtime_fence_dimension_is_checked_before_state_change(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    revision, _, instance = _runtime(repository, clean_database, online=False)
    instance = repository.accept_runtime_registration(
        instance.fence,
        runtime_contract_version=2,
        bundle_sha256=revision.artifact_digest,
    )
    instance = repository.record_runtime_heartbeat(
        instance.fence,
        heartbeat_sequence=1,
    )
    replacements = (
        {"agent_id": "other-agent"},
        {"host_id": str(uuid.uuid4())},
        {"host_session_id": str(uuid.uuid4())},
        {"delivery_id": str(uuid.uuid4())},
        {"revision_id": str(uuid.uuid4())},
        {"runtime_instance_id": str(uuid.uuid4())},
        {"process_id": str(uuid.uuid4())},
        {"lifecycle_generation": instance.fence.lifecycle_generation + 1},
    )
    for changes in replacements:
        with pytest.raises(StaleRuntimeGenerationError):
            repository.mark_runtime_ready(dataclasses.replace(instance.fence, **changes))
        current = repository.get_runtime_instance(instance.fence.runtime_instance_id)
        assert current.state == "starting"
        assert current.state_revision == instance.state_revision

    ready = repository.mark_runtime_ready(instance.fence)
    assert ready.state == "ready"
    assert ready.state_revision == instance.state_revision + 1


def test_registration_precedes_durable_monotonic_heartbeat_and_ready(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    revision, _, instance = _runtime(repository, clean_database, online=False)
    with pytest.raises(StaleRuntimeGenerationError):
        repository.record_runtime_heartbeat(
            instance.fence,
            heartbeat_sequence=1,
        )
    unchanged = repository.get_runtime_instance(instance.fence.runtime_instance_id)
    assert unchanged.registered_at is None
    assert unchanged.last_heartbeat_sequence is None
    assert unchanged.last_liveness_at is None

    registered = repository.accept_runtime_registration(
        instance.fence,
        runtime_contract_version=2,
        bundle_sha256=revision.artifact_digest,
    )
    assert registered.registered_at is not None
    assert registered.last_heartbeat_sequence is None
    assert registered.last_liveness_at is None
    assert repository.accept_runtime_registration(
        instance.fence,
        runtime_contract_version=2,
        bundle_sha256=revision.artifact_digest,
    ) == registered

    first = repository.record_runtime_heartbeat(
        instance.fence,
        heartbeat_sequence=1,
    )
    assert first.last_heartbeat_sequence == 1
    assert first.last_liveness_at is not None
    reconstructed = PersonalAgentRuntimeRepository(
        clean_database,
        compatibility_policy=_POLICY,
    )
    assert reconstructed.record_runtime_heartbeat(
        instance.fence,
        heartbeat_sequence=1,
    ) == first
    second = reconstructed.record_runtime_heartbeat(
        instance.fence,
        heartbeat_sequence=2,
    )
    assert second.last_heartbeat_sequence == 2
    assert second.last_liveness_at >= first.last_liveness_at
    assert reconstructed.mark_runtime_ready(instance.fence).state == "ready"


def test_requests_require_current_online_authority_and_complete_fence(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    _, _, starting = _runtime(repository, clean_database, online=False)
    request_operation = _running_operation(clean_database)
    with pytest.raises(AgentOfflineError):
        repository.assign_request(starting.fence, operation_fence=request_operation)

    clean_database.execute(
        "DELETE FROM operation_record WHERE operation_id = ?",
        (str(request_operation.operation_id),),
    )
    clean_database.execute(
        "UPDATE user_agent SET active_revision_id = NULL, "
        "last_known_good_revision_id = NULL, selected_host_session_id = NULL, "
        "authoritative_instance_id = NULL WHERE agent_id = ?",
        (_AGENT,),
    )
    clean_database.execute("DELETE FROM agent_runtime_instance")
    clean_database.execute("DELETE FROM user_agent_revision")
    clean_database.execute("DELETE FROM agent_host_session")
    clean_database.execute("DELETE FROM user_agent")

    _, _, online = _runtime(repository, clean_database, online=True)
    request_operation = _running_operation(clean_database)
    request = repository.assign_request(
        online.fence,
        operation_fence=request_operation,
    )
    assert request.state == "assigned"

    stale_fences = (
        dataclasses.replace(request.fence, request_id=str(uuid.uuid4())),
        dataclasses.replace(request.fence, request_generation=str(uuid.uuid4())),
        dataclasses.replace(
            request.fence,
            operation_execution_generation=(
                request.fence.operation_execution_generation + 1
            ),
        ),
        dataclasses.replace(
            request.fence,
            runtime=dataclasses.replace(
                request.fence.runtime,
                process_id=str(uuid.uuid4()),
            ),
        ),
    )
    digest = hashlib.sha256(b"normalized-result").hexdigest()
    for stale in stale_fences:
        with pytest.raises(StaleRuntimeGenerationError):
            repository.settle_request(
                stale,
                state="completed",
                result_digest=digest,
            )
        assert repository.get_runtime_request(request.fence.request_id).state == "assigned"

    completed = repository.settle_request(
        request.fence,
        state="completed",
        result_digest=digest,
    )
    assert completed.state == "completed"
    assert completed.result_digest == digest
    assert repository.settle_request(
        request.fence,
        state="completed",
        result_digest=digest,
    ) == completed
    operation = clean_database.fetch_one(
        "SELECT state FROM operation_record WHERE operation_id = ?",
        (str(request_operation.operation_id),),
    )
    assert operation["state"] == "completed"


def test_known_runtime_failure_settles_instance_requests_and_operations_immediately(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    _, _, online = _runtime(repository, clean_database, online=True)
    first = repository.assign_request(
        online.fence,
        operation_fence=_running_operation(clean_database),
    )
    second = repository.assign_request(
        online.fence,
        operation_fence=_running_operation(clean_database),
    )

    started = time.monotonic()
    settlement = repository.terminalize_runtime(
        online.fence,
        failure_code="child_exited",
    )
    assert time.monotonic() - started < 2.0
    assert settlement.instance.state == "offline"
    assert settlement.settled_request_ids == (
        first.fence.request_id,
        second.fence.request_id,
    )
    for request_id in settlement.settled_request_ids:
        request = repository.get_runtime_request(request_id)
        assert request.state == "retryable"
        assert request.terminal_code == "child_exited"
        operation = clean_database.fetch_one(
            "SELECT state, terminal_code FROM operation_record WHERE operation_id = ?",
            (request.fence.operation_id,),
        )
        assert operation["state"] == "retryable"
        assert operation["terminal_code"] == "child_exited"

    pointer = clean_database.fetch_one(
        "SELECT authoritative_instance_id FROM user_agent WHERE agent_id = ?",
        (_AGENT,),
    )
    assert pointer["authoritative_instance_id"] is None
    replay = repository.terminalize_runtime(
        online.fence,
        failure_code="child_exited",
    )
    assert replay.settled_request_ids == ()


def test_db_receipt_liveness_timeout_settles_hung_runtime_within_seven_seconds(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    _, _, online = _runtime(repository, clean_database, online=True)
    operation = _running_operation(clean_database)
    request = repository.assign_request(
        online.fence,
        operation_fence=operation,
    )
    with pytest.raises(
        StaleRuntimeGenerationError,
        match="deadline has not elapsed",
    ):
        repository.terminalize_expired_liveness(
            online.fence,
            timeout_seconds=5,
        )
    clean_database.execute(
        "UPDATE agent_runtime_instance "
        "SET last_liveness_at = now() - interval '5 seconds' "
        "WHERE runtime_instance_id = ?",
        (online.fence.runtime_instance_id,),
    )
    started = time.monotonic()
    settlement = repository.terminalize_expired_liveness(
        online.fence,
        timeout_seconds=5,
    )
    elapsed = time.monotonic() - started
    assert elapsed < 2.0
    assert 5.0 + elapsed < 7.0
    assert settlement.instance.state == "offline"
    assert settlement.instance.failure_code == "child_hung"
    assert settlement.settled_request_ids == (request.fence.request_id,)
    assert repository.get_runtime_request(request.fence.request_id).terminal_code == (
        "child_hung"
    )
    persisted_operation = clean_database.fetch_one(
        "SELECT state, terminal_code FROM operation_record WHERE operation_id = ?",
        (str(operation.operation_id),),
    )
    assert persisted_operation == {
        "state": "retryable",
        "terminal_code": "child_hung",
    }


def test_host_loss_terminalizes_exact_session_and_moves_selection_to_standby(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    revision, selected_host, online = _runtime(
        repository, clean_database, online=True
    )
    standby = repository.mark_inventory_reconciled(_host(repository).fence)
    request = repository.assign_request(
        online.fence,
        operation_fence=_running_operation(clean_database),
    )

    started = time.monotonic()
    result = repository.disconnect_host_session(
        selected_host.fence,
        failure_code="host_lost",
    )
    assert time.monotonic() - started < 2.0
    assert result.settled_request_ids == (request.fence.request_id,)
    assert result.selected_sessions[_AGENT] == standby.host_session_id
    assert repository.get_runtime_request(request.fence.request_id).terminal_code == "host_lost"
    assert repository.get_runtime_instance(online.fence.runtime_instance_id).state == "offline"

    delivery_operation = _running_operation(
        clean_database,
        operation_kind="agent_runtime_delivery",
    )
    recovery = repository.create_selected_recovery_instance(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
        operation_fence=delivery_operation,
    )
    assert recovery.host.host_session_id == standby.host_session_id
    assert recovery.revision.revision_id == revision.revision_id
    assert recovery.instance.state == "delivering"
    assert recovery.instance.fence.process_id is None
    assert recovery.instance.is_authoritative is False
    with pytest.raises(StaleRuntimeGenerationError, match="already pending"):
        repository.create_selected_recovery_instance(
            owner_user_id=_OWNER,
            agent_id=_AGENT,
            operation_fence=delivery_operation,
        )


def test_same_host_session_rollover_fences_old_runtime_before_rebinding(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    _, old_host, online = _runtime(repository, clean_database, online=True)
    request = repository.assign_request(
        online.fence,
        operation_fence=_running_operation(clean_database),
    )

    replacement = _host(repository, host_id=old_host.host_id)
    assert replacement.supersedes_session_id == old_host.host_session_id
    assert replacement.inventory_state == "pending"
    old_row = clean_database.fetch_one(
        "SELECT state FROM agent_host_session WHERE host_session_id = ?",
        (old_host.host_session_id,),
    )
    assert old_row["state"] == "disconnected"
    assert repository.get_runtime_instance(online.fence.runtime_instance_id).state == "offline"
    assert repository.get_runtime_request(request.fence.request_id).terminal_code == "host_lost"
    pointer = clean_database.fetch_one(
        "SELECT selected_host_session_id FROM user_agent WHERE agent_id = ?",
        (_AGENT,),
    )
    assert str(pointer["selected_host_session_id"]) == replacement.host_session_id


def _candidate_preparation(
    *,
    revision_id: str,
    host_session_id: str,
    operation_fence: ExecutionFence,
) -> CandidatePreparation:
    finalized = AgentCodeGenerator(
        llm_client=object(), llm_model="unused"
    ).finalize_byo_bundle(
        files={
            "agent_main.py": "from astralprims_ui import normalize_tool_result\n",
            "astralprims_ui.py": (
                "def normalize_tool_result(value):\n    return value\n"
            ),
            "mcp_tools.py": "TOOL_REGISTRY = {}\n",
        },
        agent_id=_AGENT,
        revision_id=revision_id,
        agent_name="US2 Agent",
        description="candidate promotion repository test",
        constitution_version="0.1.0",
        required_runtime_lock_sha256=_LOCK_DIGEST,
    )
    return CandidatePreparation(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
        revision_id=revision_id,
        bundle_sha256=finalized.bundle_sha256,
        runtime_manifest=finalized.manifest,
        artifact_relative_path=f"{_AGENT}/{revision_id}",
        runtime_contract_version=2,
        required_runtime_lock_sha256=_LOCK_DIGEST,
        host_session_id=host_session_id,
        operation_fence=operation_fence,
    )


def test_revision_store_rejects_malformed_manifest_and_candidate_metadata(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    store = PostgresPersonalAgentRevisionStore(repository)
    request = _candidate_preparation(
        revision_id=str(uuid.uuid4()),
        host_session_id=str(uuid.uuid4()),
        operation_fence=_running_operation(
            clean_database, operation_kind="agent_revision_promotion"
        ),
    )
    wrong_revision = json.loads(
        json.dumps(request.runtime_manifest, default=dict)
    )
    wrong_revision["revision_id"] = str(uuid.uuid4())
    missing_file = json.loads(
        json.dumps(request.runtime_manifest, default=dict)
    )
    missing_file["files"].pop()
    bad_file_hash = json.loads(
        json.dumps(request.runtime_manifest, default=dict)
    )
    bad_file_hash["files"][0]["sha256"] = "not-a-digest"
    bad_file_size = json.loads(
        json.dumps(request.runtime_manifest, default=dict)
    )
    bad_file_size["files"][0]["size_bytes"] = True
    invalid = (
        dataclasses.replace(request, bundle_sha256="not-a-digest"),
        dataclasses.replace(request, runtime_contract_version=1),
        dataclasses.replace(request, required_runtime_lock_sha256="0" * 64),
        dataclasses.replace(request, artifact_relative_path="../escape"),
        dataclasses.replace(request, operation_fence=None),
        dataclasses.replace(request, runtime_manifest=wrong_revision),
        dataclasses.replace(request, runtime_manifest=missing_file),
        dataclasses.replace(request, runtime_manifest=bad_file_hash),
        dataclasses.replace(request, runtime_manifest=bad_file_size),
    )
    for malformed in invalid:
        with pytest.raises((TypeError, ValueError)):
            store.prepare_candidate(malformed)


def test_postgres_revision_store_promotes_ready_candidate_atomically(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    old_revision, host, old_runtime = _runtime(
        repository, clean_database, online=True
    )
    store = PostgresPersonalAgentRevisionStore(repository)
    request = _candidate_preparation(
        revision_id=str(uuid.uuid4()),
        host_session_id=host.host_session_id,
        operation_fence=_running_operation(
            clean_database, operation_kind="agent_revision_promotion"
        ),
    )

    candidate = store.prepare_candidate(request)
    assert store.prepare_candidate(request) == candidate
    prelaunch = repository.get_runtime_instance(candidate.runtime_instance_id)
    store.mark_candidate_starting(candidate)
    store.mark_candidate_starting(candidate)
    started = repository.bind_runtime_process(
        prelaunch.fence,
        process_id=str(uuid.uuid4()),
        expected_state_revision=prelaunch.state_revision,
    )
    registered = repository.accept_runtime_registration(
        started.fence,
        runtime_contract_version=2,
        bundle_sha256=request.bundle_sha256,
    )
    live = repository.record_runtime_heartbeat(
        registered.fence, heartbeat_sequence=1
    )
    ready = repository.mark_runtime_ready(live.fence)
    store.confirm_candidate_ready(candidate, ready.fence.runtime_instance_id)
    store.confirm_candidate_ready(candidate, ready.fence.runtime_instance_id)

    commit = store.promote_candidate(candidate)
    replay = store.promote_candidate(candidate)

    assert commit.previous_revision_id == old_revision.revision_id
    assert commit.previous_runtime_instance_id == old_runtime.fence.runtime_instance_id
    assert replay.revision_id == commit.revision_id
    assert replay.runtime_instance_id == commit.runtime_instance_id
    pointers = clean_database.fetch_one(
        "SELECT active_revision_id, last_known_good_revision_id, "
        "authoritative_instance_id, lifecycle_generation FROM user_agent "
        "WHERE agent_id = ? AND owner_user_id = ?",
        (_AGENT, _OWNER),
    )
    assert str(pointers["active_revision_id"]) == candidate.revision_id
    assert str(pointers["last_known_good_revision_id"]) == old_revision.revision_id
    assert str(pointers["authoritative_instance_id"]) == candidate.runtime_instance_id
    assert int(pointers["lifecycle_generation"]) == ready.fence.lifecycle_generation
    old = repository.get_runtime_instance(old_runtime.fence.runtime_instance_id)
    promoted = repository.get_runtime_instance(candidate.runtime_instance_id)
    assert old.state == "stopping" and not old.is_authoritative
    assert promoted.state == "online" and promoted.is_authoritative
    states = {
        str(row["revision_id"]): row["state"]
        for row in clean_database.fetch_all(
            "SELECT revision_id, state FROM user_agent_revision WHERE agent_id = ?",
            (_AGENT,),
        )
    }
    assert states == {
        old_revision.revision_id: "retired",
        candidate.revision_id: "active",
    }


def test_postgres_revision_store_activates_first_revision_without_fake_lkg(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    create_user_agent(
        clean_database,
        agent_id=_AGENT,
        owner_user_id=_OWNER,
        display_name="First revision",
    )
    clean_database.execute(
        "UPDATE user_agent SET status = 'validated' WHERE agent_id = ?",
        (_AGENT,),
    )
    host = repository.mark_inventory_reconciled(_host(repository).fence)
    repository.select_host_for_agent(owner_user_id=_OWNER, agent_id=_AGENT)
    store = PostgresPersonalAgentRevisionStore(repository)
    request = _candidate_preparation(
        revision_id=str(uuid.uuid4()),
        host_session_id=host.host_session_id,
        operation_fence=_running_operation(
            clean_database, operation_kind="agent_revision_promotion"
        ),
    )
    candidate = store.prepare_candidate(request)
    prelaunch = repository.get_runtime_instance(candidate.runtime_instance_id)
    store.mark_candidate_starting(candidate)
    started = repository.bind_runtime_process(
        prelaunch.fence,
        process_id=str(uuid.uuid4()),
        expected_state_revision=prelaunch.state_revision,
    )
    registered = repository.accept_runtime_registration(
        started.fence,
        runtime_contract_version=2,
        bundle_sha256=request.bundle_sha256,
    )
    live = repository.record_runtime_heartbeat(
        registered.fence, heartbeat_sequence=1
    )
    ready = repository.mark_runtime_ready(live.fence)
    store.confirm_candidate_ready(candidate, ready.fence.runtime_instance_id)

    commit = store.promote_candidate(candidate)

    assert commit.previous_revision_id is None
    assert commit.previous_runtime_instance_id is None
    pointers = clean_database.fetch_one(
        "SELECT active_revision_id, last_known_good_revision_id, "
        "authoritative_instance_id FROM user_agent WHERE agent_id = ?",
        (_AGENT,),
    )
    assert str(pointers["active_revision_id"]) == candidate.revision_id
    assert pointers["last_known_good_revision_id"] is None
    assert str(pointers["authoritative_instance_id"]) == candidate.runtime_instance_id


def test_postgres_promotion_failure_preserves_old_and_terminalizes_candidate(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    old_revision, host, old_runtime = _runtime(
        repository, clean_database, online=True
    )
    store = PostgresPersonalAgentRevisionStore(repository)
    operation = _running_operation(
        clean_database, operation_kind="agent_revision_promotion"
    )
    request = _candidate_preparation(
        revision_id=str(uuid.uuid4()),
        host_session_id=host.host_session_id,
        operation_fence=operation,
    )
    candidate = store.prepare_candidate(request)
    prelaunch = repository.get_runtime_instance(candidate.runtime_instance_id)
    store.mark_candidate_starting(candidate)
    started = repository.bind_runtime_process(
        prelaunch.fence,
        process_id=str(uuid.uuid4()),
        expected_state_revision=prelaunch.state_revision,
    )
    registered = repository.accept_runtime_registration(
        started.fence,
        runtime_contract_version=2,
        bundle_sha256=request.bundle_sha256,
    )
    live = repository.record_runtime_heartbeat(
        registered.fence, heartbeat_sequence=1
    )
    ready = repository.mark_runtime_ready(live.fence)
    store.confirm_candidate_ready(candidate, ready.fence.runtime_instance_id)
    before = clean_database.fetch_one(
        "SELECT active_revision_id, last_known_good_revision_id, "
        "authoritative_instance_id FROM user_agent WHERE agent_id = ?",
        (_AGENT,),
    )

    # Losing the delivery operation fence immediately before the transaction is
    # a real promotion-boundary failure, not a fake store exception.
    clean_database.execute(
        "DELETE FROM operation_record WHERE operation_id = ?",
        (str(operation.operation_id),),
    )
    with pytest.raises(StaleRuntimeGenerationError):
        store.promote_candidate(candidate)

    assert clean_database.fetch_one(
        "SELECT active_revision_id, last_known_good_revision_id, "
        "authoritative_instance_id FROM user_agent WHERE agent_id = ?",
        (_AGENT,),
    ) == before
    still_old = repository.get_runtime_instance(old_runtime.fence.runtime_instance_id)
    assert still_old.state == "online" and still_old.is_authoritative
    store.fail_candidate(candidate, "revision_promotion_failed")
    failed = repository.get_runtime_instance(candidate.runtime_instance_id)
    assert failed.state == "offline" and not failed.is_authoritative
    candidate_state = clean_database.fetch_one(
        "SELECT state, failure_code FROM user_agent_revision WHERE revision_id = ?",
        (candidate.revision_id,),
    )
    assert candidate_state == {
        "state": "failed",
        "failure_code": "revision_promotion_failed",
    }
    active_state = clean_database.fetch_one(
        "SELECT state FROM user_agent_revision WHERE revision_id = ?",
        (old_revision.revision_id,),
    )
    assert active_state["state"] == "active"


def test_postgres_revision_recovery_follows_pointer_and_fences_orphans(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    _, host, authoritative = _runtime(repository, clean_database, online=True)
    store = PostgresPersonalAgentRevisionStore(repository)
    orphan_request = _candidate_preparation(
        revision_id=str(uuid.uuid4()),
        host_session_id=host.host_session_id,
        operation_fence=_running_operation(
            clean_database, operation_kind="agent_revision_promotion"
        ),
    )
    orphan = store.prepare_candidate(orphan_request)

    plan = store.recovery_plan(_OWNER, _AGENT)

    assert plan.authoritative_runtime_instance_id == (
        authoritative.fence.runtime_instance_id
    )
    assert plan.start_revision_id is None
    assert plan.stop_runtime_instance_ids == (orphan.runtime_instance_id,)
    revision = clean_database.fetch_one(
        "SELECT state, failure_code FROM user_agent_revision WHERE revision_id = ?",
        (orphan.revision_id,),
    )
    assert revision == {
        "state": "failed",
        "failure_code": "revision_promotion_failed",
    }
    terminal = repository.get_runtime_instance(orphan.runtime_instance_id)
    assert terminal.state == "failed"
    assert terminal.failure_code == "revision_promotion_failed"


def test_revision_prepare_refuses_inventory_pending_before_candidate_insert(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    create_user_agent(
        clean_database,
        agent_id=_AGENT,
        owner_user_id=_OWNER,
        display_name="Inventory-gated",
    )
    clean_database.execute(
        "UPDATE user_agent SET status = 'validated' WHERE agent_id = ?",
        (_AGENT,),
    )
    pending_host = _host(repository)
    selected = repository.select_host_for_agent(
        owner_user_id=_OWNER, agent_id=_AGENT
    )
    assert selected.session is not None
    assert selected.session.host_session_id == pending_host.host_session_id
    store = PostgresPersonalAgentRevisionStore(repository)
    request = _candidate_preparation(
        revision_id=str(uuid.uuid4()),
        host_session_id=pending_host.host_session_id,
        operation_fence=_running_operation(
            clean_database, operation_kind="agent_revision_promotion"
        ),
    )

    with pytest.raises(RevisionActivationError, match="inventory_required"):
        store.prepare_candidate(request)

    assert clean_database.fetch_one(
        "SELECT count(*) AS count FROM user_agent_revision"
    )["count"] == 0
    assert clean_database.fetch_one(
        "SELECT count(*) AS count FROM agent_runtime_instance"
    )["count"] == 0


def test_delayed_candidate_registration_cannot_revive_durable_tombstone(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    revision, _, started = _runtime(repository, clean_database, online=False)
    tombstone = repository.tombstone_agent(
        owner_user_id=_OWNER, agent_id=_AGENT
    )

    with pytest.raises(AgentDeletedError):
        repository.accept_runtime_registration(
            started.fence,
            runtime_contract_version=2,
            bundle_sha256=revision.artifact_digest,
        )

    row = clean_database.fetch_one(
        "SELECT status, deleted_at, active_revision_id, "
        "authoritative_instance_id, lifecycle_generation FROM user_agent "
        "WHERE agent_id = ? AND owner_user_id = ?",
        (_AGENT, _OWNER),
    )
    assert row["status"] == "disabled"
    assert row["deleted_at"] is not None
    assert row["active_revision_id"] is None
    assert row["authoritative_instance_id"] is None
    assert int(row["lifecycle_generation"]) == tombstone.lifecycle_generation


def test_post_tombstone_cleanup_settles_all_runtime_and_request_operations(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    _, _, online = _runtime(repository, clean_database, online=True)
    request_operation = _running_operation(clean_database)
    request = repository.assign_request(
        online.fence,
        operation_fence=request_operation,
    )
    assert online.operation_id is not None
    tombstone = repository.tombstone_agent(
        owner_user_id=_OWNER,
        agent_id=_AGENT,
    )
    with pytest.raises(AgentDeletedError):
        repository.terminalize_runtime(
            online.fence,
            failure_code="agent_deleted",
        )

    cleanup = repository.cleanup_tombstoned_agent(tombstone)
    assert cleanup.tombstone == tombstone
    assert cleanup.settled_request_ids == (request.fence.request_id,)
    assert [item.instance.fence.runtime_instance_id for item in cleanup.settlements] == [
        online.fence.runtime_instance_id
    ]
    terminal = repository.get_runtime_instance(online.fence.runtime_instance_id)
    assert terminal.state == "offline"
    assert terminal.failure_code == "agent_deleted"
    settled_request = repository.get_runtime_request(request.fence.request_id)
    assert settled_request.state == "retryable"
    assert settled_request.terminal_code == "agent_deleted"
    operations = clean_database.fetch_all(
        "SELECT operation_id, state, terminal_code FROM operation_record "
        "WHERE operation_id IN (?, ?) ORDER BY operation_id",
        (online.operation_id, request.fence.operation_id),
    )
    assert {str(row["operation_id"]): (row["state"], row["terminal_code"]) for row in operations} == {
        online.operation_id: ("retryable", "agent_deleted"),
        request.fence.operation_id: ("retryable", "agent_deleted"),
    }
    agent = clean_database.fetch_one(
        "SELECT deleted_at, lifecycle_generation, state_revision, "
        "active_revision_id, selected_host_session_id, authoritative_instance_id "
        "FROM user_agent WHERE agent_id = ?",
        (_AGENT,),
    )
    assert int(agent["deleted_at"]) == tombstone.deleted_at
    assert int(agent["lifecycle_generation"]) == tombstone.lifecycle_generation
    assert int(agent["state_revision"]) == tombstone.state_revision
    assert agent["active_revision_id"] is None
    assert agent["selected_host_session_id"] is None
    assert agent["authoritative_instance_id"] is None

    replay = repository.cleanup_tombstoned_agent(tombstone)
    assert replay.settlements == ()
    assert replay.settled_request_ids == ()


def test_revision_prepare_cannot_recreate_deleted_agent(
    repository: PersonalAgentRuntimeRepository,
    clean_database: Database,
) -> None:
    create_user_agent(
        clean_database,
        agent_id=_AGENT,
        owner_user_id=_OWNER,
        display_name="Deleted candidate owner",
    )
    repository.tombstone_agent(owner_user_id=_OWNER, agent_id=_AGENT)
    request = _candidate_preparation(
        revision_id=str(uuid.uuid4()),
        host_session_id=str(uuid.uuid4()),
        operation_fence=_running_operation(
            clean_database, operation_kind="agent_revision_promotion"
        ),
    )

    with pytest.raises(RevisionActivationError, match="agent_deleted"):
        PostgresPersonalAgentRevisionStore(repository).prepare_candidate(request)

    assert clean_database.fetch_one(
        "SELECT count(*) AS count FROM user_agent_revision"
    )["count"] == 0
