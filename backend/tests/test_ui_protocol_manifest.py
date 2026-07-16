"""Feature 044 — drift guards for the committed UI-protocol manifest.

``backend/shared/ui_protocol.json`` is the single machine-readable source for
(a) every server->client WS frame type, (b) the ui_event action vocabulary, and
(c) the component vocabulary. Windows and Android test suites assert their own
classification tables against the same file; these backend guards assert the
manifest stays equal to the code, so a new frame/action/component that is not
manifested fails the build (FR-014/FR-023, SC-001).
"""
import json
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
MANIFEST_PATH = BACKEND / "shared" / "ui_protocol.json"

# Modules that send frames on the UI websocket (or define their dataclasses).
UI_SEND_MODULES = [
    "orchestrator/orchestrator.py",
    "orchestrator/chrome_events.py",
    "orchestrator/async_tasks.py",
    "orchestrator/chat_steps.py",
    "orchestrator/stream_manager.py",
    "orchestrator/api.py",
    "orchestrator/agentic_creation.py",
    "orchestrator/agent_lifecycle.py",
    "scheduler/runner.py",
    "audit/ws_publisher.py",
    "llm_config/ws_handlers.py",
    "shared/protocol.py",
]

# Frame types that legitimately appear in those modules but are NOT UI pushes:
# inbound frames, agent-transport frames, and JSON-schema / LLM-payload noise.
SWEEP_ALLOWLIST = {
    # inbound (client->server / agent->server)
    "ui_event", "register_ui", "register_agent", "mcp_request", "mcp_response",
    "llm_config_set", "llm_config_clear",
    "tool_stream_data", "tool_stream_end", "tool_stream_cancel",
    # Bidirectional transport controls are handled before UI dispatch and do
    # not enter the semantic server-push vocabulary.
    "ping", "pong", "close", "cancel", "cancel_task",
    # 056: agent-channel control frames for mediated hops (loopback / agent
    # WS only — never sent to a UI client; ui_protocol.json intentionally
    # unchanged, Constitution XII)
    "agent_hop_request", "agent_hop_response",
    # JSON-schema / LLM request payload noise swept up by the literal regex
    "string", "object", "array", "function", "json_object", "json_schema", "raw",
}

_TYPE_LITERAL = re.compile(r'"type": "([a-z_]+)"')
_DATACLASS_DEFAULT = re.compile(r'type: str = "([a-z_]+)"')
_ACTION_LITERAL = re.compile(r'action == "([a-z_]+)"')
_CHROME_KEY = re.compile(r'"((?:chrome|draft|revision)_[a-z_]+)"\s*:')


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _push_names(manifest):
    return {entry["name"] for entry in manifest["push_types"]}


def test_manifest_is_well_formed():
    m = _manifest()
    names = [e["name"] for e in m["push_types"]]
    assert len(names) == len(set(names)), "duplicate push_types"
    assert names == sorted(names), "push_types must stay sorted for reviewability"
    assert len(m["accept_actions"]) == len(set(m["accept_actions"]))
    assert m["accept_actions"] == sorted(m["accept_actions"])
    assert len(m["component_types"]) == len(set(m["component_types"]))
    assert m["component_types"] == sorted(m["component_types"])
    assert "error" in _push_names(m) and "notification" in _push_names(m)


def test_admission_refusal_contract_is_exact_and_correlatable():
    contract = _manifest()["frame_contracts"]["admission_refusal"]
    assert contract == {
        "type": "error",
        "exact_fields": [
            "type",
            "submission_id",
            "accepted",
            "code",
            "message",
            "retryable",
            "retry_after_ms",
        ],
        "submission_id": "canonical_lowercase_uuid4",
        "accepted": False,
        "additional_fields": False,
        "codes": [
            "capacity_exceeded",
            "registration_required",
            "registration_timeout",
            "idempotency_conflict",
            "connection_closing",
            "service_draining",
            "invalid_input",
            "registration_queue_full",
            "operation_failed",
        ],
    }


