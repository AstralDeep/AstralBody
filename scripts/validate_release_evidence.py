#!/usr/bin/env python3
"""Validate feature-060 release evidence without candidate-trusting fallbacks.

The module deliberately uses only the Python standard library.  JSON Schema
validation proves document shape; the policy layer separately proves
same-candidate identity, required quantitative checks, protected provenance,
and append-only exception-debt state.  A locally produced result is diagnostic
only.  A qualifying decision additionally requires independently verified
protected-workflow inputs and is emitted only from the protected execution
context described by the CLI arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote, urlsplit


MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_NESTING = 128
MAX_COLLECTION_ITEMS = 100_000
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LEDGER_PATH_RE = re.compile(
    r"^(?:debts|resolutions)/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\.json$"
)
GH_RUN_MEMBER_RE = re.compile(
    r"^gh://[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/runs/[1-9][0-9]*/"
    r"attempts/[1-9][0-9]*/artifacts/[1-9][0-9]*/members/"
    r"(?P<member>[A-Za-z0-9._~!$&'()*+,;=:@%/-]+)$"
)
GH_RELEASE_ASSET_RE = re.compile(
    r"^gh://[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/"
    r"[1-9][0-9]*/assets/[1-9][0-9]*$"
)
OCI_REFERENCE_RE = re.compile(
    r"^oci://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/(?P<repository>[A-Za-z0-9._/-]+)"
    r"@sha256:[0-9a-f]{64}$"
)
GHGIT_REFERENCE_RE = re.compile(
    r"^ghgit://[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/commits/[0-9a-f]{40}"
    r"(?:/paths/(?P<member>[A-Za-z0-9._~!$&'()*+,;=:@%/-]+))?$"
)

ANNOTATION_KEYWORDS = {
    "$schema",
    "$id",
    "title",
    "description",
    "$comment",
}
ASSERTION_KEYWORDS = {
    "$defs",
    "$ref",
    "type",
    "const",
    "enum",
    "required",
    "properties",
    "additionalProperties",
    "pattern",
    "format",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
    "uniqueItems",
    "items",
    "contains",
    "allOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
}
SUPPORTED_KEYWORDS = ANNOTATION_KEYWORDS | ASSERTION_KEYWORDS
SUPPORTED_TYPES = {
    "null",
    "boolean",
    "object",
    "array",
    "number",
    "integer",
    "string",
}
SUPPORTED_FORMATS = {"uuid", "date-time", "uri"}

REQUIRED_TARGETS = (
    "backend",
    "web",
    "windows",
    "android",
    "macos",
    "ios",
    "watchos",
    "docs",
)
COMMON_CLIENT_CHECKS = {
    "sign_in",
    "rendered_chat",
    "reconnect_resume",
    "agent_lifecycle",
    "accessibility_semantics",
    "personal_agent",
}
REQUIRED_CHECKS = {
    "backend": {
        "candidate_staging",
        "runtime_admission_stress",
        "scheduler_exactly_once",
        "migration_multi_instance",
        "process_supervision_stress",
    },
    "web": COMMON_CLIENT_CHECKS,
    "windows": COMMON_CLIENT_CHECKS
    | {
        "windows_deployment_validation",
        "windows_clean_profile_no_dialog",
        "windows_frozen_worker",
        "windows_upgrade_from_0_3_0",
        "dependency_lock_reproducibility",
    },
    "android": COMMON_CLIENT_CHECKS | {"android_next_toolchain_readiness"},
    "macos": COMMON_CLIENT_CHECKS
    | {"apple_first_login_llm", "macos_personal_agent_host"},
    "ios": COMMON_CLIENT_CHECKS | {"apple_first_login_llm"},
    "watchos": COMMON_CLIENT_CHECKS,
    "docs": {"documentation_links", "apply_config_reload"},
}
SHIPPING_CLIENTS = {"web", "windows", "android", "macos", "ios", "watchos"}
NON_WAIVABLE_CHECKS = {"apple_first_login_llm", "candidate_staging"}


class ReleaseEvidenceError(ValueError):
    """Base class for deterministic release-evidence validation failures."""


class DocumentError(ReleaseEvidenceError):
    """Raised when bounded, strict JSON decoding fails."""


class SchemaDefinitionError(ReleaseEvidenceError):
    """Raised when a tracked schema exceeds the supported validator profile."""


class SchemaValidationError(ReleaseEvidenceError):
    """Raised when a document does not satisfy its tracked schema."""


class PolicyError(ReleaseEvidenceError):
    """Raised when schema-valid evidence violates release policy."""


class ProvenanceError(ReleaseEvidenceError):
    """Raised when immutable bytes or protected producer identity cannot be proven."""


class LedgerError(ReleaseEvidenceError):
    """Raised when the protected debt-ledger snapshot is invalid or stale."""


@dataclass(frozen=True)
class EvidencePolicyResult:
    """Non-authorizing result of deterministic evidence-set policy evaluation."""

    required_targets: tuple[str, ...]
    staging_environment_id: str
    used_exception_ids: tuple[str, ...]


@dataclass(frozen=True)
class LedgerSnapshot:
    """Exact protected Git commit/tree and canonical entry digest snapshot."""

    repository: str
    ref: str
    commit_sha: str
    tree_sha: str
    snapshot_sha256: str
    paths: Mapping[str, str]
    records: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class MeasurementRequirement:
    """Exact metric semantics required for a thresholded release check."""

    aggregation: str
    comparator: str
    threshold: float
    unit: str


METRIC_REQUIREMENTS: Mapping[str, Mapping[str, MeasurementRequirement]] = {
    "runtime_admission_stress": {
        "message_count": MeasurementRequirement("total", "gte", 1000, "count"),
        "active_limit_violations": MeasurementRequirement("total", "eq", 0, "count"),
        "unresolved_operations": MeasurementRequirement("total", "eq", 0, "count"),
    },
    "scheduler_exactly_once": {
        "interleaving_count": MeasurementRequirement("total", "gte", 10_000, "count"),
        "duplicate_effects": MeasurementRequirement("total", "eq", 0, "count"),
    },
    "migration_multi_instance": {
        "trial_count": MeasurementRequirement("total", "gte", 50, "count"),
        "migration_owner_violations": MeasurementRequirement("total", "eq", 0, "count"),
    },
    "process_supervision_stress": {
        "trial_count": MeasurementRequirement("total", "gte", 100, "count"),
        "residual_processes": MeasurementRequirement("total", "eq", 0, "count"),
    },
    "reconnect_resume": {
        "trial_count": MeasurementRequirement("total", "gte", 20, "count"),
        "resume_success_rate": MeasurementRequirement("rate", "gte", 100, "percent"),
    },
    "apple_first_login_llm": {
        "trial_count": MeasurementRequirement("total", "gte", 30, "count"),
        "acknowledgement_p95_ms": MeasurementRequirement(
            "p95", "lte", 250, "milliseconds"
        ),
        "success_within_five_seconds_percent": MeasurementRequirement(
            "rate", "gte", 95, "percent"
        ),
        "terminal_max_ms": MeasurementRequirement(
            "maximum", "lte", 10_000, "milliseconds"
        ),
        "responsive_interaction_p95_ms": MeasurementRequirement(
            "p95", "lte", 250, "milliseconds"
        ),
    },
}


def _duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise DocumentError(f"duplicate JSON key: {key}")
        value[key] = child
    return value


def _nonfinite(value: str) -> None:
    raise DocumentError(f"non-finite JSON number: {value}")


def _bound_document(value: Any, *, depth: int = 0) -> int:
    if depth > MAX_NESTING:
        raise DocumentError(f"JSON nesting exceeds {MAX_NESTING}")
    count = 1
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise DocumentError("JSON object key is not a string")
            count += _bound_document(child, depth=depth + 1)
    elif isinstance(value, list):
        for child in value:
            count += _bound_document(child, depth=depth + 1)
    if count > MAX_COLLECTION_ITEMS:
        raise DocumentError(f"JSON value count exceeds {MAX_COLLECTION_ITEMS}")
    return count


def load_json_bytes(content: bytes, *, source: str = "<bytes>") -> Any:
    """Decode one bounded JSON value, rejecting duplicate keys and NaN/Infinity."""

    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise DocumentError(
            f"{source}: document size must be 1..{MAX_DOCUMENT_BYTES} bytes"
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentError(f"{source}: document is not UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_object,
            parse_constant=_nonfinite,
        )
    except DocumentError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise DocumentError(f"{source}: invalid JSON: {exc}") from exc
    _bound_document(value)
    return value


def load_json_document(path: str | Path) -> dict[str, Any]:
    """Load one strict, bounded JSON object from ``path``."""

    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise DocumentError(f"cannot stat {source}: {exc}") from exc
    if size <= 0 or size > MAX_DOCUMENT_BYTES:
        raise DocumentError(
            f"{source}: document size must be 1..{MAX_DOCUMENT_BYTES} bytes"
        )
    try:
        value = load_json_bytes(source.read_bytes(), source=str(source))
    except OSError as exc:
        raise DocumentError(f"cannot read {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise DocumentError(f"{source}: top-level JSON value must be an object")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical compact sorted-key UTF-8 JSON with no trailing newline."""

    _bound_document(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DocumentError(f"value cannot be canonicalized: {exc}") from exc


def canonical_json_sha256(value: Any) -> str:
    """Hash the canonical compact JSON representation used by protected payloads."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _schema_children(schema: Mapping[str, Any]) -> Iterable[tuple[str, Any]]:
    for keyword in ("$defs", "properties"):
        values = schema.get(keyword, {})
        if not isinstance(values, dict):
            raise SchemaDefinitionError(f"{keyword} must be an object")
        for name, child in values.items():
            yield f"{keyword}/{name}", child
    for keyword in ("items", "contains", "not", "if", "then", "else"):
        if keyword in schema:
            yield keyword, schema[keyword]
    for keyword in ("allOf", "oneOf"):
        values = schema.get(keyword, [])
        if not isinstance(values, list):
            raise SchemaDefinitionError(f"{keyword} must be an array")
        for index, child in enumerate(values):
            yield f"{keyword}/{index}", child
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        yield "additionalProperties", additional


def validate_schema_document(schema: Mapping[str, Any]) -> None:
    """Fail closed unless a schema uses exactly the documented local profile."""

    def walk(node: Any, location: str) -> None:
        if not isinstance(node, dict):
            raise SchemaDefinitionError(f"{location}: schema node must be an object")
        unknown = set(node) - SUPPORTED_KEYWORDS
        if unknown:
            raise SchemaDefinitionError(
                f"{location}: unsupported schema keyword(s): {sorted(unknown)}"
            )
        declared = node.get("type")
        if declared is not None:
            options = [declared] if isinstance(declared, str) else declared
            if (
                not isinstance(options, list)
                or not options
                or not all(isinstance(item, str) for item in options)
                or not set(options) <= SUPPORTED_TYPES
                or len(options) != len(set(options))
            ):
                raise SchemaDefinitionError(
                    f"{location}: invalid type declaration {declared!r}"
                )
        reference = node.get("$ref")
        if reference is not None and (
            not isinstance(reference, str)
            or not reference.startswith("#/$defs/")
            or reference.count("#") != 1
        ):
            raise SchemaDefinitionError(
                f"{location}: only local #/$defs references are supported"
            )
        required = node.get("required")
        if required is not None and (
            not isinstance(required, list)
            or not all(isinstance(item, str) for item in required)
            or len(required) != len(set(required))
        ):
            raise SchemaDefinitionError(f"{location}: invalid required array")
        pattern = node.get("pattern")
        if pattern is not None:
            if not isinstance(pattern, str):
                raise SchemaDefinitionError(f"{location}: pattern must be a string")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise SchemaDefinitionError(
                    f"{location}: invalid regular expression: {exc}"
                ) from exc
        format_name = node.get("format")
        if format_name is not None and format_name not in SUPPORTED_FORMATS:
            raise SchemaDefinitionError(
                f"{location}: unsupported format {format_name!r}"
            )
        for label, child in _schema_children(node):
            walk(child, f"{location}/{label}")

    walk(schema, "$")
    definitions = schema.get("$defs", {})
    for location, node in _walk_schema_nodes(schema):
        reference = node.get("$ref")
        if reference is not None:
            key = reference.removeprefix("#/$defs/").replace("~1", "/").replace(
                "~0", "~"
            )
            if "/" in key or key not in definitions:
                raise SchemaDefinitionError(
                    f"{location}: unresolved or nested local reference {reference!r}"
                )


def _walk_schema_nodes(
    schema: Mapping[str, Any], *, location: str = "$"
) -> Iterable[tuple[str, Mapping[str, Any]]]:
    yield location, schema
    for label, child in _schema_children(schema):
        if isinstance(child, dict):
            yield from _walk_schema_nodes(child, location=f"{location}/{label}")


def _json_equal(left: Any, right: Any) -> bool:
    return canonical_json_bytes(left) == canonical_json_bytes(right)


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    if expected == "string":
        return isinstance(value, str)
    raise SchemaDefinitionError(f"unsupported type {expected!r}")


def _parse_timestamp(value: str, *, field: str) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise PolicyError(f"{field} must be an RFC 3339 timestamp")
    if value.endswith("z"):
        raise PolicyError(f"{field} uses a non-canonical lowercase timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PolicyError(f"{field} is not a valid RFC 3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PolicyError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _format_matches(value: str, format_name: str) -> bool:
    try:
        if format_name == "uuid":
            parsed = uuid.UUID(value)
            return str(parsed) == value.lower()
        if format_name == "date-time":
            _parse_timestamp(value, field="date-time")
            return True
        if format_name == "uri":
            if any(ord(character) <= 32 for character in value):
                return False
            parsed = urlsplit(value)
            return bool(parsed.scheme and (parsed.netloc or parsed.path))
    except (PolicyError, TypeError, ValueError):
        return False
    raise SchemaDefinitionError(f"unsupported format {format_name!r}")


def _resolve_ref(root: Mapping[str, Any], reference: str) -> Mapping[str, Any]:
    key = reference.removeprefix("#/$defs/").replace("~1", "/").replace("~0", "~")
    definitions = root.get("$defs")
    if not isinstance(definitions, dict) or key not in definitions:
        raise SchemaDefinitionError(f"unresolved local reference {reference!r}")
    resolved = definitions[key]
    if not isinstance(resolved, dict):
        raise SchemaDefinitionError(f"reference {reference!r} is not a schema object")
    return resolved


def _validation_errors(
    value: Any,
    schema: Mapping[str, Any],
    *,
    root: Mapping[str, Any],
    location: str,
) -> list[str]:
    errors: list[str] = []
    if "$ref" in schema:
        errors.extend(
            _validation_errors(
                value,
                _resolve_ref(root, schema["$ref"]),
                root=root,
                location=location,
            )
        )
    declared = schema.get("type")
    if declared is not None:
        options = [declared] if isinstance(declared, str) else declared
        if not any(_type_matches(value, option) for option in options):
            return [f"{location}: expected type {options!r}"]
    if "const" in schema and not _json_equal(value, schema["const"]):
        errors.append(f"{location}: value does not equal const")
    if "enum" in schema and not any(
        _json_equal(value, choice) for choice in schema["enum"]
    ):
        errors.append(f"{location}: value is not in enum")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in value:
                errors.append(f"{location}: missing required property {required}")
        for key, child in value.items():
            if key in properties:
                errors.extend(
                    _validation_errors(
                        child,
                        properties[key],
                        root=root,
                        location=f"{location}.{key}",
                    )
                )
            elif schema.get("additionalProperties") is False:
                errors.append(f"{location}: unexpected property {key}")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(
                    _validation_errors(
                        child,
                        schema["additionalProperties"],
                        root=root,
                        location=f"{location}.{key}",
                    )
                )
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{location}: string is shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{location}: string is longer than maxLength")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{location}: string does not match pattern")
        if "format" in schema and not _format_matches(value, schema["format"]):
            errors.append(f"{location}: string does not match format")
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    ):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{location}: number is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{location}: number is above maximum")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{location}: array has fewer than minItems")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{location}: array has more than maxItems")
        if schema.get("uniqueItems"):
            encoded = [canonical_json_bytes(item) for item in value]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{location}: array items are not unique")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, child in enumerate(value):
                errors.extend(
                    _validation_errors(
                        child,
                        item_schema,
                        root=root,
                        location=f"{location}[{index}]",
                    )
                )
        contains = schema.get("contains")
        if contains is not None and not any(
            not _validation_errors(child, contains, root=root, location=location)
            for child in value
        ):
            errors.append(f"{location}: array has no item matching contains")
    for child in schema.get("allOf", []):
        errors.extend(_validation_errors(value, child, root=root, location=location))
    if "oneOf" in schema:
        matches = sum(
            not _validation_errors(value, child, root=root, location=location)
            for child in schema["oneOf"]
        )
        if matches != 1:
            errors.append(f"{location}: oneOf matched {matches} branches")
    if "not" in schema and not _validation_errors(
        value, schema["not"], root=root, location=location
    ):
        errors.append(f"{location}: value matched forbidden schema")
    if "if" in schema:
        branch = (
            "then"
            if not _validation_errors(value, schema["if"], root=root, location=location)
            else "else"
        )
        if branch in schema:
            errors.extend(
                _validation_errors(
                    value, schema[branch], root=root, location=location
                )
            )
    return errors


def validate_document(
    document: Any,
    schema: Mapping[str, Any],
    *,
    root_schema: Mapping[str, Any] | None = None,
) -> None:
    """Validate one decoded document against the tracked schema profile."""

    root = schema if root_schema is None else root_schema
    validate_schema_document(root)
    errors = _validation_errors(document, schema, root=root, location="$")
    if errors:
        limited = errors[:50]
        suffix = "" if len(errors) <= 50 else f"\n... {len(errors) - 50} more errors"
        raise SchemaValidationError("\n".join(limited) + suffix)


def _measurement_satisfies(value: float, comparator: str, threshold: float) -> bool:
    return {
        "eq": value == threshold,
        "lt": value < threshold,
        "lte": value <= threshold,
        "gt": value > threshold,
        "gte": value >= threshold,
    }[comparator]


def _validate_measurements(check: Mapping[str, Any]) -> None:
    requirements = METRIC_REQUIREMENTS.get(str(check.get("id")))
    if not requirements or check.get("outcome") != "passed":
        return
    metrics: dict[str, Mapping[str, Any]] = {}
    for measurement in check.get("measurements", []):
        name = measurement.get("metric")
        if name in metrics:
            raise PolicyError(f"duplicate measurement {name!r} in {check['id']}")
        metrics[str(name)] = measurement
    for name, requirement in requirements.items():
        measurement = metrics.get(name)
        if measurement is None:
            raise PolicyError(
                f"required measurement {name!r} is missing from {check['id']}"
            )
        if (
            measurement.get("aggregation") != requirement.aggregation
            or measurement.get("comparator") != requirement.comparator
            or float(measurement.get("threshold", math.nan)) != requirement.threshold
            or measurement.get("unit") != requirement.unit
        ):
            raise PolicyError(
                f"measurement {name!r} in {check['id']} has noncanonical semantics"
            )
        observed = measurement.get("value")
        if (
            not isinstance(observed, (int, float))
            or isinstance(observed, bool)
            or not math.isfinite(observed)
            or not _measurement_satisfies(
                float(observed), requirement.comparator, requirement.threshold
            )
        ):
            raise PolicyError(
                f"measurement {name!r} in {check['id']} misses its threshold"
            )


def _canonical_staging(staging: Mapping[str, Any]) -> bytes:
    endpoint = staging.get("endpoint")
    parsed = urlsplit(endpoint) if isinstance(endpoint, str) else None
    if (
        parsed is None
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
    ):
        raise PolicyError("staging endpoint must be credential-free non-loopback HTTPS")
    worker_paths = staging.get("worker_paths")
    if not isinstance(worker_paths, list) or not {"background", "scheduler"} <= set(
        worker_paths
    ):
        raise PolicyError("staging must contain real background and scheduler worker paths")
    return canonical_json_bytes(staging)


def _allowed_na(platform: str, check_id: str, staging: Mapping[str, Any]) -> bool:
    if platform == "watchos" and check_id == "personal_agent":
        return True
    if platform == "macos" and check_id == "macos_personal_agent_host":
        capability = staging.get("macos_personal_agent_host")
        return (
            isinstance(capability, dict)
            and capability.get("supported") is False
            and capability.get("runtime_contract_versions") == []
            and capability.get("source_feature") is None
            and capability.get("source") == "candidate_capability_map"
        )
    return False


def _approval_for_exception(
    approvals: Sequence[Mapping[str, Any]], exception_id: str
) -> Mapping[str, Any] | None:
    matches = [item for item in approvals if item.get("exception_id") == exception_id]
    if len(matches) > 1:
        raise PolicyError(f"duplicate trusted approval for exception {exception_id}")
    return matches[0] if matches else None


def evaluate_evidence_set(
    evidence_set: Mapping[str, Any],
    *,
    now: datetime | None = None,
    trusted_approvals: Sequence[Mapping[str, Any]] = (),
) -> EvidencePolicyResult:
    """Evaluate same-candidate matrix policy without claiming protected trust."""

    now = (now or datetime.now(UTC)).astimezone(UTC)
    declared_targets = evidence_set.get("required_targets")
    if declared_targets != list(REQUIRED_TARGETS):
        raise PolicyError(
            f"required targets must be exactly {list(REQUIRED_TARGETS)!r}"
        )
    reports = evidence_set.get("evidence")
    if not isinstance(reports, list):
        raise PolicyError("evidence must be an array")
    platforms = [item.get("platform") for item in reports if isinstance(item, dict)]
    if len(platforms) != len(set(platforms)):
        raise PolicyError("duplicate platform report")
    if set(platforms) != set(REQUIRED_TARGETS):
        raise PolicyError("platform reports do not exactly match required targets")
    evidence_ids = [item.get("evidence_id") for item in reports]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise PolicyError("duplicate evidence ID")
    requests = evidence_set.get("exception_requests")
    if not isinstance(requests, list):
        raise PolicyError("exception_requests must be an array")
    request_ids = [item.get("exception_id") for item in requests if isinstance(item, dict)]
    if len(request_ids) != len(set(request_ids)):
        raise PolicyError("duplicate exception request")
    request_by_platform: dict[str, Mapping[str, Any]] = {}
    for request in requests:
        platform = request.get("platform")
        if platform in request_by_platform:
            raise PolicyError(f"multiple exception requests for platform {platform}")
        request_by_platform[str(platform)] = request

    candidate_sha = evidence_set.get("candidate_sha")
    release_id = evidence_set.get("release_id")
    release_version = evidence_set.get("release_version")
    shared_staging: bytes | None = None
    staging_id = ""
    used_exceptions: list[str] = []
    for report in reports:
        platform = str(report.get("platform"))
        for key, expected in (
            ("candidate_sha", candidate_sha),
            ("release_id", release_id),
            ("release_version", release_version),
        ):
            if report.get(key) != expected:
                raise PolicyError(f"{platform} {key} differs from evidence set")
        checks = report.get("checks")
        if not isinstance(checks, list):
            raise PolicyError(f"{platform} checks must be an array")
        check_ids = [item.get("id") for item in checks if isinstance(item, dict)]
        if len(check_ids) != len(set(check_ids)):
            raise PolicyError(f"duplicate check ID in {platform}")
        if set(check_ids) != REQUIRED_CHECKS[platform]:
            raise PolicyError(f"{platform} check set is incomplete or contains extras")

        staging = report.get("staging_environment")
        if platform != "docs":
            if not isinstance(staging, dict):
                raise PolicyError(f"{platform} lacks qualifying staging")
            normalized = _canonical_staging(staging)
            if shared_staging is None:
                shared_staging = normalized
                staging_id = str(staging["environment_id"])
            elif normalized != shared_staging:
                raise PolicyError(f"{platform} staging identity differs from matrix")

        outcome = report.get("outcome")
        if outcome == "failed":
            raise PolicyError(f"{platform} contains failed product evidence")
        if outcome == "passed":
            if platform != "docs" and not isinstance(staging, dict):
                raise PolicyError(f"{platform} lacks staging")
            for check in checks:
                check_outcome = check.get("outcome")
                if check_outcome == "not_applicable":
                    if not isinstance(staging, dict) or not _allowed_na(
                        platform, str(check.get("id")), staging
                    ):
                        raise PolicyError(
                            f"illegal not_applicable outcome for {platform}/{check.get('id')}"
                        )
                elif check_outcome != "passed":
                    raise PolicyError(
                        f"passed {platform} report contains {check_outcome} check"
                    )
                _validate_measurements(check)
            if platform == "macos" and isinstance(staging, dict):
                capability = staging.get("macos_personal_agent_host")
                host_check = next(
                    item for item in checks if item["id"] == "macos_personal_agent_host"
                )
                if isinstance(capability, dict) and capability.get("supported") is True:
                    if (
                        2 not in capability.get("runtime_contract_versions", [])
                        or capability.get("source_feature") != "059"
                        or host_check.get("outcome") != "passed"
                    ):
                        raise PolicyError(
                            "supported macOS host lacks v2 acknowledged passing evidence"
                        )
        elif outcome == "unavailable":
            if platform not in SHIPPING_CLIENTS:
                raise PolicyError(f"{platform} is not exception-eligible")
            missing = {str(item.get("id")) for item in checks}
            if missing & NON_WAIVABLE_CHECKS:
                raise PolicyError(
                    f"{platform} unavailable report includes non-waivable evidence"
                )
            if any(item.get("outcome") != "not_run" for item in checks):
                raise PolicyError(f"{platform} unavailable checks must all be not_run")
            if not report.get("unavailability_observation"):
                raise PolicyError(
                    f"{platform} unavailable report lacks protected observation"
                )
            request = request_by_platform.get(platform)
            if request is None:
                raise PolicyError(f"{platform} unavailable report lacks exception request")
            if (
                request.get("candidate_sha") != candidate_sha
                or request.get("release_id") != release_id
                or set(request.get("missing_checks", [])) != missing
            ):
                raise PolicyError(f"{platform} exception request does not bind exact gap")
            if missing & NON_WAIVABLE_CHECKS:
                raise PolicyError(f"{platform} exception attempts to waive non-waivable check")
            requested_at = _parse_timestamp(
                str(request.get("requested_at")), field="requested_at"
            )
            if requested_at > now + timedelta(minutes=5):
                raise PolicyError(f"{platform} exception request is future-dated")
            approval = _approval_for_exception(
                trusted_approvals, str(request.get("exception_id"))
            )
            if approval is None:
                raise PolicyError(f"{platform} has no trusted approval and registration")
            expiry = _parse_timestamp(str(approval.get("expires_at")), field="expires_at")
            if now >= expiry:
                raise PolicyError(f"{platform} trusted approval is expired")
            used_exceptions.append(str(request["exception_id"]))
        else:
            raise PolicyError(f"{platform} has unsupported outcome {outcome!r}")

    if evidence_set.get("decision") != "passed":
        raise PolicyError("a qualifying evidence set must have decision='passed'")
    if shared_staging is None:
        raise PolicyError("matrix contains no shared staging identity")
    unused = set(request_by_platform) - {
        report["platform"] for report in reports if report.get("outcome") == "unavailable"
    }
    if unused:
        raise PolicyError(f"unused exception request(s): {sorted(unused)}")
    return EvidencePolicyResult(
        required_targets=tuple(declared_targets),
        staging_environment_id=staging_id,
        used_exception_ids=tuple(sorted(used_exceptions)),
    )


def exception_approval_payload_sha256(receipt: Mapping[str, Any]) -> str:
    """Hash the exact requester-known fixed-field exception approval payload."""

    artifact = receipt.get("exception_artifact")
    if not isinstance(artifact, dict):
        raise ProvenanceError("approval receipt lacks exception_artifact")
    payload = {
        "candidate_sha": receipt.get("candidate_sha"),
        "exception_artifact_id": artifact.get("artifact_id"),
        "exception_artifact_immutable_reference": artifact.get("immutable_reference"),
        "exception_artifact_sha256": artifact.get("sha256"),
        "exception_id": receipt.get("exception_id"),
        "release_id": receipt.get("release_id"),
    }
    return canonical_json_sha256(payload)


class ArtifactResolver:
    """Resolve pre-fetched immutable references and always recompute byte hashes."""

    def __init__(
        self,
        *,
        bundle_root: str | Path,
        resolved: Mapping[str, str | Path] | None = None,
    ) -> None:
        self.bundle_root = Path(bundle_root).resolve(strict=True)
        self.resolved = {
            reference: Path(path).absolute()
            for reference, path in (resolved or {}).items()
        }

    @staticmethod
    def _safe_relative(reference: str) -> PurePosixPath:
        encoded = reference.removeprefix("bundle://")
        decoded = unquote(encoded)
        path = PurePosixPath(decoded)
        if (
            not encoded
            or decoded.startswith("/")
            or "//" in decoded
            or "\\" in decoded
            or "\x00" in decoded
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ProvenanceError(f"bundle reference contains traversal: {reference}")
        return path

    @staticmethod
    def _assert_no_symlink(root: Path, relative: PurePosixPath) -> Path:
        cursor = root
        for part in relative.parts:
            cursor = cursor / part
            try:
                if cursor.is_symlink():
                    raise ProvenanceError(f"bundle reference crosses symlink: {cursor}")
            except OSError as exc:
                raise ProvenanceError(f"cannot inspect bundle member {cursor}: {exc}") from exc
        try:
            target = cursor.resolve(strict=True)
        except OSError as exc:
            raise ProvenanceError(f"bundle member does not exist: {cursor}") from exc
        if not target.is_relative_to(root) or not target.is_file():
            raise ProvenanceError(f"bundle member escapes evidence root: {cursor}")
        return target

    @staticmethod
    def _assert_prefetched_regular(target: Path) -> Path:
        """Reject a pre-fetched path whose file or any parent is a symlink."""

        cursor = Path(target.anchor)
        try:
            for part in target.parts[1:]:
                cursor /= part
                if cursor.is_symlink():
                    raise ProvenanceError(
                        f"resolved artifact crosses a symlink: {cursor}"
                    )
            if not target.is_file():
                raise ProvenanceError(
                    f"resolved artifact is not a regular file: {target}"
                )
        except OSError as exc:
            raise ProvenanceError(
                f"cannot inspect resolved artifact {target}: {exc}"
            ) from exc
        return target

    @staticmethod
    def _validate_prefetched_reference(reference: str) -> None:
        """Require the exact immutable URI grammar and a normalized member path."""

        member: str | None = None
        if match := GH_RUN_MEMBER_RE.fullmatch(reference):
            member = match.group("member")
        elif GH_RELEASE_ASSET_RE.fullmatch(reference):
            return
        elif match := OCI_REFERENCE_RE.fullmatch(reference):
            repository_text = match.group("repository")
            repository = PurePosixPath(repository_text)
            if "//" in repository_text or any(
                part in {"", ".", ".."} for part in repository.parts
            ):
                raise ProvenanceError(
                    f"OCI reference contains a noncanonical repository path: {reference}"
                )
            return
        elif match := GHGIT_REFERENCE_RE.fullmatch(reference):
            member = match.group("member")
            if member is None:
                return
        else:
            raise ProvenanceError(
                f"immutable reference has a noncanonical URI: {reference}"
            )
        decoded = unquote(member)
        path = PurePosixPath(decoded)
        if (
            decoded.startswith("/")
            or "//" in decoded
            or "\\" in decoded
            or "\x00" in decoded
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ProvenanceError(
                f"immutable reference member contains traversal: {reference}"
            )
        if reference.startswith("ghgit://") and not LEDGER_PATH_RE.fullmatch(decoded):
            raise ProvenanceError(
                f"Git ledger reference has a noncanonical path: {reference}"
            )

    def resolve(self, reference: str, expected_sha256: str) -> bytes:
        """Resolve one allowed immutable reference and compare its actual SHA-256."""

        if not SHA256_RE.fullmatch(expected_sha256):
            raise ProvenanceError("expected artifact SHA-256 is malformed")
        if reference.startswith("bundle://"):
            target = self._assert_no_symlink(
                self.bundle_root, self._safe_relative(reference)
            )
        elif reference.startswith(("gh://", "oci://", "ghgit://")):
            self._validate_prefetched_reference(reference)
            target = self.resolved.get(reference)
            if target is None:
                raise ProvenanceError(
                    f"immutable reference was not independently pre-fetched: {reference}"
                )
            target = self._assert_prefetched_regular(target)
        else:
            raise ProvenanceError(f"mutable or unknown artifact reference: {reference}")
        try:
            content = target.read_bytes()
        except OSError as exc:
            raise ProvenanceError(f"cannot read resolved artifact {target}: {exc}") from exc
        actual = hashlib.sha256(content).hexdigest()
        if actual != expected_sha256:
            raise ProvenanceError(
                f"artifact digest mismatch for {reference}: {actual} != {expected_sha256}"
            )
        return content


def _manifest_artifact_identities(
    manifest: Mapping[str, Any],
) -> set[tuple[str, str]]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return set()
    identities: set[tuple[str, str]] = set()
    for artifact in artifacts:
        if isinstance(artifact, dict):
            reference = artifact.get("immutable_reference")
            digest = artifact.get("sha256")
            if isinstance(reference, str) and isinstance(digest, str):
                identities.add((reference, digest))
    return identities


def bind_report_to_producer(
    report: Mapping[str, Any],
    manifests: Sequence[Mapping[str, Any]],
    *,
    repository: str,
    candidate_sha: str,
    protected_builder_sha: str,
    protected_builder_identity: str,
) -> Mapping[str, Any]:
    """Bind one platform report to exactly one externally pinned producer job."""

    artifact = report.get("artifact")
    if not isinstance(artifact, dict):
        raise ProvenanceError("report lacks an artifact")
    identity = (artifact.get("immutable_reference"), artifact.get("sha256"))
    matches: list[Mapping[str, Any]] = []
    for manifest in manifests:
        builder = manifest.get("trusted_builder")
        if not isinstance(builder, dict):
            continue
        if (
            manifest.get("document_type") == "trusted_workflow_provenance"
            and manifest.get("repository") == repository
            and manifest.get("candidate_sha") == candidate_sha
            and manifest.get("workflow") == report.get("workflow")
            and manifest.get("runner") == report.get("runner")
            and builder.get("signer_digest") == protected_builder_sha
            and builder.get("certificate_identity") == protected_builder_identity
            and identity in _manifest_artifact_identities(manifest)
        ):
            matches.append(manifest)
    if len(matches) != 1:
        raise ProvenanceError(
            f"report did not bind to exactly one protected producer: {report.get('platform')}"
        )
    return matches[0]


def _git(path: Path, *arguments: str, binary: bool = False) -> str | bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=not binary,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"" if binary else "")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        raise LedgerError(f"git {' '.join(arguments)} failed: {str(detail).strip()}") from exc
    return completed.stdout


def read_ledger_snapshot(
    checkout: str | Path,
    *,
    repository: str,
    ref: str,
    commit: str,
) -> LedgerSnapshot:
    """Read canonical debt/resolution bytes from one exact protected Git commit."""

    root = Path(checkout).resolve(strict=True)
    if not GIT_SHA_RE.fullmatch(commit):
        raise LedgerError("exception ledger commit must be one lowercase Git SHA")
    resolved_ref = str(_git(root, "rev-parse", ref)).strip()
    if resolved_ref != commit:
        raise LedgerError(
            f"exception ledger ref {ref} does not equal requested commit {commit}"
        )
    tree_sha = str(_git(root, "rev-parse", f"{commit}^{{tree}}")).strip()
    if not GIT_SHA_RE.fullmatch(tree_sha):
        raise LedgerError("exception ledger tree identity is malformed")
    listing = _git(root, "ls-tree", "-r", "-z", "--full-tree", commit, binary=True)
    assert isinstance(listing, bytes)
    paths: dict[str, str] = {}
    records: dict[str, Mapping[str, Any]] = {}
    for raw in listing.split(b"\x00"):
        if not raw:
            continue
        try:
            metadata, raw_path = raw.split(b"\t", 1)
            mode, object_type, _ = metadata.decode("ascii").split(" ", 2)
            path = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise LedgerError("exception ledger has malformed tree entry") from exc
        if object_type != "blob" or mode != "100644":
            raise LedgerError(f"exception ledger path is not a regular blob: {path}")
        if not LEDGER_PATH_RE.fullmatch(path):
            raise LedgerError(f"exception ledger contains noncanonical path: {path}")
        content = _git(root, "show", f"{commit}:{path}", binary=True)
        assert isinstance(content, bytes)
        digest = hashlib.sha256(content).hexdigest()
        record = load_json_bytes(content, source=f"{commit}:{path}")
        if not isinstance(record, dict):
            raise LedgerError(f"exception ledger entry is not an object: {path}")
        expected_type = (
            "release_evidence_debt" if path.startswith("debts/") else "release_evidence_debt_resolution"
        )
        if record.get("document_type") != expected_type:
            raise LedgerError(f"exception ledger entry type/path mismatch: {path}")
        paths[path] = digest
        records[path] = record
    snapshot_hash = canonical_json_sha256(paths)
    return LedgerSnapshot(
        repository=repository,
        ref=ref,
        commit_sha=commit,
        tree_sha=tree_sha,
        snapshot_sha256=snapshot_hash,
        paths=dict(sorted(paths.items())),
        records=dict(sorted(records.items())),
    )


def validate_exception_approval(
    request: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    now: datetime,
    resolver: ArtifactResolver,
    ledger: LedgerSnapshot,
) -> None:
    """Validate exact request bytes, protected approval, and registered debt bytes."""

    for field in ("exception_id", "candidate_sha", "release_id", "requester_login"):
        if receipt.get(field) != request.get(field):
            raise ProvenanceError(f"exception approval {field} does not match request")
    if receipt.get("reviewer_login") == receipt.get("requester_login"):
        raise ProvenanceError("exception requester cannot approve their own request")
    approved = _parse_timestamp(str(receipt.get("approved_at")), field="approved_at")
    expires = _parse_timestamp(str(receipt.get("expires_at")), field="expires_at")
    if expires <= approved or expires - approved > timedelta(days=7) or now >= expires:
        raise ProvenanceError("exception approval expiry is invalid or expired")
    artifact = receipt.get("exception_artifact")
    if not isinstance(artifact, dict):
        raise ProvenanceError("exception approval lacks immutable request artifact")
    content = resolver.resolve(
        str(artifact.get("immutable_reference")), str(artifact.get("sha256"))
    )
    resolved_request = load_json_bytes(content, source="exception request artifact")
    if resolved_request != request:
        raise ProvenanceError("protected approval request bytes differ from evidence request")
    if exception_approval_payload_sha256(receipt) != receipt.get(
        "approval_payload_sha256"
    ):
        raise ProvenanceError("protected approval payload hash is incorrect")
    path = str(receipt.get("ledger_entry_path"))
    if path != f"debts/{request.get('exception_id')}.json":
        raise ProvenanceError("protected approval debt path is noncanonical")
    if ledger.paths.get(path) != receipt.get("ledger_entry_sha256"):
        raise ProvenanceError("protected approval debt is absent from exact ledger snapshot")
    if ledger.records.get(path) != receipt.get("ledger_entry"):
        raise ProvenanceError("protected approval debt bytes differ from ledger snapshot")
    expected_reference = (
        f"ghgit://{ledger.repository}/commits/{receipt.get('ledger_commit_sha')}/paths/{path}"
    )
    if receipt.get("ledger_entry_immutable_reference") != expected_reference:
        raise ProvenanceError("protected approval ledger reference is noncanonical")
    entry = receipt.get("ledger_entry")
    if not isinstance(entry, dict):
        raise ProvenanceError("protected approval lacks canonical debt entry")
    for field in (
        "exception_id",
        "candidate_sha",
        "release_id",
        "platform",
        "missing_checks",
        "reason",
        "requester_login",
        "maximum_valid_days",
        "blocks_next_release",
    ):
        if entry.get(field) != request.get(field):
            raise ProvenanceError(f"registered debt {field} does not match request")
    if entry.get("reviewer_login") != receipt.get("reviewer_login"):
        raise ProvenanceError("registered debt reviewer does not match protected approval")


def validate_exception_history(
    ledger: LedgerSnapshot,
    *,
    evidence_set: Mapping[str, Any],
    approval_receipts: Sequence[Mapping[str, Any]],
    resolution_receipts: Sequence[Mapping[str, Any]],
) -> None:
    """Require one-time resolutions and block unresolved historical exception debt."""

    debts: dict[str, tuple[str, Mapping[str, Any]]] = {}
    resolutions: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for path, record in ledger.records.items():
        if path.startswith("debts/"):
            exception_id = str(record.get("exception_id"))
            if exception_id in debts:
                raise LedgerError(f"duplicate debt for exception {exception_id}")
            debts[exception_id] = (path, record)
        else:
            resolutions.setdefault(str(record.get("exception_id")), []).append(
                (path, record)
            )
    current_exception_ids = {
        str(item.get("exception_id"))
        for item in evidence_set.get("exception_requests", [])
    }
    approval_ids = {str(item.get("exception_id")) for item in approval_receipts}
    resolution_by_id = {
        str(item.get("resolution_id")): item for item in resolution_receipts
    }
    reports = {
        str(item.get("platform")): item for item in evidence_set.get("evidence", [])
    }
    for exception_id, (path, debt) in debts.items():
        entries = resolutions.get(exception_id, [])
        if exception_id in current_exception_ids:
            if exception_id not in approval_ids:
                raise LedgerError(f"current exception {exception_id} lacks approval receipt")
            if entries:
                raise LedgerError(f"current exception {exception_id} is already resolved")
            continue
        if len(entries) != 1:
            raise LedgerError(
                f"historical debt {exception_id} must have exactly one resolution"
            )
        _, resolution = entries[0]
        receipt = resolution_by_id.get(str(resolution.get("resolution_id")))
        if receipt is None or receipt.get("ledger_entry") != resolution:
            raise LedgerError(f"resolution for debt {exception_id} lacks trusted receipt")
        if resolution.get("debt_entry_sha256") != ledger.paths[path]:
            raise LedgerError(f"resolution for debt {exception_id} names wrong debt bytes")
        if (
            resolution.get("platform") != debt.get("platform")
            or set(resolution.get("resolved_checks", []))
            != set(debt.get("missing_checks", []))
        ):
            raise LedgerError(f"resolution for debt {exception_id} is partial or mismatched")
        report = reports.get(str(debt.get("platform")))
        current_checks = {
            str(item.get("id")): item.get("outcome")
            for item in (report or {}).get("checks", [])
        }
        if any(
            current_checks.get(check_id) != "passed"
            for check_id in debt.get("missing_checks", [])
        ):
            raise LedgerError(f"historical debt {exception_id} lacks current passing evidence")


def validate_windows_draft_provenance(
    document: Mapping[str, Any],
    *,
    trusted_decision: Mapping[str, Any],
    now: datetime,
    resolver: ArtifactResolver,
) -> None:
    """Validate build-once Windows draft lineage before any public transition."""

    for field in ("candidate_sha", "release_id"):
        if document.get(field) != trusted_decision.get(field):
            raise PolicyError(f"Windows draft {field} differs from trusted decision")
    if document.get("readiness_evidence_set_id") != trusted_decision.get(
        "readiness_evidence_set_id"
    ):
        raise PolicyError("Windows draft evidence-set ID differs from trusted decision")
    valid_until = _parse_timestamp(
        str(document.get("trusted_decision", {}).get("valid_until")),
        field="trusted_decision.valid_until",
    )
    if now >= valid_until:
        raise PolicyError("trusted release decision expired before publication")
    version = document.get("release_version")
    release = document.get("draft_release")
    publisher = document.get("protected_publisher")
    signing = document.get("signing")
    if not all(isinstance(value, dict) for value in (release, publisher, signing)):
        raise PolicyError("Windows draft lacks publisher/release/signing objects")
    expected_tag = f"v{version}"
    if release.get("tag") != expected_tag or release.get("release_name") != expected_tag:
        raise PolicyError("Windows draft tag and release name must equal v plus SemVer")
    if publisher.get("reviewer_login") == publisher.get("requester_login"):
        raise PolicyError("Windows protected publisher cannot be self-approved")
    if signing.get("bridge_workflow_sha256") != publisher.get(
        "bridge_workflow_sha256"
    ):
        raise PolicyError("Windows legacy bridge bytes differ from protected template")
    tested = document.get("tested_executable")
    draft = document.get("draft_executable")
    checksum = document.get("draft_checksum_manifest")
    signature = document.get("draft_signature_bundle")
    if not all(isinstance(value, dict) for value in (tested, draft, checksum, signature)):
        raise PolicyError("Windows draft lacks all three immutable assets")
    if tested.get("sha256") != draft.get("sha256") or tested.get(
        "build_identity"
    ) != draft.get("build_identity"):
        raise PolicyError("Windows draft executable was rebuilt or modified")
    ids = {
        release.get("executable_asset_database_id"),
        release.get("checksum_asset_database_id"),
        release.get("signature_bundle_asset_database_id"),
    }
    if len(ids) != 3:
        raise PolicyError("Windows draft asset IDs must be distinct")
    executable_bytes = resolver.resolve(
        str(draft.get("immutable_reference")), str(draft.get("sha256"))
    )
    checksum_bytes = resolver.resolve(
        str(checksum.get("immutable_reference")), str(checksum.get("sha256"))
    )
    resolver.resolve(
        str(signature.get("immutable_reference")), str(signature.get("sha256"))
    )
    expected_line = f"{hashlib.sha256(executable_bytes).hexdigest()}  AstralDeep.exe"
    if checksum_bytes.decode("utf-8", "strict").strip() != expected_line:
        raise PolicyError("SHA256SUMS does not bind the re-downloaded executable")


def _load_json_directory(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    root = Path(path)
    if not root.is_dir():
        raise DocumentError(f"JSON directory does not exist: {root}")
    documents = [load_json_document(item) for item in sorted(root.glob("*.json"))]
    return documents


def _load_resolved_map(path: str | Path | None) -> dict[str, Path]:
    if path is None:
        return {}
    document = load_json_document(path)
    entries = document.get("artifacts")
    if not isinstance(entries, list):
        raise DocumentError("resolved-artifacts manifest needs an artifacts array")
    result: dict[str, Path] = {}
    base = Path(path).resolve().parent
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"immutable_reference", "path"}:
            raise DocumentError("resolved-artifacts entries have unexpected fields")
        reference = item["immutable_reference"]
        if not isinstance(reference, str):
            raise DocumentError("resolved-artifacts immutable_reference must be a string")
        try:
            ArtifactResolver._validate_prefetched_reference(reference)
        except ProvenanceError as exc:
            raise DocumentError(str(exc)) from exc
        raw_path = item["path"]
        if not isinstance(raw_path, str):
            raise DocumentError("resolved-artifacts path must be a relative string")
        relative = Path(raw_path)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise DocumentError("resolved-artifacts path contains traversal")
        cursor = base
        try:
            for part in relative.parts:
                cursor /= part
                if cursor.is_symlink():
                    raise DocumentError(
                        f"resolved-artifacts path crosses symlink: {raw_path}"
                    )
            target = cursor.resolve(strict=True)
        except OSError as exc:
            raise DocumentError(
                f"cannot resolve pre-fetched artifact {raw_path}: {exc}"
            ) from exc
        if not target.is_relative_to(base) or not target.is_file():
            raise DocumentError(
                f"resolved-artifacts path is not a regular in-root file: {raw_path}"
            )
        if reference in result:
            raise DocumentError(f"duplicate resolved artifact {reference}")
        result[reference] = target
    return result


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".release-decision-", dir=path.parent) as temp:
        temporary = Path(temp) / "decision.json"
        temporary.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        os.replace(temporary, path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--trust-schema", required=True)
    parser.add_argument("--deployment-profile-schema", required=True)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--trusted-provenance-dir", required=True)
    parser.add_argument("--trusted-stage-deploy", required=True)
    parser.add_argument("--trusted-approvals-dir", required=True)
    parser.add_argument("--trusted-debt-resolutions-dir", required=True)
    parser.add_argument("--attestation-verification-dir", required=True)
    parser.add_argument("--resolved-artifacts-manifest")
    parser.add_argument("--protected-builder-sha", required=True)
    parser.add_argument("--protected-builder-identity", required=True)
    parser.add_argument("--protected-policy-sha", required=True)
    parser.add_argument("--exception-ledger-repository", required=True)
    parser.add_argument(
        "--exception-ledger-ref", default="refs/heads/release-evidence-debt"
    )
    parser.add_argument("--exception-ledger-commit", required=True)
    parser.add_argument(
        "--exception-ledger-checkout", default="build/060/exception-ledger"
    )
    parser.add_argument("--coverage-percent", type=float)
    parser.add_argument("--coverage-artifact")
    parser.add_argument("--evidence-set-artifact")
    parser.add_argument("--protected-workflow-ref")
    parser.add_argument("--valid-until")
    parser.add_argument("--decision-output")
    parser.add_argument("--now")
    return parser


def _load_evidence_documents(
    root: Path, schema: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not root.is_dir():
        raise DocumentError(f"evidence directory does not exist: {root}")
    documents: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        document = load_json_document(path)
        if document.get("document_type") in {
            "platform_evidence",
            "evidence_exception_request",
            "release_evidence_set",
            "windows_draft_verification_provenance",
        }:
            validate_document(document, schema)
            documents.append(document)
    sets = [item for item in documents if item.get("document_type") == "release_evidence_set"]
    if len(sets) != 1:
        raise PolicyError("evidence directory must contain exactly one release_evidence_set")
    return sets[0], documents


def _verify_attestation_receipts(
    manifests: Sequence[Mapping[str, Any]],
    receipts: Sequence[Mapping[str, Any]],
    *,
    repository: str,
    candidate_sha: str,
    builder_sha: str,
    builder_identity: str,
) -> dict[str, Mapping[str, Any]]:
    by_manifest = {
        str(receipt.get("manifest_id")): receipt for receipt in receipts
    }
    if len(by_manifest) != len(receipts):
        raise ProvenanceError("duplicate attestation verification receipt")
    verified: dict[str, Mapping[str, Any]] = {}
    for manifest in manifests:
        manifest_id = str(manifest.get("manifest_id"))
        receipt = by_manifest.get(manifest_id)
        if receipt is None:
            raise ProvenanceError(f"manifest {manifest_id} lacks attestation verification")
        expected = {
            "verification_outcome": "passed",
            "repository": repository,
            "candidate_sha": candidate_sha,
            "protected_builder_sha": builder_sha,
            "protected_builder_identity": builder_identity,
        }
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise ProvenanceError(f"manifest {manifest_id} has untrusted verification receipt")
        artifact = receipt.get("manifest_artifact")
        if not isinstance(artifact, dict):
            raise ProvenanceError(f"manifest {manifest_id} receipt lacks exact artifact member")
        verified[manifest_id] = receipt
    extras = set(by_manifest) - set(verified)
    if extras:
        raise ProvenanceError(f"unconsumed attestation receipt(s): {sorted(extras)}")
    return verified


def _decision_manifest(
    *,
    args: argparse.Namespace,
    evidence_set: Mapping[str, Any],
    policy_result: EvidencePolicyResult,
    ledger: LedgerSnapshot,
    verification_receipts: Mapping[str, Mapping[str, Any]],
    approvals: Sequence[Mapping[str, Any]],
    now: datetime,
    trust_schema: Mapping[str, Any],
) -> dict[str, Any]:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_JOB") != "protected-decision":
        raise ProvenanceError(
            "decision output is allowed only in the protected-decision GitHub job"
        )
    if not args.protected_workflow_ref or not re.fullmatch(
        r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/\.github/workflows/"
        r"release-trusted-builder\.yml@[0-9a-f]{40}",
        args.protected_workflow_ref,
    ):
        raise ProvenanceError("protected workflow ref is missing or not commit-pinned")
    if (
        not isinstance(args.coverage_percent, (int, float))
        or isinstance(args.coverage_percent, bool)
        or not math.isfinite(args.coverage_percent)
        or not (90 <= args.coverage_percent <= 100)
    ):
        raise PolicyError("coverage-percent must be 90..100")
    if not args.coverage_artifact or not args.evidence_set_artifact:
        raise ProvenanceError("decision output needs exact evidence-set and coverage artifacts")
    coverage_artifact = load_json_document(args.coverage_artifact)
    evidence_artifact = load_json_document(args.evidence_set_artifact)
    valid_until = _parse_timestamp(str(args.valid_until), field="valid_until")
    if valid_until <= now or valid_until > now + timedelta(hours=24):
        raise PolicyError("protected decision lifetime must be positive and no more than 24h")
    for approval in approvals:
        if valid_until > _parse_timestamp(str(approval["expires_at"]), field="expires_at"):
            raise PolicyError("decision outlives a used exception approval")
    input_manifests = []
    for manifest_id, receipt in sorted(verification_receipts.items()):
        role = receipt.get("role")
        if role not in {"producer", "stage_deploy", "exception_approval", "debt_resolution"}:
            raise ProvenanceError(f"manifest {manifest_id} has invalid protected role")
        input_manifests.append(
            {
                "manifest_id": manifest_id,
                "role": role,
                "artifact": receipt["manifest_artifact"],
            }
        )
    workflow = {
        "name": os.environ.get("GITHUB_WORKFLOW", "release-trusted-builder"),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")),
        "job_id": os.environ.get("GITHUB_JOB", ""),
    }
    runner = {
        "os": os.environ.get("ASTRAL_RUNNER_OS", "linux"),
        "architecture": os.environ.get("ASTRAL_RUNNER_ARCH", "x86_64"),
        "runner_image": os.environ.get("ImageOS", "protected-runner"),
        "runner_name": os.environ.get("RUNNER_NAME", "protected-runner"),
        "runner_environment": os.environ.get(
            "ASTRAL_RUNNER_ENVIRONMENT", "github_hosted"
        ),
    }
    decision = {
        "document_type": "trusted_release_decision",
        "schema_version": 1,
        "decision_id": str(uuid.uuid4()),
        "repository": args.repository,
        "base_sha": args.base_sha,
        "candidate_sha": args.candidate_sha,
        "release_id": evidence_set["release_id"],
        "readiness_evidence_set_id": evidence_set["evidence_set_id"],
        "evidence_set_artifact": evidence_artifact,
        "coverage_artifact": coverage_artifact,
        "input_manifests": input_manifests,
        "exception_ledger_repository": args.exception_ledger_repository,
        "exception_ledger_ref": args.exception_ledger_ref,
        "exception_ledger_commit_sha": ledger.commit_sha,
        "exception_ledger_tree_sha": ledger.tree_sha,
        "exception_ledger_snapshot_sha256": ledger.snapshot_sha256,
        "exception_ledger_immutable_reference": (
            f"ghgit://{args.exception_ledger_repository}/commits/{ledger.commit_sha}"
        ),
        "exception_ledger_verified_at": now.isoformat().replace("+00:00", "Z"),
        "policy_sha256": args.protected_policy_sha,
        "decision": "passed",
        "coverage_percent": args.coverage_percent,
        "required_check_name": "release-readiness / protected-decision",
        "workflow": workflow,
        "workflow_ref": args.protected_workflow_ref,
        "runner": runner,
        "trusted_builder": {
            "repository": args.repository,
            "workflow_path": ".github/workflows/release-trusted-builder.yml",
            "signer_digest": args.protected_builder_sha,
            "certificate_identity": args.protected_builder_identity,
        },
        "valid_until": valid_until.isoformat().replace("+00:00", "Z"),
        "generated_at": now.isoformat().replace("+00:00", "Z"),
    }
    del policy_result  # The validated set is already bound above; no candidate verdict is copied.
    validate_document(decision, trust_schema)
    return decision


def main(argv: Sequence[str] | None = None) -> int:
    """Run protected release-evidence validation and optionally emit a decision."""

    args = _parser().parse_args(argv)
    try:
        if not GIT_SHA_RE.fullmatch(args.base_sha) or not GIT_SHA_RE.fullmatch(
            args.candidate_sha
        ):
            raise PolicyError("base-sha and candidate-sha must be exact lowercase Git SHAs")
        if args.base_sha == args.candidate_sha:
            raise PolicyError("base-sha must differ from candidate-sha")
        if not args.repository or "/" not in args.repository:
            raise ProvenanceError("same-repository identity is required")
        if not GIT_SHA_RE.fullmatch(args.protected_builder_sha):
            raise ProvenanceError("protected builder SHA is malformed")
        if not SHA256_RE.fullmatch(args.protected_policy_sha):
            raise ProvenanceError("protected policy SHA-256 is malformed")
        now = (
            _parse_timestamp(args.now, field="now")
            if args.now
            else datetime.now(UTC)
        )
        evidence_schema = load_json_document(args.schema)
        trust_schema = load_json_document(args.trust_schema)
        profile_schema = load_json_document(args.deployment_profile_schema)
        for schema in (evidence_schema, trust_schema, profile_schema):
            validate_schema_document(schema)
        evidence_set, _ = _load_evidence_documents(
            Path(args.evidence_dir), evidence_schema
        )
        if evidence_set.get("candidate_sha") != args.candidate_sha:
            raise PolicyError("evidence-set candidate SHA differs from CLI candidate")

        provenance = _load_json_directory(args.trusted_provenance_dir)
        stage = load_json_document(args.trusted_stage_deploy)
        approvals = _load_json_directory(args.trusted_approvals_dir)
        resolutions = _load_json_directory(args.trusted_debt_resolutions_dir)
        trust_documents = [*provenance, stage, *approvals, *resolutions]
        for document in trust_documents:
            validate_document(document, trust_schema)
        attestation_receipts = _load_json_directory(
            args.attestation_verification_dir
        )
        verified = _verify_attestation_receipts(
            trust_documents,
            attestation_receipts,
            repository=args.repository,
            candidate_sha=args.candidate_sha,
            builder_sha=args.protected_builder_sha,
            builder_identity=args.protected_builder_identity,
        )
        for report in evidence_set["evidence"]:
            bind_report_to_producer(
                report,
                provenance,
                repository=args.repository,
                candidate_sha=args.candidate_sha,
                protected_builder_sha=args.protected_builder_sha,
                protected_builder_identity=args.protected_builder_identity,
            )
        if stage.get("deployment") is None:
            raise ProvenanceError("trusted stage deploy lacks deployment identity")
        normalized_stage = canonical_json_bytes(stage["deployment"])
        for report in evidence_set["evidence"]:
            if report["platform"] == "docs":
                continue
            # The trust manifest has two additional deployment-only fields.
            projected = dict(stage["deployment"])
            projected.pop("request_namespace", None)
            projected.pop("capability_manifest_sha256", None)
            projected.pop("service_identity_sha256", None)
            projected["deployed_at"] = report["staging_environment"]["deployed_at"]
            projected["macos_personal_agent_host"] = report["staging_environment"][
                "macos_personal_agent_host"
            ]
            if canonical_json_bytes(projected) != canonical_json_bytes(
                report["staging_environment"]
            ):
                raise ProvenanceError(
                    f"{report['platform']} staging differs from protected stage deploy"
                )
        del normalized_stage

        ledger = read_ledger_snapshot(
            args.exception_ledger_checkout,
            repository=args.exception_ledger_repository,
            ref=args.exception_ledger_ref,
            commit=args.exception_ledger_commit,
        )
        resolver = ArtifactResolver(
            bundle_root=args.evidence_dir,
            resolved=_load_resolved_map(args.resolved_artifacts_manifest),
        )
        requests = {
            str(item["exception_id"]): item
            for item in evidence_set.get("exception_requests", [])
        }
        for receipt in approvals:
            request = requests.get(str(receipt.get("exception_id")))
            if request is None:
                raise ProvenanceError("trusted approval has no exact current request")
            validate_exception_approval(
                request, receipt, now=now, resolver=resolver, ledger=ledger
            )
        validate_exception_history(
            ledger,
            evidence_set=evidence_set,
            approval_receipts=approvals,
            resolution_receipts=resolutions,
        )
        result = evaluate_evidence_set(
            evidence_set, now=now, trusted_approvals=approvals
        )
        if args.decision_output:
            decision = _decision_manifest(
                args=args,
                evidence_set=evidence_set,
                policy_result=result,
                ledger=ledger,
                verification_receipts=verified,
                approvals=approvals,
                now=now,
                trust_schema=trust_schema,
            )
            _atomic_json(Path(args.decision_output), decision)
        else:
            print(
                json.dumps(
                    {
                        "candidate_sha": args.candidate_sha,
                        "decision": "diagnostic_policy_passed",
                        "protected_release_authorization": False,
                        "required_targets": list(result.required_targets),
                        "staging_environment_id": result.staging_environment_id,
                        "used_exception_ids": list(result.used_exception_ids),
                    },
                    sort_keys=True,
                )
            )
        return 0
    except ReleaseEvidenceError as exc:
        print(f"release evidence rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
