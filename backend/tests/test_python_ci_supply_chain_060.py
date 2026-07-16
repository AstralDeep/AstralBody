"""Supply-chain contracts for Spec 060's isolated Python CI tooling."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLING_ROOT = REPO_ROOT / "tooling" / "python-ci"
INPUT = TOOLING_ROOT / "requirements.in"
LOCK = TOOLING_ROOT / "requirements.lock.txt"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
WINDOWS_CANDIDATE = (
    REPO_ROOT / ".github" / "workflows" / "build-windows-candidate.yml"
)
LEGACY_WINDOWS_RELEASE = (
    REPO_ROOT / ".github" / "workflows" / "release-windows.yml"
)
LOCK_INSTALL = (
    "python -m pip install --require-hashes -r "
    "tooling/python-ci/requirements.lock.txt"
)


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _logical_requirements(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8").replace("\\\n", " ")
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _pins(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for requirement in _logical_requirements(path):
        match = re.match(
            r"^([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([^ ;\\]+)",
            requirement,
        )
        assert match, f"requirement is not an exact direct pin: {requirement}"
        pins[_normalized(match.group(1))] = match.group(2)
    return pins


def _workflow_job(workflow: str, job_name: str) -> str:
    jobs = workflow.partition("\njobs:\n")[2]
    assert jobs, "workflow does not define jobs"
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\n(?P<body>.*?)"
        rf"(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        jobs,
    )
    assert match, f"workflow job is missing: {job_name}"
    return match.group("body")


def test_python_ci_direct_inputs_are_exact_and_minimal() -> None:
    assert _pins(INPUT) == {
        "coverage": "7.15.2",
        "diff-cover": "10.3.0",
        "psycopg2-binary": "2.9.12",
        "pytest": "9.1.1",
        "pytest-cov": "7.0.0",
        "ruff": "0.15.21",
    }
    text = INPUT.read_text(encoding="utf-8")
    assert "-r " not in text
    assert "--index-url" not in text
    assert "--extra-index-url" not in text


def test_python_ci_lock_hashes_every_exact_transitive_block() -> None:
    requirements = _logical_requirements(LOCK)
    assert len(requirements) >= 15
    for requirement in requirements:
        assert re.match(
            r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[^ ;\\]+",
            requirement,
        ), f"lock requirement is not exact: {requirement}"
        assert "--hash=sha256:" in requirement, (
            f"lock requirement has no SHA-256 artifact hash: {requirement}"
        )
        assert " @ " not in requirement

    direct = _pins(INPUT)
    locked = _pins(LOCK)
    assert all(locked.get(name) == version for name, version in direct.items())


def test_ci_uses_one_hash_lock_for_every_python_test_tool_install() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    for job_name in (
        "lint",
        "release-tooling-tests",
        "coverage-gate",
    ):
        job = _workflow_job(workflow, job_name)
        assert LOCK_INSTALL in job
        assert "cache-dependency-path: tooling/python-ci/requirements.lock.txt" in job

    windows = _workflow_job(workflow, "windows-client")
    assert "runs-on: windows-latest" in windows
    assert LOCK_INSTALL in windows
    assert (
        "python -m pip install --require-hashes -r "
        "windows-client/requirements-release.lock.txt"
    ) in windows
    assert "windows-client/requirements.txt" not in windows
    assert "sudo apt-get" not in windows

    backend = _workflow_job(workflow, "test")
    assert '-v "$PWD/tooling/python-ci:/ci/python:ro"' in backend
    assert (
        "python -m pip install --require-hashes -r "
        "/ci/python/requirements.lock.txt"
    ) in backend

    assert "pip install ruff" not in workflow
    assert "pip install diff-cover" not in workflow
    assert "pip install pytest-cov" not in workflow
    assert "pip install pytest 'coverage" not in workflow
    assert "requirements.txt pytest" not in workflow
    assert "python -m pip install -r " not in workflow


def test_release_tooling_job_covers_every_maintained_script_non_vacuously() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    job = _workflow_job(workflow, "release-tooling-tests")
    assert "RELEASE_TOOL_TESTS=(" in job
    assert 'test "${#RELEASE_TOOL_TESTS[@]}" -gt 0' in job
    assert "coverage run --source=scripts -m pytest" in job
    assert "coverage report --fail-under=90" in job

    expected_scripts = {
        "check_changed_coverage.py",
        "check_doc_links.py",
        "run_android_next_major_canary.py",
        "run_candidate_staging.py",
        "validate_release_evidence.py",
        "windows_release_candidate.py",
    }
    assert {path.name for path in (REPO_ROOT / "scripts").glob("*.py")} == (
        expected_scripts
    )
    for test_path in (
        "backend/tests/test_changed_coverage_060.py",
        "backend/tests/test_release_tooling_coverage_060.py",
        "backend/tests/test_documentation_060.py",
        "backend/tests/test_quickstart_commands.py",
        "backend/tests/test_ci_javascript_lint.py",
        "backend/tests/test_python_ci_supply_chain_060.py",
        "backend/tests/test_android_next_major_canary.py",
        "backend/tests/test_candidate_staging_060.py",
        "backend/tests/test_release_evidence_validator.py",
        "windows-client/tests/test_release_lock_060.py",
    ):
        assert test_path in job


def test_windows_candidate_installs_test_lock_only_after_candidate_build() -> None:
    workflow = WINDOWS_CANDIDATE.read_text(encoding="utf-8")
    build = workflow.index("- name: Build the unsigned executable exactly once")
    test_install = workflow.index(
        "python -m pip install --require-hashes -r "
        "tooling\\python-ci\\requirements.lock.txt"
    )
    assert build < test_install
    assert "pytest==" not in workflow
    assert "pytest-cov==" not in workflow
    assert "tooling/python-ci/requirements.lock.txt" in workflow


def test_legacy_windows_release_uses_only_complete_release_lock() -> None:
    workflow = LEGACY_WINDOWS_RELEASE.read_text(encoding="utf-8")
    install = (
        "python -m pip install --require-hashes -r "
        "windows-client/requirements-release.lock.txt"
    )
    assert install in workflow
    assert workflow.index(install) < workflow.index("- name: Build the exe")
    assert "pip install --upgrade" not in workflow
    assert "pip install -r windows-client/requirements.txt" not in workflow
    assert "sigstore>=" not in workflow


def test_ci_only_python_manifest_cannot_enter_product_artifacts() -> None:
    product_inputs = (
        REPO_ROOT / "Dockerfile",
        REPO_ROOT / "backend" / "requirements.txt",
        REPO_ROOT / "windows-client" / "AstralDeep.spec",
        REPO_ROOT / "windows-client" / "requirements.in",
        REPO_ROOT / "apple-clients" / "AstralCore" / "Package.swift",
        REPO_ROOT / "android-client" / "settings.gradle.kts",
    )
    for path in product_inputs:
        assert "tooling/python-ci" not in path.read_text(encoding="utf-8"), path

    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"(?mi)^\s*COPY\s+\.\s", dockerfile) is None
