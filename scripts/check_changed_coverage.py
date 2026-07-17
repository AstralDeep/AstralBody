#!/usr/bin/env python3
"""Fail-closed changed executable-line coverage across maintained languages.

The collector deliberately owns only policy and report parsing. Coverage producers
remain platform-native, while this script selects an immutable event-aware Git
comparison, maps changed source lines to their reports, unions repeated observations,
and emits one deterministic JSON decision.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = 1
JAVASCRIPT_REPORT_KEYS = {
    "schema_version",
    "producer",
    "producer_version",
    "v8_to_istanbul_version",
    "espree_version",
    "coverage",
}
JAVASCRIPT_REPORT_IDENTITY = {
    "schema_version": 1,
    "producer": "astraldeep-playwright-executable-lines",
    "producer_version": 1,
    "v8_to_istanbul_version": "9.3.0",
    "espree_version": "11.2.0",
}
MAX_REPORT_BYTES = 64 * 1024 * 1024
HEX_SHA = re.compile(r"^[0-9a-fA-F]+$")
HUNK_HEADER = re.compile(
    r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@",
    re.MULTILINE,
)


class CoveragePolicyError(RuntimeError):
    """A stable fail-closed policy or input error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CoverageTarget:
    """One report-producing maintained-code partition."""

    key: str
    language: str
    roots: tuple[str, ...]
    report_kind: str


@dataclass(frozen=True)
class RevisionSelection:
    """Unresolved event-authoritative base and candidate identities."""

    event_name: str
    base_sha: str
    candidate_sha: str
    base_source: str
    candidate_source: str


@dataclass
class CoverageData:
    """Unique source-line observations parsed from one or more reports."""

    files: set[str] = field(default_factory=set)
    observed: set[tuple[str, int]] = field(default_factory=set)
    executable: set[tuple[str, int]] = field(default_factory=set)
    covered: set[tuple[str, int]] = field(default_factory=set)

    def add(self, path: str, line: int, covered: bool) -> None:
        if line <= 0:
            raise CoveragePolicyError(
                "unparseable_report", f"non-positive source line for {path!r}"
            )
        observation = (path, line)
        self.files.add(path)
        self.observed.add(observation)
        self.executable.add(observation)
        if covered:
            self.covered.add(observation)

    def merge(self, other: CoverageData) -> None:
        self.files.update(other.files)
        self.observed.update(other.observed)
        self.executable.update(other.executable)
        self.covered.update(other.covered)


TARGETS = (
    CoverageTarget("backend_python", "python", ("backend",), "cobertura"),
    CoverageTarget("tooling_python", "python", ("scripts",), "cobertura"),
    CoverageTarget("windows_python", "python", ("windows-client",), "cobertura"),
    CoverageTarget(
        "javascript",
        "javascript",
        ("backend/webrender", "tooling/web-ci"),
        "javascript",
    ),
    CoverageTarget(
        "android_app",
        "kotlin",
        (
            "android-client/app/src/main/kotlin",
            "android-client/app/src/main/java",
        ),
        "kover",
    ),
    CoverageTarget(
        "android_core",
        "kotlin",
        (
            "android-client/core/src/main/kotlin",
            "android-client/core/src/main/java",
        ),
        "kover",
    ),
    CoverageTarget(
        "apple",
        "swift",
        (
            "apple-clients/AstralApp/AstralApp",
            "apple-clients/AstralCore/Sources",
            "apple-clients/AstralWatch",
        ),
        "xccov",
    ),
)
TARGET_BY_KEY = {target.key: target for target in TARGETS}
REPORT_FLAGS = {
    "backend_python": "backend-python",
    "tooling_python": "tooling-python",
    "windows_python": "windows-python",
    "javascript": "javascript",
    "android_app": "android-app",
    "android_core": "android-core",
    "apple": "apple",
}
ANCHORS = (
    "backend/",
    "scripts/",
    "windows-client/",
    "android-client/",
    "apple-clients/",
    "tooling/web-ci/",
)


def _repo_path(path: str) -> str:
    value = path.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    pure = PurePosixPath(value)
    if not value or pure.is_absolute() or ".." in pure.parts:
        raise CoveragePolicyError("invalid_diff_path", f"unsafe Git path {path!r}")
    return pure.as_posix()


def _is_test_or_generated(path: str) -> bool:
    parts = PurePosixPath(path).parts
    lowered = {part.lower() for part in parts}
    if lowered & {
        "tests",
        "test",
        "vendor",
        "generated",
        "node_modules",
        "build",
        "dist",
        "deriveddata",
        ".build",
    }:
        return True
    name = parts[-1].lower()
    return name.startswith("test_") or name.endswith(("_test.py", "tests.swift"))


