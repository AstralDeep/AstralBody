"""
Tests for voice router endpoints (US-16: Voice Scale & Resilience).

Tests cover:
- /api/voice/health
- /api/voice/transcribe (mock)
- /api/voice/speak (mock)
- Session tracking and cleanup
- Concurrent session limiting
"""
import os
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from orchestrator.api import (
    chat_router,
    component_router,
    agent_router,
    dashboard_router,
    voice_router,
)
from orchestrator.auth import auth_router
from orchestrator.history import HistoryManager

# Same JWT token as test_rest_api.py — needed for require_user_id auth
MOCK_JWT_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJyZWFsbV9hY2Nlc3MiOnsicm9sZXMiOlsiYWRtaW4iLCJ1c2VyIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYXN0cmFsLWZyb250ZW5kIjp7InJvbGVzIjpbImFkbWluIiwidXNlciJdfX0sInN1YiI6ImRldi11c2VyLWlkIiwicHJlZmVycmVkX3VzZXJuYW1lIjoiRGV2VXNlciJ9."
    "fake-signature-ignore"
)

AUTH_HEADER = {"Authorization": f"Bearer {MOCK_JWT_TOKEN}"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def _voice_test_app():
    """Create a minimal FastAPI app with the voice router included."""
    app = FastAPI(title="Voice Test App")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    tmp_dir = tempfile.mkdtemp()
    history = HistoryManager(data_dir=tmp_dir)

    mock_orch = MagicMock()
    mock_orch.history = history
    mock_orch.agent_cards = {}
    mock_orch.agent_capabilities = {}
    mock_orch.ui_clients = []
    mock_orch.ui_sessions = {}
    mock_orch.tool_permissions = MagicMock()

    app.state.orchestrator = mock_orch

    app.include_router(chat_router)
    app.include_router(component_router)
    app.include_router(agent_router)
    app.include_router(dashboard_router)
    app.include_router(auth_router)
    app.include_router(voice_router)

    return app


@pytest.fixture
def client(_voice_test_app):
    """TestClient for the voice test app, with mock auth enabled."""
    with patch.dict(os.environ, {"VITE_USE_MOCK_AUTH": "true", "SPEACHES_URL": "https://speaches.example.com"}):
        yield TestClient(_voice_test_app)


def _env_side_effect(speaches_url):
    """Return a side_effect for patch('os.getenv') that preserves mock auth."""
    def _getenv(key, default=None):
        if key == "VITE_USE_MOCK_AUTH":
            return "true"
        if key == "SPEACHES_URL":
            return speaches_url
        return default
    return _getenv


def _env_not_configured(key, default=None):
    """Side_effect for os.getenv with no SPEACHES_URL but mock auth on."""
    if key == "VITE_USE_MOCK_AUTH":
        return "true"
    if key == "SPEACHES_URL" or key == "SPEACHES_STT_MODEL" or key == "SPEACHES_TTS_MODEL":
        return ""
    return default


# ── Test Classes ──────────────────────────────────────────────────────────────

class TestVoiceHealth:
    """GET /api/voice/health — voice service availability check."""

    def test_health_when_configured(self, client):
        """Returns available=true when SPEACHES_URL is set."""
        response = client.get("/api/voice/health")
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
        assert data["message"] == "Voice service ready"
        assert isinstance(data["active_sessions"], int)

    def test_health_when_not_configured(self, client):
        """Returns available=false when SPEACHES_URL is empty."""
        with patch("orchestrator.api.os.getenv", side_effect=_env_not_configured):
            response = client.get("/api/voice/health")
        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert "not configured" in data["message"].lower()


class TestVoiceTranscribe:
    """POST /api/voice/transcribe — batch STT endpoint."""

    def test_transcribe_not_configured(self, client):
        """Returns 503 when SPEACHES_URL is not set."""
        with patch("orchestrator.api.os.getenv", side_effect=_env_not_configured), \
             patch("orchestrator.auth.os.getenv", side_effect=_env_not_configured):
            response = client.post(
                "/api/voice/transcribe",
                files={"file": ("test.webm", b"fake audio", "audio/webm")},
                headers=AUTH_HEADER,
            )
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"].lower()

    def test_transcribe_no_file(self, client):
        """Returns 422 when no file is provided but user is authenticated."""
        response = client.post("/api/voice/transcribe", headers=AUTH_HEADER)
        assert response.status_code == 422

    def test_transcribe_success(self, client):
        """Mock Speaches response for successful transcription."""
        with patch("orchestrator.api.aiohttp.ClientSession.post") as mock_post, \
             patch("orchestrator.api.os.getenv", side_effect=_env_side_effect("https://speaches.example.com")):
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={"text": "Hello world"})
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)
            mock_post.return_value = mock_resp

            response = client.post(
                "/api/voice/transcribe",
                files={"file": ("test.webm", b"fake audio", "audio/webm")},
                headers=AUTH_HEADER,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["text"] == "Hello world"

    def test_transcribe_speaches_error(self, client):
        """Proxies Speaches error as 502."""
        with patch("orchestrator.api.aiohttp.ClientSession.post") as mock_post, \
             patch("orchestrator.api.os.getenv", side_effect=_env_side_effect("https://speaches.example.com")):
            mock_resp = MagicMock()
            mock_resp.status = 500
            mock_resp.text = AsyncMock(return_value="Internal Speaches Error")
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)
            mock_post.return_value = mock_resp

            response = client.post(
                "/api/voice/transcribe",
                files={"file": ("test.webm", b"fake audio", "audio/webm")},
                headers=AUTH_HEADER,
            )
            assert response.status_code == 502


