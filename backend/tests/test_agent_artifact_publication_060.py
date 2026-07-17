"""Fault-injected tests for feature-060 immutable agent publication."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import uuid

import pytest

from orchestrator.agent_generator import (
    BYO_RUNTIME_LOCK_SHA256,
    AgentCodeGenerator,
)
from orchestrator.artifact_publication import (
    ArtifactIntegrityError,
    ImmutableAgentArtifactStore,
)


_AGENT_ID = "ua-atomic-agent-owner"
_CONSTITUTION_VERSION = "0.1.0"


def _ids() -> tuple[str, str, str]:
    return str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())


def _bundle(revision_id: str, *, marker: str = "one"):
    generator = AgentCodeGenerator()
    files = generator.generate_byo_scaffold(
        agent_name="Atomic Agent",
        description="Safely tests immutable artifact publication.",
        agent_id=_AGENT_ID,
    )
    files["mcp_tools.py"] = (
        '"""Generated tools."""\n'
        f'MARKER = "{marker}"\n'
        "TOOL_REGISTRY = {}\n"
    )
    return generator.finalize_byo_bundle(
        files=files,
        agent_id=_AGENT_ID,
        revision_id=revision_id,
        agent_name="Atomic Agent",
        description="Safely tests immutable artifact publication.",
        constitution_version=_CONSTITUTION_VERSION,
        required_runtime_lock_sha256=BYO_RUNTIME_LOCK_SHA256,
    )


def _publish(store, finalized, draft_uuid, publication_id, revision_id, **kwargs):
    return store.publish(
        finalized,
        draft_uuid=draft_uuid,
        source_state_revision=7,
        publication_id=publication_id,
        agent_id=_AGENT_ID,
        revision_id=revision_id,
        **kwargs,
    )


def test_publish_fsyncs_and_atomically_exposes_exact_revision(tmp_path, monkeypatch):
    store = ImmutableAgentArtifactStore(tmp_path / "artifacts")
    draft_uuid, publication_id, revision_id = _ids()
    finalized = _bundle(revision_id)
    fsynced: list[int] = []
    real_fsync = os.fsync

    def recording_fsync(descriptor: int) -> None:
        fsynced.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", recording_fsync)
    published = _publish(
        store, finalized, draft_uuid, publication_id, revision_id
    )

    assert published.artifact_relative_path == (
        f"revisions/{_AGENT_ID}/{revision_id}"
    )
    assert published.bundle_sha256 == finalized.bundle_sha256
    assert published.files == finalized.files
    assert published.manifest_dict() == finalized.manifest_dict()
    assert published.manifest_sha256 == hashlib.sha256(
        finalized.manifest_json.encode("utf-8")
    ).hexdigest()
    revision_path = store.root / published.artifact_relative_path
    assert {entry.name for entry in revision_path.iterdir()} == {
        "agent_main.py",
        "astralprims_ui.py",
        "mcp_tools.py",
        "manifest.json",
    }
    assert not (store.root / "staging" / draft_uuid).joinpath(
        "7", publication_id
    ).exists()
    # Four files plus staging/revision directory durability require more than
    # a token file flush; exact descriptor identities are platform-specific.
    assert len(fsynced) >= 9


@pytest.mark.parametrize(
    "boundary",
    [
        "before_stage",
        "after_staging_directory",
        "after_file:agent_main.py",
        "after_file:astralprims_ui.py",
        "after_file:mcp_tools.py",
        "after_file:manifest.json",
        "after_staging_fsync",
        "after_validate",
        "before_replace",
        "after_replace",
        "after_revision_fsync",
    ],
)
def test_crash_at_every_publication_boundary_replays_same_identity(
    tmp_path, boundary
):
    store = ImmutableAgentArtifactStore(tmp_path / boundary.replace(":", "-"))
    draft_uuid, publication_id, revision_id = _ids()
    finalized = _bundle(revision_id)

    def crash(current: str) -> None:
        if current == boundary:
            raise RuntimeError("simulated process crash")

    with pytest.raises(RuntimeError, match="simulated process crash"):
        _publish(
            store,
            finalized,
            draft_uuid,
            publication_id,
            revision_id,
            fault_hook=crash,
        )

    recovered = _publish(
        store, finalized, draft_uuid, publication_id, revision_id
    )
    assert recovered.bundle_sha256 == finalized.bundle_sha256
    assert recovered.artifact_relative_path.endswith(revision_id)
    assert recovered.files["mcp_tools.py"].find('MARKER = "one"') >= 0


def test_fence_is_rechecked_before_replace_and_stale_claim_never_publishes(
    tmp_path,
):
    store = ImmutableAgentArtifactStore(tmp_path / "artifacts")
    draft_uuid, publication_id, revision_id = _ids()
    finalized = _bundle(revision_id)
    boundaries: list[str] = []

    def fence(boundary: str) -> None:
        boundaries.append(boundary)
        if boundary == "before_replace":
            raise RuntimeError("generation claim is stale")

    with pytest.raises(RuntimeError, match="generation claim is stale"):
        _publish(
            store,
            finalized,
            draft_uuid,
            publication_id,
            revision_id,
            fence_check=fence,
        )

    assert boundaries == ["before_stage", "before_replace"]
    assert not (
        store.root / f"revisions/{_AGENT_ID}/{revision_id}"
    ).exists()


def test_same_revision_is_idempotent_but_different_bytes_are_rejected(tmp_path):
    store = ImmutableAgentArtifactStore(tmp_path / "artifacts")
    draft_uuid, publication_id, revision_id = _ids()
    original = _bundle(revision_id, marker="original")
    first = _publish(store, original, draft_uuid, publication_id, revision_id)
    replay = _publish(store, original, draft_uuid, publication_id, revision_id)
    assert replay.bundle_sha256 == first.bundle_sha256

    replacement = _bundle(revision_id, marker="replacement")
    with pytest.raises(ArtifactIntegrityError, match="digest mismatch"):
        _publish(
            store,
            replacement,
            draft_uuid,
            publication_id,
            revision_id,
        )
    loaded = store.load(
        first.artifact_relative_path,
        expected_digest=first.bundle_sha256,
        expected_manifest_digest=first.manifest_sha256,
    )
    assert 'MARKER = "original"' in loaded.files["mcp_tools.py"]


def test_concurrent_same_revision_publication_has_one_stable_result(tmp_path):
    store = ImmutableAgentArtifactStore(tmp_path / "artifacts")
    draft_uuid, publication_id, revision_id = _ids()
    finalized = _bundle(revision_id)

    def publish_once(_index: int):
        return _publish(
            store, finalized, draft_uuid, publication_id, revision_id
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(publish_once, range(32)))

    assert {result.bundle_sha256 for result in results} == {
        finalized.bundle_sha256
    }
    revision_path = store.root / results[0].artifact_relative_path
    assert len(list(revision_path.parent.iterdir())) == 1


def test_load_rejects_traversal_extra_entries_symlinks_and_tampering(tmp_path):
    store = ImmutableAgentArtifactStore(tmp_path / "artifacts")
    draft_uuid, publication_id, revision_id = _ids()
    finalized = _bundle(revision_id)
    published = _publish(
        store, finalized, draft_uuid, publication_id, revision_id
    )

    with pytest.raises(ValueError, match="outside the revision root"):
        store.load("../escape", expected_digest=published.bundle_sha256)

    revision_path = store.root / published.artifact_relative_path
    extra = revision_path / "extra.py"
    extra.write_text("pass\n", encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError, match="contents are not exact"):
        store.load(
            published.artifact_relative_path,
            expected_digest=published.bundle_sha256,
        )
    extra.unlink()

    tools = revision_path / "mcp_tools.py"
    tools.unlink()
    tools.symlink_to(revision_path / "agent_main.py")
    with pytest.raises(ArtifactIntegrityError, match="unsafe entry"):
        store.load(
            published.artifact_relative_path,
            expected_digest=published.bundle_sha256,
        )
    tools.unlink()
    tools.write_text('MARKER = "tampered"\n', encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError, match="bundle digest mismatch"):
        store.load(
            published.artifact_relative_path,
            expected_digest=published.bundle_sha256,
        )
