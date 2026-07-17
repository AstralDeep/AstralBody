"""Strict, immutable Windows deployment-profile resolution for Spec 060.

This module is deliberately standard-library-only so ``windows-client/main.py``
can resolve and validate the complete deployment before importing Qt, auth,
transport, or either hosted-agent implementation. Resolution is whole-profile:
no field from one source is ever overlaid onto another source.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlsplit

from .integrity import parse_semver


PROFILE_SCHEMA_VERSION = 1
RUNTIME_MANIFEST_SCHEMA_VERSION = 1
RUNTIME_CONTRACT_VERSION = 2
_MAX_PROFILE_BYTES = 64 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
_CLIENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_PLACEHOLDERS = {"changeme", "placeholder", "example", "default"}

_PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "release_id",
    "client_version",
    "distribution",
    "local_only",
    "authority",
    "websocket_endpoint",
    "client_id",
    "auth_mode",
    "override_policy",
    "agent_connection",
}
_OVERRIDE_FIELDS = {
    "managed_profile_allowed",
    "command_line_profile_allowed",
    "persisted_profile_allowed",
    "configure_dialog_allowed",
    "development_defaults_allowed",
}
_RUNTIME_MANIFEST_FIELDS = {
    "schema_version",
    "release_id",
    "client_version",
    "python_version",
    "target_platform",
    "deployment_profile_sha256",
    "requirements_input_sha256",
    "requirements_lock_sha256",
    "runtime_contract_version",
    "required_runtime_lock_sha256",
    "worker_entrypoint",
}


class DeploymentProfileError(ValueError):
    """A deployment input or packaged metadata value failed closed."""


def _exact_fields(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise DeploymentProfileError(f"{label} fields do not match the contract")
    return value


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise DeploymentProfileError(f"{label} must be a boolean")
    return value


def _string(value: object, label: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise DeploymentProfileError(f"{label} must be a non-empty bounded string")
    if any(character.isspace() for character in value):
        raise DeploymentProfileError(f"{label} must not contain whitespace")
    return value


def _identifier(value: object, label: str, pattern: re.Pattern[str]) -> str:
    result = _string(value, label, maximum=128)
    if pattern.fullmatch(result) is None or result.lower() in _PLACEHOLDERS:
        raise DeploymentProfileError(f"{label} is invalid or placeholder-valued")
    return result


def _is_local_host(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    if normalized in {"localhost", "0.0.0.0", "::", "::1"} or normalized.endswith(
        ".localhost"
    ):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def _uri(value: object, label: str, *, websocket: bool) -> tuple[str, bool]:
    result = _string(value, label)
    try:
        parsed = urlsplit(result)
        # Accessing port performs range and syntax validation.
        parsed.port
    except ValueError as exc:
        raise DeploymentProfileError(f"{label} is not a valid URI") from exc
    allowed = {"ws", "wss"} if websocket else {"http", "https"}
    if parsed.scheme not in allowed or not parsed.hostname or not parsed.netloc:
        raise DeploymentProfileError(f"{label} has an unsupported or incomplete URI")
    if parsed.username is not None or parsed.password is not None:
        raise DeploymentProfileError(f"{label} must not contain URI userinfo")
    if parsed.query:
        raise DeploymentProfileError(f"{label} must not contain a URI query")
    if parsed.fragment:
        raise DeploymentProfileError(f"{label} must not contain a URI fragment")
    if parsed.hostname.lower() in {"example.com", "example.invalid", "changeme.invalid"}:
        raise DeploymentProfileError(f"{label} is placeholder-valued")
    return result, _is_local_host(parsed.hostname)


@dataclass(frozen=True)
class OverridePolicy:
    managed_profile_allowed: bool
    command_line_profile_allowed: bool
    persisted_profile_allowed: bool
    configure_dialog_allowed: bool
    development_defaults_allowed: bool

    def as_dict(self) -> dict[str, bool]:
        return {
            "managed_profile_allowed": self.managed_profile_allowed,
            "command_line_profile_allowed": self.command_line_profile_allowed,
            "persisted_profile_allowed": self.persisted_profile_allowed,
            "configure_dialog_allowed": self.configure_dialog_allowed,
            "development_defaults_allowed": self.development_defaults_allowed,
        }


@dataclass(frozen=True)
class ByoHostDisposition:
    disposition: str


@dataclass(frozen=True)
class LegacyToolsDisposition:
    disposition: str
    credential_source: str


@dataclass(frozen=True)
class AgentConnection:
    byo_host: ByoHostDisposition
    legacy_tools: LegacyToolsDisposition

    def as_dict(self) -> dict[str, dict[str, str]]:
        return {
            "byo_host": {"disposition": self.byo_host.disposition},
            "legacy_tools": {
                "disposition": self.legacy_tools.disposition,
                "credential_source": self.legacy_tools.credential_source,
            },
        }


@dataclass(frozen=True)
class DeploymentProfile:
    schema_version: int
    profile_id: str
    release_id: str
    client_version: str
    distribution: str
    local_only: bool
    authority: str
    websocket_endpoint: str
    client_id: str
    auth_mode: str
    override_policy: OverridePolicy
    agent_connection: AgentConnection

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "release_id": self.release_id,
            "client_version": self.client_version,
            "distribution": self.distribution,
            "local_only": self.local_only,
            "authority": self.authority,
            "websocket_endpoint": self.websocket_endpoint,
            "client_id": self.client_id,
            "auth_mode": self.auth_mode,
            "override_policy": self.override_policy.as_dict(),
            "agent_connection": self.agent_connection.as_dict(),
        }


@dataclass(frozen=True)
class EffectiveDeploymentProfile:
    """One frozen source selection shared by every Windows runtime component."""

    profile: DeploymentProfile
    source: str
    digest: str
    managed_agent_api_key: Optional[str] = field(default=None, repr=False)

    def redacted_report(self) -> dict[str, Any]:
        """Return deployment identity and dispositions without connection values."""

        return {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "profile_id": self.profile.profile_id,
            "release_id": self.profile.release_id,
            "client_version": self.profile.client_version,
            "distribution": self.profile.distribution,
            "local_only": self.profile.local_only,
            "source": self.source,
            "profile_sha256": self.digest,
            "auth_mode": self.profile.auth_mode,
            "client_mode": "public" if self.profile.auth_mode == "keycloak_oidc_pkce" else "bff",
            "byo_host_disposition": self.profile.agent_connection.byo_host.disposition,
            "legacy_tools_disposition": self.profile.agent_connection.legacy_tools.disposition,
            "legacy_tools_credential_source": (
                self.profile.agent_connection.legacy_tools.credential_source
            ),
        }


def _parse_json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    if not raw or len(raw) > _MAX_PROFILE_BYTES:
        raise DeploymentProfileError(f"{label} is empty or too large")

    def _no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DeploymentProfileError(f"{label} contains duplicate JSON keys")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeploymentProfileError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise DeploymentProfileError(f"{label} must contain one JSON object")
    return value


def _load_json_file(path: os.PathLike[str] | str, label: str) -> dict[str, Any]:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise DeploymentProfileError(f"{label} is missing or unreadable") from exc
    return _parse_json_bytes(raw, label)


def parse_profile(
    value: Mapping[str, Any], *, expected_client_version: Optional[str] = None
) -> DeploymentProfile:
    """Validate an exact profile mapping and materialize immutable values."""

    data = _exact_fields(dict(value), _PROFILE_FIELDS, "deployment profile")
    if data["schema_version"] != PROFILE_SCHEMA_VERSION:
        raise DeploymentProfileError("deployment profile schema_version is unsupported")
    profile_id = _identifier(data["profile_id"], "profile_id", _PROFILE_ID)
    release_id = _identifier(data["release_id"], "release_id", _RELEASE_ID)
    client_version = _string(data["client_version"], "client_version", maximum=128)
    try:
        parse_semver(client_version)
    except ValueError as exc:
        raise DeploymentProfileError("client_version must be strict SemVer") from exc
    if expected_client_version is not None and client_version != expected_client_version:
        raise DeploymentProfileError("profile client_version does not match the client")
    distribution = data["distribution"]
    if distribution not in {"production", "generic_developer"}:
        raise DeploymentProfileError("distribution is unsupported")
    local_only = _bool(data["local_only"], "local_only")
    authority, authority_local = _uri(data["authority"], "authority", websocket=False)
    endpoint, endpoint_local = _uri(
        data["websocket_endpoint"], "websocket_endpoint", websocket=True
    )
    client_id = _identifier(data["client_id"], "client_id", _CLIENT_ID)
    auth_mode = data["auth_mode"]
    if auth_mode not in {"keycloak_oidc_pkce", "keycloak_bff"}:
        raise DeploymentProfileError("auth_mode is unsupported")

    policy_data = _exact_fields(data["override_policy"], _OVERRIDE_FIELDS, "override_policy")
    for field_name in _OVERRIDE_FIELDS:
        _bool(policy_data[field_name], f"override_policy.{field_name}")
    policy = OverridePolicy(
        managed_profile_allowed=policy_data["managed_profile_allowed"],
        command_line_profile_allowed=policy_data["command_line_profile_allowed"],
        persisted_profile_allowed=policy_data["persisted_profile_allowed"],
        configure_dialog_allowed=policy_data["configure_dialog_allowed"],
        development_defaults_allowed=policy_data["development_defaults_allowed"],
    )

    agent_data = _exact_fields(
        data["agent_connection"], {"byo_host", "legacy_tools"}, "agent_connection"
    )
    byo_data = _exact_fields(
        agent_data["byo_host"], {"disposition"}, "agent_connection.byo_host"
    )
    legacy_data = _exact_fields(
        agent_data["legacy_tools"],
        {"disposition", "credential_source"},
        "agent_connection.legacy_tools",
    )
    byo_disposition = byo_data["disposition"]
    if byo_disposition not in {"authenticated_ui_tunnel", "disabled"}:
        raise DeploymentProfileError("BYO host disposition is unsupported")
    legacy_disposition = legacy_data["disposition"]
    credential_source = legacy_data["credential_source"]
    valid_legacy = {
        ("disabled", "none"),
        ("managed_api_key", "managed_environment_agent_api_key"),
    }
    if (legacy_disposition, credential_source) not in valid_legacy:
        raise DeploymentProfileError("legacy tools disposition and credential source disagree")

    if distribution == "production":
        if local_only or authority_local or endpoint_local:
            raise DeploymentProfileError("production deployment values must be non-local")
        if not authority.startswith("https://") or not endpoint.startswith("wss://"):
            raise DeploymentProfileError("production deployment values require TLS")
        if policy.configure_dialog_allowed or policy.development_defaults_allowed:
            raise DeploymentProfileError("production profile permits a developer fallback")
        if byo_disposition != "authenticated_ui_tunnel" or legacy_disposition != "disabled":
            raise DeploymentProfileError("production agent dispositions are inconsistent")
    else:
        if not local_only or not authority_local or not endpoint_local:
            raise DeploymentProfileError("generic developer profiles must be explicitly local-only")

    return DeploymentProfile(
        schema_version=PROFILE_SCHEMA_VERSION,
        profile_id=profile_id,
        release_id=release_id,
        client_version=client_version,
        distribution=distribution,
        local_only=local_only,
        authority=authority,
        websocket_endpoint=endpoint,
        client_id=client_id,
        auth_mode=auth_mode,
        override_policy=policy,
        agent_connection=AgentConnection(
            byo_host=ByoHostDisposition(byo_disposition),
            legacy_tools=LegacyToolsDisposition(legacy_disposition, credential_source),
        ),
    )


def canonical_profile_digest(value: Mapping[str, Any] | DeploymentProfile) -> str:
    """Return SHA-256 over canonical UTF-8 JSON for one complete profile."""

    mapping = value.as_dict() if isinstance(value, DeploymentProfile) else dict(value)
    canonical = json.dumps(
        mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _development_profile() -> DeploymentProfile:
    return parse_profile(
        {
            "schema_version": 1,
            "profile_id": "astraldeep-local-developer",
            "release_id": "generic-developer-0.4.0",
            "client_version": "0.4.0",
            "distribution": "generic_developer",
            "local_only": True,
            "authority": "http://127.0.0.1:8080/realms/Astral",
            "websocket_endpoint": "ws://127.0.0.1:8001/ws",
            "client_id": "astral-desktop",
            "auth_mode": "keycloak_oidc_pkce",
            "override_policy": {
                "managed_profile_allowed": True,
                "command_line_profile_allowed": True,
                "persisted_profile_allowed": True,
                "configure_dialog_allowed": True,
                "development_defaults_allowed": True,
            },
            "agent_connection": {
                "byo_host": {"disposition": "authenticated_ui_tunnel"},
                "legacy_tools": {"disposition": "disabled", "credential_source": "none"},
            },
        }
    )


def read_persisted_profile() -> Optional[str]:
    """Read the atomically persisted whole profile from the Windows QSettings key.

    Importing ``winreg`` instead of Qt keeps resolution before all Qt imports.
    Both layouts cover QSettings' native nested-group and slash-key encodings.
    """

    if os.name != "nt":
        return None
    try:  # pragma: no cover - exercised on the Windows candidate runner
        import winreg
    except ImportError:
        return None
    locations = (
        (r"Software\AstralDeep\WindowsClient\deployment", "profile_json"),
        (r"Software\AstralDeep\WindowsClient", "deployment/profile_json"),
    )
    for key_path, value_name in locations:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, value_type = winreg.QueryValueEx(key, value_name)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise DeploymentProfileError("persisted deployment profile is unreadable") from exc
        if value_type not in {winreg.REG_SZ, winreg.REG_EXPAND_SZ} or not isinstance(value, str):
            raise DeploymentProfileError("persisted deployment profile has an invalid registry type")
        return value
    return None


def resolve_effective_profile(
    *,
    bundled_profile_path: Optional[os.PathLike[str] | str],
    expected_client_version: str,
    managed_profile_path: Optional[os.PathLike[str] | str] = None,
    command_line_profile_path: Optional[os.PathLike[str] | str] = None,
    persisted_profile_json: Optional[str] = None,
    allow_development_defaults: bool = False,
    frozen: bool = False,
    environment: Optional[Mapping[str, str]] = None,
) -> EffectiveDeploymentProfile:
    """Resolve exactly one immutable profile with deterministic whole-source precedence."""

    try:
        parse_semver(expected_client_version)
    except ValueError as exc:
        raise DeploymentProfileError("client build version is not strict SemVer") from exc
    env = dict(os.environ if environment is None else environment)
    managed_profile_path = managed_profile_path or env.get(
        "ASTRAL_MANAGED_DEPLOYMENT_PROFILE"
    )

    if bundled_profile_path is not None and Path(bundled_profile_path).is_file():
        base = parse_profile(
            _load_json_file(bundled_profile_path, "bundled deployment profile"),
            expected_client_version=expected_client_version,
        )
        base_source = "bundled_release"
    elif frozen or not allow_development_defaults:
        raise DeploymentProfileError("bundled deployment profile is missing")
    else:
        base = _development_profile()
        if base.client_version != expected_client_version:
            raise DeploymentProfileError("development default version does not match the client")
        base_source = "development_default"

    selected = base
    source = base_source
    if managed_profile_path:
        if not base.override_policy.managed_profile_allowed:
            raise DeploymentProfileError("managed deployment-profile override is not permitted")
        selected = parse_profile(
            _load_json_file(managed_profile_path, "managed deployment profile"),
            expected_client_version=expected_client_version,
        )
        source = "managed_override"
    elif command_line_profile_path:
        if not base.override_policy.command_line_profile_allowed:
            raise DeploymentProfileError("command-line deployment-profile override is not permitted")
        selected = parse_profile(
            _load_json_file(command_line_profile_path, "command-line deployment profile"),
            expected_client_version=expected_client_version,
        )
        source = "command_line_override"
    elif persisted_profile_json is not None:
        if not base.override_policy.persisted_profile_allowed:
            raise DeploymentProfileError("persisted deployment-profile override is not permitted")
        selected = parse_profile(
            _parse_json_bytes(
                persisted_profile_json.encode("utf-8"), "persisted deployment profile"
            ),
            expected_client_version=expected_client_version,
        )
        source = "persisted_override"

    managed_key = None
    legacy = selected.agent_connection.legacy_tools
    if legacy.disposition == "managed_api_key":
        managed_key = env.get("AGENT_API_KEY")
        if not managed_key:
            raise DeploymentProfileError("managed legacy-tools credential is unavailable")
    return EffectiveDeploymentProfile(
        profile=selected,
        source=source,
        digest=canonical_profile_digest(selected),
        managed_agent_api_key=managed_key,
    )


def _file_sha256(path: os.PathLike[str] | str, label: str) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DeploymentProfileError(f"{label} is missing or unreadable") from exc
    return digest.hexdigest()


def validate_packaged_deployment(
    effective: EffectiveDeploymentProfile,
    *,
    runtime_manifest_path: os.PathLike[str] | str,
    requirements_lock_path: os.PathLike[str] | str,
    requirements_input_path: os.PathLike[str] | str,
    expected_client_version: str,
) -> dict[str, Any]:
    """Validate bundled profile/runtime identities and return a redacted report."""

    manifest = _exact_fields(
        _load_json_file(runtime_manifest_path, "packaged runtime manifest"),
        _RUNTIME_MANIFEST_FIELDS,
        "packaged runtime manifest",
    )
    if manifest["schema_version"] != RUNTIME_MANIFEST_SCHEMA_VERSION:
        raise DeploymentProfileError("packaged runtime manifest schema is unsupported")
    if manifest["client_version"] != expected_client_version:
        raise DeploymentProfileError("packaged runtime version does not match the client")
    if manifest["release_id"] != effective.profile.release_id:
        raise DeploymentProfileError("packaged runtime release identity does not match the profile")
    if manifest["deployment_profile_sha256"] != effective.digest:
        raise DeploymentProfileError("bundled deployment profile is not the approved release profile")
    lock_digest = _file_sha256(requirements_lock_path, "release requirements lock")
    input_digest = _file_sha256(requirements_input_path, "release requirements input")
    if manifest["requirements_lock_sha256"] != lock_digest:
        raise DeploymentProfileError("release lock digest does not match packaged metadata")
    if manifest["requirements_input_sha256"] != input_digest:
        raise DeploymentProfileError("release input digest does not match packaged metadata")
    if manifest["runtime_contract_version"] != RUNTIME_CONTRACT_VERSION:
        raise DeploymentProfileError("packaged personal-agent runtime contract is unsupported")
    if manifest["required_runtime_lock_sha256"] != lock_digest:
        raise DeploymentProfileError("personal-agent runtime is not bound to the final release lock")
    for digest_field in (
        "deployment_profile_sha256",
        "requirements_input_sha256",
        "requirements_lock_sha256",
        "required_runtime_lock_sha256",
    ):
        if (
            not isinstance(manifest[digest_field], str)
            or _SHA256.fullmatch(manifest[digest_field]) is None
        ):
            raise DeploymentProfileError(f"{digest_field} must be lowercase SHA-256")
    if manifest["python_version"] != "3.11" or manifest["target_platform"] != "win_amd64":
        raise DeploymentProfileError("packaged runtime target is not Windows/Python 3.11")
    if manifest["worker_entrypoint"] != "AstralDeep.exe --byo-worker":
        raise DeploymentProfileError("packaged worker entry point is inconsistent")

    report = effective.redacted_report()
    report.update(
        {
            "status": "valid",
            "python_version": manifest["python_version"],
            "target_platform": manifest["target_platform"],
            "requirements_input_sha256": input_digest,
            "requirements_lock_sha256": lock_digest,
            "runtime_contract_version": manifest["runtime_contract_version"],
            "required_runtime_lock_sha256": manifest["required_runtime_lock_sha256"],
            "worker_entrypoint": manifest["worker_entrypoint"],
        }
    )
    return report


def write_redacted_report(path: os.PathLike[str] | str, report: Mapping[str, Any]) -> None:
    """Atomically write a bounded validation report with no credential fields."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dict(report), sort_keys=True, indent=2) + "\n"
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=destination.parent, delete=False
        ) as handle:
            temporary_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.remove(temporary_name)


