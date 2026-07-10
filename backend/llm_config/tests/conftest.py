"""Shared fixtures for the llm_config test suite (feature 054-byo-llm-setup).

The persisted store (``UserLLMConfigStore``) only touches its DB handle via
``execute``/``fetch_one`` with ``?`` placeholders, so these tests run against
a lightweight in-memory fake instead of postgres. Rows are RealDictCursor-
style dicts, matching what ``shared/database.py`` returns.

``CREDENTIAL_ENCRYPTION_KEY`` is monkeypatched to a per-test generated
Fernet key so no dev key file is ever written by the suite.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from llm_config.user_store import UserLLMConfigStore


class FakeDB:
    """Minimal stand-in for the shared Database facade.

    Implements exactly the surface ``UserLLMConfigStore`` uses:
    ``execute(sql, params=())`` and ``fetch_one(sql, params=())`` with
    ``?`` placeholders, returning dict rows.
    """

    def __init__(self) -> None:
        self.users: Dict[str, Dict[str, Any]] = {}
        self.system: Optional[Dict[str, Any]] = None

    def execute(self, sql: str, params: tuple = ()) -> None:
        s = " ".join(sql.split()).lower()
        if s.startswith("insert into user_llm_config"):
            user_id, provider, base_url, model, api_key_enc = params
            self.users[user_id] = {
                "provider": provider,
                "base_url": base_url,
                "model": model,
                "api_key_enc": api_key_enc,
                "updated_at": time.time(),
            }
        elif s.startswith("insert into system_llm_config"):
            provider, base_url, model, api_key_enc, updated_by = params
            self.system = {
                "provider": provider,
                "base_url": base_url,
                "model": model,
                "api_key_enc": api_key_enc,
                "updated_by": updated_by,
                "updated_at": time.time(),
            }
        elif s.startswith("delete from user_llm_config"):
            self.users.pop(params[0], None)
        elif s.startswith("delete from system_llm_config"):
            self.system = None
        else:  # pragma: no cover — guards against silent SQL drift
            raise AssertionError(f"FakeDB got unexpected execute SQL: {sql}")

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        s = " ".join(sql.split()).lower()
        if "from user_llm_config" in s:
            row = self.users.get(params[0])
            if row is None:
                return None
            if s.startswith("select 1"):
                return {"present": 1}
            return dict(row)
        if "from system_llm_config" in s:
            if self.system is None:
                return None
            if s.startswith("select 1"):
                return {"present": 1}
            return dict(self.system)
        raise AssertionError(  # pragma: no cover
            f"FakeDB got unexpected fetch_one SQL: {sql}")


@pytest.fixture
def fernet_key(monkeypatch) -> str:
    """Set CREDENTIAL_ENCRYPTION_KEY to a fresh Fernet key (no key file)."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", key)
    return key


@pytest.fixture
def fake_db() -> FakeDB:
    return FakeDB()


@pytest.fixture
def store(fernet_key, fake_db) -> UserLLMConfigStore:
    return UserLLMConfigStore(fake_db)


@pytest.fixture
def fake_recorder():
    rec = MagicMock()
    rec.record = AsyncMock()
    return rec


@pytest.fixture
def safe_send():
    return AsyncMock()