def test_runtime_reliability_frames_and_structured_host_registration_are_manifested():
    """Feature 060 additions must land as one reviewable cross-client contract.

    ``register_ui.agent_host`` is deliberately represented as an additive field:
    it is a client-to-server registration payload, not a server push type.
    """
    manifest = _manifest()
    required_pushes = {
        "conversation_commit_ready",
        "conversation_snapshot",
        "operation_status",
        "agent_lifecycle",
        "agent_host_inventory_reconciled",
        "agent_host_registered",
        "agent_host_registration_refused",
    }
    assert required_pushes <= _push_names(manifest), (
        "feature-060 server frames are missing from shared/ui_protocol.json: "
        f"{sorted(required_pushes - _push_names(manifest))}"
    )

    registrations = [
        entry
        for entry in manifest["additive_fields"]
        if entry.get("field") == "agent_host"
        and entry.get("carried_on") == ["register_ui"]
    ]
    assert len(registrations) == 1, (
        "shared/ui_protocol.json must declare structured register_ui.agent_host exactly once"
    )
    shape = registrations[0].get("shape")
    assert isinstance(shape, dict)
    assert set(shape) == {
        "host_id",
        "supported_runtime_contract_versions",
        "runtime_lock_sha256",
        "platform",
        "client_version",
    }

    fields = {
        entry["field"]: entry for entry in manifest["additive_fields"]
    }
    transient_frames = {
        "ui_render",
        "ui_update",
        "ui_upsert",
        "ui_append",
        "ui_stream_data",
    }
    for field_name in ("base_render_revision", "frame_sequence"):
        assert set(fields[field_name]["carried_on"]) == transient_frames
    for field_name in ("chat_id", "connection_generation", "request_generation"):
        assert transient_frames <= set(fields[field_name]["carried_on"])

    capability = fields["capabilities.personal_agent_host.macos"]
    assert set(capability["carried_on"]) == {
        "system_config",
        "GET /api/dashboard",
    }
    assert set(capability["shape"]) == {
        "supported",
        "runtime_contract_versions",
        "source_feature",
    }


def test_component_vocabulary_matches_renderer():
    from webrender.renderer import allowed_primitive_types

    m = _manifest()
    assert sorted(m["component_types"]) == sorted(allowed_primitive_types()), (
        "webrender's renderer registry and ui_protocol.json disagree — update the "
        "manifest in the same PR that changes the component vocabulary"
    )


def test_push_types_cover_send_sites():
    """Every `"type": "<literal>"` sent from a UI-socket module (and every
    protocol dataclass default) must be a manifested push type, an allowlisted
    inbound type, or a component type (component dicts share the same key)."""
    m = _manifest()
    allowed = _push_names(m) | set(m["component_types"]) | SWEEP_ALLOWLIST

    unmanifested: dict[str, list[str]] = {}
    for rel in UI_SEND_MODULES:
        src = (BACKEND / rel).read_text(encoding="utf-8")
        found = set(_TYPE_LITERAL.findall(src)) | set(_DATACLASS_DEFAULT.findall(src))
        for name in sorted(found - allowed):
            unmanifested.setdefault(name, []).append(rel)

    assert not unmanifested, (
        "frame types sent to UI clients but missing from shared/ui_protocol.json "
        f"(add them + classify on every client): {unmanifested}"
    )


def test_accept_actions_cover_dispatch():
    """Every ui_event action the orchestrator or chrome layer dispatches on must
    be manifested (client-local actions live in client_local_actions)."""
    m = _manifest()
    manifested = set(m["accept_actions"])

    orch_src = (BACKEND / "orchestrator/orchestrator.py").read_text(encoding="utf-8")
    actions = set(_ACTION_LITERAL.findall(orch_src))
    # values compared against payload fields, not top-level actions
    actions -= {"block", "modify", "session_resumed"}

    for rel in ["orchestrator/chrome_events.py", "orchestrator/agentic_creation.py"]:
        src = (BACKEND / rel).read_text(encoding="utf-8")
        actions |= set(_CHROME_KEY.findall(src))
    surfaces = BACKEND / "webrender" / "chrome" / "surfaces"
    for path in surfaces.glob("*.py"):
        actions |= set(_CHROME_KEY.findall(path.read_text(encoding="utf-8")))
    # payload keys that match the draft/revision prefix but are not actions
    actions -= {"draft_id", "draft_status", "revision_staged"}

    missing = sorted(actions - manifested)
    assert not missing, f"dispatched ui_event actions missing from the manifest: {missing}"


def test_client_local_actions_never_dispatched_server_side():
    m = _manifest()
    orch_src = (BACKEND / "orchestrator/orchestrator.py").read_text(encoding="utf-8")
    for action in m["client_local_actions"]:
        assert f'action == "{action}"' not in orch_src, (
            f"{action} is documented client-local; a server handler contradicts the contract"
        )
