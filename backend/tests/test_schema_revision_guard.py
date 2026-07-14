"""SCHEMA_REVISION source-hash guard for shared/database.py (feature 052).

Editing _init_db, _apply_full_schema, or any _migrate_*/_cleanup_* helper
without bumping SCHEMA_REVISION would leave already-marked databases on
the schema fast path with the new migration silently never applied. This
test pins a sha256 of that source region beside the expected revision, so
any schema-code change fails CI until SCHEMA_REVISION is bumped and both
constants below are updated in the same commit. No database required.
"""
from __future__ import annotations

import hashlib
import inspect

import pytest

try:
    from shared.database import Database, SCHEMA_REVISION
except Exception:  # pragma: no cover - import guard
    Database = None  # type: ignore
    SCHEMA_REVISION = None  # type: ignore

EXPECTED_SCHEMA_REVISION = "055.002"
EXPECTED_SOURCE_SHA256 = (
    "3e495e6b11917b3b4440f4e29e79b329862ab4690fafc8c1a52d120475fb8933"
)

_BUMP_INSTRUCTIONS = (
    "You changed the schema-initialization source in backend/shared/database.py "
    "(_init_db, _apply_full_schema, or a _migrate_*/_cleanup_* helper). "
    "Bump SCHEMA_REVISION in backend/shared/database.py so deployed databases "
    "re-run the full migration set, then update EXPECTED_SCHEMA_REVISION and "
    "EXPECTED_SOURCE_SHA256 in backend/tests/test_schema_revision_guard.py "
    "to the new values (print the hash via "
    "tests.test_schema_revision_guard.schema_source_sha256())."
)


def _guarded_method_names() -> list:
    """Names of the schema-shaping methods covered by the hash."""
    names = ["_init_db", "_apply_full_schema"]
    names.extend(
        sorted(
            name
            for name in dir(Database)
            if name.startswith(("_migrate_", "_cleanup_"))
        )
    )
    return names


def schema_source_sha256() -> str:
    """sha256 over the concatenated source of every guarded method."""
    source = "\n".join(
        inspect.getsource(getattr(Database, name))
        for name in _guarded_method_names()
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _skip_unless_importable():
    if Database is None:
        pytest.skip("shared.database unavailable")


def test_schema_revision_matches_expected():
    _skip_unless_importable()
    assert SCHEMA_REVISION == EXPECTED_SCHEMA_REVISION, (
        f"SCHEMA_REVISION is {SCHEMA_REVISION!r} but this guard expects "
        f"{EXPECTED_SCHEMA_REVISION!r}. {_BUMP_INSTRUCTIONS}"
    )


def test_init_db_source_hash_requires_revision_bump():
    _skip_unless_importable()
    actual = schema_source_sha256()
    assert actual == EXPECTED_SOURCE_SHA256, (
        f"schema source hash changed: {actual} != {EXPECTED_SOURCE_SHA256}. "
        f"{_BUMP_INSTRUCTIONS}"
    )


def test_guard_covers_all_migration_helpers():
    _skip_unless_importable()
    names = _guarded_method_names()
    assert "_init_db" in names
    assert "_apply_full_schema" in names
    assert "_migrate_backfill_tool_kinds_052" in names
    assert any(name.startswith("_cleanup_") for name in names)
