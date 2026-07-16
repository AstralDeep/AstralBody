"""Durable immutable publication for user-authored agent revisions.

The runtime database stores only a validated relative path and digests.  This
module owns the corresponding filesystem transaction: write a revision into a
generation-specific staging directory, flush every byte and directory entry,
validate the staged bytes, then atomically rename that directory into the
immutable revision namespace.  Runtime activation remains owned by
``agent_lifecycle``; this seam never starts or promotes an agent.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping, Optional
import uuid

from orchestrator.agent_generator import BYO_BUNDLE_FILENAMES, FinalizedBYOBundle


_SHA256 = re.compile(r"[0-9a-f]{64}")
_SAFE_AGENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}")
_MANIFEST_FILENAME = "manifest.json"
_MAX_EXECUTABLE_BYTES = 2 * 1024 * 1024
_MAX_MANIFEST_BYTES = 64 * 1024


class ArtifactPublicationError(RuntimeError):
    """Base class for safe immutable-publication failures."""


class ArtifactCollisionError(ArtifactPublicationError):
    """An immutable revision path already identifies different bytes."""


class ArtifactIntegrityError(ArtifactPublicationError):
    """Published bytes do not match their manifest or expected digest."""


@dataclass(frozen=True)
class PublishedAgentArtifact:
    """One re-hashed immutable agent revision loaded from durable storage."""

    artifact_relative_path: str
    bundle_sha256: str
    manifest_sha256: str
    files: Mapping[str, str]
    manifest: Mapping[str, Any]
    manifest_json: str

    def manifest_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible manifest copy."""

        return json.loads(self.manifest_json)


