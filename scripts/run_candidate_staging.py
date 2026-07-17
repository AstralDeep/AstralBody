#!/usr/bin/env python3
"""Deploy and clean one fail-closed, request-scoped feature-060 staging stack."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import importlib.util
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = REPO_ROOT / "docker-compose.staging.yml"
TRUST_SCHEMA_PATH = (
    REPO_ROOT
    / "specs/060-runtime-reliability-hardening/contracts/release-trust.schema.json"
)
WORKFLOW_PATH_RE = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/\.github/workflows/[A-Za-z0-9_.-]+$"
)
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ARTIFACT_ID_RE = re.compile(r"^[1-9][0-9]*$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_RE = re.compile(
    r"^[A-Za-z0-9.-]+(?::[0-9]{1,5})?/[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}$"
)
ENVIRONMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
SECRET_KEY_RE = re.compile(
    r"(?i)(?:secret|password|api[_-]?key|access[_-]?token|refresh[_-]?token)"
)
MAX_JSON_BYTES = 4 * 1024 * 1024


class StagingError(ValueError):
    """Raised when candidate staging cannot satisfy its qualifying contract."""


def _strict_json(path: Path) -> dict[str, Any]:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise StagingError(f"duplicate JSON key {key!r} in {path}")
            result[key] = value
        return result

    def nonfinite(value: str) -> None:
        raise StagingError(f"non-finite JSON value {value!r} in {path}")

    try:
        size = path.stat().st_size
        if size <= 0 or size > MAX_JSON_BYTES:
            raise StagingError(f"JSON size is invalid for {path}")
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=nonfinite,
        )
    except StagingError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StagingError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StagingError(f"{path} must contain one JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise StagingError(f"cannot hash fixture {path}: {exc}") from exc
    return digest.hexdigest()


def _assert_no_secret_values(value: Any, *, location: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if SECRET_KEY_RE.search(key) and child not in (None, "", [], {}):
                raise StagingError(f"fixture contains a secret-bearing value at {location}.{key}")
            _assert_no_secret_values(child, location=f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_secret_values(child, location=f"{location}[{index}]")


def validate_fixtures(manifest_path: str | Path) -> dict[str, Any]:
    """Validate the tracked synthetic 057 fixture and return public fingerprints."""

    manifest_path = Path(manifest_path).resolve(strict=True)
    manifest = _strict_json(manifest_path)
    root = manifest_path.parent
    if manifest.get("schema_version") != 1:
        raise StagingError("fixture manifest schema version is unsupported")
    if manifest.get("source_schema_revision") != "057.001":
        raise StagingError("fixture source schema revision must be 057.001")
    if manifest.get("provenance") != {
        "classification": "synthetic",
        "source": "feature-060",
    }:
        raise StagingError("fixture provenance is not the reviewed synthetic source")
    if manifest.get("sanitization") != {
        "contains_real_user_data": False,
        "contains_credentials": False,
        "reviewed": True,
    }:
        raise StagingError("fixture sanitization contract is incomplete")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise StagingError("fixture manifest has no file fingerprints")
    for relative, record in files.items():
        if (
            not isinstance(relative, str)
            or relative.startswith("/")
            or ".." in Path(relative).parts
            or not isinstance(record, dict)
            or set(record) != {"sha256", "size_bytes"}
        ):
            raise StagingError(f"fixture manifest entry is invalid: {relative!r}")
        path = (root / relative).resolve(strict=True)
        if not path.is_file() or not path.is_relative_to(root.resolve()):
            # A diagnostic copied manifest may point through a symlink; retain
            # fingerprint checking but never accept it for deployment below.
            if manifest_path.parent == (
                REPO_ROOT
                / "backend/tests/fixtures/runtime_reliability_060/staging"
            ).resolve():
                raise StagingError(f"tracked fixture escapes its root: {relative}")
        actual_digest = _sha256(path)
        actual_size = path.stat().st_size
        if actual_digest != record.get("sha256") or actual_size != record.get(
            "size_bytes"
        ):
            raise StagingError(f"fixture fingerprint drift: {relative}")

    sql_path = root / "representative-057.sql"
    realm_path = root / "keycloak-realm.json"
    try:
        sql = sql_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StagingError(f"cannot read representative SQL: {exc}") from exc
    if (
        "requires schema revision 057.001" not in sql
        or "BEGIN;" not in sql
        or "COMMIT;" not in sql
        or re.search(r"(?i)\b(?:password|access_token|refresh_token)\b", sql)
    ):
        raise StagingError("representative SQL is not a sanitized 057 transaction")
    realm = _strict_json(realm_path)
    if realm.get("users", []) != []:
        raise StagingError("tracked Keycloak realm must contain no runtime users")
    clients = realm.get("clients")
    if not isinstance(clients, list) or not clients:
        raise StagingError("tracked Keycloak realm has no public PKCE clients")
    for client in clients:
        if not isinstance(client, dict):
            raise StagingError("Keycloak client fixture is malformed")
        if client.get("publicClient") is not True or client.get("secret"):
            raise StagingError("Keycloak fixture contains a confidential client")
    _assert_no_secret_values(realm)
    return {
        "source_schema_revision": "057.001",
        "synthetic": True,
        "contains_credentials": False,
        "fixture_manifest_sha256": _sha256(manifest_path),
        "representative_dataset_sha256": _sha256(sql_path),
        "keycloak_realm_sha256": _sha256(realm_path),
    }


def validate_endpoint(endpoint: str) -> str:
    """Validate one archived non-loopback HTTPS staging endpoint."""

    try:
        parsed = urlsplit(endpoint)
    except ValueError as exc:
        raise StagingError(f"staging endpoint is malformed: {exc}") from exc
    if parsed.scheme != "https":
        raise StagingError("staging endpoint must use HTTPS")
    if not parsed.hostname:
        raise StagingError("staging endpoint has no host")
    if parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
        raise StagingError("staging endpoint cannot use a loopback host")
    if parsed.username is not None or parsed.password is not None:
        raise StagingError("staging endpoint cannot contain userinfo")
    if parsed.query:
        raise StagingError("staging endpoint cannot contain a query")
    if parsed.fragment:
        raise StagingError("staging endpoint cannot contain a fragment")
    if any(ord(character) <= 32 for character in endpoint):
        raise StagingError("staging endpoint contains whitespace/control bytes")
    return endpoint.rstrip("/")


def validate_image_reference(reference: str) -> str:
    """Require a registry image reference pinned by lowercase SHA-256 digest."""

    if not IMAGE_RE.fullmatch(reference):
        raise StagingError(f"image is not digest-qualified: {reference}")
    return reference


def _project_name(environment_id: str) -> str:
    if not ENVIRONMENT_RE.fullmatch(environment_id):
        raise StagingError("environment-id is not a bounded deployment identity")
    normalized = re.sub(r"[^a-z0-9_-]", "-", environment_id.lower())
    return f"astral060-{normalized}"[:63]


def _required_environment() -> dict[str, str]:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get(
        "ASTRAL_STAGING_RUNNER_TRUSTED"
    ) != "true":
        raise StagingError("deploy/cleanup requires the configured trusted staging runner")
    names = (
        "ASTRAL_STAGING_ENDPOINT",
        "ASTRAL_STAGING_PROBE_TOKEN",
        "STAGING_POSTGRES_IMAGE",
        "STAGING_KEYCLOAK_IMAGE",
        "STAGING_SCHEMA_BASELINE_IMAGE",
        "STAGING_RUNTIME_ENV_FILE",
        "STAGING_DB_USER",
        "STAGING_DB_PASSWORD",
        "STAGING_DB_NAME",
        "STAGING_KEYCLOAK_DB_USER",
        "STAGING_KEYCLOAK_DB_PASSWORD",
        "STAGING_KEYCLOAK_DB_NAME",
        "STAGING_KEYCLOAK_ADMIN_USER",
        "STAGING_KEYCLOAK_ADMIN_PASSWORD",
        "STAGING_BIND_PORT",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_JOB",
        "RUNNER_NAME",
    )
    values = {name: os.environ.get(name, "") for name in names}
    missing = [name for name, value in values.items() if not value.strip()]
    if missing:
        raise StagingError(f"required protected staging input is absent: {', '.join(missing)}")
    for name in (
        "STAGING_POSTGRES_IMAGE",
        "STAGING_KEYCLOAK_IMAGE",
        "STAGING_SCHEMA_BASELINE_IMAGE",
    ):
        validate_image_reference(values[name])
    runtime_env = Path(values["STAGING_RUNTIME_ENV_FILE"])
    if not runtime_env.is_absolute() or not runtime_env.is_file():
        raise StagingError("STAGING_RUNTIME_ENV_FILE must be an existing absolute protected file")
    try:
        mode = runtime_env.stat().st_mode & 0o777
    except OSError as exc:
        raise StagingError(f"cannot stat protected runtime environment file: {exc}") from exc
    if mode & 0o077:
        raise StagingError("protected runtime environment file must not be group/world accessible")
    validate_endpoint(values["ASTRAL_STAGING_ENDPOINT"])
    return values


def _run(
    arguments: Sequence[str],
    *,
    environment: Mapping[str, str],
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            list(arguments),
            cwd=REPO_ROOT,
            env=dict(environment),
            input=input_bytes,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", b"")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        raise StagingError(
            f"command failed without producing staging evidence: {str(stderr).strip()}"
        ) from exc


def _compose(environment: Mapping[str, str], project: str, *arguments: str) -> list[str]:
    del environment
    return [
        "docker",
        "compose",
        "--file",
        str(COMPOSE_PATH),
        "--project-name",
        project,
        *arguments,
    ]


def _git_identity(candidate_sha: str) -> None:
    if not GIT_SHA_RE.fullmatch(candidate_sha):
        raise StagingError("candidate-sha must be one lowercase 40-character Git SHA")
    actual = _run(
        ["git", "rev-parse", "HEAD"], environment=os.environ
    ).stdout.decode("ascii").strip()
    if actual != candidate_sha:
        raise StagingError(f"checked-out source {actual} differs from candidate {candidate_sha}")
    dirty = _run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        environment=os.environ,
    ).stdout
    if dirty:
        raise StagingError("qualifying candidate staging requires a clean checkout")


def _probe(endpoint: str, token: str, *, timeout_seconds: int = 180) -> dict[str, Any]:
    parsed = urlsplit(endpoint)
    context = ssl.create_default_context()
    deadline = time.monotonic() + timeout_seconds
    last_error = "not attempted"
    while time.monotonic() < deadline:
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            parsed.port or 443,
            timeout=10,
            context=context,
        )
        try:
            ready_path = f"{parsed.path.rstrip('/')}/readyz" or "/readyz"
            connection.request("GET", ready_path)
            response = connection.getresponse()
            response.read(1024)
            if response.status != 200:
                raise StagingError(f"readiness returned HTTP {response.status}")
            dashboard_path = f"{parsed.path.rstrip('/')}/api/dashboard" or "/api/dashboard"
            connection.request(
                "GET", dashboard_path, headers={"Authorization": f"Bearer {token}"}
            )
            dashboard_response = connection.getresponse()
            body = dashboard_response.read(MAX_JSON_BYTES + 1)
            if dashboard_response.status != 200 or len(body) > MAX_JSON_BYTES:
                raise StagingError(
                    f"authenticated dashboard returned HTTP {dashboard_response.status}"
                )
            dashboard = json.loads(body)
            capability = dashboard.get("capabilities", {}).get(
                "personal_agent_host", {}
            ).get("macos")
            if not isinstance(capability, dict):
                raise StagingError("candidate dashboard lacks the macOS host capability map")
            return capability
        except (OSError, ValueError, json.JSONDecodeError, StagingError) as exc:
            last_error = str(exc)
            time.sleep(3)
        finally:
            connection.close()
    raise StagingError(f"staging endpoint did not become reachable: {last_error}")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staging-output-", dir=path.parent) as temp:
        temporary = Path(temp) / "outputs.json"
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)


def _load_evidence_validator() -> Any:
    """Import scripts/validate_release_evidence.py for trust-schema validation."""

    path = Path(__file__).resolve().parent / "validate_release_evidence.py"
    spec = importlib.util.spec_from_file_location(
        "candidate_staging_release_validator", path
    )
    if spec is None or spec.loader is None:
        raise StagingError(f"cannot import release-evidence validator at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _trusted_manifest_identity(protected: Mapping[str, str]) -> dict[str, Any]:
    """Collect fail-closed GitHub identity for the trusted stage-deploy manifest."""

    if protected["GITHUB_JOB"] != "stage-deploy":
        raise StagingError("--trusted-manifest requires the stage-deploy GitHub job")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if not REPOSITORY_RE.fullmatch(repository):
        raise StagingError("trusted manifest requires GITHUB_REPOSITORY as owner/repo")
    workflow_name = os.environ.get("GITHUB_WORKFLOW", "")
    if not workflow_name:
        raise StagingError("trusted manifest requires GITHUB_WORKFLOW")
    workflow_path = os.environ.get("GITHUB_WORKFLOW_REF", "").partition("@")[0]
    workflow_sha = os.environ.get("GITHUB_WORKFLOW_SHA", "")
    if not WORKFLOW_PATH_RE.fullmatch(workflow_path) or not GIT_SHA_RE.fullmatch(
        workflow_sha
    ):
        raise StagingError(
            "trusted manifest requires GITHUB_WORKFLOW_REF and a 40-hex GITHUB_WORKFLOW_SHA"
        )
    builder_sha = os.environ.get("RELEASE_TRUSTED_BUILDER_SHA", "")
    builder_identity = os.environ.get("RELEASE_TRUSTED_BUILDER_IDENTITY", "")
    if not GIT_SHA_RE.fullmatch(builder_sha) or not builder_identity:
        raise StagingError(
            "trusted manifest requires RELEASE_TRUSTED_BUILDER_SHA and "
            "RELEASE_TRUSTED_BUILDER_IDENTITY"
        )
    try:
        run_attempt = int(protected["GITHUB_RUN_ATTEMPT"])
    except ValueError as exc:
        raise StagingError("GITHUB_RUN_ATTEMPT must be an integer") from exc
    artifact_id = os.environ.get("ASTRAL_STAGE_OUTPUTS_ARTIFACT_ID", "1")
    if not ARTIFACT_ID_RE.fullmatch(artifact_id):
        raise StagingError("ASTRAL_STAGE_OUTPUTS_ARTIFACT_ID must be a positive integer")
    return {
        "repository": repository,
        "workflow_name": workflow_name,
        "workflow_ref": f"{workflow_path}@{workflow_sha}",
        "builder_sha": builder_sha,
        "builder_identity": builder_identity,
        "run_attempt": run_attempt,
        "artifact_id": artifact_id,
    }


def _write_trusted_manifest(
    *,
    path: Path,
    identity: Mapping[str, Any],
    protected: Mapping[str, str],
    candidate_sha: str,
    environment_id: str,
    output: Mapping[str, Any],
    outputs_path: Path,
) -> None:
    """Emit one schema-valid trusted_stage_deploy manifest beside ``--outputs``.

    The self-declared artifact/builder values are never a trust root: the
    protected trusted-builder workflow reconstructs run/job/artifact identity
    from the GitHub API for the current run and ignores producer-uploaded
    bytes as authority (release-trust.schema.json $comment).
    """

    repository = str(identity["repository"])
    run_id = protected["GITHUB_RUN_ID"]
    member = outputs_path.name
    artifact_name = os.environ.get(
        "ASTRAL_STAGE_OUTPUTS_ARTIFACT_NAME", f"stage-outputs-{run_id}"
    )
    # The trust deployment identity is the deploy output minus the two
    # evidence-only fields (deployed_at, macos_personal_agent_host).
    deployment = {
        key: value
        for key, value in output.items()
        if key not in {"deployed_at", "macos_personal_agent_host"}
    }
    manifest = {
        "document_type": "trusted_stage_deploy",
        "schema_version": 1,
        "manifest_id": str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "astraldeep:060:trusted-stage-deploy:"
                f"{repository}:{run_id}:{identity['run_attempt']}:{environment_id}",
            )
        ),
        "repository": repository,
        "candidate_sha": candidate_sha,
        "workflow": {
            "name": identity["workflow_name"],
            "run_id": run_id,
            "run_attempt": identity["run_attempt"],
            "job_id": protected["GITHUB_JOB"],
        },
        "workflow_ref": identity["workflow_ref"],
        "runner": {
            "os": os.environ.get("ASTRAL_RUNNER_OS", "linux"),
            "architecture": os.environ.get("ASTRAL_RUNNER_ARCH", "x86_64"),
            "runner_image": os.environ.get("ImageOS", "self-hosted-staging"),
            "runner_name": protected["RUNNER_NAME"],
            "runner_environment": os.environ.get(
                "ASTRAL_RUNNER_ENVIRONMENT", "self_hosted"
            ),
        },
        "trusted_builder": {
            "repository": repository,
            "workflow_path": ".github/workflows/release-trusted-builder.yml",
            "signer_digest": identity["builder_sha"],
            "certificate_identity": identity["builder_identity"],
        },
        "generated_at": output["deployed_at"],
        "stage_outputs_artifact": {
            "kind": "github_actions_artifact_member",
            "repository": repository,
            "run_id": run_id,
            "run_attempt": identity["run_attempt"],
            "artifact_id": identity["artifact_id"],
            "artifact_name": artifact_name,
            "member": member,
            "immutable_reference": (
                f"gh://{repository}/runs/{run_id}/attempts/"
                f"{identity['run_attempt']}/artifacts/{identity['artifact_id']}/"
                f"members/{member}"
            ),
            "sha256": _sha256(outputs_path),
        },
        "deployment": deployment,
    }
    validator = _load_evidence_validator()
    trust_schema = validator.load_json_document(TRUST_SCHEMA_PATH)
    try:
        validator.validate_document(manifest, trust_schema)
    except validator.ReleaseEvidenceError as exc:
        raise StagingError(
            f"trusted stage-deploy manifest is schema-invalid: {exc}"
        ) from exc
    _atomic_json(path, manifest)


def _deploy(args: argparse.Namespace) -> int:
    protected = _required_environment()
    if not args.leave_running:
        raise StagingError("qualifying deploy must use --leave-running until matrix cleanup")
    trusted_manifest = getattr(args, "trusted_manifest", None)
    identity = _trusted_manifest_identity(protected) if trusted_manifest else None
    candidate_image = validate_image_reference(args.candidate_image)
    _git_identity(args.candidate_sha)
    fixtures = validate_fixtures(args.fixture_manifest)
    tracked_fixture_root = (
        REPO_ROOT / "backend/tests/fixtures/runtime_reliability_060/staging"
    ).resolve()
    if Path(args.fixture_manifest).resolve().parent != tracked_fixture_root:
        raise StagingError("qualifying deploy must use the tracked fixture root")
    project = _project_name(args.environment_id)
    environment = dict(os.environ)
    environment.update(
        {
            "STAGING_PROJECT_NAME": project,
            "ASTRAL_CANDIDATE_IMAGE": candidate_image,
        }
    )
    _run(_compose(environment, project, "config", "--quiet"), environment=environment)
    _run(
        _compose(environment, project, "up", "--detach", "postgres", "keycloak-postgres", "keycloak"),
        environment=environment,
    )
    _run(
        _compose(
            environment,
            project,
            "--profile",
            "bootstrap",
            "run",
            "--rm",
            "schema-baseline",
        ),
        environment=environment,
    )
    fixture_bytes = (
        Path(args.fixture_manifest).resolve().parent / "representative-057.sql"
    ).read_bytes()
    _run(
        _compose(
            environment,
            project,
            "exec",
            "--no-TTY",
            "postgres",
            "psql",
            "--username",
            protected["STAGING_DB_USER"],
            "--dbname",
            protected["STAGING_DB_NAME"],
            "--set",
            "ON_ERROR_STOP=1",
        ),
        environment=environment,
        input_bytes=fixture_bytes,
    )
    _run(
        _compose(environment, project, "up", "--detach", "astraldeep"),
        environment=environment,
    )
    capability = _probe(
        protected["ASTRAL_STAGING_ENDPOINT"],
        protected["ASTRAL_STAGING_PROBE_TOKEN"],
    )
    revision = _run(
        _compose(
            environment,
            project,
            "exec",
            "--no-TTY",
            "postgres",
            "psql",
            "--tuples-only",
            "--no-align",
            "--username",
            protected["STAGING_DB_USER"],
            "--dbname",
            protected["STAGING_DB_NAME"],
            "--command",
            "SELECT value FROM schema_meta WHERE key='revision';",
        ),
        environment=environment,
    ).stdout.decode("utf-8").strip()
    if revision != "060.004":
        raise StagingError(f"candidate normal startup ended at schema {revision!r}")
    ps_bytes = _run(
        _compose(environment, project, "ps", "--format", "json"),
        environment=environment,
    ).stdout
    candidate_digest = candidate_image.rsplit("@sha256:", 1)[1]
    capability_bytes = json.dumps(
        capability,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    deployed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    output = {
        "environment_id": args.environment_id,
        "request_namespace": project,
        "topology": "shared_reachable_ephemeral",
        "deployment_run_id": protected["GITHUB_RUN_ID"],
        "deployed_at": deployed_at,
        "endpoint": validate_endpoint(protected["ASTRAL_STAGING_ENDPOINT"]),
        "candidate_image_reference": candidate_image,
        "candidate_image_sha256": candidate_digest,
        "representative_dataset_sha256": fixtures[
            "representative_dataset_sha256"
        ],
        "fixture_manifest_sha256": fixtures["fixture_manifest_sha256"],
        "keycloak_realm_sha256": fixtures["keycloak_realm_sha256"],
        "source_schema_revision": "057.001",
        "migrated_schema_revision": "060.004",
        "authentication_posture": "real_keycloak_oidc",
        "database_posture": "representative_postgresql",
        "worker_paths": ["background", "scheduler", "maintenance"],
        "macos_personal_agent_host": {
            **capability,
            "source": "candidate_capability_map",
            "manifest_sha256": hashlib.sha256(capability_bytes).hexdigest(),
        },
        "capability_manifest_sha256": hashlib.sha256(capability_bytes).hexdigest(),
        "service_identity_sha256": hashlib.sha256(ps_bytes).hexdigest(),
    }
    _atomic_json(Path(args.outputs), output)
    if trusted_manifest and identity is not None:
        _write_trusted_manifest(
            path=Path(trusted_manifest),
            identity=identity,
            protected=protected,
            candidate_sha=args.candidate_sha,
            environment_id=args.environment_id,
            output=output,
            outputs_path=Path(args.outputs),
        )
    print(
        json.dumps(
            {
                "candidate_sha": args.candidate_sha,
                "environment_id": args.environment_id,
                "output": str(Path(args.outputs)),
                "qualifying_decision": False,
                "requires_protected_attestation": True,
            },
            sort_keys=True,
        )
    )
    return 0


def _cleanup(args: argparse.Namespace) -> int:
    _required_environment()
    project = _project_name(args.environment_id)
    environment = dict(os.environ)
    environment["STAGING_PROJECT_NAME"] = project
    # Project scoping is mandatory: no global container, image, or volume cleanup.
    _run(
        _compose(
            environment,
            project,
            "down",
            "--volumes",
            "--remove-orphans",
            "--timeout",
            "30",
        ),
        environment=environment,
    )
    print(json.dumps({"environment_id": args.environment_id, "removed": True}))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fixtures = commands.add_parser("validate-fixtures")
    fixtures.add_argument("--manifest", required=True)
    deploy = commands.add_parser("deploy")
    deploy.add_argument("--candidate-sha", required=True)
    deploy.add_argument("--candidate-image", required=True)
    deploy.add_argument("--fixture-manifest", required=True)
    deploy.add_argument("--environment-id", required=True)
    deploy.add_argument("--outputs", required=True)
    deploy.add_argument("--leave-running", action="store_true")
    deploy.add_argument("--trusted-manifest")
    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("--environment-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute fixture validation, protected deploy, or exact-namespace cleanup."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "validate-fixtures":
            print(json.dumps(validate_fixtures(args.manifest), sort_keys=True))
            return 0
        if args.command == "deploy":
            return _deploy(args)
        if args.command == "cleanup":
            return _cleanup(args)
        raise StagingError(f"unknown staging command: {args.command}")
    except StagingError as exc:
        print(f"candidate staging rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
