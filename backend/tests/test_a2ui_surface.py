"""
A2UI Surface Manager Tests — Surface lifecycle and session management.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.a2ui_primitives import A2UIComponent, text, column
from shared.a2ui_surface import SurfaceManager, Surface
from shared.a2ui_protocol import (
    CreateSurfaceMessage,
    UpdateComponentsMessage,
    UpdateDataModelMessage,
    DeleteSurfaceMessage,
)


class TestSurfaceManager:
    def setup_method(self):
        self.mgr = SurfaceManager()
        self.ws_id = 12345

    def test_create_surface(self):
        t = text("Hello")
        msg = self.mgr.create_surface(
            self.ws_id, [t], t.id
        )
        assert isinstance(msg, CreateSurfaceMessage)
        assert msg.surface_id != ""
        assert msg.root_component_id == t.id
        assert msg.catalog_id == "astral-default"
        assert len(msg.components) == 1

    def test_create_surface_stores_surface(self):
        t = text("Hi")
        msg = self.mgr.create_surface(self.ws_id, [t], t.id)
        surface = self.mgr.get_surface(msg.surface_id)
        assert surface is not None
        assert surface.root_id == t.id

    def test_update_components(self):
        t1 = text("Old")
        create_msg = self.mgr.create_surface(self.ws_id, [t1], t1.id)
        sid = create_msg.surface_id

        t2 = text("New")
        update_msg = self.mgr.update_components(sid, [t2], t2.id)
        assert isinstance(update_msg, UpdateComponentsMessage)
        assert update_msg.root_component_id == t2.id

        surface = self.mgr.get_surface(sid)
        assert surface.root_id == t2.id

    def test_update_nonexistent_surface(self):
        t = text("X")
        result = self.mgr.update_components("nonexistent", [t], t.id)
        assert result is None

    def test_update_data_model(self):
        t = text("Hi")
        create_msg = self.mgr.create_surface(
            self.ws_id, [t], t.id,
            data_model={"user": {"name": "Alice"}}
        )
        sid = create_msg.surface_id

        update_msg = self.mgr.update_data_model(sid, "/user/name", "Bob")
        assert isinstance(update_msg, UpdateDataModelMessage)
        assert update_msg.value == "Bob"

        surface = self.mgr.get_surface(sid)
        assert surface.data_model.get("/user/name") == "Bob"

    def test_delete_surface(self):
        t = text("Hi")
        create_msg = self.mgr.create_surface(self.ws_id, [t], t.id)
        sid = create_msg.surface_id

        del_msg = self.mgr.delete_surface(sid)
        assert isinstance(del_msg, DeleteSurfaceMessage)
        assert del_msg.surface_id == sid
        assert self.mgr.get_surface(sid) is None

    def test_delete_nonexistent(self):
        assert self.mgr.delete_surface("nope") is None

    def test_cleanup(self):
        t1 = text("A")
        t2 = text("B")
        self.mgr.create_surface(self.ws_id, [t1], t1.id)
        self.mgr.create_surface(self.ws_id, [t2], t2.id)

        assert len(self.mgr.get_session_surfaces(self.ws_id)) == 2

        del_msgs = self.mgr.cleanup(self.ws_id)
        assert len(del_msgs) == 2
        assert len(self.mgr.get_session_surfaces(self.ws_id)) == 0

    def test_multiple_sessions(self):
        ws1, ws2 = 111, 222
        t1 = text("A")
        t2 = text("B")
        self.mgr.create_surface(ws1, [t1], t1.id)
        self.mgr.create_surface(ws2, [t2], t2.id)

        assert len(self.mgr.get_session_surfaces(ws1)) == 1
        assert len(self.mgr.get_session_surfaces(ws2)) == 1

        self.mgr.cleanup(ws1)
        assert len(self.mgr.get_session_surfaces(ws1)) == 0
        assert len(self.mgr.get_session_surfaces(ws2)) == 1

    def test_create_with_theme(self):
        t = text("Hi")
        msg = self.mgr.create_surface(
            self.ws_id, [t], t.id,
            theme={"primary": "#ff0000"}
        )
        assert msg.theme == {"primary": "#ff0000"}
        surface = self.mgr.get_surface(msg.surface_id)
        assert surface.theme == {"primary": "#ff0000"}
