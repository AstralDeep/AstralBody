"""Spec 060 Windows deployment-profile contract tests (T058)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from astral_client.deployment import (
    DeploymentProfileError,
    canonical_profile_digest,
    parse_profile,
    resolve_effective_profile,
    resolve_startup,
    validate_packaged_deployment,
)


ROOT = Path(__file__).resolve().parents[1]
RELEASE_PROFILE = ROOT / "deployment" / "release-profile.json"
RUNTIME_MANIFEST = ROOT / "deployment" / "runtime-manifest.json"
RELEASE_LOCK = ROOT / "requirements-release.lock.txt"
REQUIREMENTS_INPUT = ROOT / "requirements.in"


def _profile(**changes):
    value = json.loads(RELEASE_PROFILE.read_text(encoding="utf-8"))
    value.update(changes)
    return value


def _generic(**changes):
    value = _profile(
        profile_id="astraldeep-local-developer",
        release_id="generic-developer-0.4.0",
        distribution="generic_developer",
        local_only=True,
        authority="http://127.0.0.1:8080/realms/Astral",
        websocket_endpoint="ws://127.0.0.1:8001/ws",
        agent_connection={
            "byo_host": {"disposition": "authenticated_ui_tunnel"},
            "legacy_tools": {
                "disposition": "disabled",
                "credential_source": "none",
            },
        },
        override_policy={
            "managed_profile_allowed": True,
            "command_line_profile_allowed": True,
            "persisted_profile_allowed": True,
            "configure_dialog_allowed": True,
            "development_defaults_allowed": True,
        },
    )
    value.update(changes)
    return value


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_reviewed_release_profile_is_complete_strict_and_nonlocal():
    effective = resolve_effective_profile(
        bundled_profile_path=RELEASE_PROFILE,
        expected_client_version="0.4.0",
    )
    assert effective.source == "bundled_release"
    assert effective.profile.distribution == "production"
    assert effective.profile.local_only is False
    assert effective.profile.authority == "https://iam.ai.uky.edu/realms/Astral"
    assert effective.profile.websocket_endpoint == "wss://sandbox.ai.uky.edu/ws"
    assert effective.profile.agent_connection.byo_host.disposition == "authenticated_ui_tunnel"
    assert effective.profile.agent_connection.legacy_tools.disposition == "disabled"


@pytest.mark.parametrize("field", sorted(_profile()))
def test_every_top_level_profile_field_is_required(field):
    value = _profile()
    del value[field]
    with pytest.raises(DeploymentProfileError, match="fields"):
        parse_profile(value)


def test_unknown_profile_fields_fail_closed():
    with pytest.raises(DeploymentProfileError, match="fields"):
        parse_profile(_profile(secret="must-not-be-accepted"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_id", "placeholder"),
        ("release_id", "changeme"),
        ("client_id", "example"),
        ("authority", "https://example.invalid"),
        ("websocket_endpoint", "wss://example.com/ws"),
    ],
)
def test_placeholder_values_are_rejected(field, value):
    with pytest.raises(DeploymentProfileError):
        parse_profile(_profile(**{field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authority", "https://user@iam.ai.uky.edu/realms/Astral"),
        ("authority", "https://iam.ai.uky.edu/realms/Astral?tenant=1"),
        ("authority", "https://iam.ai.uky.edu/realms/Astral#fragment"),
        ("websocket_endpoint", "wss://user@sandbox.ai.uky.edu/ws"),
        ("websocket_endpoint", "wss://sandbox.ai.uky.edu/ws?token=x"),
        ("websocket_endpoint", "wss://sandbox.ai.uky.edu/ws#fragment"),
    ],
)
def test_uri_userinfo_query_and_fragment_are_rejected(field, value):
    with pytest.raises(DeploymentProfileError, match="userinfo|query|fragment"):
        parse_profile(_profile(**{field: value}))


@pytest.mark.parametrize(
    ("authority", "endpoint"),
    [
        ("https://localhost/realms/Astral", "wss://sandbox.ai.uky.edu/ws"),
        ("https://iam.ai.uky.edu/realms/Astral", "wss://127.0.0.1:8001/ws"),
    ],
)
def test_production_profile_cannot_be_local(authority, endpoint):
    with pytest.raises(DeploymentProfileError, match="production|local"):
        parse_profile(_profile(authority=authority, websocket_endpoint=endpoint))


def test_generic_developer_profile_is_explicitly_local_only():
    parsed = parse_profile(_generic())
    assert parsed.local_only is True
    with pytest.raises(DeploymentProfileError, match="local"):
        parse_profile(
            _generic(
                authority="https://iam.ai.uky.edu/realms/Astral",
                websocket_endpoint="wss://sandbox.ai.uky.edu/ws",
            )
        )


def test_whole_profile_precedence_is_managed_cli_persisted_bundled(tmp_path):
    bundled = _write(tmp_path / "bundled.json", _profile())
    persisted = _generic(profile_id="persisted-profile")
    cli = _write(tmp_path / "cli.json", _generic(profile_id="cli-profile"))
    managed = _write(tmp_path / "managed.json", _generic(profile_id="managed-profile"))

    result = resolve_effective_profile(
        bundled_profile_path=bundled,
        persisted_profile_json=json.dumps(persisted),
        command_line_profile_path=cli,
        managed_profile_path=managed,
        expected_client_version="0.4.0",
    )
    assert result.source == "managed_override"
    assert result.profile.profile_id == "managed-profile"

    result = resolve_effective_profile(
        bundled_profile_path=bundled,
        persisted_profile_json=json.dumps(persisted),
        command_line_profile_path=cli,
        expected_client_version="0.4.0",
    )
    assert result.source == "command_line_override"
    assert result.profile.profile_id == "cli-profile"

    result = resolve_effective_profile(
        bundled_profile_path=bundled,
        persisted_profile_json=json.dumps(persisted),
        expected_client_version="0.4.0",
    )
    assert result.source == "persisted_override"
    assert result.profile.profile_id == "persisted-profile"


def test_higher_precedence_profile_does_not_probe_broken_persisted_state(
    tmp_path, monkeypatch
):
    import astral_client.deployment as deployment

    selected = _write(tmp_path / "selected.json", _generic(profile_id="selected-profile"))

    def _broken_persisted_state():
        raise AssertionError("lower-precedence persisted state was read")

    monkeypatch.setattr(deployment, "read_persisted_profile", _broken_persisted_state)
    cli = resolve_startup(
        ["--deployment-profile", str(selected)],
        resource_root=ROOT,
        expected_client_version="0.4.0",
        frozen=True,
        environment={},
    )
    assert cli.effective_profile.source == "command_line_override"

    managed = resolve_startup(
        [],
        resource_root=ROOT,
        expected_client_version="0.4.0",
        frozen=True,
        environment={"ASTRAL_MANAGED_DEPLOYMENT_PROFILE": str(selected)},
    )
    assert managed.effective_profile.source == "managed_override"


def test_invalid_selected_override_never_falls_back(tmp_path):
    bundled = _write(tmp_path / "bundled.json", _profile())
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    with pytest.raises(DeploymentProfileError, match="fields"):
        resolve_effective_profile(
            bundled_profile_path=bundled,
            command_line_profile_path=invalid,
            expected_client_version="0.4.0",
        )


def test_disallowed_override_never_falls_back(tmp_path):
    bundled_value = _profile()
    bundled_value["override_policy"]["command_line_profile_allowed"] = False
    bundled = _write(tmp_path / "bundled.json", bundled_value)
    cli = _write(tmp_path / "cli.json", _generic())
    with pytest.raises(DeploymentProfileError, match="not permitted"):
        resolve_effective_profile(
            bundled_profile_path=bundled,
            command_line_profile_path=cli,
            expected_client_version="0.4.0",
        )


def test_resolution_is_immutable_and_digest_is_canonical(tmp_path):
    reordered = dict(reversed(list(_profile().items())))
    assert canonical_profile_digest(reordered) == canonical_profile_digest(_profile())
    effective = resolve_effective_profile(
        bundled_profile_path=RELEASE_PROFILE,
        expected_client_version="0.4.0",
    )
    with pytest.raises(FrozenInstanceError):
        effective.source = "different"
    with pytest.raises(FrozenInstanceError):
        effective.profile.authority = "https://different.invalid"


def test_resolved_profile_does_not_reread_environment(monkeypatch):
    monkeypatch.setenv("ASTRAL_WS_URL", "ws://127.0.0.1:1/ws")
    effective = resolve_effective_profile(
        bundled_profile_path=RELEASE_PROFILE,
        expected_client_version="0.4.0",
        environment={},
    )
    monkeypatch.setenv("ASTRAL_WS_URL", "ws://127.0.0.1:2/ws")
    monkeypatch.setenv("KEYCLOAK_AUTHORITY", "http://127.0.0.1:2/realms/x")
    assert effective.profile.websocket_endpoint == "wss://sandbox.ai.uky.edu/ws"
    assert effective.profile.authority == "https://iam.ai.uky.edu/realms/Astral"


def test_built_in_tools_agent_consumes_the_same_profile_identity(monkeypatch):
    from win_agent.agent import _register_message, build_card

    effective = resolve_effective_profile(
        bundled_profile_path=RELEASE_PROFILE,
        expected_client_version="0.4.0",
        environment={},
    )
    monkeypatch.setenv("AGENT_API_KEY", "must-not-be-reread")
    card = build_card(effective)
    metadata = card["metadata"]
    assert metadata["deployment_profile_sha256"] == effective.digest
    assert metadata["deployment_release_id"] == effective.profile.release_id
    assert len(metadata["deployment_endpoint_sha256"]) == 64
    message = json.loads(_register_message(effective))
    assert message["api_key"] is None
    assert message["agent_card"]["metadata"] == metadata


def test_every_packaged_runtime_consumer_agrees_on_profile_and_endpoint():
    from astral_client.app import _runtime_profile_checks

    effective = resolve_effective_profile(
        bundled_profile_path=RELEASE_PROFILE,
        expected_client_version="0.4.0",
        environment={},
    )
    window = SimpleNamespace(
        _deployment_profile=effective,
        deployment_profile_digest=effective.digest,
        _url=effective.profile.websocket_endpoint,
        client=SimpleNamespace(url=effective.profile.websocket_endpoint),
        _byo=SimpleNamespace(deployment_profile_digest=effective.digest),
    )
    assert _runtime_profile_checks(window, effective) == {
        "window_profile_match": True,
        "byo_profile_match": True,
        "tools_agent_profile_match": True,
    }


def test_redacted_report_contains_identity_not_connection_values():
    effective = resolve_effective_profile(
        bundled_profile_path=RELEASE_PROFILE,
        expected_client_version="0.4.0",
    )
    report = effective.redacted_report()
    encoded = json.dumps(report, sort_keys=True)
    assert report["profile_id"] == "astraldeep-production-uky-0.4.0"
    assert report["profile_sha256"] == effective.digest
    assert "iam.ai.uky.edu" not in encoded
    assert "sandbox.ai.uky.edu" not in encoded
    assert "authority" not in report
    assert "websocket_endpoint" not in report


def test_packaged_validation_binds_profile_lock_input_and_worker():
    effective = resolve_effective_profile(
        bundled_profile_path=RELEASE_PROFILE,
        expected_client_version="0.4.0",
    )
    report = validate_packaged_deployment(
        effective,
        runtime_manifest_path=RUNTIME_MANIFEST,
        requirements_lock_path=RELEASE_LOCK,
        requirements_input_path=REQUIREMENTS_INPUT,
        expected_client_version="0.4.0",
    )
    assert report["status"] == "valid"
    assert report["worker_entrypoint"] == "AstralDeep.exe --byo-worker"
    assert report["requirements_lock_sha256"] == report["required_runtime_lock_sha256"]
    assert set(report).isdisjoint({"authority", "websocket_endpoint", "credential"})
