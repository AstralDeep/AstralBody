"""Fail-closed candidate-staging driver and topology contracts (T103/T107)."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "run_candidate_staging.py"
COMPOSE = REPO_ROOT / "docker-compose.staging.yml"
MANIFEST = (
    REPO_ROOT
    / "backend/tests/fixtures/runtime_reliability_060/staging/fixture-manifest.json"
)

if not (
    (REPO_ROOT / "scripts").is_dir() and (REPO_ROOT / "specs").is_dir()
):  # repo root absent inside the product image
    pytest.skip(
        "repo-root tooling files are not part of the product image",
        allow_module_level=True,
    )


def _load_driver() -> Any:
    spec = importlib.util.spec_from_file_location("candidate_staging_060", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver() -> Any:
    return _load_driver()


def test_tracked_fixture_set_validates_and_reports_only_nonsecret_identity(
    driver: Any,
) -> None:
    result = driver.validate_fixtures(MANIFEST)
    assert result["source_schema_revision"] == "057.001"
    assert result["synthetic"] is True
    assert result["contains_credentials"] is False
    assert len(result["fixture_manifest_sha256"]) == 64
    assert len(result["representative_dataset_sha256"]) == 64
    assert len(result["keycloak_realm_sha256"]) == 64
    serialized = json.dumps(result, sort_keys=True).lower()
    assert "password" not in serialized
    assert "access_token" not in serialized


def test_fixture_validation_detects_manifest_fingerprint_drift(
    driver: Any, tmp_path: Path
) -> None:
    fixture_root = MANIFEST.parent
    copied = copy.deepcopy(json.loads(MANIFEST.read_text(encoding="utf-8")))
    copied["files"]["representative-057.sql"]["sha256"] = "0" * 64
    path = tmp_path / "fixture-manifest.json"
    path.write_text(json.dumps(copied), encoding="utf-8")
    # Keep the tampered manifest beside symlinks to the real public fixtures.
    for name in ("representative-057.sql", "keycloak-realm.json", "legacy-agent-root"):
        (tmp_path / name).symlink_to(fixture_root / name, target_is_directory=name.endswith("root"))
    with pytest.raises(driver.StagingError, match="fingerprint"):
        driver.validate_fixtures(path)


@pytest.mark.parametrize(
    ("endpoint", "message"),
    [
        ("http://stage.astraldeep.invalid", "HTTPS"),
        ("https://localhost:8001", "loopback"),
        ("https://user@stage.astraldeep.invalid", "userinfo"),
        ("https://stage.astraldeep.invalid?candidate=x", "query"),
        ("https://stage.astraldeep.invalid/#fragment", "fragment"),
        ("https:///missing-host", "no host"),
        ("https://stage.astraldeep.invalid/path\n", "whitespace"),
        ("https://[malformed", "malformed"),
    ],
)
def test_staging_endpoint_must_be_archivable_nonlocal_https(
    driver: Any, endpoint: str, message: str
) -> None:
    with pytest.raises(driver.StagingError, match=message):
        driver.validate_endpoint(endpoint)


@pytest.mark.parametrize(
    "reference",
    [
        "astraldeep:latest",
        "ghcr.io/AstralDeep/AstralDeep:060",
        "http://registry.invalid/image@sha256:" + "a" * 64,
        "ghcr.io/AstralDeep/AstralDeep@sha256:" + "A" * 64,
    ],
)
def test_candidate_and_dependency_images_must_be_digest_qualified(
    driver: Any, reference: str
) -> None:
    with pytest.raises(driver.StagingError, match="digest-qualified"):
        driver.validate_image_reference(reference)


def test_deploy_fails_before_docker_without_protected_runner_inputs() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "deploy",
            "--candidate-sha",
            "a" * 40,
            "--candidate-image",
            "ghcr.io/AstralDeep/AstralDeep@sha256:" + "b" * 64,
            "--fixture-manifest",
            str(MANIFEST),
            "--environment-id",
            "stage-060-test",
            "--outputs",
            "/tmp/stage-060-output-must-not-exist.json",
            "--leave-running",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    assert completed.returncode == 2
    assert "trusted staging runner" in completed.stderr
    assert not Path("/tmp/stage-060-output-must-not-exist.json").exists()


def test_compose_topology_has_real_baseline_restore_auth_database_and_candidate_paths() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    for service in ("postgres:", "keycloak:", "schema-baseline:", "astraldeep:"):
        assert service in source
    for variable in (
        "STAGING_POSTGRES_IMAGE",
        "STAGING_KEYCLOAK_IMAGE",
        "STAGING_SCHEMA_BASELINE_IMAGE",
        "ASTRAL_CANDIDATE_IMAGE",
    ):
        assert "${" + variable in source
    assert "representative-057.sql" not in source, (
        "the populated fixture must be restored after baseline 057 startup, not as empty-db init SQL"
    )
    assert "keycloak-realm.json" in source
    assert "latest" not in source.lower()
    assert "build:" not in source
    assert "mock" not in source.lower()


def test_cli_exposes_only_validate_deploy_and_scoped_cleanup_commands() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert "validate-fixtures" in completed.stdout
    assert "deploy" in completed.stdout
    assert "cleanup" in completed.stdout
    source = SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert "docker compose down" not in source
    assert "docker system prune" not in source


def _protected_environment(runtime_env: Path) -> dict[str, str]:
    image = "registry.example.invalid/astral/dependency@sha256:" + "a" * 64
    return {
        "ASTRAL_STAGING_ENDPOINT": "https://stage-060.example.invalid",
        "ASTRAL_STAGING_PROBE_TOKEN": "test-only-probe-value",
        "STAGING_POSTGRES_IMAGE": image,
        "STAGING_KEYCLOAK_IMAGE": image,
        "STAGING_SCHEMA_BASELINE_IMAGE": image,
        "STAGING_RUNTIME_ENV_FILE": str(runtime_env),
        "STAGING_DB_USER": "astral",
        "STAGING_DB_PASSWORD": "test-only-database-value",
        "STAGING_DB_NAME": "astral",
        "STAGING_KEYCLOAK_DB_USER": "keycloak",
        "STAGING_KEYCLOAK_DB_PASSWORD": "test-only-keycloak-database-value",
        "STAGING_KEYCLOAK_DB_NAME": "keycloak",
        "STAGING_KEYCLOAK_ADMIN_USER": "bootstrap-admin",
        "STAGING_KEYCLOAK_ADMIN_PASSWORD": "test-only-bootstrap-value",
        "STAGING_BIND_PORT": "18061",
        "GITHUB_RUN_ID": "6001",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_JOB": "stage-deploy",
        "RUNNER_NAME": "trusted-staging-1",
    }


def test_protected_environment_validation_accepts_only_private_complete_inputs(
    driver: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("ASTRAL_ENV=staging\n", encoding="utf-8")
    runtime_env.chmod(0o600)
    values = _protected_environment(runtime_env)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("ASTRAL_STAGING_RUNNER_TRUSTED", "true")
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    assert driver._required_environment() == values

    runtime_env.chmod(0o644)
    with pytest.raises(driver.StagingError, match="group/world"):
        driver._required_environment()
    runtime_env.chmod(0o600)
    monkeypatch.delenv("GITHUB_RUN_ID")
    with pytest.raises(driver.StagingError, match="absent"):
        driver._required_environment()

    monkeypatch.setenv("GITHUB_RUN_ID", "6001")
    monkeypatch.setenv("STAGING_POSTGRES_IMAGE", "postgres:mutable")
    with pytest.raises(driver.StagingError, match="digest-qualified"):
        driver._required_environment()
    monkeypatch.setenv(
        "STAGING_POSTGRES_IMAGE",
        "registry.example.invalid/astral/dependency@sha256:" + "a" * 64,
    )
    monkeypatch.setenv("STAGING_RUNTIME_ENV_FILE", "relative.env")
    with pytest.raises(driver.StagingError, match="absolute protected file"):
        driver._required_environment()


def test_git_identity_requires_exact_clean_head(
    driver: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = "b" * 40

    def clean(arguments: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        output = f"{candidate}\n".encode() if arguments[1:3] == ["rev-parse", "HEAD"] else b""
        return subprocess.CompletedProcess(arguments, 0, output, b"")

    monkeypatch.setattr(driver, "_run", clean)
    driver._git_identity(candidate)
    with pytest.raises(driver.StagingError, match="candidate-sha"):
        driver._git_identity("not-a-sha")

    def wrong(arguments: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(arguments, 0, ("c" * 40 + "\n").encode(), b"")

    monkeypatch.setattr(driver, "_run", wrong)
    with pytest.raises(driver.StagingError, match="differs"):
        driver._git_identity(candidate)

    calls = 0

    def dirty(arguments: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal calls
        calls += 1
        output = f"{candidate}\n".encode() if calls == 1 else b"?? generated.txt\n"
        return subprocess.CompletedProcess(arguments, 0, output, b"")

    monkeypatch.setattr(driver, "_run", dirty)
    with pytest.raises(driver.StagingError, match="clean checkout"):
        driver._git_identity(candidate)


def test_probe_reads_real_readiness_and_authenticated_capability_shape(
    driver: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    capability = {
        "supported": False,
        "runtime_contract_versions": [],
        "source_feature": None,
    }

    class Response:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self.body = body

        def read(self, _limit: int) -> bytes:
            return self.body

    class Connection:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.responses = [
                Response(200, b"ready"),
                Response(200, json.dumps({"capabilities": {"personal_agent_host": {"macos": capability}}}).encode()),
            ]
            self.requests: list[tuple[Any, ...]] = []

        def request(self, *args: Any, **kwargs: Any) -> None:
            self.requests.append((*args, kwargs))

        def getresponse(self) -> Response:
            return self.responses.pop(0)

        def close(self) -> None:
            return None

    monkeypatch.setattr(driver.http.client, "HTTPSConnection", Connection)
    monkeypatch.setattr(driver.ssl, "create_default_context", object)
    assert driver._probe("https://stage.example.invalid/request-1", "opaque") == capability


def test_deploy_and_cleanup_execute_exact_request_scoped_sequence(
    driver: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("ASTRAL_ENV=staging\n", encoding="utf-8")
    runtime_env.chmod(0o600)
    protected = _protected_environment(runtime_env)
    monkeypatch.setattr(driver, "_required_environment", lambda: protected)
    monkeypatch.setattr(driver, "_git_identity", lambda _candidate: None)
    capability = {"supported": False, "runtime_contract_versions": [], "source_feature": None}
    monkeypatch.setattr(driver, "_probe", lambda _endpoint, _token: capability)
    calls: list[tuple[list[str], bytes | None]] = []

    def run(
        arguments: list[str],
        *,
        environment: dict[str, str],
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        del environment
        calls.append((list(arguments), input_bytes))
        if "SELECT value FROM schema_meta" in arguments[-1]:
            output = b"060.004\n"
        elif "ps" in arguments and "--format" in arguments:
            output = b'[{"Service":"astraldeep"}]\n'
        else:
            output = b""
        return subprocess.CompletedProcess(arguments, 0, output, b"")

    monkeypatch.setattr(driver, "_run", run)
    output_path = tmp_path / "outputs" / "stage.json"
    candidate = "b" * 40
    candidate_image = "ghcr.io/astraldeep/astraldeep@sha256:" + "c" * 64
    args = SimpleNamespace(
        leave_running=True,
        candidate_image=candidate_image,
        candidate_sha=candidate,
        fixture_manifest=str(MANIFEST),
        environment_id="request-060-1",
        outputs=str(output_path),
    )
    assert driver._deploy(args) == 0
    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["candidate_image_reference"] == candidate_image
    assert output["candidate_image_sha256"] == "c" * 64
    assert output["migrated_schema_revision"] == "060.004"
    assert output["authentication_posture"] == "real_keycloak_oidc"
    assert any(input_bytes and b"requires schema revision 057.001" in input_bytes for _, input_bytes in calls)
    commands = [arguments for arguments, _ in calls]
    assert any("schema-baseline" in command for command in commands)
    assert any(command[-2:] == ["--detach", "astraldeep"] for command in commands)
    assert "requires_protected_attestation" in capsys.readouterr().out

    calls.clear()
    assert driver._cleanup(SimpleNamespace(environment_id="request-060-1")) == 0
    assert calls[0][0][-5:] == ["down", "--volumes", "--remove-orphans", "--timeout", "30"]


def test_deploy_rejects_early_cleanup_and_untracked_fixture_root(
    driver: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("ASTRAL_ENV=staging\n", encoding="utf-8")
    runtime_env.chmod(0o600)
    monkeypatch.setattr(driver, "_required_environment", lambda: _protected_environment(runtime_env))
    common = {
        "candidate_image": "ghcr.io/astraldeep/astraldeep@sha256:" + "c" * 64,
        "candidate_sha": "b" * 40,
        "fixture_manifest": str(MANIFEST),
        "environment_id": "request-060-early",
        "outputs": str(tmp_path / "out.json"),
    }
    with pytest.raises(driver.StagingError, match="leave-running"):
        driver._deploy(SimpleNamespace(leave_running=False, **common))

    monkeypatch.setattr(driver, "_git_identity", lambda _candidate: None)
    monkeypatch.setattr(
        driver,
        "validate_fixtures",
        lambda _manifest: {
            "representative_dataset_sha256": "1" * 64,
            "fixture_manifest_sha256": "2" * 64,
            "keycloak_realm_sha256": "3" * 64,
        },
    )
    common["fixture_manifest"] = str(tmp_path / "untracked-manifest.json")
    with pytest.raises(driver.StagingError, match="tracked fixture root"):
        driver._deploy(SimpleNamespace(leave_running=True, **common))


def test_run_wraps_command_failures_without_leaking_raw_control(
    driver: Any, tmp_path: Path
) -> None:
    with pytest.raises(driver.StagingError, match="command failed"):
        driver._run(
            [sys.executable, "-c", "import sys; print('bounded failure', file=sys.stderr); raise SystemExit(3)"],
            environment=os.environ,
        )
    assert driver._project_name("Request.060_A") == "astral060-request-060_a"
    with pytest.raises(driver.StagingError, match="deployment identity"):
        driver._project_name("x")


def test_main_dispatches_all_commands_and_normalizes_staging_errors(
    driver: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert driver.main(["validate-fixtures", "--manifest", str(MANIFEST)]) == 0
    assert "fixture_manifest_sha256" in capsys.readouterr().out

    monkeypatch.setattr(driver, "_deploy", lambda args: 7 if args.leave_running else 8)
    assert driver.main(
        [
            "deploy",
            "--candidate-sha",
            "a" * 40,
            "--candidate-image",
            "ghcr.io/astraldeep/astraldeep@sha256:" + "b" * 64,
            "--fixture-manifest",
            str(MANIFEST),
            "--environment-id",
            "request-060-main",
            "--outputs",
            str(tmp_path / "out.json"),
            "--leave-running",
        ]
    ) == 7
    monkeypatch.setattr(driver, "_cleanup", lambda args: 9 if args.environment_id else 10)
    assert driver.main(["cleanup", "--environment-id", "request-060-main"]) == 9

    def reject(_manifest: str) -> dict[str, Any]:
        raise driver.StagingError("normalized fixture rejection")

    monkeypatch.setattr(driver, "validate_fixtures", reject)
    assert driver.main(["validate-fixtures", "--manifest", str(MANIFEST)]) == 2
    assert "candidate staging rejected: normalized fixture rejection" in capsys.readouterr().err


def test_strict_fixture_helpers_reject_malformed_and_secret_bearing_values(
    driver: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty.json"
    empty.write_bytes(b"")
    with pytest.raises(driver.StagingError, match="size"):
        driver._strict_json(empty)
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(driver.StagingError, match="duplicate"):
        driver._strict_json(duplicate)
    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"a":NaN}', encoding="utf-8")
    with pytest.raises(driver.StagingError, match="non-finite"):
        driver._strict_json(nonfinite)
    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    with pytest.raises(driver.StagingError, match="one JSON object"):
        driver._strict_json(array)
    with pytest.raises(driver.StagingError, match="secret-bearing"):
        driver._assert_no_secret_values({"nested": [{"access_token": "must-not-appear"}]})

    monkeypatch.setattr(driver, "MAX_JSON_BYTES", 1)
    with pytest.raises(driver.StagingError, match="size"):
        driver._strict_json(MANIFEST)


def test_fixture_manifest_revision_and_version_are_closed_contracts(
    driver: Any, tmp_path: Path
) -> None:
    manifest = tmp_path / "fixture-manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    with pytest.raises(driver.StagingError, match="schema version"):
        driver.validate_fixtures(manifest)
    manifest.write_text(
        json.dumps({"schema_version": 1, "source_schema_revision": "056.001"}),
        encoding="utf-8",
    )
    with pytest.raises(driver.StagingError, match="057.001"):
        driver.validate_fixtures(manifest)


def _load_release_validator() -> Any:
    validator_path = REPO_ROOT / "scripts" / "validate_release_evidence.py"
    spec = importlib.util.spec_from_file_location(
        "candidate_staging_test_release_validator", validator_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _stage_deploy_github_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "AstralDeep/AstralDeep")
    monkeypatch.setenv("GITHUB_WORKFLOW", "release-readiness")
    monkeypatch.setenv(
        "GITHUB_WORKFLOW_REF",
        "AstralDeep/AstralDeep/.github/workflows/release-readiness.yml"
        "@refs/heads/060-runtime-reliability-hardening",
    )
    monkeypatch.setenv("GITHUB_WORKFLOW_SHA", "d" * 40)
    monkeypatch.setenv("RELEASE_TRUSTED_BUILDER_SHA", "e" * 40)
    monkeypatch.setenv(
        "RELEASE_TRUSTED_BUILDER_IDENTITY",
        "https://github.com/AstralDeep/AstralDeep/.github/workflows/"
        "release-trusted-builder.yml@refs/heads/main",
    )


def _fake_docker_deploy(
    driver: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("ASTRAL_ENV=staging\n", encoding="utf-8")
    runtime_env.chmod(0o600)
    protected = _protected_environment(runtime_env)
    monkeypatch.setattr(driver, "_required_environment", lambda: protected)
    monkeypatch.setattr(driver, "_git_identity", lambda _candidate: None)
    capability = {"supported": False, "runtime_contract_versions": [], "source_feature": None}
    monkeypatch.setattr(driver, "_probe", lambda _endpoint, _token: capability)

    def run(
        arguments: list[str],
        *,
        environment: dict[str, str],
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        del environment, input_bytes
        if "SELECT value FROM schema_meta" in arguments[-1]:
            output = b"060.004\n"
        elif "ps" in arguments and "--format" in arguments:
            output = b'[{"Service":"astraldeep"}]\n'
        else:
            output = b""
        return subprocess.CompletedProcess(arguments, 0, output, b"")

    monkeypatch.setattr(driver, "_run", run)


def test_deploy_help_lists_the_optional_trusted_manifest_flag() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "deploy", "--help"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert "--trusted-manifest" in completed.stdout


def test_trusted_manifest_is_schema_valid_and_binds_the_deploy_outputs(
    driver: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _fake_docker_deploy(driver, monkeypatch, tmp_path)
    _stage_deploy_github_identity(monkeypatch)
    output_path = tmp_path / "outputs" / "staging-outputs.json"
    manifest_path = tmp_path / "outputs" / "trusted-stage-deploy.json"
    args = SimpleNamespace(
        leave_running=True,
        candidate_image="ghcr.io/astraldeep/astraldeep@sha256:" + "c" * 64,
        candidate_sha="b" * 40,
        fixture_manifest=str(MANIFEST),
        environment_id="request-060-1",
        outputs=str(output_path),
        trusted_manifest=str(manifest_path),
    )
    assert driver._deploy(args) == 0
    capsys.readouterr()

    output = json.loads(output_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["document_type"] == "trusted_stage_deploy"
    assert manifest["candidate_sha"] == "b" * 40
    assert manifest["workflow"] == {
        "name": "release-readiness",
        "run_id": "6001",
        "run_attempt": 1,
        "job_id": "stage-deploy",
    }
    assert manifest["workflow_ref"] == (
        "AstralDeep/AstralDeep/.github/workflows/release-readiness.yml@" + "d" * 40
    )
    assert manifest["trusted_builder"]["signer_digest"] == "e" * 40
    assert manifest["generated_at"] == output["deployed_at"]
    assert manifest["deployment"] == {
        key: value
        for key, value in output.items()
        if key not in {"deployed_at", "macos_personal_agent_host"}
    }
    artifact = manifest["stage_outputs_artifact"]
    assert artifact["member"] == "staging-outputs.json"
    assert artifact["sha256"] == hashlib.sha256(output_path.read_bytes()).hexdigest()
    assert artifact["immutable_reference"].startswith(
        "gh://AstralDeep/AstralDeep/runs/6001/attempts/1/artifacts/"
    )

    validator = _load_release_validator()
    trust_schema = validator.load_json_document(
        REPO_ROOT
        / "specs/060-runtime-reliability-hardening/contracts/release-trust.schema.json"
    )
    validator.validate_document(manifest, trust_schema)


def test_trusted_manifest_requires_stage_deploy_job_and_github_identity(
    driver: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("ASTRAL_ENV=staging\n", encoding="utf-8")
    runtime_env.chmod(0o600)
    protected = _protected_environment(runtime_env)
    protected["GITHUB_JOB"] = "producer"
    monkeypatch.setattr(driver, "_required_environment", lambda: protected)
    _stage_deploy_github_identity(monkeypatch)
    manifest_path = tmp_path / "trusted-stage-deploy.json"
    args = SimpleNamespace(
        leave_running=True,
        candidate_image="ghcr.io/astraldeep/astraldeep@sha256:" + "c" * 64,
        candidate_sha="b" * 40,
        fixture_manifest=str(MANIFEST),
        environment_id="request-060-1",
        outputs=str(tmp_path / "out.json"),
        trusted_manifest=str(manifest_path),
    )
    with pytest.raises(driver.StagingError, match="stage-deploy"):
        driver._deploy(args)
    assert not manifest_path.exists()

    protected["GITHUB_JOB"] = "stage-deploy"
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    with pytest.raises(driver.StagingError, match="GITHUB_REPOSITORY"):
        driver._deploy(args)
    monkeypatch.setenv("GITHUB_REPOSITORY", "AstralDeep/AstralDeep")
    monkeypatch.delenv("GITHUB_WORKFLOW_SHA", raising=False)
    with pytest.raises(driver.StagingError, match="GITHUB_WORKFLOW_SHA"):
        driver._deploy(args)
    monkeypatch.setenv("GITHUB_WORKFLOW_SHA", "d" * 40)
    monkeypatch.delenv("RELEASE_TRUSTED_BUILDER_SHA", raising=False)
    with pytest.raises(driver.StagingError, match="RELEASE_TRUSTED_BUILDER_SHA"):
        driver._deploy(args)
    monkeypatch.setenv("RELEASE_TRUSTED_BUILDER_SHA", "e" * 40)
    protected["GITHUB_RUN_ATTEMPT"] = "not-a-number"
    with pytest.raises(driver.StagingError, match="GITHUB_RUN_ATTEMPT"):
        driver._deploy(args)
    protected["GITHUB_RUN_ATTEMPT"] = "1"
    monkeypatch.setenv("ASTRAL_STAGE_OUTPUTS_ARTIFACT_ID", "0")
    with pytest.raises(driver.StagingError, match="ASTRAL_STAGE_OUTPUTS_ARTIFACT_ID"):
        driver._deploy(args)
    assert not manifest_path.exists()


def test_schema_invalid_trusted_manifest_is_refused_before_writing(
    driver: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _fake_docker_deploy(driver, monkeypatch, tmp_path)
    _stage_deploy_github_identity(monkeypatch)
    # A run identity that survives the driver's own checks but violates the
    # trust schema's run_id grammar must be rejected by schema validation.
    driver._required_environment()["GITHUB_RUN_ID"] = "0"
    manifest_path = tmp_path / "trusted-stage-deploy.json"
    args = SimpleNamespace(
        leave_running=True,
        candidate_image="ghcr.io/astraldeep/astraldeep@sha256:" + "c" * 64,
        candidate_sha="b" * 40,
        fixture_manifest=str(MANIFEST),
        environment_id="request-060-1",
        outputs=str(tmp_path / "staging-outputs.json"),
        trusted_manifest=str(manifest_path),
    )
    with pytest.raises(driver.StagingError, match="schema-invalid"):
        driver._deploy(args)
    capsys.readouterr()
    assert not manifest_path.exists()


def test_deploy_without_the_flag_writes_no_trusted_manifest(
    driver: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _fake_docker_deploy(driver, monkeypatch, tmp_path)
    output_path = tmp_path / "outputs" / "staging-outputs.json"
    args = SimpleNamespace(
        leave_running=True,
        candidate_image="ghcr.io/astraldeep/astraldeep@sha256:" + "c" * 64,
        candidate_sha="b" * 40,
        fixture_manifest=str(MANIFEST),
        environment_id="request-060-1",
        outputs=str(output_path),
        trusted_manifest=None,
    )
    assert driver._deploy(args) == 0
    capsys.readouterr()
    assert [path.name for path in output_path.parent.iterdir()] == [output_path.name]