def default_personal_agent_artifact_root() -> Path:
    """Return the configured persistent root for immutable agent revisions."""

    configured = os.getenv("PERSONAL_AGENT_ARTIFACT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    backend_dir = Path(__file__).resolve().parent.parent
    return (backend_dir / "data" / "personal-agent-artifacts").resolve()


def _uuid_text(value: Any, field_name: str) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a UUID") from exc
    if parsed.version != 4:
        raise ValueError(f"{field_name} must be a UUID4")
    return str(parsed)


def _safe_agent_id(value: Any) -> str:
    if not isinstance(value, str) or _SAFE_AGENT_ID.fullmatch(value) is None:
        raise ValueError("agent_id is not a safe path component")
    if value in {".", ".."}:
        raise ValueError("agent_id is not a safe path component")
    return value


def _canonical_bundle_digest(files: Mapping[str, str]) -> str:
    canonical = json.dumps(
        {name: files[name] for name in BYO_BUNDLE_FILENAMES},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


class ImmutableAgentArtifactStore:
    """Publish and load exact, immutable three-file BYO agent revisions.

    Args:
        root: Persistent same-filesystem root.  When omitted,
            :func:`default_personal_agent_artifact_root` is used.
    """

    def __init__(self, root: Optional[os.PathLike[str] | str] = None) -> None:
        selected = Path(root) if root is not None else default_personal_agent_artifact_root()
        self._root = selected.expanduser().resolve()
        self._staging_root = self._root / "staging"
        self._revision_root = self._root / "revisions"
        self._ensure_directory(self._root)
        self._ensure_directory(self._staging_root)
        self._ensure_directory(self._revision_root)

    @property
    def root(self) -> Path:
        """Resolved storage root (primarily for diagnostics and tests)."""

        return self._root

    @staticmethod
    def _ensure_directory(path: Path) -> None:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise ArtifactPublicationError("artifact directory is not trustworthy")

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _fault(
        fault_hook: Optional[Callable[[str], None]], boundary: str
    ) -> None:
        if fault_hook is not None:
            fault_hook(boundary)

    @contextmanager
    def _publication_lock(self, lock_name: str = ".publication.lock") -> Iterator[None]:
        lock_path = self._root / lock_name
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @staticmethod
    def _write_durable_file(path: Path, content: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            view = memoryview(content)
            while view:
                try:
                    written = os.write(descriptor, view)
                except InterruptedError:
                    continue
                if written <= 0:  # pragma: no cover - defensive OS invariant
                    raise OSError("short artifact write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _remove_stale_staging(path: Path) -> None:
        if not path.exists():
            return
        if path.is_symlink() or not path.is_dir():
            raise ArtifactPublicationError("staging path is not a directory")
        shutil.rmtree(path)

    def _revision_relative_path(self, agent_id: str, revision_id: str) -> str:
        return PurePosixPath("revisions", agent_id, revision_id).as_posix()

    def publish(
        self,
        finalized: FinalizedBYOBundle,
        *,
        draft_uuid: str,
        source_state_revision: int,
        publication_id: str,
        agent_id: str,
        revision_id: str,
        fence_check: Optional[Callable[[str], None]] = None,
        fault_hook: Optional[Callable[[str], None]] = None,
    ) -> PublishedAgentArtifact:
        """Durably publish one finalized revision, or replay the same bytes.

        ``fence_check`` is called before staging and before the atomic replace.
        A database-backed caller uses it to re-check the current draft,
        generation claim, and operation execution generation.  The filesystem
        store deliberately does not own those database transitions.
        """

        revision_lock = hashlib.sha256(
            f"{agent_id}\0{revision_id}".encode("utf-8")
        ).hexdigest()
        with self._publication_lock(f".revision-{revision_lock}.lock"):
            return self._publish_locked(
                finalized,
                draft_uuid=draft_uuid,
                source_state_revision=source_state_revision,
                publication_id=publication_id,
                agent_id=agent_id,
                revision_id=revision_id,
                fence_check=fence_check,
                fault_hook=fault_hook,
            )

    def _publish_locked(
        self,
        finalized: FinalizedBYOBundle,
        *,
        draft_uuid: str,
        source_state_revision: int,
        publication_id: str,
        agent_id: str,
        revision_id: str,
        fence_check: Optional[Callable[[str], None]],
        fault_hook: Optional[Callable[[str], None]],
    ) -> PublishedAgentArtifact:
        """Publish while holding the cross-process revision lock."""

        if not isinstance(finalized, FinalizedBYOBundle):
            raise TypeError("finalized must be FinalizedBYOBundle")
        draft_uuid = _uuid_text(draft_uuid, "draft_uuid")
        publication_id = _uuid_text(publication_id, "publication_id")
        revision_id = _uuid_text(revision_id, "revision_id")
        agent_id = _safe_agent_id(agent_id)
        if type(source_state_revision) is not int or source_state_revision < 0:
            raise ValueError("source_state_revision must be non-negative")
        if finalized.manifest.get("agent_id") != agent_id:
            raise ArtifactIntegrityError("finalized manifest agent does not match path")
        if finalized.manifest.get("revision_id") != revision_id:
            raise ArtifactIntegrityError("finalized manifest revision does not match path")
        if _SHA256.fullmatch(finalized.bundle_sha256 or "") is None:
            raise ArtifactIntegrityError("finalized bundle digest is invalid")

        relative_path = self._revision_relative_path(agent_id, revision_id)
        revision_path = self._root.joinpath(*PurePosixPath(relative_path).parts)
        staging_path = (
            self._staging_root
            / draft_uuid
            / str(source_state_revision)
            / publication_id
        )
        manifest_bytes = finalized.manifest_json.encode("utf-8")
        manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()

        if fence_check is not None:
            fence_check("before_stage")
        self._fault(fault_hook, "before_stage")

        with self._publication_lock():
            if revision_path.exists():
                existing = self.load(
                    relative_path,
                    expected_digest=finalized.bundle_sha256,
                    expected_manifest_digest=manifest_digest,
                )
                self._remove_stale_staging(staging_path)
                return existing

        self._ensure_directory(staging_path.parent)
        self._fsync_directory(staging_path.parent)
        self._remove_stale_staging(staging_path)
        staging_path.mkdir(mode=0o700)
        self._fault(fault_hook, "after_staging_directory")

        for filename in BYO_BUNDLE_FILENAMES:
            content = finalized.files[filename].encode("utf-8")
            if len(content) > _MAX_EXECUTABLE_BYTES:
                raise ArtifactPublicationError("agent executable exceeds size limit")
            self._write_durable_file(staging_path / filename, content)
            self._fault(fault_hook, f"after_file:{filename}")
        if len(manifest_bytes) > _MAX_MANIFEST_BYTES:
            raise ArtifactPublicationError("runtime manifest exceeds size limit")
        self._write_durable_file(staging_path / _MANIFEST_FILENAME, manifest_bytes)
        self._fault(fault_hook, "after_file:manifest.json")
        self._fsync_directory(staging_path)
        self._fault(fault_hook, "after_staging_fsync")

        staged = self._load_path(
            staging_path,
            relative_path=relative_path,
            expected_digest=finalized.bundle_sha256,
            expected_manifest_digest=manifest_digest,
        )
        self._fault(fault_hook, "after_validate")
        if fence_check is not None:
            fence_check("before_replace")
        self._fault(fault_hook, "before_replace")

        self._ensure_directory(revision_path.parent)
        self._fsync_directory(revision_path.parent)
        with self._publication_lock():
            if revision_path.exists():
                existing = self.load(
                    relative_path,
                    expected_digest=finalized.bundle_sha256,
                    expected_manifest_digest=manifest_digest,
                )
                self._remove_stale_staging(staging_path)
                return existing
            os.replace(staging_path, revision_path)
            self._fault(fault_hook, "after_replace")
            self._fsync_directory(revision_path)
            self._fsync_directory(revision_path.parent)
            self._fault(fault_hook, "after_revision_fsync")

        # Re-open and re-hash the durable namespace.  Returning the staged
        # object would hide corruption between validate and rename on a broken
        # or externally modified filesystem.
        published = self.load(
            relative_path,
            expected_digest=staged.bundle_sha256,
            expected_manifest_digest=staged.manifest_sha256,
        )
        return published

    def load(
        self,
        artifact_relative_path: str,
        *,
        expected_digest: str,
        expected_manifest_digest: Optional[str] = None,
    ) -> PublishedAgentArtifact:
        """Load and re-hash one immutable revision beneath this store's root."""

        if _SHA256.fullmatch(expected_digest or "") is None:
            raise ValueError("expected_digest must be lowercase SHA-256")
        if (
            expected_manifest_digest is not None
            and _SHA256.fullmatch(expected_manifest_digest) is None
        ):
            raise ValueError("expected_manifest_digest must be lowercase SHA-256")
        if not isinstance(artifact_relative_path, str):
            raise ValueError("artifact_relative_path must be text")
        relative = PurePosixPath(artifact_relative_path)
        if (
            relative.is_absolute()
            or "\\" in artifact_relative_path
            or len(relative.parts) != 3
            or relative.parts[0] != "revisions"
            or ".." in relative.parts
        ):
            raise ValueError("artifact_relative_path is outside the revision root")
        _safe_agent_id(relative.parts[1])
        _uuid_text(relative.parts[2], "revision_id")
        path = self._root.joinpath(*relative.parts)
        return self._load_path(
            path,
            relative_path=relative.as_posix(),
            expected_digest=expected_digest,
            expected_manifest_digest=expected_manifest_digest,
        )

    def _load_path(
        self,
        path: Path,
        *,
        relative_path: str,
        expected_digest: str,
        expected_manifest_digest: Optional[str],
    ) -> PublishedAgentArtifact:
        if path.is_symlink() or not path.is_dir():
            raise ArtifactIntegrityError("artifact revision directory is unavailable")
        expected_names = set(BYO_BUNDLE_FILENAMES) | {_MANIFEST_FILENAME}
        entries = list(path.iterdir())
        if {entry.name for entry in entries} != expected_names:
            raise ArtifactIntegrityError("artifact revision contents are not exact")
        if any(entry.is_symlink() or not entry.is_file() for entry in entries):
            raise ArtifactIntegrityError("artifact revision contains an unsafe entry")

        files: dict[str, str] = {}
        for filename in BYO_BUNDLE_FILENAMES:
            raw = (path / filename).read_bytes()
            if len(raw) > _MAX_EXECUTABLE_BYTES:
                raise ArtifactIntegrityError("agent executable exceeds size limit")
            try:
                files[filename] = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ArtifactIntegrityError("agent executable is not UTF-8") from exc

        digest = _canonical_bundle_digest(files)
        if digest != expected_digest:
            raise ArtifactIntegrityError("artifact bundle digest mismatch")

        manifest_bytes = (path / _MANIFEST_FILENAME).read_bytes()
        if len(manifest_bytes) > _MAX_MANIFEST_BYTES:
            raise ArtifactIntegrityError("runtime manifest exceeds size limit")
        manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
        if (
            expected_manifest_digest is not None
            and manifest_digest != expected_manifest_digest
        ):
            raise ArtifactIntegrityError("runtime manifest digest mismatch")
        try:
            manifest_json = manifest_bytes.decode("utf-8")
            manifest = json.loads(manifest_json)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactIntegrityError("runtime manifest is invalid JSON") from exc
        if not isinstance(manifest, dict):
            raise ArtifactIntegrityError("runtime manifest must be an object")

        relative = PurePosixPath(relative_path)
        if (
            manifest.get("bundle_sha256") != digest
            or manifest.get("agent_id") != relative.parts[1]
            or manifest.get("revision_id") != relative.parts[2]
        ):
            raise ArtifactIntegrityError("runtime manifest identity mismatch")
        manifest_files = manifest.get("files")
        if not isinstance(manifest_files, list) or tuple(
            item.get("name") if isinstance(item, dict) else None
            for item in manifest_files
        ) != BYO_BUNDLE_FILENAMES:
            raise ArtifactIntegrityError("runtime manifest file inventory is invalid")
        for item in manifest_files:
            name = item["name"]
            raw = files[name].encode("utf-8")
            if (
                item.get("sha256") != hashlib.sha256(raw).hexdigest()
                or item.get("size_bytes") != len(raw)
            ):
                raise ArtifactIntegrityError("runtime manifest file metadata mismatch")

        return PublishedAgentArtifact(
            artifact_relative_path=relative.as_posix(),
            bundle_sha256=digest,
            manifest_sha256=manifest_digest,
            files=MappingProxyType(files),
            manifest=_freeze_json(manifest),
            manifest_json=manifest_json,
        )


__all__ = [
    "ArtifactCollisionError",
    "ArtifactIntegrityError",
    "ArtifactPublicationError",
    "ImmutableAgentArtifactStore",
    "PublishedAgentArtifact",
    "default_personal_agent_artifact_root",
]