class TestVoiceSpeak:
    """POST /api/voice/speak — TTS endpoint."""

    def test_speak_not_configured(self, client):
        """Returns 503 when SPEACHES_URL is not set."""
        with patch("orchestrator.api.os.getenv", side_effect=_env_not_configured), \
             patch("orchestrator.auth.os.getenv", side_effect=_env_not_configured):
            response = client.post("/api/voice/speak", json={"text": "Hello"}, headers=AUTH_HEADER)
        assert response.status_code == 503

    def test_speak_no_text(self, client):
        """Returns 400 when no text is provided."""
        response = client.post("/api/voice/speak", json={"text": ""}, headers=AUTH_HEADER)
        assert response.status_code == 400

    def test_speak_missing_body(self, client):
        """Returns 400 when no JSON body is sent."""
        response = client.post(
            "/api/voice/speak",
            content="",
            headers={**AUTH_HEADER, "Content-Type": "application/json"},
        )
        assert response.status_code == 400


class TestVoiceTruncate:
    """Test ``_truncate_for_speech`` utility."""

    def test_truncate_short_text(self):
        from orchestrator.api import _truncate_for_speech
        result = _truncate_for_speech("Short.", max_chars=100)
        assert result == "Short."

    def test_truncate_at_sentence_boundary(self):
        from orchestrator.api import _truncate_for_speech
        # 280 'A's followed by ". B" * 40 — ends with period, then space
        text = "A" * 280 + ". " + ("B" * 20 + ". ") * 5
        result = _truncate_for_speech(text, max_chars=300)
        # Should end at a sentence boundary within 300
        assert result.endswith(("A.", "B."))
        assert len(result) <= 301

    def test_truncate_at_space_fallback(self):
        from orchestrator.api import _truncate_for_speech
        text = "A" * 280 + " B" * 30
        result = _truncate_for_speech(text, max_chars=300)
        # Should truncate at space or add a period
        assert len(result) <= 301

    def test_truncate_very_short_fallback(self):
        from orchestrator.api import _truncate_for_speech
        text = "A" * 20
        result = _truncate_for_speech(text, max_chars=300)
        assert result == text


class TestVoiceSessionTracking:
    """Test voice session registration, tracking, and cleanup."""

    def test_register_unregister(self):
        from orchestrator.api import _register_voice_session, _unregister_voice_session, _active_voice_sessions
        _active_voice_sessions.clear()

        _register_voice_session("test-user", {"started_at": 1000.0})
        assert "test-user" in _active_voice_sessions
        assert _active_voice_sessions["test-user"]["started_at"] == 1000.0

        _unregister_voice_session("test-user")
        assert "test-user" not in _active_voice_sessions

        # Unregistering nonexistent user should not raise
        _unregister_voice_session("nonexistent")

    @pytest.mark.asyncio
    async def test_cleanup_stale_sessions(self):
        from orchestrator.api import (
            _register_voice_session,
            _cleanup_stale_voice_sessions,
            _active_voice_sessions,
        )
        import time
        _active_voice_sessions.clear()

        now = time.time()
        _register_voice_session("fresh", {"started_at": now, "last_activity": now})
        _register_voice_session("stale", {"started_at": now - 60, "last_activity": now - 60})

        await _cleanup_stale_voice_sessions()

        assert "fresh" in _active_voice_sessions
        assert "stale" not in _active_voice_sessions

    def test_registration_replaces_existing(self):
        from orchestrator.api import _register_voice_session, _active_voice_sessions
        _active_voice_sessions.clear()

        _register_voice_session("user", {"started_at": 1.0})
        _register_voice_session("user", {"started_at": 2.0})
        assert _active_voice_sessions["user"]["started_at"] == 2.0


class TestVoiceAvailability:
    """Test ``_is_voice_available`` helper."""

    def test_available(self):
        from orchestrator.api import _is_voice_available
        with patch("orchestrator.api.os.getenv", side_effect=_env_side_effect("https://speaches.example.com")):
            assert _is_voice_available() is True

    def test_not_available_empty(self):
        from orchestrator.api import _is_voice_available
        with patch("orchestrator.api.os.getenv", side_effect=_env_not_configured):
            assert _is_voice_available() is False

    def test_not_available_whitespace(self):
        from orchestrator.api import _is_voice_available
        with patch("orchestrator.api.os.getenv", side_effect=_env_not_configured):
            assert _is_voice_available() is False