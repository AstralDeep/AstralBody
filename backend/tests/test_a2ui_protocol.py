"""
A2UI Protocol Tests — Message serialization, deserialization, and factory.
"""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestCreateSurfaceMessage:
    def test_serialization(self):
        from shared.a2ui_protocol import CreateSurfaceMessage
        msg = CreateSurfaceMessage(
            surface_id="s-1",
            catalog_id="astral-default",
            components=[{"id": "t1", "type": "Text", "properties": {"text": "Hi"}}],
            root_component_id="t1",
        )
        d = msg.to_dict()
        assert d["type"] == "a2ui_create_surface"
        assert d["surfaceId"] == "s-1"
        assert d["catalogId"] == "astral-default"
        assert d["rootComponentId"] == "t1"
        assert len(d["components"]) == 1
        assert "dataModel" not in d  # None omitted

    def test_with_data_model(self):
        from shared.a2ui_protocol import CreateSurfaceMessage
        msg = CreateSurfaceMessage(
            surface_id="s-2",
            components=[],
            root_component_id="",
            data_model={"user": {"name": "Alice"}},
        )
        d = msg.to_dict()
        assert d["dataModel"]["user"]["name"] == "Alice"

    def test_json_roundtrip(self):
        from shared.a2ui_protocol import CreateSurfaceMessage
        msg = CreateSurfaceMessage(
            surface_id="s-3",
            components=[{"id": "x", "type": "Text"}],
            root_component_id="x",
        )
        json_str = msg.to_json()
        data = json.loads(json_str)
        assert data["surfaceId"] == "s-3"


class TestUpdateComponentsMessage:
    def test_serialization(self):
        from shared.a2ui_protocol import UpdateComponentsMessage
        msg = UpdateComponentsMessage(
            surface_id="s-1",
            components=[{"id": "t2", "type": "Text"}],
            root_component_id="t2",
        )
        d = msg.to_dict()
        assert d["type"] == "a2ui_update_components"
        assert d["surfaceId"] == "s-1"


class TestUpdateDataModelMessage:
    def test_serialization(self):
        from shared.a2ui_protocol import UpdateDataModelMessage
        msg = UpdateDataModelMessage(
            surface_id="s-1",
            path="/user/name",
            value="Bob",
        )
        d = msg.to_dict()
        assert d["path"] == "/user/name"
        assert d["value"] == "Bob"


class TestDeleteSurfaceMessage:
    def test_serialization(self):
        from shared.a2ui_protocol import DeleteSurfaceMessage
        msg = DeleteSurfaceMessage(surface_id="s-1")
        d = msg.to_dict()
        assert d["type"] == "a2ui_delete_surface"
        assert d["surfaceId"] == "s-1"


class TestA2UIActionMessage:
    def test_serialization(self):
        from shared.a2ui_protocol import A2UIActionMessage
        msg = A2UIActionMessage(
            name="chat_message",
            surface_id="s-1",
            source_component_id="btn-1",
            timestamp="2026-01-01T00:00:00Z",
            context={"message": "hello"},
        )
        d = msg.to_dict()
        assert d["name"] == "chat_message"
        assert d["surfaceId"] == "s-1"
        assert d["sourceComponentId"] == "btn-1"
        assert d["context"]["message"] == "hello"


class TestParseA2UIMessage:
    def test_parse_create_surface(self):
        from shared.a2ui_protocol import parse_a2ui_message, CreateSurfaceMessage
        data = {
            "type": "a2ui_create_surface",
            "version": "v0.10",
            "surfaceId": "s-1",
            "catalogId": "astral-default",
            "components": [{"id": "t1", "type": "Text"}],
            "rootComponentId": "t1",
        }
        msg = parse_a2ui_message(data)
        assert isinstance(msg, CreateSurfaceMessage)
        assert msg.surface_id == "s-1"
        assert msg.root_component_id == "t1"

    def test_parse_action(self):
        from shared.a2ui_protocol import parse_a2ui_message, A2UIActionMessage
        data = {
            "type": "a2ui_action",
            "name": "table_paginate",
            "surfaceId": "s-1",
            "sourceComponentId": "tbl-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "context": {"tool_name": "get_data", "limit": 25, "offset": 50},
        }
        msg = parse_a2ui_message(data)
        assert isinstance(msg, A2UIActionMessage)
        assert msg.name == "table_paginate"
        assert msg.context["limit"] == 25

    def test_parse_unknown_returns_none(self):
        from shared.a2ui_protocol import parse_a2ui_message
        assert parse_a2ui_message({"type": "unknown"}) is None

    def test_is_a2ui_message(self):
        from shared.a2ui_protocol import is_a2ui_message
        assert is_a2ui_message("a2ui_create_surface") is True
        assert is_a2ui_message("a2ui_action") is True
        assert is_a2ui_message("ui_render") is False
        assert is_a2ui_message("ui_event") is False


class TestProtocolIntegration:
    """Test that Message.from_json dispatches A2UI messages correctly."""

    def test_from_json_dispatches_a2ui_action(self):
        from shared.protocol import Message
        from shared.a2ui_protocol import A2UIActionMessage
        json_str = json.dumps({
            "type": "a2ui_action",
            "name": "chat_message",
            "surfaceId": "s-1",
            "sourceComponentId": "btn-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "context": {"message": "hello"},
        })
        msg = Message.from_json(json_str)
        assert isinstance(msg, A2UIActionMessage)
        assert msg.name == "chat_message"

    def test_from_json_still_handles_legacy(self):
        from shared.protocol import Message, UIEvent
        json_str = json.dumps({
            "type": "ui_event",
            "action": "chat_message",
            "payload": {"message": "hi"},
        })
        msg = Message.from_json(json_str)
        assert isinstance(msg, UIEvent)
        assert msg.action == "chat_message"

    def test_register_ui_protocol_version(self):
        from shared.protocol import RegisterUI
        msg = RegisterUI(
            token="test-token",
            capabilities=["render"],
            protocol_version="a2ui",
        )
        assert msg.protocol_version == "a2ui"
        json_str = msg.to_json()
        data = json.loads(json_str)
        assert data["protocol_version"] == "a2ui"

    def test_register_ui_default_legacy(self):
        from shared.protocol import RegisterUI
        msg = RegisterUI(token="test")
        assert msg.protocol_version == "legacy"
