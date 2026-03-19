"""
A2UI Data Model Tests — JSON Pointer resolution, mutation, and change tracking.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.a2ui_data_model import (
    resolve_pointer, set_pointer, delete_pointer,
    DataModel, JsonPointerError,
)


class TestResolvePointer:
    def test_root_pointer(self):
        data = {"a": 1}
        assert resolve_pointer(data, "") == {"a": 1}

    def test_simple_key(self):
        assert resolve_pointer({"name": "Alice"}, "/name") == "Alice"

    def test_nested_key(self):
        data = {"a": {"b": {"c": 42}}}
        assert resolve_pointer(data, "/a/b/c") == 42

    def test_array_index(self):
        data = {"items": [10, 20, 30]}
        assert resolve_pointer(data, "/items/1") == 20

    def test_nested_array(self):
        data = {"a": [{"b": 1}, {"b": 2}]}
        assert resolve_pointer(data, "/a/1/b") == 2

    def test_missing_key_raises(self):
        with pytest.raises(JsonPointerError):
            resolve_pointer({"a": 1}, "/b")

    def test_array_index_out_of_range(self):
        with pytest.raises(JsonPointerError):
            resolve_pointer({"a": [1]}, "/a/5")

    def test_invalid_pointer_no_slash(self):
        with pytest.raises(JsonPointerError):
            resolve_pointer({}, "invalid")

    def test_escape_tilde(self):
        # RFC 6901: ~0 → ~, ~1 → /
        data = {"a/b": {"c~d": 42}}
        assert resolve_pointer(data, "/a~1b/c~0d") == 42


class TestSetPointer:
    def test_set_simple(self):
        data = {"a": 1}
        set_pointer(data, "/a", 99)
        assert data["a"] == 99

    def test_set_nested(self):
        data = {"a": {"b": 1}}
        set_pointer(data, "/a/b", 42)
        assert data["a"]["b"] == 42

    def test_set_creates_intermediate(self):
        data = {}
        set_pointer(data, "/a", {"b": 1})
        assert data["a"]["b"] == 1

    def test_set_array_element(self):
        data = {"items": [1, 2, 3]}
        set_pointer(data, "/items/1", 99)
        assert data["items"] == [1, 99, 3]

    def test_set_array_append(self):
        data = {"items": [1, 2]}
        set_pointer(data, "/items/2", 3)
        assert data["items"] == [1, 2, 3]

    def test_set_root_raises(self):
        with pytest.raises(JsonPointerError):
            set_pointer({}, "", {"new": "data"})


class TestDeletePointer:
    def test_delete_key(self):
        data = {"a": 1, "b": 2}
        removed = delete_pointer(data, "/a")
        assert removed == 1
        assert "a" not in data

    def test_delete_array_element(self):
        data = {"items": [10, 20, 30]}
        removed = delete_pointer(data, "/items/1")
        assert removed == 20
        assert data["items"] == [10, 30]

    def test_delete_root_raises(self):
        with pytest.raises(JsonPointerError):
            delete_pointer({}, "")


class TestDataModel:
    def test_initial_data(self):
        dm = DataModel({"user": {"name": "Alice"}})
        assert dm.get("/user/name") == "Alice"

    def test_get_root(self):
        dm = DataModel({"a": 1})
        assert dm.get() == {"a": 1}

    def test_set_tracks_changes(self):
        dm = DataModel({"a": 1})
        dm.set("/a", 2)
        assert dm.get("/a") == 2
        assert dm.has_changes()

    def test_flush_changes(self):
        dm = DataModel({"a": 1})
        dm.set("/a", 2)
        dm.set("/b", 3)
        changes = dm.flush_changes()
        assert len(changes) == 2
        assert changes[0] == ("/a", 2)
        assert changes[1] == ("/b", 3)
        assert not dm.has_changes()

    def test_delete_tracks_change(self):
        dm = DataModel({"a": 1, "b": 2})
        removed = dm.delete("/a")
        assert removed == 1
        assert dm.has_changes()
        changes = dm.flush_changes()
        assert changes[0] == ("/a", None)

    def test_replace(self):
        dm = DataModel({"old": True})
        dm.replace({"new": True})
        assert dm.data == {"new": True}
        assert dm.has_changes()

    def test_empty_model(self):
        dm = DataModel()
        assert dm.data == {}
        assert not dm.has_changes()
