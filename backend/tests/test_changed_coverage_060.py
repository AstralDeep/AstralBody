"""Direct contract tests for the feature-060 changed-code coverage collector."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_changed_coverage.py"


def _load_collector() -> ModuleType:
    spec = importlib.util.spec_from_file_location("changed_coverage_060", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


collector = _load_collector()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def git_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "coverage@example.invalid")
    _git(repo, "config", "user.name", "Coverage Fixture")
    source = repo / "backend" / "service.py"
    source.parent.mkdir(parents=True)
    source.write_text("first = 1\nsecond = 2\n", encoding="utf-8")
    return repo, _commit(repo, "base")


def _selection(repo: Path, base: str, candidate: str):
    selected = collector.select_revisions(
        event_name="manual",
        event_payload=None,
        base_sha=base,
        candidate_sha=candidate,
    )
    return collector.validate_revisions(repo, selected)


def _cobertura(path: Path, filename: str, lines: dict[int, int]) -> Path:
    rendered = "".join(
        f'<line number="{line}" hits="{hits}"/>' for line, hits in lines.items()
    )
    covered = sum(hits > 0 for hits in lines.values())
    total = len(lines)
    rate = covered / total if total else 1
    path.write_text(
        f'<coverage lines-valid="{total}" lines-covered="{covered}" '
        f'line-rate="{rate}"><sources><source>/work</source></sources>'
        "<packages><package><classes>"
        f'<class filename="{filename}" line-rate="{rate}">'
        f"<lines>{rendered}</lines></class>"
        "</classes></package></packages></coverage>\n",
        encoding="utf-8",
    )
    return path


def _javascript_envelope(coverage: dict[str, object]) -> dict[str, object]:
    return {
        **collector.JAVASCRIPT_REPORT_IDENTITY,
        "coverage": coverage,
    }


def test_event_selection_is_authoritative_for_pr_main_and_manual() -> None:
    base = "1" * 40
    candidate = "2" * 40
    pull_request = {"pull_request": {"base": {"sha": base}, "head": {"sha": candidate}}}
    selected = collector.select_revisions(
        event_name="pull_request",
        event_payload=pull_request,
        base_sha=base,
        candidate_sha=candidate,
    )
    assert selected.base_source == "pull_request.base.sha"
    assert selected.candidate_source == "pull_request.head.sha"

    with pytest.raises(collector.CoveragePolicyError) as mismatch:
        collector.select_revisions(
            event_name="pull_request",
            event_payload=pull_request,
            base_sha="3" * 40,
            candidate_sha=candidate,
        )
    assert mismatch.value.code == "event_identity_mismatch"

    push = collector.select_revisions(
        event_name="push",
        event_payload={"ref": "refs/heads/main", "before": base, "after": candidate},
        base_sha=None,
        candidate_sha=None,
    )
    assert (push.base_sha, push.candidate_sha) == (base, candidate)
    with pytest.raises(collector.CoveragePolicyError, match="refs/heads/main"):
        collector.select_revisions(
            event_name="push",
            event_payload={
                "ref": "refs/heads/topic",
                "before": base,
                "after": candidate,
            },
            base_sha=None,
            candidate_sha=None,
        )

    manual = collector.select_revisions(
        event_name="workflow_dispatch",
        event_payload={"inputs": {"base_sha": base, "candidate_sha": candidate}},
        base_sha=None,
        candidate_sha=None,
    )
    assert manual.base_source == "manual.base_sha"


def test_event_selection_rejects_missing_unknown_and_conflicting_manual_inputs() -> (
    None
):
    base = "1" * 40
    candidate = "2" * 40
    cases = [
        {
            "event_name": "pull_request",
            "event_payload": {},
            "base_sha": None,
            "candidate_sha": None,
        },
        {
            "event_name": "schedule",
            "event_payload": {},
            "base_sha": base,
            "candidate_sha": candidate,
        },
        {
            "event_name": "workflow_dispatch",
            "event_payload": {"inputs": {"base_sha": base, "candidate_sha": candidate}},
            "base_sha": "3" * 40,
            "candidate_sha": candidate,
        },
        {
            "event_name": "workflow_dispatch",
            "event_payload": {"inputs": {"base_sha": base, "candidate_sha": candidate}},
            "base_sha": base,
            "candidate_sha": "3" * 40,
        },
        {
            "event_name": "manual",
            "event_payload": None,
            "base_sha": None,
            "candidate_sha": None,
        },
    ]
    for case in cases:
        with pytest.raises(collector.CoveragePolicyError):
            collector.select_revisions(**case)


def test_revision_validation_rejects_zero_equal_and_nonancestor(
    git_repo: tuple[Path, str],
) -> None:
    repo, base = git_repo
    (repo / "backend" / "service.py").write_text("first = 3\n", encoding="utf-8")
    candidate = _commit(repo, "candidate")
    assert _selection(repo, base, candidate).candidate_sha == candidate

    with pytest.raises(collector.CoveragePolicyError) as zero:
        collector.validate_revisions(
            repo,
            collector.RevisionSelection(
                "manual", "0" * 40, candidate, "manual", "manual"
            ),
        )
    assert zero.value.code == "zero_revision"
    with pytest.raises(collector.CoveragePolicyError) as equal:
        _selection(repo, candidate, candidate)
    assert equal.value.code == "empty_revision_range"

    _git(repo, "checkout", "--orphan", "unrelated")
    (repo / "backend" / "service.py").write_text("other = 1\n", encoding="utf-8")
    unrelated = _commit(repo, "unrelated")
    with pytest.raises(collector.CoveragePolicyError) as nonancestor:
        _selection(repo, base, unrelated)
    assert nonancestor.value.code == "non_ancestor_base"


def test_null_delimited_diff_and_explicit_path_mapping(
    git_repo: tuple[Path, str],
) -> None:
    repo, base = git_repo
    unusual = repo / "backend" / "space name.py"
    unusual.write_text("value = 1\n", encoding="utf-8")
    candidate = _commit(repo, "space path")
    changed = collector.read_changed_lines(repo, base, candidate)
    assert changed["backend/space name.py"] == {1}

    expected = {
        "backend/orchestrator/a.py": "backend_python",
        "scripts/release.py": "tooling_python",
        "windows-client/win_agent/host.py": "windows_python",
        "backend/webrender/static/client.js": "javascript",
        "tooling/web-ci/eslint.config.mjs": "javascript",
        "android-client/app/src/main/kotlin/x/App.kt": "android_app",
        "android-client/app/src/main/java/x/Compat.kt": "android_app",
        "android-client/core/src/main/kotlin/x/Core.kt": "android_core",
        "apple-clients/AstralApp/AstralApp/AppModel.swift": "apple",
        "apple-clients/AstralCore/Sources/AstralCore/API/Rest.swift": "apple",
        "apple-clients/AstralWatch/WatchModel.swift": "apple",
    }
    assert {path: collector.classify_path(path).key for path in expected} == expected
    for excluded in (
        "backend/tests/test_a.py",
        "backend/webrender/static/vendor/plotly.min.js",
        "tooling/web-ci/tests/release.spec.js",
        "android-client/app/src/test/kotlin/x/AppTest.kt",
        "apple-clients/AstralCore/Tests/AstralCoreTests/CoreTests.swift",
        "android-client/build.gradle.kts",
    ):
        assert collector.classify_path(excluded) is None


def test_repeated_cobertura_reports_union_and_dedupe_changed_lines(
    git_repo: tuple[Path, str], tmp_path: Path
) -> None:
    repo, base = git_repo
    (repo / "backend" / "service.py").write_text(
        "first = 10\nsecond = 20\n", encoding="utf-8"
    )
    candidate = _commit(repo, "both lines")
    first = _cobertura(tmp_path / "first.xml", "backend/service.py", {1: 1, 2: 0})
    second = _cobertura(
        tmp_path / "second.xml", "/app/backend/service.py", {1: 1, 2: 1}
    )
    decision = collector.evaluate_changed_coverage(
        repo,
        _selection(repo, base, candidate),
        {"backend_python": [first, second, first]},
    )
    assert decision["status"] == "pass"
    assert decision["languages"]["python"] == {
        "covered_lines": 2,
        "executable_lines": 2,
        "percent": 100.0,
    }
    assert len(decision["reports"]["backend_python"]["artifacts"]) == 2
    assert len(decision["lines"]) == 2


@pytest.mark.parametrize(
    ("reports", "expected"),
    [
        ({}, "missing_report"),
        ({"backend_python": ["broken"]}, "unparseable_report"),
        ({"backend_python": ["unmapped"]}, "unmapped_changed_file"),
    ],
)
def test_missing_unparseable_and_unmapped_reports_fail_closed(
    git_repo: tuple[Path, str],
    tmp_path: Path,
    reports: dict[str, list[str]],
    expected: str,
) -> None:
    repo, base = git_repo
    (repo / "backend" / "service.py").write_text("first = 9\n", encoding="utf-8")
    candidate = _commit(repo, "changed")
    broken = tmp_path / "broken.xml"
    broken.write_text("not xml", encoding="utf-8")
    unmapped = _cobertura(tmp_path / "unmapped.xml", "backend/other.py", {1: 1})
    resolved = {
        key: [broken if item == "broken" else unmapped for item in values]
        for key, values in reports.items()
    }
    with pytest.raises(collector.CoveragePolicyError) as failure:
        collector.evaluate_changed_coverage(
            repo, _selection(repo, base, candidate), resolved
        )
    assert failure.value.code == expected


def test_unexpected_empty_executable_selection_fails(
    git_repo: tuple[Path, str], tmp_path: Path
) -> None:
    repo, base = git_repo
    (repo / "backend" / "service.py").write_text(
        "# changed comment\nfirst = 1\nsecond = 2\n", encoding="utf-8"
    )
    candidate = _commit(repo, "comment")
    report = _cobertura(tmp_path / "coverage.xml", "backend/service.py", {2: 1, 3: 1})
    with pytest.raises(collector.CoveragePolicyError) as failure:
        collector.evaluate_changed_coverage(
            repo,
            _selection(repo, base, candidate),
            {"backend_python": [report]},
        )
    assert failure.value.code == "unexpected_empty_executable_diff"


def test_per_language_gate_cannot_be_hidden_by_combined_coverage(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "coverage@example.invalid")
    _git(repo, "config", "user.name", "Coverage Fixture")
    python_path = repo / "backend" / "service.py"
    js_path = repo / "backend" / "webrender" / "static" / "client.js"
    python_path.parent.mkdir(parents=True)
    js_path.parent.mkdir(parents=True)
    python_path.write_text(
        "".join(f"value_{n} = 0\n" for n in range(9)), encoding="utf-8"
    )
    js_path.write_text("const value = 0;\n", encoding="utf-8")
    base = _commit(repo, "base")
    python_path.write_text(
        "".join(f"value_{n} = 1\n" for n in range(9)), encoding="utf-8"
    )
    js_path.write_text("const value = 1;\n", encoding="utf-8")
    candidate = _commit(repo, "candidate")
    py_report = _cobertura(
        tmp_path / "python.xml", "backend/service.py", dict.fromkeys(range(1, 10), 1)
    )
    js_report = tmp_path / "javascript.json"
    js_report.write_text(
        json.dumps(
            _javascript_envelope(
                {
                    "backend/webrender/static/client.js": {
                        "path": "backend/webrender/static/client.js",
                        "statementMap": {
                            "0": {
                                "start": {"line": 1, "column": 0},
                                "end": {"line": 1, "column": 16},
                            }
                        },
                        "s": {"0": 0},
                    }
                }
            )
        ),
        encoding="utf-8",
    )
    decision = collector.evaluate_changed_coverage(
        repo,
        _selection(repo, base, candidate),
        {"backend_python": [py_report], "javascript": [js_report]},
    )
    assert decision["combined"]["percent"] == 90.0
    assert decision["status"] == "fail"
    assert [(item["scope"], item["code"]) for item in decision["failures"]] == [
        ("javascript", "coverage_below_threshold")
    ]


def test_kover_istanbul_and_xccov_line_observations_parse(tmp_path: Path) -> None:
    kover = tmp_path / "app.xml"
    kover.write_text(
        '<report><package name="com/example"><sourcefile name="App.kt">'
        '<line nr="3" mi="0" ci="2" mb="0" cb="0"/>'
        '<line nr="4" mi="2" ci="0" mb="0" cb="0"/>'
        '<counter type="LINE" missed="1" covered="1"/>'
        '</sourcefile><counter type="LINE" missed="1" covered="1"/>'
        '</package><counter type="LINE" missed="1" covered="1"/></report>',
        encoding="utf-8",
    )
    kotlin = collector.parse_coverage_report(kover, "android_app")
    kotlin_path = "android-client/app/src/main/kotlin/com/example/App.kt"
    assert kotlin.executable == {(kotlin_path, 3), (kotlin_path, 4)}
    assert kotlin.covered == {(kotlin_path, 3)}

    js_path = "backend/webrender/static/client.js"
    istanbul = tmp_path / "istanbul.json"
    istanbul.write_text(
        json.dumps(
            _javascript_envelope(
                {
                    js_path: {
                        "path": js_path,
                        "statementMap": {
                            "0": {
                                "start": {"line": 1, "column": 0},
                                "end": {"line": 1, "column": 10},
                            },
                            "1": {
                                "start": {"line": 2, "column": 0},
                                "end": {"line": 2, "column": 10},
                            },
                        },
                        "s": {"0": 0, "1": 3},
                    }
                }
            )
        ),
        encoding="utf-8",
    )
    javascript = collector.parse_coverage_report(istanbul, "javascript")
    assert javascript.executable == {(js_path, 1), (js_path, 2)}
    assert javascript.covered == {(js_path, 2)}

    xccov = tmp_path / "apple.json"
    swift_path = "apple-clients/AstralWatch/WatchModel.swift"
    xccov.write_text(
        json.dumps(
            {
                f"/work/{swift_path}": [
                    *[{"line": line, "isExecutable": False} for line in range(1, 7)],
                    {"line": 7, "isExecutable": True, "executionCount": 0},
                    {"line": 8, "isExecutable": True, "executionCount": 1},
                ]
            }
        ),
        encoding="utf-8",
    )
    apple = collector.parse_coverage_report(xccov, "apple")
    assert apple.observed == {(swift_path, line) for line in range(1, 9)}
    assert apple.executable == {(swift_path, 7), (swift_path, 8)}
    assert apple.covered == {(swift_path, 8)}


def test_istanbul_statement_ranges_are_supported(
    tmp_path: Path,
) -> None:
    js_path = "tooling/web-ci/eslint.config.mjs"
    istanbul = tmp_path / "statements.json"
    istanbul.write_text(
        json.dumps(
            _javascript_envelope(
                {
                    js_path: {
                        "path": js_path,
                        "statementMap": {
                            "0": {
                                "start": {"line": 2, "column": 0},
                                "end": {"line": 3, "column": 1},
                            }
                        },
                        "s": {"0": 1},
                    }
                }
            )
        ),
        encoding="utf-8",
    )
    parsed = collector.parse_coverage_report(istanbul, "javascript")
    assert parsed.executable == {(js_path, 2)}
    assert parsed.covered == parsed.executable


def test_realistic_xccov_report_summary_is_not_misused_as_line_proof(
    tmp_path: Path,
) -> None:
    """`xccov view --report --json` exposes aggregates, not raw line counts."""

    report = tmp_path / "xccov-report.json"
    report.write_text(
        json.dumps(
            {
                "coveredLines": 8,
                "executableLines": 10,
                "lineCoverage": 0.8,
                "targets": [
                    {
                        "name": "AstralWatch",
                        "coveredLines": 8,
                        "executableLines": 10,
                        "lineCoverage": 0.8,
                        "files": [
                            {
                                "path": "/work/apple-clients/AstralWatch/WatchModel.swift",
                                "coveredLines": 8,
                                "executableLines": 10,
                                "lineCoverage": 0.8,
                                "functions": [
                                    {
                                        "name": "WatchModel.refresh()",
                                        "lineNumber": 20,
                                        "executionCount": 1,
                                        "coveredLines": 8,
                                        "executableLines": 10,
                                        "lineCoverage": 0.8,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(collector.CoveragePolicyError) as failure:
        collector.parse_coverage_report(report, "apple")
    assert failure.value.code == "unsupported_xccov_report"
    assert "xcrun xccov view --archive --json <xcresult>" in failure.value.message


def test_compact_fail_closed_parser_edge_contracts(tmp_path: Path) -> None:
    with pytest.raises(collector.CoveragePolicyError):
        collector.CoverageData().add("backend/a.py", 0, False)
    assert collector.classify_path("./backend/a.py").key == "backend_python"
    with pytest.raises(collector.CoveragePolicyError):
        collector.classify_path("../backend/a.py")

    for value in (True, "not-an-integer", -1):
        with pytest.raises(collector.CoveragePolicyError):
            collector._integer(value, label="fixture")
    for payload in (b'{"x":1,"x":2}', b'{"x":NaN}', b"not-json"):
        with pytest.raises(collector.CoveragePolicyError):
            collector._strict_json(payload)
    for threshold in ("not-a-number", -1, 101):
        with pytest.raises(collector.CoveragePolicyError):
            collector._threshold(threshold)

    empty = tmp_path / "empty.xml"
    empty.write_bytes(b"")
    with pytest.raises(collector.CoveragePolicyError):
        collector.parse_coverage_report(empty, "backend_python")
    with pytest.raises(collector.CoveragePolicyError):
        collector.parse_coverage_report(tmp_path / "missing.xml", "backend_python")
    valid = _cobertura(tmp_path / "valid.xml", "backend/a.py", {1: 1})
    with pytest.raises(collector.CoveragePolicyError):
        collector.parse_coverage_report(valid, "unknown")


def test_real_playwright_v8_comment_vector_is_rejected(tmp_path: Path) -> None:
    source = (
        "\n// pure comment\nconst hit = 1;\n\nfunction never() {\n"
        "  return 2;\n}\n//# sourceURL=https://candidate.invalid/static/client.js\n"
    )
    report = tmp_path / "raw-playwright-v8.json"
    report.write_text(
        json.dumps(
            [
                {
                    "url": "https://candidate.invalid/static/client.js",
                    "source": source,
                    "functions": [
                        {
                            "ranges": [
                                {"startOffset": 0, "endOffset": 123, "count": 1},
                                {"startOffset": 33, "endOffset": 65, "count": 0},
                            ]
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(collector.CoveragePolicyError) as failure:
        collector.parse_coverage_report(report, "javascript")
    assert failure.value.code == "unparseable_report"
    assert "executable-line producer envelope" in failure.value.message


def test_istanbul_comment_padding_cannot_mask_uncovered_statement(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "coverage@example.invalid")
    _git(repo, "config", "user.name", "Coverage Fixture")
    source_path = repo / "backend" / "webrender" / "static" / "client.js"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("", encoding="utf-8")
    base = _commit(repo, "base")
    source_path.write_text(
        "".join(f"// padding {index}\n" for index in range(1, 10)) + "neverCalled();\n",
        encoding="utf-8",
    )
    candidate = _commit(repo, "candidate")
    report = tmp_path / "istanbul.json"
    report.write_text(
        json.dumps(
            _javascript_envelope(
                {
                    "backend/webrender/static/client.js": {
                        "path": "backend/webrender/static/client.js",
                        "statementMap": {
                            "0": {
                                "start": {"line": 10, "column": 0},
                                "end": {"line": 10, "column": 13},
                            }
                        },
                        "s": {"0": 0},
                    }
                }
            )
        ),
        encoding="utf-8",
    )
    decision = collector.evaluate_changed_coverage(
        repo,
        _selection(repo, base, candidate),
        {"javascript": [report]},
    )
    assert decision["status"] == "fail"
    assert decision["languages"]["javascript"] == {
        "covered_lines": 0,
        "executable_lines": 1,
        "percent": 0.0,
    }
    assert [(line["line"], line["covered"]) for line in decision["lines"]] == [
        (10, False)
    ]


@pytest.mark.parametrize(
    "hidden_record",
    [
        {
            "path": "backend/webrender/static/hidden.js",
            "l": {},
            "statementMap": {
                "0": {
                    "start": {"line": 1, "column": 0},
                    "end": {"line": 1, "column": 11},
                }
            },
            "s": {"0": 0},
        },
        {
            "path": "backend/webrender/static/hidden.js",
            "l": {"1": 1},
            "statementMap": {
                "0": {
                    "start": {"line": 1, "column": 0},
                    "end": {"line": 1, "column": 11},
                }
            },
            "s": {"0": 0},
        },
        {
            "path": "backend/webrender/static/hidden.js",
            "statementMap": {},
            "s": {},
        },
        {
            "path": "backend/webrender/static/hidden.js",
            "statementMap": {
                "0": {
                    "start": {"line": 1, "column": 0},
                    "end": {"line": 1, "column": 11},
                }
            },
            "s": {"1": 0},
        },
    ],
)
def test_malformed_istanbul_cannot_hide_uncovered_file_behind_covered_peer(
    tmp_path: Path, hidden_record: dict[str, object]
) -> None:
    peer_path = "backend/webrender/static/peer.js"
    report = tmp_path / "malformed-istanbul.json"
    report.write_text(
        json.dumps(
            _javascript_envelope(
                {
                    "backend/webrender/static/hidden.js": hidden_record,
                    peer_path: {
                        "path": peer_path,
                        "statementMap": {
                            "0": {
                                "start": {"line": 1, "column": 0},
                                "end": {"line": 1, "column": 9},
                            }
                        },
                        "s": {"0": 1},
                    },
                }
            )
        ),
        encoding="utf-8",
    )
    with pytest.raises(collector.CoveragePolicyError) as failure:
        collector.parse_coverage_report(report, "javascript")
    assert failure.value.code == "unparseable_report"


def test_gitattributes_cannot_hide_uncovered_maintained_source(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "coverage@example.invalid")
    _git(repo, "config", "user.name", "Coverage Fixture")
    backend = repo / "backend"
    backend.mkdir()
    hidden = backend / "hidden.py"
    peer = backend / "peer.py"
    hidden.write_text("hidden = 0\n", encoding="utf-8")
    peer.write_text("peer = 0\n", encoding="utf-8")
    base = _commit(repo, "base")
    (repo / ".gitattributes").write_text("backend/hidden.py -diff\n", encoding="utf-8")
    hidden.write_text("hidden = 1\n", encoding="utf-8")
    peer.write_text("peer = 1\n", encoding="utf-8")
    candidate = _commit(repo, "candidate")

    changed = collector.read_changed_lines(repo, base, candidate)
    assert changed["backend/hidden.py"] == {1}
    assert changed["backend/peer.py"] == {1}
    report = tmp_path / "python.xml"
    report.write_text(
        '<coverage lines-valid="2" lines-covered="1" line-rate="0.5">'
        "<sources><source>/work</source></sources><packages><package><classes>"
        '<class filename="backend/hidden.py" line-rate="0"><lines>'
        '<line number="1" hits="0"/></lines></class>'
        '<class filename="backend/peer.py" line-rate="1"><lines>'
        '<line number="1" hits="1"/></lines></class>'
        "</classes></package></packages></coverage>\n",
        encoding="utf-8",
    )
    decision = collector.evaluate_changed_coverage(
        repo,
        _selection(repo, base, candidate),
        {"backend_python": [report]},
    )
    assert decision["status"] == "fail"
    assert decision["languages"]["python"]["percent"] == 50.0


def test_cobertura_resolves_relative_filenames_against_declared_sources(
    tmp_path: Path,
) -> None:
    backend = tmp_path / "backend.xml"
    backend.write_text(
        '<coverage lines-valid="1" lines-covered="0">'
        "<sources><source>/work/backend</source></sources>"
        '<packages><package><classes><class filename="scripts/prod.py" '
        'line-rate="0"><lines><line number="4" hits="0"/></lines></class>'
        "</classes></package></packages></coverage>",
        encoding="utf-8",
    )
    tooling = tmp_path / "tooling.xml"
    tooling.write_text(
        '<coverage lines-valid="1" lines-covered="1">'
        "<sources><source>/work</source></sources>"
        '<packages><package><classes><class filename="scripts/prod.py" '
        'line-rate="1"><lines><line number="4" hits="1"/></lines></class>'
        "</classes></package></packages></coverage>",
        encoding="utf-8",
    )

    parsed_backend = collector.parse_coverage_report(backend, "backend_python")
    parsed_tooling = collector.parse_coverage_report(tooling, "tooling_python")
    assert parsed_backend.executable == {("backend/scripts/prod.py", 4)}
    assert parsed_backend.covered == set()
    assert parsed_tooling.covered == {("scripts/prod.py", 4)}


@pytest.mark.parametrize(
    "contents",
    [
        (
            '<coverage lines-valid="2" lines-covered="1"><sources>'
            "<source>/work</source></sources><packages><package><classes>"
            '<class filename="backend/hidden.py" line-rate="1"><lines/></class>'
            '<class filename="backend/peer.py" line-rate="1"><lines>'
            '<line number="1" hits="1"/></lines></class>'
            "</classes></package></packages></coverage>"
        ),
        (
            '<coverage lines-valid="1" lines-covered="1"><sources>'
            "<source>/work</source></sources><packages><package><classes>"
            '<class filename="backend/hidden.py" line-rate="1"><lines>'
            '<line number="1" hits="0"/></lines></class>'
            "</classes></package></packages></coverage>"
        ),
        (
            '<coverage lines-valid="2" lines-covered="1"><sources>'
            "<source>/work</source></sources><packages><package><classes>"
            '<class filename="backend/hidden.py"><lines>'
            '<line number="1" hits="0"/></lines></class>'
            '<class filename="/app/backend/hidden.py"><lines>'
            '<line number="1" hits="1"/></lines></class>'
            "</classes></package></packages></coverage>"
        ),
    ],
)
def test_cobertura_omissions_rates_and_normalized_aliases_fail_closed(
    tmp_path: Path, contents: str
) -> None:
    report = tmp_path / "invalid.xml"
    report.write_text(contents, encoding="utf-8")
    with pytest.raises(collector.CoveragePolicyError) as failure:
        collector.parse_coverage_report(report, "backend_python")
    assert failure.value.code == "unparseable_report"


def test_first_repository_anchor_prevents_cross_target_and_repeated_aliases(
    tmp_path: Path,
) -> None:
    tooling = collector.TARGET_BY_KEY["tooling_python"]
    backend = collector.TARGET_BY_KEY["backend_python"]
    assert (
        collector._normalized_report_path("/app/backend/scripts/release.py", tooling)
        is None
    )
    assert (
        collector._normalized_report_path("/app/backend/scripts/release.py", backend)
        == "backend/scripts/release.py"
    )
    assert (
        collector._normalized_report_path("/app/backend/backend/foo.py", backend)
        == "backend/backend/foo.py"
    )

    report = tmp_path / "aliases.xml"
    report.write_text(
        '<coverage lines-valid="3" lines-covered="2"><sources>'
        "<source>/work</source></sources><packages><package><classes>"
        '<class filename="scripts/release.py"><lines>'
        '<line number="1" hits="0"/></lines></class>'
        '<class filename="/app/backend/scripts/release.py"><lines>'
        '<line number="1" hits="1"/></lines></class>'
        '<class filename="/app/backend/backend/foo.py"><lines>'
        '<line number="1" hits="1"/></lines></class>'
        "</classes></package></packages></coverage>",
        encoding="utf-8",
    )
    parsed = collector.parse_coverage_report(report, "tooling_python")
    assert parsed.executable == {("scripts/release.py", 1)}
    assert parsed.covered == set()


@pytest.mark.parametrize(
    "contents",
    [
        (
            '<report><package name="com/example">'
            '<sourcefile name="Hidden.kt">'
            '<counter type="LINE" missed="1" covered="0"/></sourcefile>'
            '<sourcefile name="Peer.kt"><line nr="1" mi="0" ci="1"/>'
            '<counter type="LINE" missed="0" covered="1"/></sourcefile>'
            '<counter type="LINE" missed="1" covered="1"/></package>'
            '<counter type="LINE" missed="1" covered="1"/></report>'
        ),
        (
            '<report><package name="com/example"><sourcefile name="Hidden.kt">'
            '<line nr="1" mi="1" ci="0"/><line nr="1" mi="0" ci="1"/>'
            '<counter type="LINE" missed="1" covered="1"/></sourcefile>'
            '<counter type="LINE" missed="1" covered="1"/></package>'
            '<counter type="LINE" missed="1" covered="1"/></report>'
        ),
        (
            '<report><package name="com/example"><sourcefile name="Hidden.kt">'
            '<line nr="1" mi="1" ci="0"/>'
            '<counter type="LINE" missed="1" covered="0"/></sourcefile>'
            '<counter type="LINE" missed="0" covered="1"/></package>'
            '<counter type="LINE" missed="0" covered="1"/></report>'
        ),
    ],
)
def test_kover_omissions_duplicates_and_counter_mismatches_fail_closed(
    tmp_path: Path, contents: str
) -> None:
    report = tmp_path / "invalid-kover.xml"
    report.write_text(contents, encoding="utf-8")
    with pytest.raises(collector.CoveragePolicyError) as failure:
        collector.parse_coverage_report(report, "android_app")
    assert failure.value.code == "unparseable_report"


@pytest.mark.parametrize(
    "observations",
    [
        [],
        [
            {"line": 1, "isExecutable": False},
            {"line": 3, "isExecutable": True, "executionCount": 0},
        ],
        [
            {"line": 1, "isExecutable": False},
            {"line": 1, "isExecutable": True, "executionCount": 0},
        ],
    ],
)
def test_xccov_empty_partial_and_duplicate_physical_lines_fail_closed(
    tmp_path: Path, observations: list[dict[str, object]]
) -> None:
    report = tmp_path / "invalid-archive.json"
    report.write_text(
        json.dumps({"/work/apple-clients/AstralWatch/WatchModel.swift": observations}),
        encoding="utf-8",
    )
    with pytest.raises(collector.CoveragePolicyError) as failure:
        collector.parse_coverage_report(report, "apple")
    assert failure.value.code == "unparseable_report"


def test_xccov_non_executable_changed_line_is_observed_but_not_counted(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "coverage@example.invalid")
    _git(repo, "config", "user.name", "Coverage Fixture")
    hidden = repo / "apple-clients" / "AstralWatch" / "Hidden.swift"
    peer = repo / "apple-clients" / "AstralWatch" / "Peer.swift"
    hidden.parent.mkdir(parents=True)
    hidden.write_text("// old\n", encoding="utf-8")
    peer.write_text("let peer = 0\n", encoding="utf-8")
    base = _commit(repo, "base")
    hidden.write_text("// changed\n", encoding="utf-8")
    peer.write_text("let peer = 1\n", encoding="utf-8")
    candidate = _commit(repo, "candidate")
    report = tmp_path / "archive.json"
    report.write_text(
        json.dumps(
            {
                str(hidden): [{"line": 1, "isExecutable": False}],
                str(peer): [{"line": 1, "isExecutable": True, "executionCount": 1}],
            }
        ),
        encoding="utf-8",
    )
    decision = collector.evaluate_changed_coverage(
        repo,
        _selection(repo, base, candidate),
        {"apple": [report]},
    )
    assert decision["status"] == "pass"
    assert decision["languages"]["swift"]["executable_lines"] == 1
    assert decision["lines"] == [
        {
            "path": "apple-clients/AstralWatch/Peer.swift",
            "line": 1,
            "target": "apple",
            "language": "swift",
            "covered": True,
        }
    ]


def test_xccov_must_observe_each_changed_physical_line(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "coverage@example.invalid")
    _git(repo, "config", "user.name", "Coverage Fixture")
    source = repo / "apple-clients" / "AstralWatch" / "WatchModel.swift"
    source.parent.mkdir(parents=True)
    source.write_text("// first\n// old\n", encoding="utf-8")
    base = _commit(repo, "base")
    source.write_text("// first\n// changed\n", encoding="utf-8")
    candidate = _commit(repo, "candidate")
    report = tmp_path / "archive.json"
    report.write_text(
        json.dumps({str(source): [{"line": 1, "isExecutable": False}]}),
        encoding="utf-8",
    )
    with pytest.raises(collector.CoveragePolicyError) as failure:
        collector.evaluate_changed_coverage(
            repo,
            _selection(repo, base, candidate),
            {"apple": [report]},
        )
    assert failure.value.code == "unmapped_changed_line"


def test_bare_unfiltered_istanbul_output_is_rejected(tmp_path: Path) -> None:
    path = "backend/webrender/static/client.js"
    report = tmp_path / "unfiltered-v8-to-istanbul.json"
    report.write_text(
        json.dumps(
            {
                path: {
                    "path": path,
                    "statementMap": {
                        "0": {
                            "start": {"line": 1, "column": 0},
                            "end": {"line": 1, "column": 10},
                        }
                    },
                    "s": {"0": 1},
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(collector.CoveragePolicyError) as failure:
        collector.parse_coverage_report(report, "javascript")
    assert failure.value.code == "unparseable_report"
    assert "producer envelope" in failure.value.message


def test_cli_writes_repeatable_exact_identity_json(
    git_repo: tuple[Path, str], tmp_path: Path
) -> None:
    repo, base = git_repo
    (repo / "backend" / "service.py").write_text(
        "first = 10\nsecond = 2\n", encoding="utf-8"
    )
    candidate = _commit(repo, "candidate")
    report = _cobertura(tmp_path / "coverage.xml", "backend/service.py", {1: 1, 2: 1})
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    common = [
        "--repo",
        str(repo),
        "--base-sha",
        base,
        "--candidate-sha",
        candidate,
        "--backend-python",
        str(report),
    ]
    assert collector.main([*common, "--output", str(first)]) == 0
    assert collector.main([*common, "--output", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()
    document = json.loads(first.read_text(encoding="utf-8"))
    assert document["base_sha"] == base
    assert document["candidate_sha"] == candidate
    assert document["revisions_validated"] is True
    assert document["status"] == "pass"


def test_cli_missing_report_error_retains_validated_revision_audit_fields(
    git_repo: tuple[Path, str], tmp_path: Path
) -> None:
    repo, base = git_repo
    (repo / "backend" / "service.py").write_text("first = 10\n", encoding="utf-8")
    candidate = _commit(repo, "candidate")
    output = tmp_path / "error.json"
    assert (
        collector.main(
            [
                "--repo",
                str(repo),
                "--base-sha",
                base,
                "--candidate-sha",
                candidate,
                "--fail-under",
                "91",
                "--output",
                str(output),
            ]
        )
        == 1
    )
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["error"]["code"] == "missing_report"
    assert document["base_sha"] == base
    assert document["candidate_sha"] == candidate
    assert document["revisions_validated"] is True
    assert document["selection"] == {
        "event_name": "manual",
        "base_source": "manual.base_sha",
        "candidate_source": "manual.candidate_sha",
    }
    assert document["fail_under"] == 91.0
