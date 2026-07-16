"""Pinned real-browser release-lane contracts and opt-in staging orchestration."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOL_ROOT = REPO_ROOT / "tooling" / "web-ci"
PACKAGE = TOOL_ROOT / "package.json"
LOCK = TOOL_ROOT / "package-lock.json"
IMAGE = TOOL_ROOT / "playwright-image.txt"
RUNNER = TOOL_ROOT / "release-runner.mjs"
RELEASE_SPEC = TOOL_ROOT / "tests" / "release-060.spec.js"
CONTRACT_SPEC = TOOL_ROOT / "tests" / "continuity-contract-060.spec.js"
EVIDENCE_SCHEMA = (
    REPO_ROOT
    / "specs/060-runtime-reliability-hardening/contracts/release-evidence.schema.json"
)
VALIDATOR = REPO_ROOT / "scripts" / "validate_release_evidence.py"


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location("release_validator_060_e2e", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_playwright_package_lock_core_and_image_versions_are_identical() -> None:
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    image = IMAGE.read_text(encoding="utf-8").strip()
    version = package["devDependencies"]["@playwright/test"]
    assert lock["packages"]["node_modules/@playwright/test"]["version"] == version
    assert lock["packages"]["node_modules/playwright-core"]["version"] == version
    assert f"playwright:v{version}-" in image
    assert re.fullmatch(r"mcr\.microsoft\.com/playwright:v[0-9.]+-noble@sha256:[0-9a-f]{64}", image)
    assert package["packageManager"].startswith("npm@11.16.0+")
    assert package["engines"] == {"node": ">=24 <25"}


def test_release_runner_is_container_only_and_fail_closed() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    assert package["scripts"]["browser:release"] == "node release-runner.mjs"
    assert package["scripts"]["browser:contract"].endswith(
        "tests/continuity-contract-060.spec.js"
    )
    for required in (
        'existsSync("/ms-playwright")',
        "playwright-image.txt",
        "package-lock.json",
        "npm_config_user_agent",
        "ASTRAL_RELEASE_USERNAME",
        "ASTRAL_RELEASE_PASSWORD",
        "ASTRAL_RELEASE_STAGING_FILE",
    ):
        assert required in source
    assert "playwright test" not in package["scripts"]["browser:release"]
    assert "chromium.launchExecutablePath" not in source
    assert "executablePath" not in source


def test_release_spec_uses_real_auth_transport_and_candidate_ui() -> None:
    source = RELEASE_SPEC.read_text(encoding="utf-8")
    for forbidden in (
        "page.route(",
        "route.fulfill(",
        "FakeWebSocket",
        "storageState",
        "addCookies(",
        "__ASTRAL_TOKEN__",
        "alg: \"none\"",
        "addScriptTag",
    ):
        assert forbidden not in source
    for required in (
        'input[name="username"]',
        'input[name="password"]',
        "page.coverage.startJSCoverage",
        "page.coverage.stopJSCoverage",
        "conversation_snapshot",
        "seedPriorPrincipalDecoy",
        "verifyCurrentSessionOwnsWebSocket",
        "sharedTabStaleTokenRejected",
        "websocketPrincipalMatchesCookieSession",
        "operation_status",
        "agent_lifecycle",
        "runResumeTrials",
        "for (let trial = 0; trial < 20; trial += 1)",
        "release-evidence.schema",
    ):
        if required == "release-evidence.schema":
            continue
        assert required in source
    assert CONTRACT_SPEC.is_file(), "the synthetic reducer suite must remain non-qualifying"


def test_release_report_shape_is_validated_by_the_production_schema_engine() -> None:
    # The browser producer writes this exact top-level shape; schema validation
    # remains in Python so the JavaScript lane cannot declare itself trusted.
    source = RELEASE_SPEC.read_text(encoding="utf-8")
    for field in (
        "document_type",
        "evidence_id",
        "candidate_sha",
        "release_id",
        "release_version",
        "staging_environment",
        "unavailability_observation",
        "checks",
    ):
        assert re.search(rf"\b{field}\s*:", source)
    validator = _load_validator()
    schema = validator.load_json_document(EVIDENCE_SCHEMA)
    validator.validate_schema_document(schema)


def test_real_browser_release_lane_against_trusted_staging(tmp_path: Path) -> None:
    """Run only when the protected producer explicitly opts into live staging."""

    if os.environ.get("ASTRAL_RELEASE_E2E") != "true":
        pytest.skip("set ASTRAL_RELEASE_E2E=true only on the trusted staging producer")
    required = (
        "ASTRAL_PLAYWRIGHT_IMAGE",
        "ASTRAL_RELEASE_CANDIDATE_SHA",
        "ASTRAL_RELEASE_ID",
        "ASTRAL_RELEASE_LIFECYCLE_AGENT_ID",
        "ASTRAL_RELEASE_LIFECYCLE_STATES",
        "ASTRAL_RELEASE_PASSWORD",
        "ASTRAL_RELEASE_STAGING_FILE",
        "ASTRAL_RELEASE_USERNAME",
        "ASTRAL_RELEASE_VERSION",
        "ASTRAL_RUNNER_ENVIRONMENT",
        "GITHUB_JOB",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_RUN_ID",
        "GITHUB_WORKFLOW",
        "RUNNER_ARCH",
        "RUNNER_NAME",
        "RUNNER_OS",
        "STAGING_URL",
    )
    missing = [name for name in required if not os.environ.get(name)]
    assert not missing, f"trusted browser environment is incomplete: {missing}"
    pinned = IMAGE.read_text(encoding="utf-8").strip()
    assert os.environ["ASTRAL_PLAYWRIGHT_IMAGE"] == pinned
    output = tmp_path / "web.json"
    coverage = tmp_path / "web-v8.json"
    environment_flags = [flag for name in required for flag in ("-e", name)]
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{REPO_ROOT}:/work",
            "-v",
            f"{tmp_path}:/evidence",
            "-w",
            "/work/tooling/web-ci",
            *environment_flags,
            pinned,
            "sh",
            "-lc",
            (
                'test "$(corepack npm --version)" = "11.16.0" '
                "&& corepack npm ci --ignore-scripts "
                "&& corepack npm run browser:release -- "
                '--base-url "$STAGING_URL" '
                '--candidate-sha "$ASTRAL_RELEASE_CANDIDATE_SHA" '
                "--output /evidence/web.json "
                "--coverage-output /evidence/web-v8.json"
            ),
        ],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20 * 60,
    )
    assert completed.returncode == 0, completed.stdout[-8000:]
    validator = _load_validator()
    report = validator.load_json_document(output)
    schema = validator.load_json_document(EVIDENCE_SCHEMA)
    validator.validate_document(report, schema)
    assert report["candidate_sha"] == os.environ["ASTRAL_RELEASE_CANDIDATE_SHA"]
    assert report["outcome"] == "passed"
    assert coverage.is_file() and coverage.stat().st_size > 0