def classify_path(path: str) -> CoverageTarget | None:
    """Return the explicit maintained-code coverage target for a repo path.

    Tests, generated/build output, vendored JavaScript, and declarative build files
    are intentionally excluded by concrete path and suffix rules.
    """

    path = _repo_path(path)
    if _is_test_or_generated(path):
        return None
    if path.endswith(".py"):
        if path.startswith("backend/"):
            return TARGET_BY_KEY["backend_python"]
        if path.startswith("scripts/"):
            return TARGET_BY_KEY["tooling_python"]
        if path.startswith("windows-client/"):
            return TARGET_BY_KEY["windows_python"]
    if path.endswith((".js", ".mjs")):
        if path.startswith("backend/webrender/") and "/static/vendor/" not in path:
            return TARGET_BY_KEY["javascript"]
        if path.startswith("tooling/web-ci/"):
            return TARGET_BY_KEY["javascript"]
    if path.endswith(".kt"):
        if any(
            path.startswith(f"{root}/") for root in TARGET_BY_KEY["android_app"].roots
        ):
            return TARGET_BY_KEY["android_app"]
        if any(
            path.startswith(f"{root}/") for root in TARGET_BY_KEY["android_core"].roots
        ):
            return TARGET_BY_KEY["android_core"]
    if path.endswith(".swift"):
        if any(path.startswith(f"{root}/") for root in TARGET_BY_KEY["apple"].roots):
            return TARGET_BY_KEY["apple"]
    return None


def _payload_string(payload: Mapping[str, Any], *keys: str) -> str | None:
    value: Any = payload
    for key in keys:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value if isinstance(value, str) and value else None


def _event_identity(
    explicit: str | None,
    event_value: str | None,
    *,
    field: str,
) -> str:
    if event_value is None:
        raise CoveragePolicyError(
            "invalid_event", f"event payload does not contain {field}"
        )
    if explicit is not None and explicit.lower() != event_value.lower():
        raise CoveragePolicyError(
            "event_identity_mismatch",
            f"explicit {field} does not match the immutable event value",
        )
    return event_value


def select_revisions(
    *,
    event_name: str | None,
    event_payload: Mapping[str, Any] | None,
    base_sha: str | None,
    candidate_sha: str | None,
    main_ref: str = "refs/heads/main",
) -> RevisionSelection:
    """Select immutable revision inputs from a PR, main push, or manual run.

    Pull requests and main pushes are event-authoritative: explicit values may only
    repeat, never replace, the event identities. Manual runs require explicit SHAs
    (CLI values or workflow-dispatch inputs) and are later ancestry-verified.
    """

    event = (event_name or "manual").strip()
    payload = event_payload or {}
    if event == "pull_request":
        base = _event_identity(
            base_sha,
            _payload_string(payload, "pull_request", "base", "sha"),
            field="pull_request.base.sha",
        )
        candidate = _event_identity(
            candidate_sha,
            _payload_string(payload, "pull_request", "head", "sha"),
            field="pull_request.head.sha",
        )
        return RevisionSelection(
            event, base, candidate, "pull_request.base.sha", "pull_request.head.sha"
        )
    if event == "push":
        if _payload_string(payload, "ref") != main_ref:
            raise CoveragePolicyError(
                "invalid_event", f"coverage push must target {main_ref}"
            )
        base = _event_identity(
            base_sha, _payload_string(payload, "before"), field="push.before"
        )
        candidate = _event_identity(
            candidate_sha, _payload_string(payload, "after"), field="push.after"
        )
        return RevisionSelection(event, base, candidate, "push.before", "push.after")
    if event not in {"manual", "workflow_dispatch"}:
        raise CoveragePolicyError("invalid_event", f"unsupported event {event!r}")
    inputs = payload.get("inputs") if isinstance(payload, Mapping) else None
    event_base = inputs.get("base_sha") if isinstance(inputs, Mapping) else None
    event_candidate = (
        inputs.get("candidate_sha") if isinstance(inputs, Mapping) else None
    )
    if base_sha and event_base and base_sha.lower() != str(event_base).lower():
        raise CoveragePolicyError(
            "event_identity_mismatch", "explicit base_sha disagrees with manual input"
        )
    if (
        candidate_sha
        and event_candidate
        and candidate_sha.lower() != str(event_candidate).lower()
    ):
        raise CoveragePolicyError(
            "event_identity_mismatch",
            "explicit candidate_sha disagrees with manual input",
        )
    base = base_sha or (event_base if isinstance(event_base, str) else None)
    candidate = candidate_sha or (
        event_candidate if isinstance(event_candidate, str) else None
    )
    if not base or not candidate:
        raise CoveragePolicyError(
            "missing_revision",
            "manual coverage requires explicit base and candidate SHAs",
        )
    return RevisionSelection(
        event, base, candidate, "manual.base_sha", "manual.candidate_sha"
    )


def _git(
    repo: Path,
    arguments: Sequence[str],
    *,
    allow_ancestor_false: bool = False,
) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if allow_ancestor_false and process.returncode == 1:
        return b""
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", "replace").strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise CoveragePolicyError(
            "git_error", f"git {' '.join(arguments[:2])} failed{suffix}"
        )
    return process.stdout


def _validate_sha_text(value: str, label: str) -> str:
    if len(value) not in {40, 64} or not HEX_SHA.fullmatch(value):
        raise CoveragePolicyError(
            "invalid_revision", f"{label} must be a full hexadecimal commit SHA"
        )
    lowered = value.lower()
    if set(lowered) == {"0"}:
        raise CoveragePolicyError("zero_revision", f"{label} cannot be the zero SHA")
    return lowered


