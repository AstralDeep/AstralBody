"""Feature 060 BYO revision generation, activation, and crash recovery.

The tests use a deterministic transactional fake for the activation coordinator.
PostgreSQL transition details remain covered by the runtime repository suite; this
module stresses the lifecycle rule at every externally visible boundary without
turning timing or process scheduling into test authority.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator.agent_generator import (  # noqa: E402
    BYO_BUNDLE_FILENAMES,
    BYO_RUNTIME_CONTRACT_VERSION,
    BYO_RUNTIME_LOCK_ARTIFACT,
    BYO_RUNTIME_LOCK_SHA256,
    AgentCodeGenerator,
)
from orchestrator.agent_lifecycle import (  # noqa: E402
    AgentRevisionActivator,
    CandidatePreparation,
    CandidateRevision,
    PromotionCommit,
    RecoveryPlan,
    RevisionActivationError,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

AGENT_ID = "ua-recovery-owner"
OWNER_ID = "recovery-owner"
OLD_REVISION = str(uuid.UUID(int=1))
OLD_RUNTIME = str(uuid.UUID(int=2))
HOST_ID = str(uuid.UUID(int=3))
HOST_SESSION_ID = str(uuid.UUID(int=4))


def _source_files() -> dict[str, str]:
    return {
        "agent_main.py": "from astralprims_ui import normalize_tool_result\n",
        "astralprims_ui.py": "def normalize_tool_result(value):\n    return value\n",
        "mcp_tools.py": "TOOL_REGISTRY = {}\n",
    }


@pytest.mark.skipif(
    not (REPO_ROOT / "windows-client").is_dir(),  # repo root absent inside the product image
    reason="repo-root tooling files are not part of the product image",
)
def test_runtime_manifest_constants_match_reviewed_lock_fixture():
    fixture = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "runtime_reliability_060"
            / "runtime-lock-contract.json"
        ).read_text(encoding="utf-8")
    )
    assert fixture["runtime_contract_version"] == BYO_RUNTIME_CONTRACT_VERSION
    assert fixture["lock_artifact"] == BYO_RUNTIME_LOCK_ARTIFACT
    assert fixture["lock_digest"] == BYO_RUNTIME_LOCK_SHA256
    assert hashlib.sha256(
        (REPO_ROOT / BYO_RUNTIME_LOCK_ARTIFACT).read_bytes()
    ).hexdigest() == BYO_RUNTIME_LOCK_SHA256
    digest_vector = fixture["bundle_digest_vector"]
    assert fixture["bundle_digest_contract"] == "canonical-json-utf8-v1"
    assert AgentCodeGenerator._bundle_digest(digest_vector["files"]) == (
        digest_vector["bundle_sha256"]
    )


def test_runtime_manifest_is_deterministic_complete_and_revision_bound():
    generator = AgentCodeGenerator(llm_client=object(), llm_model="unused")
    revision_id = str(uuid.UUID(int=10))
    files = _source_files()

    first = generator.finalize_byo_bundle(
        files=files,
        agent_id=AGENT_ID,
        revision_id=revision_id,
        agent_name="Recovery Agent",
        description="keeps the prior revision available",
        constitution_version="0.1.0",
        required_runtime_lock_sha256=BYO_RUNTIME_LOCK_SHA256,
    )
    second = generator.finalize_byo_bundle(
        files=dict(reversed(tuple(files.items()))),
        agent_id=AGENT_ID,
        revision_id=revision_id,
        agent_name="Recovery Agent",
        description="keeps the prior revision available",
        constitution_version="0.1.0",
        required_runtime_lock_sha256=BYO_RUNTIME_LOCK_SHA256,
    )

    assert tuple(first.files) == BYO_BUNDLE_FILENAMES
    assert first.bundle_sha256 == second.bundle_sha256
    assert first.manifest_json == second.manifest_json
    assert first.manifest == second.manifest
    assert first.manifest["manifest_version"] == 2
    assert first.manifest["runtime_contract_version"] == BYO_RUNTIME_CONTRACT_VERSION
    assert first.manifest["revision_id"] == revision_id
    assert first.manifest["required_runtime_lock_sha256"] == BYO_RUNTIME_LOCK_SHA256
    assert first.manifest["bundle_sha256"] == first.bundle_sha256
    assert [entry["name"] for entry in first.manifest["files"]] == list(
        BYO_BUNDLE_FILENAMES
    )
    assert "generated_at" not in first.manifest
    assert json.loads(first.manifest_json) == first.manifest_dict()
    with pytest.raises(TypeError):
        first.manifest["files"][0]["name"] = "changed"
    detached = first.manifest_dict()
    detached["files"][0]["name"] = "changed"
    assert first.manifest["files"][0]["name"] == "agent_main.py"

    expected_file_hashes = {
        name: hashlib.sha256(files[name].encode("utf-8")).hexdigest()
        for name in BYO_BUNDLE_FILENAMES
    }
    assert {
        entry["name"]: entry["sha256"] for entry in first.manifest["files"]
    } == expected_file_hashes


def test_generated_v2_child_registers_and_echoes_complete_request_fence(
    tmp_path: Path,
) -> None:
    generator = AgentCodeGenerator(llm_client=object(), llm_model="unused")
    revision_id = str(uuid.uuid4())
    files = generator.generate_byo_scaffold(
        agent_name="Fenced Child",
        description="proves the exact runtime and request generations",
        agent_id=AGENT_ID,
    ) | {"mcp_tools.py": "TOOL_REGISTRY = {}\n"}
    finalized = generator.finalize_byo_bundle(
        files=files,
        agent_id=AGENT_ID,
        revision_id=revision_id,
        agent_name="Fenced Child",
        description="proves the exact runtime and request generations",
        constitution_version="0.1.0",
        required_runtime_lock_sha256=BYO_RUNTIME_LOCK_SHA256,
    )
    for name, source in finalized.files.items():
        (tmp_path / name).write_text(source, encoding="utf-8")

    fence = {
        "agent_id": AGENT_ID,
        "host_id": str(uuid.uuid4()),
        "host_session_id": str(uuid.uuid4()),
        "delivery_id": str(uuid.uuid4()),
        "revision_id": revision_id,
        "runtime_instance_id": str(uuid.uuid4()),
        "process_id": str(uuid.uuid4()),
        "lifecycle_generation": 17,
    }
    request_id = str(uuid.uuid4())
    request_generation = str(uuid.uuid4())
    stale_request = {
        "type": "mcp_request",
        "method": "tools/list",
        "params": {},
        "fence": fence,
        "request_id": request_id,
        "request_generation": "not-a-uuid",
    }
    valid_request = stale_request | {"request_generation": request_generation}
    environment = os.environ.copy()
    environment.update(
        {
            "ASTRAL_RUNTIME_FENCE_JSON": json.dumps(fence),
            "ASTRAL_RUNTIME_CONTRACT_VERSION": "2",
            "ASTRAL_RUNTIME_BUNDLE_SHA256": finalized.bundle_sha256,
        }
    )
    completed = subprocess.run(
        [sys.executable, "agent_main.py"],
        cwd=tmp_path,
        env=environment,
        input=f"{json.dumps(stale_request)}\n{json.dumps(valid_request)}\n",
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    frames = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [frame["type"] for frame in frames] == [
        "agent_runtime_register",
        "mcp_response",
    ]
    registration, response = frames
    assert registration["fence"] == fence
    assert registration["runtime_contract_version"] == 2
    assert registration["bundle_sha256"] == finalized.bundle_sha256
    assert registration["agent_card"]["agent_id"] == AGENT_ID
    assert response["fence"] == fence
    assert response["request_id"] == request_id
    assert response["request_generation"] == request_generation


@pytest.mark.parametrize(
    "files",
    [
        {},
        {"agent_main.py": "x", "mcp_tools.py": "y"},
        {**_source_files(), "manifest.json": "{}"},
        {**_source_files(), "nested/file.py": "x"},
        {**_source_files(), "mcp_tools.py": b"not text"},
    ],
)
def test_runtime_manifest_refuses_incomplete_or_ambiguous_bundle(files):
    generator = AgentCodeGenerator(llm_client=object(), llm_model="unused")
    with pytest.raises((TypeError, ValueError)):
        generator.finalize_byo_bundle(
            files=files,
            agent_id=AGENT_ID,
            revision_id=str(uuid.UUID(int=11)),
            agent_name="Recovery Agent",
            description="keeps the prior revision available",
            constitution_version="0.1.0",
            required_runtime_lock_sha256=BYO_RUNTIME_LOCK_SHA256,
        )


def test_digest_changes_for_every_file_and_not_for_mapping_order():
    generator = AgentCodeGenerator(llm_client=object(), llm_model="unused")
    baseline = generator.finalize_byo_bundle(
        files=_source_files(),
        agent_id=AGENT_ID,
        revision_id=str(uuid.UUID(int=12)),
        agent_name="Recovery Agent",
        description="keeps the prior revision available",
        constitution_version="0.1.0",
        required_runtime_lock_sha256=BYO_RUNTIME_LOCK_SHA256,
    )
    for name in BYO_BUNDLE_FILENAMES:
        changed = _source_files()
        changed[name] += "# changed\n"
        candidate = generator.finalize_byo_bundle(
            files=changed,
            agent_id=AGENT_ID,
            revision_id=str(uuid.UUID(int=12)),
            agent_name="Recovery Agent",
            description="keeps the prior revision available",
            constitution_version="0.1.0",
            required_runtime_lock_sha256=BYO_RUNTIME_LOCK_SHA256,
        )
        assert candidate.bundle_sha256 != baseline.bundle_sha256


class SimulatedCrash(BaseException):
    """Power loss: bypass ordinary Exception cleanup and preserve durable state."""


class _TransactionalRevisionStore:
    """Small deterministic implementation of the lifecycle store protocol."""

    def __init__(self) -> None:
        self.active_revision_id = OLD_REVISION
        self.last_known_good_revision_id = OLD_REVISION
        self.authoritative_runtime_id = OLD_RUNTIME
        self.invocable_runtime_ids = {OLD_RUNTIME}
        self.candidates: dict[str, CandidateRevision] = {}
        self.failed_revision_ids: set[str] = set()
        self.events: list[str] = []
        self._counter = 20
        self.fail_promote = False

    def _uuid(self) -> str:
        self._counter += 1
        return str(uuid.UUID(int=self._counter))

    def prepare_candidate(self, request: CandidatePreparation) -> CandidateRevision:
        candidate = CandidateRevision(
            owner_user_id=request.owner_user_id,
            agent_id=request.agent_id,
            revision_id=request.revision_id,
            promotion_token=self._uuid(),
            runtime_instance_id=self._uuid(),
            previous_active_revision_id=self.active_revision_id,
            previous_runtime_instance_id=self.authoritative_runtime_id,
        )
        self.candidates[candidate.revision_id] = candidate
        self.events.append("prepared")
        return candidate

    def mark_candidate_starting(self, candidate: CandidateRevision) -> None:
        assert candidate.revision_id in self.candidates
        self.events.append("starting")

    def confirm_candidate_ready(
        self, candidate: CandidateRevision, ready_runtime_instance_id: str
    ) -> CandidateRevision:
        if ready_runtime_instance_id != candidate.runtime_instance_id:
            raise RevisionActivationError("stale_runtime_generation")
        self.events.append("ready")
        return candidate

    def promote_candidate(self, candidate: CandidateRevision) -> PromotionCommit:
        # Snapshot + restore models one database transaction. Every injected
        # failure before commit leaves all authoritative pointers untouched.
        before = (
            self.active_revision_id,
            self.last_known_good_revision_id,
            self.authoritative_runtime_id,
            set(self.invocable_runtime_ids),
        )
        try:
            if self.fail_promote:
                raise RuntimeError("database transaction rolled back")
            if self.active_revision_id != candidate.previous_active_revision_id:
                raise RevisionActivationError("revision_promotion_failed")
            previous_runtime = self.authoritative_runtime_id
            self.active_revision_id = candidate.revision_id
            self.last_known_good_revision_id = candidate.previous_active_revision_id
            self.authoritative_runtime_id = candidate.runtime_instance_id
            self.invocable_runtime_ids = {candidate.runtime_instance_id}
            self.events.append("promoted")
            return PromotionCommit(
                owner_user_id=candidate.owner_user_id,
                agent_id=candidate.agent_id,
                revision_id=candidate.revision_id,
                runtime_instance_id=candidate.runtime_instance_id,
                previous_revision_id=candidate.previous_active_revision_id,
                previous_runtime_instance_id=previous_runtime,
            )
        except BaseException:
            (
                self.active_revision_id,
                self.last_known_good_revision_id,
                self.authoritative_runtime_id,
                self.invocable_runtime_ids,
            ) = before
            raise

    def fail_candidate(self, candidate: CandidateRevision, failure_code: str) -> None:
        if self.active_revision_id == candidate.revision_id:
            return
        self.failed_revision_ids.add(candidate.revision_id)
        self.invocable_runtime_ids.discard(candidate.runtime_instance_id)
        self.events.append(f"failed:{failure_code}")

    def recovery_plan(self, owner_user_id: str, agent_id: str) -> RecoveryPlan:
        assert owner_user_id == OWNER_ID and agent_id == AGENT_ID
        stop = tuple(
            candidate.runtime_instance_id
            for candidate in self.candidates.values()
            if candidate.runtime_instance_id != self.authoritative_runtime_id
        )
        start_revision = (
            None if self.authoritative_runtime_id else self.active_revision_id
        )
        return RecoveryPlan(
            owner_user_id=owner_user_id,
            agent_id=agent_id,
            active_revision_id=self.active_revision_id,
            authoritative_runtime_instance_id=self.authoritative_runtime_id,
            start_revision_id=start_revision,
            stop_runtime_instance_ids=stop,
        )


def _preparation(revision_id: str) -> CandidatePreparation:
    finalized = AgentCodeGenerator(
        llm_client=object(), llm_model="unused"
    ).finalize_byo_bundle(
        files=_source_files(),
        agent_id=AGENT_ID,
        revision_id=revision_id,
        agent_name="Recovery Agent",
        description="keeps the prior revision available",
        constitution_version="0.1.0",
        required_runtime_lock_sha256=BYO_RUNTIME_LOCK_SHA256,
    )
    return CandidatePreparation(
        owner_user_id=OWNER_ID,
        agent_id=AGENT_ID,
        revision_id=revision_id,
        bundle_sha256=finalized.bundle_sha256,
        runtime_manifest=finalized.manifest,
        artifact_relative_path=f"{AGENT_ID}/{revision_id}",
        runtime_contract_version=BYO_RUNTIME_CONTRACT_VERSION,
        required_runtime_lock_sha256=BYO_RUNTIME_LOCK_SHA256,
        host_session_id=HOST_SESSION_ID,
        operation_fence=None,
    )


async def _activate(store, *, fault_boundary=None, start_failure=False):
    stopped: list[str] = []

    async def start(candidate):
        if start_failure:
            raise RuntimeError("host refused candidate")
        return candidate.runtime_instance_id

    async def ready(candidate):
        return candidate.runtime_instance_id

    async def stop(runtime_instance_id):
        stopped.append(runtime_instance_id)
        store.events.append(f"stop:{runtime_instance_id}")

    def fault(boundary, _candidate):
        if boundary == fault_boundary:
            raise SimulatedCrash(boundary)

    activator = AgentRevisionActivator(
        store,
        start_candidate=start,
        await_candidate_ready=ready,
        stop_runtime=stop,
        fault_hook=fault,
    )
    revision_id = str(uuid.UUID(int=100 + len(store.candidates)))
    return activator, stopped, _preparation(revision_id)


async def test_preparation_or_start_failure_never_stops_working_runtime():
    store = _TransactionalRevisionStore()
    activator, stopped, request = await _activate(store, start_failure=True)

    with pytest.raises(RevisionActivationError, match="child_start_failed"):
        await activator.activate(request)

    assert store.active_revision_id == OLD_REVISION
    assert store.authoritative_runtime_id == OLD_RUNTIME
    assert store.invocable_runtime_ids == {OLD_RUNTIME}
    assert stopped and OLD_RUNTIME not in stopped
    assert request.revision_id in store.failed_revision_ids


async def test_inventory_refusal_creates_no_candidate_or_stop_side_effect():
    store = _TransactionalRevisionStore()
    stopped: list[str] = []

    def refuse(_request):
        raise RevisionActivationError("inventory_required")

    store.prepare_candidate = refuse
    activator = AgentRevisionActivator(
        store,
        start_candidate=lambda candidate: candidate.runtime_instance_id,
        await_candidate_ready=lambda candidate: candidate.runtime_instance_id,
        stop_runtime=lambda runtime_id: stopped.append(runtime_id),
    )

    with pytest.raises(RevisionActivationError, match="inventory_required"):
        await activator.activate(_preparation(str(uuid.UUID(int=6100))))

    assert store.candidates == {}
    assert stopped == []
    assert store.invocable_runtime_ids == {OLD_RUNTIME}


async def test_promotion_failure_terminalizes_only_candidate():
    store = _TransactionalRevisionStore()
    store.fail_promote = True
    activator, stopped, request = await _activate(store)

    with pytest.raises(RevisionActivationError, match="revision_promotion_failed"):
        await activator.activate(request)

    assert store.active_revision_id == OLD_REVISION
    assert store.last_known_good_revision_id == OLD_REVISION
    assert store.authoritative_runtime_id == OLD_RUNTIME
    assert store.invocable_runtime_ids == {OLD_RUNTIME}
    assert stopped and OLD_RUNTIME not in stopped
    assert request.revision_id in store.failed_revision_ids


def test_two_ready_candidates_cannot_both_become_authoritative():
    store = _TransactionalRevisionStore()
    first = store.prepare_candidate(_preparation(str(uuid.UUID(int=6300))))
    second = store.prepare_candidate(_preparation(str(uuid.UUID(int=6301))))
    store.mark_candidate_starting(first)
    store.mark_candidate_starting(second)
    store.confirm_candidate_ready(first, first.runtime_instance_id)
    store.confirm_candidate_ready(second, second.runtime_instance_id)

    committed = store.promote_candidate(first)
    with pytest.raises(RevisionActivationError, match="revision_promotion_failed"):
        store.promote_candidate(second)
    store.fail_candidate(second, "revision_promotion_failed")

    assert store.active_revision_id == first.revision_id
    assert store.authoritative_runtime_id == committed.runtime_instance_id
    assert store.invocable_runtime_ids == {first.runtime_instance_id}
    assert second.revision_id in store.failed_revision_ids


async def test_prior_runtime_stops_only_after_promotion_commit():
    store = _TransactionalRevisionStore()
    activator, stopped, request = await _activate(store)

    result = await activator.activate(request)

    assert result.commit.revision_id == request.revision_id
    assert result.prior_runtime_stopped
    assert store.active_revision_id == request.revision_id
    assert store.last_known_good_revision_id == OLD_REVISION
    assert store.authoritative_runtime_id == result.commit.runtime_instance_id
    assert stopped == [OLD_RUNTIME]
    assert store.events.index("promoted") < store.events.index(f"stop:{OLD_RUNTIME}")


async def test_post_commit_observer_failure_cannot_relabel_promotion_failed():
    store = _TransactionalRevisionStore()
    stopped: list[str] = []

    async def start(candidate):
        return candidate.runtime_instance_id

    async def ready(candidate):
        return candidate.runtime_instance_id

    async def stop(runtime_instance_id):
        stopped.append(runtime_instance_id)

    def observer(boundary, _candidate):
        if boundary == "after_promote_commit":
            raise RuntimeError("metrics sink unavailable")

    activator = AgentRevisionActivator(
        store,
        start_candidate=start,
        await_candidate_ready=ready,
        stop_runtime=stop,
        fault_hook=observer,
    )
    request = _preparation(str(uuid.UUID(int=6000)))

    result = await activator.activate(request)

    assert result.commit.revision_id == request.revision_id
    assert store.active_revision_id == request.revision_id
    assert request.revision_id not in store.failed_revision_ids
    assert stopped == [OLD_RUNTIME]


async def test_post_commit_stop_failure_reports_cleanup_without_rollback():
    store = _TransactionalRevisionStore()

    async def start(candidate):
        return candidate.runtime_instance_id

    async def ready(candidate):
        return candidate.runtime_instance_id

    async def stop(_runtime_instance_id):
        raise RuntimeError("host disconnected during stop")

    activator = AgentRevisionActivator(
        store,
        start_candidate=start,
        await_candidate_ready=ready,
        stop_runtime=stop,
    )
    request = _preparation(str(uuid.UUID(int=6200)))

    result = await activator.activate(request)

    assert result.cleanup_pending
    assert not result.prior_runtime_stopped
    assert store.active_revision_id == request.revision_id
    assert request.revision_id not in store.failed_revision_ids


@pytest.mark.parametrize(
    "boundary",
    [
        "after_prepare",
        "before_start",
        "after_start",
        "before_ready",
        "after_ready",
        "before_promote",
        "after_promote_commit",
        "before_prior_stop",
        "after_prior_stop",
    ],
)
async def test_one_hundred_fault_boundaries_preserve_one_durable_authority(boundary):
    # Nine boundaries x twelve deterministic trials = 108, satisfying SC-004's
    # minimum while covering both sides of the database commit.
    elapsed_ms = []
    outcomes = {"prior_authority": 0, "candidate_authority": 0}
    for trial in range(12):
        store = _TransactionalRevisionStore()
        activator, _stopped, request = await _activate(store, fault_boundary=boundary)
        request = replace(request, revision_id=str(uuid.UUID(int=1000 + trial)))

        started = time.perf_counter()
        with pytest.raises(SimulatedCrash):
            await activator.activate(request)
        elapsed_ms.append(round((time.perf_counter() - started) * 1000, 3))

        if boundary in {
            "after_promote_commit",
            "before_prior_stop",
            "after_prior_stop",
        }:
            outcomes["candidate_authority"] += 1
            assert store.active_revision_id == request.revision_id
            assert store.authoritative_runtime_id != OLD_RUNTIME
            assert store.invocable_runtime_ids != {OLD_RUNTIME}
        else:
            outcomes["prior_authority"] += 1
            assert store.active_revision_id == OLD_REVISION
            assert store.authoritative_runtime_id == OLD_RUNTIME
            assert store.invocable_runtime_ids == {OLD_RUNTIME}
    ordered = sorted(elapsed_ms)
    print(
        "US2_PROMOTION_DISTRIBUTION="
        + json.dumps(
            {
                "boundary": boundary,
                "count": len(ordered),
                "outcomes": outcomes,
                "p50_ms": ordered[5],
                "p95_ms": ordered[11],
                "max_ms": ordered[-1],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


async def test_crash_recovery_follows_durable_pointer_and_stops_candidates():
    store = _TransactionalRevisionStore()
    activator, stopped, request = await _activate(
        store, fault_boundary="after_promote_commit"
    )
    with pytest.raises(SimulatedCrash):
        await activator.activate(request)

    # A second candidate was durable but never promoted. Recovery must not infer
    # authority from recency or readiness; only the committed active pointer wins.
    orphan = store.prepare_candidate(
        _preparation(str(uuid.UUID(int=5000)))
    )
    plan = await activator.reconcile_after_crash(OWNER_ID, AGENT_ID)

    assert plan.active_revision_id == request.revision_id
    assert plan.authoritative_runtime_instance_id == store.authoritative_runtime_id
    assert orphan.runtime_instance_id in plan.stop_runtime_instance_ids
    assert orphan.runtime_instance_id in stopped
    assert plan.start_revision_id is None