@dataclass(frozen=True)
class StartupResolution:
    effective_profile: EffectiveDeploymentProfile
    remaining_args: tuple[str, ...]
    validation_report: Optional[dict[str, Any]]


def resolve_startup(
    argv: Sequence[str],
    *,
    resource_root: os.PathLike[str] | str,
    expected_client_version: str,
    frozen: bool,
    environment: Optional[Mapping[str, str]] = None,
    persisted_profile_json: Optional[str] = None,
) -> StartupResolution:
    """Resolve pre-Qt CLI/profile state and optionally validate the package."""

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--deployment-profile")
    parser.add_argument("--validate-deployment", action="store_true")
    parser.add_argument("--report")
    options, remaining = parser.parse_known_args(list(argv))
    if options.report and not options.validate_deployment:
        raise DeploymentProfileError("--report requires --validate-deployment")
    root = Path(resource_root)

    def _release_file(name: str) -> Path:
        bundled = root / "deployment" / name
        return bundled if bundled.is_file() else root / name

    resolution_environment = os.environ if environment is None else environment
    higher_precedence_profile_selected = bool(
        options.deployment_profile
        or resolution_environment.get("ASTRAL_MANAGED_DEPLOYMENT_PROFILE")
    )
    if persisted_profile_json is None and not higher_precedence_profile_selected:
        persisted_profile_json = read_persisted_profile()
    effective = resolve_effective_profile(
        bundled_profile_path=root / "deployment" / "release-profile.json",
        expected_client_version=expected_client_version,
        command_line_profile_path=options.deployment_profile,
        persisted_profile_json=persisted_profile_json,
        allow_development_defaults=not frozen,
        frozen=frozen,
        environment=environment,
    )
    report = None
    if options.validate_deployment:
        report = validate_packaged_deployment(
            effective,
            runtime_manifest_path=root / "deployment" / "runtime-manifest.json",
            requirements_lock_path=_release_file("requirements-release.lock.txt"),
            requirements_input_path=_release_file("requirements.in"),
            expected_client_version=expected_client_version,
        )
        if options.report:
            write_redacted_report(options.report, report)
    return StartupResolution(effective, tuple(remaining), report)