def validate_revisions(repo: Path, selection: RevisionSelection) -> RevisionSelection:
    """Resolve exact commits and prove a non-zero base ancestor of the candidate."""

    repo = repo.resolve()
    base_input = _validate_sha_text(selection.base_sha, "base_sha")
    candidate_input = _validate_sha_text(selection.candidate_sha, "candidate_sha")

    def resolve(value: str, label: str) -> str:
        output = _git(repo, ["rev-parse", "--verify", f"{value}^{{commit}}"])
        resolved = output.decode("ascii", "strict").strip().lower()
        if resolved != value:
            raise CoveragePolicyError(
                "revision_mismatch",
                f"{label} did not resolve to the exact supplied SHA",
            )
        return resolved

    base = resolve(base_input, "base_sha")
    candidate = resolve(candidate_input, "candidate_sha")
    if base == candidate:
        raise CoveragePolicyError(
            "empty_revision_range", "base and candidate SHAs must be distinct"
        )
    process = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", base, candidate],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.returncode == 1:
        raise CoveragePolicyError(
            "non_ancestor_base", "base SHA is not an ancestor of candidate SHA"
        )
    if process.returncode != 0:
        raise CoveragePolicyError("git_error", "git merge-base ancestry check failed")
    return RevisionSelection(
        selection.event_name,
        base,
        candidate,
        selection.base_source,
        selection.candidate_source,
    )


def read_changed_lines(
    repo: Path, base_sha: str, candidate_sha: str
) -> dict[str, set[int]]:
    """Read added/modified candidate lines from a NUL-delimited immutable Git diff."""

    raw_paths = _git(
        repo,
        [
            "diff",
            "--name-only",
            "-z",
            "--diff-filter=AM",
            "--no-renames",
            base_sha,
            candidate_sha,
            "--",
        ],
    )
    if raw_paths and not raw_paths.endswith(b"\0"):
        raise CoveragePolicyError(
            "invalid_git_diff", "NUL-delimited Git path output was truncated"
        )
    try:
        decoded = [
            item.decode("utf-8", "strict") for item in raw_paths.split(b"\0") if item
        ]
    except UnicodeDecodeError as exc:
        raise CoveragePolicyError(
            "invalid_git_diff", "Git diff contains a non-UTF-8 path"
        ) from exc
    changed: dict[str, set[int]] = {}
    for raw_path in sorted(set(decoded)):
        path = _repo_path(raw_path)
        maintained = classify_path(path) is not None
        text_override = ["--text"] if maintained else []
        patch = _git(
            repo,
            [
                "diff",
                "--unified=0",
                "--no-color",
                "--no-ext-diff",
                "--no-renames",
                *text_override,
                base_sha,
                candidate_sha,
                "--",
                path,
            ],
        ).decode("utf-8", "strict")
        lines: set[int] = set()
        hunks = list(HUNK_HEADER.finditer(patch))
        if maintained and not hunks:
            raise CoveragePolicyError(
                "invalid_git_diff",
                f"maintained source path {path!r} has no textual diff hunks",
            )
        for match in hunks:
            start = int(match.group("start"))
            count = int(match.group("count") or "1")
            lines.update(range(start, start + count))
        changed[path] = lines
    return changed


def _read_report(path: Path) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise CoveragePolicyError(
            "missing_report", f"coverage report is unavailable: {path}"
        ) from exc
    if size <= 0 or size > MAX_REPORT_BYTES:
        raise CoveragePolicyError(
            "unparseable_report", f"coverage report has invalid size: {path}"
        )
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CoveragePolicyError(
            "missing_report", f"coverage report is unreadable: {path}"
        ) from exc


def _normalized_report_path(raw: str, target: CoverageTarget) -> str | None:
    """Map a producer path from its first repository anchor only.

    The first anchor is authoritative.  Looking for a later anchor that happens to
    match ``target`` would let an absolute ``backend/scripts/...`` path masquerade
    as a repository-root ``scripts/...`` path.
    """

    value = raw.strip().replace("\\", "/")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme in {"file", "http", "https"}:
        value = urllib.parse.unquote(parsed.path)
    value = value.replace("\\", "/")
    anchored: list[tuple[int, str]] = []
    for anchor in ANCHORS:
        if value.startswith(anchor):
            anchored.append((0, value))
        marker = f"/{anchor}"
        start = 0
        while (index := value.find(marker, start)) >= 0:
            anchored.append((index + 1, value[index + 1 :]))
            start = index + 1
    if anchored:
        candidate = min(anchored, key=lambda item: item[0])[1]
    else:
        relative = value.lstrip("/")
        if target.key == "javascript" and relative.startswith("static/"):
            candidate = f"backend/webrender/{relative}"
        else:
            return None
    try:
        normalized = _repo_path(candidate)
    except CoveragePolicyError:
        return None
    classified = classify_path(normalized)
    return normalized if classified and classified.key == target.key else None


def _integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise CoveragePolicyError("unparseable_report", f"invalid integer for {label}")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        result = int(value)
    else:
        raise CoveragePolicyError("unparseable_report", f"invalid integer for {label}")
    if result < 0:
        raise CoveragePolicyError("unparseable_report", f"negative integer for {label}")
    return result


