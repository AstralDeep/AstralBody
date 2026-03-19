"""
A2UI Data Model — JSON Pointer (RFC 6901) binding and change tracking.

Provides resolve/set operations on a nested dict using JSON Pointer paths,
plus a DataModel wrapper that tracks mutations for efficient delta sync.
"""

from typing import Any, Dict, List, Optional, Tuple


class JsonPointerError(Exception):
    """Raised when a JSON Pointer path is invalid or cannot be resolved."""


def _parse_pointer(pointer: str) -> List[str]:
    """Parse a JSON Pointer string into a list of reference tokens."""
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise JsonPointerError(f"JSON Pointer must start with '/' or be empty: {pointer!r}")
    parts = pointer[1:].split("/")
    # Unescape ~1 → / and ~0 → ~  (order matters per RFC 6901)
    return [p.replace("~1", "/").replace("~0", "~") for p in parts]


def resolve_pointer(data: Any, pointer: str) -> Any:
    """
    Resolve a JSON Pointer (RFC 6901) against *data*.

    >>> resolve_pointer({"a": {"b": [1, 2, 3]}}, "/a/b/1")
    2
    >>> resolve_pointer({"a": 1}, "")
    {"a": 1}
    """
    tokens = _parse_pointer(pointer)
    current = data
    for token in tokens:
        if isinstance(current, dict):
            if token not in current:
                raise JsonPointerError(f"Key {token!r} not found at pointer {pointer!r}")
            current = current[token]
        elif isinstance(current, list):
            try:
                idx = int(token)
            except ValueError:
                raise JsonPointerError(
                    f"Expected array index, got {token!r} at pointer {pointer!r}"
                )
            if idx < 0 or idx >= len(current):
                raise JsonPointerError(
                    f"Array index {idx} out of range at pointer {pointer!r}"
                )
            current = current[idx]
        else:
            raise JsonPointerError(
                f"Cannot traverse into {type(current).__name__} at pointer {pointer!r}"
            )
    return current


def set_pointer(data: Any, pointer: str, value: Any) -> None:
    """
    Set a value at the location identified by *pointer* within *data*.

    Creates intermediate dicts as needed. For the root pointer (""), raises
    because you can't replace the root through a mutable reference.

    >>> d = {"a": {"b": 1}}
    >>> set_pointer(d, "/a/b", 42)
    >>> d
    {"a": {"b": 42}}
    """
    tokens = _parse_pointer(pointer)
    if not tokens:
        raise JsonPointerError("Cannot set the root pointer; replace the data model directly")

    current = data
    for token in tokens[:-1]:
        if isinstance(current, dict):
            if token not in current:
                current[token] = {}
            current = current[token]
        elif isinstance(current, list):
            try:
                idx = int(token)
            except ValueError:
                raise JsonPointerError(f"Expected array index, got {token!r}")
            current = current[idx]
        else:
            raise JsonPointerError(f"Cannot traverse into {type(current).__name__}")

    last = tokens[-1]
    if isinstance(current, dict):
        current[last] = value
    elif isinstance(current, list):
        try:
            idx = int(last)
        except ValueError:
            raise JsonPointerError(f"Expected array index, got {last!r}")
        if idx == len(current):
            current.append(value)
        elif 0 <= idx < len(current):
            current[idx] = value
        else:
            raise JsonPointerError(f"Array index {idx} out of range")
    else:
        raise JsonPointerError(f"Cannot set on {type(current).__name__}")


def delete_pointer(data: Any, pointer: str) -> Any:
    """
    Delete the value at *pointer* and return the deleted value.
    """
    tokens = _parse_pointer(pointer)
    if not tokens:
        raise JsonPointerError("Cannot delete the root pointer")

    current = data
    for token in tokens[:-1]:
        if isinstance(current, dict):
            current = current[token]
        elif isinstance(current, list):
            current = current[int(token)]
        else:
            raise JsonPointerError(f"Cannot traverse into {type(current).__name__}")

    last = tokens[-1]
    if isinstance(current, dict):
        return current.pop(last)
    elif isinstance(current, list):
        return current.pop(int(last))
    else:
        raise JsonPointerError(f"Cannot delete from {type(current).__name__}")


class DataModel:
    """
    Wraps a dict with change tracking for A2UI data model sync.

    Tracks which paths have been mutated since the last ``flush_changes()``
    so that only deltas need to be sent to clients.
    """

    def __init__(self, initial: Optional[Dict[str, Any]] = None):
        self._data: Dict[str, Any] = initial or {}
        self._changes: List[Tuple[str, Any]] = []  # (pointer, new_value) pairs

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    def get(self, pointer: str = "") -> Any:
        """Resolve a JSON Pointer against the data model."""
        if pointer == "":
            return self._data
        return resolve_pointer(self._data, pointer)

    def set(self, pointer: str, value: Any) -> None:
        """Set a value and record the change."""
        set_pointer(self._data, pointer, value)
        self._changes.append((pointer, value))

    def delete(self, pointer: str) -> Any:
        """Delete a value and record the change."""
        removed = delete_pointer(self._data, pointer)
        self._changes.append((pointer, None))
        return removed

    def has_changes(self) -> bool:
        return len(self._changes) > 0

    def flush_changes(self) -> List[Tuple[str, Any]]:
        """Return accumulated changes and clear the buffer."""
        changes = self._changes[:]
        self._changes.clear()
        return changes

    def replace(self, data: Dict[str, Any]) -> None:
        """Replace the entire data model."""
        self._data = data
        self._changes.append(("", data))
