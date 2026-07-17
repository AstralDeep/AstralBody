"""Windows wire-model and structured host-registration contracts for 060."""

from __future__ import annotations

import dataclasses

import pytest

pytest.importorskip("PySide6")

from astral_client.protocol import (  # noqa: E402
    AgentHostRegistered,
    AgentLifecycle,
    ConversationSnapshot,
    MacOSHostCapability,
    OperationStatus,
    OrchestratorClient,
    WindowsProtocolError,
    parse_runtime_frame,
)


CHAT_ID = "11111111-1111-4111-8111-111111111111"
CONNECTION = "22222222-2222-4222-8222-222222222222"
REQUEST = "33333333-3333-4333-8333-333333333333"
SNAPSHOT = "44444444-4444-4444-8444-444444444444"
OPERATION = "55555555-5555-4555-8555-555555555555"
REVISION = "66666666-6666-4666-8666-666666666666"
RUNTIME = "77777777-7777-4777-8777-777777777777"
HOST_SESSION = "88888888-8888-4888-8888-888888888888"


def _snapshot_payload() -> dict:
    return {
        "type": "conversation_snapshot",
        "schema_version": 1,
        "snapshot_id": SNAPSHOT,
        "chat_id": CHAT_ID,
        "connection_generation": CONNECTION,
        "request_generation": REQUEST,
        "snapshot_purpose": "hydration",
        "render_revision": 7,
        "committed_at": "2026-07-15T18:41:00Z",
        "transcript": [],
        "canvas": {"target": "canvas", "components": []},
    }


def test_snapshot_model_is_complete_and_fails_closed() -> None:
    model = parse_runtime_frame(_snapshot_payload())

    assert isinstance(model, ConversationSnapshot)
    assert model.snapshot_purpose == "hydration"
    assert model.render_revision == 7
    with pytest.raises(dataclasses.FrozenInstanceError):
        model.render_revision = 8  # type: ignore[misc]

    malformed = _snapshot_payload()
    malformed["canvas"] = []
    with pytest.raises(WindowsProtocolError, match="canvas"):
        parse_runtime_frame(malformed)


def test_operation_and_lifecycle_models_validate_generation_fences() -> None:
    status = parse_runtime_frame(
        {
            "type": "operation_status",
            "operation_id": OPERATION,
            "action": "chrome_llm_save",
            "surface": "llm_settings",
            "chat_id": None,
            "connection_generation": CONNECTION,
            "request_generation": REQUEST,
            "sequence": 2,
            "state": "validating",
            "phase": "validating_credentials",
            "label": "Checking credentials",
            "terminal": False,
            "retryable": False,
            "error": None,
            "retry_after_ms": None,
            "updated_at": "2026-07-15T18:41:00Z",
        }
    )
    lifecycle = parse_runtime_frame(
        {
            "type": "agent_lifecycle",
            "agent_id": "ua-dice-4f3c2a",
            "revision_id": REVISION,
            "runtime_instance_id": RUNTIME,
            "lifecycle_generation": 14,
            "state_revision": 3,
            "state": "online",
            "reason_code": None,
            "label": "Online",
            "updated_at": "2026-07-15T18:41:00Z",
        }
    )

    assert isinstance(status, OperationStatus)
    assert isinstance(lifecycle, AgentLifecycle)
    assert (lifecycle.lifecycle_generation, lifecycle.state_revision) == (14, 3)

    invalid = dict(status.__dict__)
    invalid.update(type="operation_status", state="completed", terminal=False)
    with pytest.raises(WindowsProtocolError, match="flags"):
        OperationStatus.from_dict(invalid)


def test_register_frame_is_structured_and_ack_binds_only_matching_host(qapp) -> None:
    client = OrchestratorClient("ws://127.0.0.1:9/ws", "token")
    frame = client._register_frame()

    assert set(frame["agent_host"]) == {
        "host_id",
        "supported_runtime_contract_versions",
        "runtime_lock_sha256",
        "platform",
        "client_version",
    }
    assert frame["agent_host"]["supported_runtime_contract_versions"] == [2]
    assert frame["agent_host"]["platform"] == "windows"
    assert "host_session_id" not in frame

    acknowledgement = {
        "type": "agent_host_registered",
        "host_id": client.host_id,
        "host_session_id": HOST_SESSION,
        "inventory_required": True,
        "accepted_at": "2026-07-15T18:41:00Z",
    }
    assert client._handle_runtime_frame(acknowledgement) is True
    assert client.host_session_id == HOST_SESSION
    assert isinstance(parse_runtime_frame(acknowledgement), AgentHostRegistered)

    wrong_host = dict(acknowledgement, host_id=CHAT_ID)
    assert client._handle_runtime_frame(wrong_host) is False
    assert client.host_session_id == HOST_SESSION


def test_candidate_macos_host_applicability_never_defaults_malformed_to_false() -> None:
    unsupported = MacOSHostCapability.from_dict(
        {
            "supported": False,
            "runtime_contract_versions": [],
            "source_feature": None,
        }
    )
    supported = MacOSHostCapability.from_dict(
        {
            "supported": True,
            "runtime_contract_versions": [2],
            "source_feature": "059",
        }
    )

    assert unsupported.supported is False
    assert supported.supported is True
    with pytest.raises(WindowsProtocolError):
        MacOSHostCapability.from_dict(
            {
                "supported": False,
                "runtime_contract_versions": [2],
                "source_feature": None,
            }
        )