def _local_name(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _direct_children(node: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in node if _local_name(child) == name]


def _line_counter(node: ET.Element, *, label: str) -> tuple[int, int]:
    counters = [
        child
        for child in _direct_children(node, "counter")
        if child.get("type") == "LINE"
    ]
    if len(counters) != 1:
        raise CoveragePolicyError(
            "unparseable_report", f"{label} must contain exactly one LINE counter"
        )
    counter = counters[0]
    return (
        _integer(counter.get("missed"), label=f"{label} missed LINE counter"),
        _integer(counter.get("covered"), label=f"{label} covered LINE counter"),
    )


def _rate(value: str | None, *, label: str) -> Decimal:
    try:
        result = Decimal(value) if value is not None else Decimal("NaN")
    except InvalidOperation as exc:
        raise CoveragePolicyError(
            "unparseable_report", f"invalid line rate for {label}"
        ) from exc
    if not result.is_finite() or result < 0 or result > 1:
        raise CoveragePolicyError(
            "unparseable_report", f"invalid line rate for {label}"
        )
    return result


def _validate_rate(value: str | None, *, covered: int, total: int, label: str) -> None:
    if value is None:
        return
    actual = _rate(value, label=label)
    expected = Decimal(covered) / Decimal(total) if total else Decimal(1)
    if abs(actual - expected) > Decimal("0.0001"):
        raise CoveragePolicyError(
            "unparseable_report", f"{label} disagrees with its line observations"
        )


def _cobertura_sources(root: ET.Element) -> list[str]:
    sources: list[str] = []
    for container in root.iter():
        if _local_name(container) != "sources":
            continue
        for source in _direct_children(container, "source"):
            if source.text and source.text.strip():
                sources.append(source.text.strip().replace("\\", "/"))
    return sources


def _cobertura_path(
    raw: str, sources: Sequence[str], target: CoverageTarget
) -> str | None:
    """Resolve coverage.py filenames against their declared source roots."""

    candidates: set[str] = set()
    direct = _normalized_report_path(raw, target)
    if direct is not None:
        candidates.add(direct)
    parsed = urllib.parse.urlsplit(raw)
    is_relative = (
        not parsed.scheme and not PurePosixPath(raw.replace("\\", "/")).is_absolute()
    )
    if is_relative:
        for source in sources:
            combined = f"{source.rstrip('/')}/{raw.lstrip('./')}"
            mapped = _normalized_report_path(combined, target)
            if mapped is not None:
                candidates.add(mapped)
    if len(candidates) > 1:
        raise CoveragePolicyError(
            "unparseable_report", f"ambiguous Cobertura source path {raw!r}"
        )
    return next(iter(candidates), None)


def _parse_cobertura(content: bytes, target: CoverageTarget) -> CoverageData:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise CoveragePolicyError(
            "unparseable_report", "invalid Cobertura XML"
        ) from exc
    data = CoverageData()
    declared_valid = _integer(root.get("lines-valid"), label="Cobertura lines-valid")
    declared_covered = _integer(
        root.get("lines-covered"), label="Cobertura lines-covered"
    )
    if declared_covered > declared_valid:
        raise CoveragePolicyError(
            "unparseable_report", "Cobertura covered line total exceeds valid lines"
        )
    sources = _cobertura_sources(root)
    classes = [node for node in root.iter() if _local_name(node) == "class"]
    if not classes:
        raise CoveragePolicyError(
            "unparseable_report", "Cobertura report has no classes"
        )
    artifact_lines: dict[tuple[str, int], bool] = {}
    normalized_lines: set[tuple[str, int]] = set()
    for class_node in classes:
        raw = class_node.get("filename")
        if not raw:
            raise CoveragePolicyError(
                "unparseable_report", "Cobertura class lacks filename"
            )
        path = _cobertura_path(raw, sources, target)
        class_total = 0
        class_covered = 0
        for line_node in class_node.iter():
            if _local_name(line_node) != "line":
                continue
            number = _integer(line_node.get("number"), label="Cobertura line")
            if number <= 0:
                raise CoveragePolicyError(
                    "unparseable_report", "Cobertura line must be positive"
                )
            hits = _integer(line_node.get("hits"), label="Cobertura hits")
            identity = (raw.replace("\\", "/"), number)
            if identity in artifact_lines:
                raise CoveragePolicyError(
                    "unparseable_report", "duplicate Cobertura source-line observation"
                )
            covered = hits > 0
            artifact_lines[identity] = covered
            class_total += 1
            class_covered += int(covered)
            if path is not None:
                observation = (path, number)
                if observation in normalized_lines:
                    raise CoveragePolicyError(
                        "unparseable_report",
                        "duplicate normalized Cobertura source-line observation",
                    )
                normalized_lines.add(observation)
                data.add(path, number, covered)
        _validate_rate(
            class_node.get("line-rate"),
            covered=class_covered,
            total=class_total,
            label=f"Cobertura class {raw!r} line-rate",
        )
        if path is not None:
            data.files.add(path)
    parsed_covered = sum(artifact_lines.values())
    if len(artifact_lines) != declared_valid or parsed_covered != declared_covered:
        raise CoveragePolicyError(
            "unparseable_report",
            "Cobertura root totals disagree with class line observations",
        )
    _validate_rate(
        root.get("line-rate"),
        covered=parsed_covered,
        total=len(artifact_lines),
        label="Cobertura root line-rate",
    )
    return data


def _parse_kover(content: bytes, target: CoverageTarget) -> CoverageData:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise CoveragePolicyError("unparseable_report", "invalid Kover XML") from exc
    data = CoverageData()
    packages = _direct_children(root, "package")
    if not packages:
        raise CoveragePolicyError("unparseable_report", "Kover report has no packages")
    report_missed = 0
    report_covered = 0
    normalized_lines: set[tuple[str, int]] = set()
    for package in packages:
        package_name = (package.get("name") or "").replace(".", "/").strip("/")
        package_missed = 0
        package_covered = 0
        for source in _direct_children(package, "sourcefile"):
            name = source.get("name")
            if not name:
                raise CoveragePolicyError(
                    "unparseable_report", "Kover sourcefile lacks a name"
                )
            relative = f"{package_name}/{name}" if package_name else name
            relative = f"{target.roots[0]}/{relative}"
            path = _normalized_report_path(relative, target)
            source_missed = 0
            source_covered = 0
            seen_numbers: set[int] = set()
            for line_node in _direct_children(source, "line"):
                line = _integer(line_node.get("nr"), label="Kover line")
                if line <= 0 or line in seen_numbers:
                    raise CoveragePolicyError(
                        "unparseable_report",
                        "Kover source lines must be positive and unique",
                    )
                seen_numbers.add(line)
                covered = _integer(line_node.get("ci", 0), label="Kover ci")
                missed = _integer(line_node.get("mi", 0), label="Kover mi")
                if covered + missed <= 0:
                    raise CoveragePolicyError(
                        "unparseable_report", "Kover line has no instructions"
                    )
                is_covered = covered > 0
                source_covered += int(is_covered)
                source_missed += int(not is_covered)
                if path is not None:
                    observation = (path, line)
                    if observation in normalized_lines:
                        raise CoveragePolicyError(
                            "unparseable_report",
                            "duplicate normalized Kover source-line observation",
                        )
                    normalized_lines.add(observation)
                    data.add(path, line, is_covered)
            if _line_counter(source, label=f"Kover sourcefile {name!r}") != (
                source_missed,
                source_covered,
            ):
                raise CoveragePolicyError(
                    "unparseable_report",
                    f"Kover sourcefile {name!r} LINE counter disagrees with lines",
                )
            package_missed += source_missed
            package_covered += source_covered
            if path is not None:
                data.files.add(path)
        if _line_counter(package, label=f"Kover package {package_name!r}") != (
            package_missed,
            package_covered,
        ):
            raise CoveragePolicyError(
                "unparseable_report",
                f"Kover package {package_name!r} LINE counter disagrees with sourcefiles",
            )
        report_missed += package_missed
        report_covered += package_covered
    if _line_counter(root, label="Kover report") != (
        report_missed,
        report_covered,
    ):
        raise CoveragePolicyError(
            "unparseable_report",
            "Kover report LINE counter disagrees with packages",
        )
    return data


def _strict_json(content: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise CoveragePolicyError(
                    "unparseable_report", f"duplicate JSON key {key!r}"
                )
            result[key] = value
        return result

    def nonfinite(value: str) -> None:
        raise CoveragePolicyError(
            "unparseable_report", f"non-finite JSON value {value}"
        )

    try:
        return json.loads(content, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoveragePolicyError(
            "unparseable_report", "invalid coverage JSON"
        ) from exc


def _parse_istanbul(
    document: Mapping[str, Any], target: CoverageTarget
) -> CoverageData:
    data = CoverageData()
    normalized_sources: set[str] = set()
    normalized_lines: set[tuple[str, int]] = set()
    for raw_key, raw_record in document.items():
        if not isinstance(raw_record, Mapping):
            raise CoveragePolicyError(
                "unparseable_report", "Istanbul source record must be an object"
            )
        if not ({"statementMap", "s", "l"} & set(raw_record)):
            raise CoveragePolicyError(
                "unparseable_report",
                "Istanbul source record lacks canonical statementMap+s data",
            )
        if "l" in raw_record:
            raise CoveragePolicyError(
                "unparseable_report",
                "Istanbul line maps are not accepted; canonical statementMap+s is required",
            )
        raw_path = raw_record.get("path", raw_key)
        if not isinstance(raw_path, str):
            continue
        path = _normalized_report_path(raw_path, target)
        if path is None:
            continue
        if path in normalized_sources:
            raise CoveragePolicyError(
                "unparseable_report", "duplicate normalized Istanbul source record"
            )
        normalized_sources.add(path)
        data.files.add(path)
        statements = raw_record.get("statementMap")
        hits_by_id = raw_record.get("s")
        if not isinstance(statements, Mapping) or not isinstance(hits_by_id, Mapping):
            raise CoveragePolicyError(
                "unparseable_report", "Istanbul statement maps are incomplete"
            )
        if not statements or not hits_by_id:
            raise CoveragePolicyError(
                "unparseable_report", "Istanbul statement maps cannot be empty"
            )
        if set(statements) != set(hits_by_id):
            raise CoveragePolicyError(
                "unparseable_report", "Istanbul statement and hit keys differ"
            )
        for statement_id, location in statements.items():
            if not isinstance(location, Mapping) or statement_id not in hits_by_id:
                raise CoveragePolicyError(
                    "unparseable_report", "Istanbul statement entry is incomplete"
                )
            start = location.get("start")
            end = location.get("end")
            if not isinstance(start, Mapping) or not isinstance(end, Mapping):
                raise CoveragePolicyError(
                    "unparseable_report", "Istanbul statement location is invalid"
                )
            first = _integer(start.get("line"), label="Istanbul start line")
            last = _integer(end.get("line"), label="Istanbul end line")
            if last < first:
                raise CoveragePolicyError(
                    "unparseable_report", "Istanbul statement range is reversed"
                )
            covered = (
                _integer(hits_by_id[statement_id], label="Istanbul statement hits") > 0
            )
            if (path, first) in normalized_lines:
                raise CoveragePolicyError(
                    "unparseable_report",
                    "duplicate Istanbul executable-line observation",
                )
            normalized_lines.add((path, first))
            data.add(path, first, covered)
    if not data.files:
        raise CoveragePolicyError(
            "unparseable_report", "Istanbul report has no sources"
        )
    return data


def _parse_javascript(content: bytes, target: CoverageTarget) -> CoverageData:
    document = _strict_json(content)
    if not isinstance(document, Mapping) or set(document) != JAVASCRIPT_REPORT_KEYS:
        raise CoveragePolicyError(
            "unparseable_report",
            "JavaScript coverage requires the exact lock-pinned AstralDeep "
            "executable-line producer envelope",
        )
    for key, expected in JAVASCRIPT_REPORT_IDENTITY.items():
        if document.get(key) != expected:
            raise CoveragePolicyError(
                "unparseable_report",
                f"JavaScript coverage has unsupported producer field {key!r}",
            )
    coverage = document.get("coverage")
    if not isinstance(coverage, Mapping) or not coverage:
        raise CoveragePolicyError(
            "unparseable_report", "JavaScript coverage envelope is empty"
        )
    return _parse_istanbul(coverage, target)


def _add_xccov_archive_lines(data: CoverageData, path: str, values: Any) -> None:
    if not isinstance(values, list):
        raise CoveragePolicyError(
            "unparseable_report", "xccov archive file observations must be an array"
        )
    if not values:
        raise CoveragePolicyError(
            "unparseable_report", "xccov archive file observations cannot be empty"
        )
    seen_lines: set[int] = set()
    for item in values:
        if not isinstance(item, Mapping):
            raise CoveragePolicyError(
                "unparseable_report", "invalid xccov archive line observation"
            )
        executable = item.get("isExecutable")
        if not isinstance(executable, bool):
            raise CoveragePolicyError(
                "unparseable_report", "xccov archive line lacks isExecutable"
            )
        line = _integer(item.get("line"), label="xccov archive line")
        if line <= 0 or line in seen_lines:
            raise CoveragePolicyError(
                "unparseable_report",
                "xccov archive lines must be positive and unique",
            )
        seen_lines.add(line)
        data.observed.add((path, line))
        if executable:
            count = _integer(
                item.get("executionCount", 0),
                label="xccov archive execution count",
            )
            data.add(path, line, count > 0)
        elif "executionCount" in item:
            _integer(item.get("executionCount"), label="xccov archive execution count")
    if seen_lines != set(range(1, max(seen_lines) + 1)):
        raise CoveragePolicyError(
            "unparseable_report",
            "xccov archive must observe every physical line contiguously from line 1",
        )
    data.files.add(path)


def _parse_xccov(content: bytes, target: CoverageTarget) -> CoverageData:
    document = _strict_json(content)
    if not isinstance(document, Mapping):
        raise CoveragePolicyError(
            "unparseable_report", "xccov report must be an object"
        )
    if "targets" in document or "files" in document:
        raise CoveragePolicyError(
            "unsupported_xccov_report",
            "xccov summary JSON lacks per-line execution counts; export and "
            "map `xcrun xccov view --archive --json <xcresult>` observations",
        )
    data = CoverageData()
    archive_entries = [
        (raw_path, observations)
        for raw_path, observations in document.items()
        if isinstance(raw_path, str) and raw_path.endswith(".swift")
    ]
    if not archive_entries:
        raise CoveragePolicyError(
            "unparseable_report", "xccov archive has no Swift line observations"
        )
    normalized_sources: set[str] = set()
    for raw_path, observations in archive_entries:
        path = _normalized_report_path(raw_path, target)
        if path is not None:
            if path in normalized_sources:
                raise CoveragePolicyError(
                    "unparseable_report", "duplicate normalized xccov source record"
                )
            normalized_sources.add(path)
            _add_xccov_archive_lines(data, path, observations)
    if not data.files:
        raise CoveragePolicyError(
            "unparseable_report", "xccov archive has no maintained Swift sources"
        )
    return data


def parse_coverage_report(path: Path, target_key: str) -> CoverageData:
    """Parse one Cobertura/Kover, V8/Istanbul, or xccov report."""

    try:
        target = TARGET_BY_KEY[target_key]
    except KeyError as exc:
        raise CoveragePolicyError(
            "invalid_target", f"unknown target {target_key!r}"
        ) from exc
    content = _read_report(path)
    try:
        if target.report_kind == "cobertura":
            return _parse_cobertura(content, target)
        if target.report_kind == "kover":
            return _parse_kover(content, target)
        if target.report_kind == "javascript":
            return _parse_javascript(content, target)
        return _parse_xccov(content, target)
    except CoveragePolicyError as exc:
        if exc.code in {"missing_report", "unsupported_xccov_report"}:
            raise
        raise CoveragePolicyError(
            "unparseable_report", f"{path}: {exc.message}"
        ) from exc


def _percentage(covered: int, executable: int) -> float:
    return round(covered * 100.0 / executable, 2)


def _threshold(value: float | int | str) -> Decimal:
    try:
        threshold = Decimal(str(value))
    except InvalidOperation as exc:
        raise CoveragePolicyError(
            "invalid_threshold", "fail-under is not numeric"
        ) from exc
    if not threshold.is_finite() or threshold < 0 or threshold > 100:
        raise CoveragePolicyError(
            "invalid_threshold", "fail-under must be between 0 and 100"
        )
    return threshold


def evaluate_changed_coverage(
    repo: Path,
    selection: RevisionSelection,
    reports: Mapping[str, Sequence[Path]],
    *,
    fail_under: float | int | str = 90,
) -> dict[str, Any]:
    """Evaluate changed executable lines and return a deterministic decision.

    Repeated reports are unioned by normalized ``(source path, line)``. Every
    applicable target must supply parseable coverage and map every changed source
    file before per-language and combined thresholds are evaluated.
    """

    threshold = _threshold(fail_under)
    changed = read_changed_lines(repo, selection.base_sha, selection.candidate_sha)
    maintained: dict[str, CoverageTarget] = {}
    for path in sorted(changed):
        target = classify_path(path)
        if target is not None:
            maintained[path] = target
    if not maintained:
        raise CoveragePolicyError(
            "unexpected_empty_executable_diff",
            "immutable comparison contains no maintained executable source paths",
        )

    target_data: dict[str, CoverageData] = {}
    report_summary: dict[str, Any] = {}
    for target_key in sorted({target.key for target in maintained.values()}):
        target = TARGET_BY_KEY[target_key]
        artifacts = sorted(
            {Path(path) for path in reports.get(target_key, ())}, key=str
        )
        if not artifacts:
            raise CoveragePolicyError(
                "missing_report",
                f"changed {target_key} code requires --{REPORT_FLAGS[target_key]}",
            )
        merged = CoverageData()
        for artifact in artifacts:
            merged.merge(parse_coverage_report(artifact, target_key))
        changed_files = sorted(
            path for path, mapped in maintained.items() if mapped.key == target_key
        )
        missing_files = sorted(set(changed_files) - merged.files)
        if missing_files:
            raise CoveragePolicyError(
                "unmapped_changed_file",
                f"{target_key} reports do not map changed file {missing_files[0]!r}",
            )
        if target_key == "apple":
            for changed_file in changed_files:
                missing_lines = sorted(
                    changed[changed_file]
                    - {
                        line
                        for observed_path, line in merged.observed
                        if observed_path == changed_file
                    }
                )
                if missing_lines:
                    raise CoveragePolicyError(
                        "unmapped_changed_line",
                        "apple reports do not observe changed physical line "
                        f"{changed_file!r}:{missing_lines[0]}",
                    )
        target_data[target_key] = merged
        report_summary[target_key] = {
            "artifacts": [str(path).replace("\\", "/") for path in artifacts],
            "changed_files": changed_files,
            "mapped_files": sorted(set(changed_files) & merged.files),
        }

    line_records: list[dict[str, Any]] = []
    language_lines: dict[str, set[tuple[str, int]]] = {}
    covered_lines: set[tuple[str, int]] = set()
    for path, target in sorted(maintained.items()):
        parsed = target_data[target.key]
        for line in sorted(changed[path]):
            observation = (path, line)
            if observation not in parsed.executable:
                continue
            language_lines.setdefault(target.language, set()).add(observation)
            covered = observation in parsed.covered
            if covered:
                covered_lines.add(observation)
            line_records.append(
                {
                    "path": path,
                    "line": line,
                    "target": target.key,
                    "language": target.language,
                    "covered": covered,
                }
            )
    if not line_records:
        raise CoveragePolicyError(
            "unexpected_empty_executable_diff",
            "coverage reports map no executable added or modified lines",
        )

    failures: list[dict[str, str]] = []
    language_summary: dict[str, Any] = {}
    for language in sorted(language_lines):
        observations = language_lines[language]
        covered = len(observations & covered_lines)
        executable = len(observations)
        percent = _percentage(covered, executable)
        language_summary[language] = {
            "covered_lines": covered,
            "executable_lines": executable,
            "percent": percent,
        }
        if Decimal(covered * 100) < threshold * executable:
            failures.append(
                {
                    "code": "coverage_below_threshold",
                    "scope": language,
                    "message": f"{language} changed-line coverage {percent:.2f}% is below {threshold}%",
                }
            )
    combined_observations = set().union(*language_lines.values())
    combined_covered = len(combined_observations & covered_lines)
    combined_total = len(combined_observations)
    combined_percent = _percentage(combined_covered, combined_total)
    if Decimal(combined_covered * 100) < threshold * combined_total:
        failures.append(
            {
                "code": "coverage_below_threshold",
                "scope": "combined",
                "message": (
                    f"combined changed-line coverage {combined_percent:.2f}% "
                    f"is below {threshold}%"
                ),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "fail" if failures else "pass",
        "base_sha": selection.base_sha,
        "candidate_sha": selection.candidate_sha,
        "revisions_validated": True,
        "selection": {
            "event_name": selection.event_name,
            "base_source": selection.base_source,
            "candidate_source": selection.candidate_source,
        },
        "fail_under": float(threshold),
        "diff": {
            "changed_paths": sorted(changed),
            "maintained_paths": sorted(maintained),
            "changed_maintained_lines": sum(len(changed[path]) for path in maintained),
            "executable_lines": len(line_records),
        },
        "reports": report_summary,
        "languages": language_summary,
        "combined": {
            "covered_lines": combined_covered,
            "executable_lines": combined_total,
            "percent": combined_percent,
        },
        "lines": line_records,
        "failures": failures,
    }


def _write_document(document: Mapping[str, Any], output: str) -> None:
    rendered = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if output == "-":
        sys.stdout.write(rendered)
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def _load_event(path: str | None, event_name: str | None) -> Mapping[str, Any] | None:
    if not path:
        if event_name in {"pull_request", "push"}:
            raise CoveragePolicyError(
                "invalid_event",
                "pull_request and push selection require an event payload",
            )
        return None
    content = _read_report(Path(path))
    payload = _strict_json(content)
    if not isinstance(payload, Mapping):
        raise CoveragePolicyError(
            "invalid_event", "event payload must be a JSON object"
        )
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Git repository root")
    parser.add_argument(
        "--event-name", choices=("pull_request", "push", "workflow_dispatch", "manual")
    )
    parser.add_argument("--event-path", help="GitHub event JSON path")
    parser.add_argument("--main-ref", default="refs/heads/main")
    parser.add_argument("--base-sha")
    parser.add_argument("--candidate-sha")
    parser.add_argument("--backend-python", action="append", default=[])
    parser.add_argument("--tooling-python", action="append", default=[])
    parser.add_argument("--windows-python", action="append", default=[])
    parser.add_argument("--javascript", action="append", default=[])
    parser.add_argument("--android-app", action="append", default=[])
    parser.add_argument("--android-core", action="append", default=[])
    parser.add_argument("--apple", action="append", default=[])
    parser.add_argument("--fail-under", default="90")
    parser.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the collector CLI, always writing deterministic pass/fail JSON."""

    args = _parser().parse_args(argv)
    event_name = args.event_name or os.environ.get("GITHUB_EVENT_NAME")
    event_path = args.event_path or os.environ.get("GITHUB_EVENT_PATH")
    selected: RevisionSelection | None = None
    revisions_validated = False
    threshold: Decimal | None = None
    try:
        threshold = _threshold(args.fail_under)
        payload = _load_event(event_path, event_name)
        selected = select_revisions(
            event_name=event_name,
            event_payload=payload,
            base_sha=args.base_sha,
            candidate_sha=args.candidate_sha,
            main_ref=args.main_ref,
        )
        selected = validate_revisions(Path(args.repo), selected)
        revisions_validated = True
        reports = {
            "backend_python": [Path(path) for path in args.backend_python],
            "tooling_python": [Path(path) for path in args.tooling_python],
            "windows_python": [Path(path) for path in args.windows_python],
            "javascript": [Path(path) for path in args.javascript],
            "android_app": [Path(path) for path in args.android_app],
            "android_core": [Path(path) for path in args.android_core],
            "apple": [Path(path) for path in args.apple],
        }
        decision = evaluate_changed_coverage(
            Path(args.repo), selected, reports, fail_under=args.fail_under
        )
    except CoveragePolicyError as exc:
        decision = {
            "schema_version": SCHEMA_VERSION,
            "status": "error",
            "error": {"code": exc.code, "message": exc.message},
        }
        if threshold is not None:
            decision["fail_under"] = float(threshold)
        if selected is not None:
            decision.update(
                {
                    "base_sha": selected.base_sha,
                    "candidate_sha": selected.candidate_sha,
                    "revisions_validated": revisions_validated,
                    "selection": {
                        "event_name": selected.event_name,
                        "base_source": selected.base_source,
                        "candidate_source": selected.candidate_source,
                    },
                }
            )
    _write_document(decision, args.output)
    return 0 if decision["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
