"""Feature 027 — T013: LLM settings surface (key ``llm``).

Structural/behavioral tests on a minimal fake orchestrator — no Postgres,
no network. The per-session credential store is the REAL
``SessionCredentialStore`` (pure in-memory); the list-models / test
probes are monkeypatched at their ``llm_config.api`` definitions (the
surface lazy-imports them per call, matching the orchestrator pattern).
"""
import asyncio
from types import SimpleNamespace

from llm_config.api import ListModelsResponse, TestConnectionResponse
from llm_config.session_creds import SessionCredentialStore
from webrender.chrome.surfaces import get_surface
from webrender.chrome.surfaces import llm as llm_surface

SECRET = "sk-supersecret-test-key-123456789012345"


class FakeRecorder:
    """Collects audit events (stand-in for ``orch.audit_recorder``)."""

    def __init__(self):
        self.events = []

    async def record(self, event):
        self.events.append(event)


class FakeWS:
    """Identity-only websocket stand-in (the store keys by ``id(ws)``)."""


def make_orch():
    """Minimal orch exposing exactly what the surface touches."""
    sent = []

    async def safe_send(websocket, text):
        sent.append((websocket, text))

    orch = SimpleNamespace(
        ui_sessions={},
        _session_llm_creds=SessionCredentialStore(),
        audit_recorder=FakeRecorder(),
        _safe_send=safe_send,
    )
    orch.sent = sent
    return orch


def register(orch, ws, sub="u1"):
    orch.ui_sessions[ws] = {"sub": sub, "preferred_username": f"{sub}@example"}


def run(coro):
    return asyncio.run(coro)


def render(orch, user_id="u1", roles=None, params=None):
    return run(llm_surface.render(orch, user_id, roles or ["user"], params or {}))


# ---------------------------------------------------------------------------
# Registry / module contract
# ---------------------------------------------------------------------------

def test_registry_resolves_llm_surface():
    mod = get_surface("llm")
    assert mod is llm_surface
    assert mod.TITLE == "LLM settings"
    assert not getattr(mod, "ADMIN_ONLY", False)


def test_handlers_cover_contract_actions():
    assert set(llm_surface.HANDLERS) == {
        "chrome_llm_models", "chrome_llm_test", "chrome_llm_save", "chrome_llm_clear",
    }
    for fn in llm_surface.HANDLERS.values():
        assert asyncio.iscoroutinefunction(fn)


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def test_render_empty_state_form_structure():
    html = render(make_orch())
    assert "data-ui-form" in html
    assert 'name="base_url"' in html
    assert 'type="password"' in html and 'name="api_key"' in html
    assert 'name="model"' in html and "<select" not in html
    for action in ("chrome_llm_models", "chrome_llm_test", "chrome_llm_save"):
        assert f'data-ui-action="{action}"' in html
        assert 'data-ui-collect="true"' in html
    # No saved creds -> no clear affordance, generic key placeholder.
    assert "chrome_llm_clear" not in html
    assert "sk-..." in html


def test_render_saved_state_shows_placeholder_never_echoes_key():
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws, sub="u1")
    orch._session_llm_creds.set(id(ws), SECRET, "https://api.example.com/v1", "gpt-x")
    html = render(orch, user_id="u1")
    assert "leave blank to keep" in html
    assert SECRET not in html  # write-only display — the key is NEVER echoed
    assert 'value="https://api.example.com/v1"' in html
    assert 'value="gpt-x"' in html
    assert 'data-ui-action="chrome_llm_clear"' in html


def test_render_saved_state_is_per_user():
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws, sub="someone-else")
    orch._session_llm_creds.set(id(ws), SECRET, "https://api.example.com/v1", "gpt-x")
    html = render(orch, user_id="u1")
    assert "chrome_llm_clear" not in html
    assert "https://api.example.com/v1" not in html


def test_render_models_param_builds_escaped_select():
    html = render(make_orch(), params={"models": ["m-one", "<bad>"], "model": "m-one"})
    assert '<select name="model"' in html
    assert '<option value="m-one" selected>' in html
    assert "&lt;bad&gt;" in html and "<bad>" not in html


def test_render_preserves_submitted_values_from_params():
    html = render(make_orch(), params={"base_url": "https://x.test/v1", "model": "my-model"})
    assert 'value="https://x.test/v1"' in html
    assert 'value="my-model"' in html


# ---------------------------------------------------------------------------
# chrome_llm_save / chrome_llm_clear (session store + audit, ws-handler reuse)
# ---------------------------------------------------------------------------

def _payload(**fields):
    return {"fields": fields}


def test_save_persists_audits_and_acks():
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    result = run(llm_surface.HANDLERS["chrome_llm_save"](
        orch, ws, "u1", ["user"],
        _payload(base_url="https://api.example.com/v1/", api_key=SECRET, model="gpt-x"),
    ))
    surface, params, notice = result
    assert surface == "llm"
    creds = orch._session_llm_creds.get(id(ws))
    assert creds is not None and creds.api_key == SECRET
    assert creds.base_url == "https://api.example.com/v1"  # store rstrips '/'
    # Audit preserved (same path as WS llm_config_set).
    assert [e.action_type for e in orch.audit_recorder.events] == ["llm_config.created"]
    assert orch.audit_recorder.events[0].auth_principal == "u1@example"
    # llm_config_ack still sent over the live websocket.
    assert any("llm_config_ack" in text for sock, text in orch.sent if sock is ws)
    # Key never leaks into the re-render inputs.
    assert SECRET not in notice and SECRET not in str(params)
    assert "saved" in notice


def test_save_missing_fields_is_error_without_mutation():
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    surface, params, notice = run(llm_surface.HANDLERS["chrome_llm_save"](
        orch, ws, "u1", ["user"], _payload(base_url="https://x.test/v1", api_key="", model=""),
    ))
    assert surface == "llm"
    assert id(ws) not in orch._session_llm_creds
    assert orch.audit_recorder.events == []
    assert "astral-chrome-notice" in notice and "missing" in notice
    assert params["base_url"] == "https://x.test/v1"  # submitted values preserved


def test_save_blank_key_keeps_saved_key():
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    orch._session_llm_creds.set(id(ws), SECRET, "https://old.test/v1", "old-model")
    surface, _params, notice = run(llm_surface.HANDLERS["chrome_llm_save"](
        orch, ws, "u1", ["user"],
        _payload(base_url="https://new.test/v1", api_key="", model="new-model"),
    ))
    assert surface == "llm"
    creds = orch._session_llm_creds.get(id(ws))
    assert creds.api_key == SECRET and creds.model == "new-model"
    assert [e.action_type for e in orch.audit_recorder.events] == ["llm_config.updated"]
    assert "kept" in notice


def test_clear_drops_creds_and_audits():
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    orch._session_llm_creds.set(id(ws), SECRET, "https://x.test/v1", "m")
    surface, params, notice = run(llm_surface.HANDLERS["chrome_llm_clear"](
        orch, ws, "u1", ["user"], {},
    ))
    assert surface == "llm" and params == {}
    assert id(ws) not in orch._session_llm_creds
    assert [e.action_type for e in orch.audit_recorder.events] == ["llm_config.cleared"]
    assert "cleared" in notice


def test_clear_when_empty_is_quiet_noop():
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    _surface, _params, notice = run(llm_surface.HANDLERS["chrome_llm_clear"](
        orch, ws, "u1", ["user"], {},
    ))
    assert orch.audit_recorder.events == []  # no audit noise on empty clear
    assert "No session LLM credentials" in notice


# ---------------------------------------------------------------------------
# chrome_llm_models / chrome_llm_test (probe-internals reuse)
# ---------------------------------------------------------------------------

def test_models_success_rerenders_with_select(monkeypatch):
    calls = {}

    async def fake_list_models(*, body, request, user_id, user_payload):
        calls["base_url"] = body.base_url
        calls["api_key"] = body.api_key
        return ListModelsResponse(ok=True, models=["m-a", "m-b"], probed_at="t", latency_ms=5)

    monkeypatch.setattr("llm_config.api.list_models", fake_list_models)
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    surface, params, notice = run(llm_surface.HANDLERS["chrome_llm_models"](
        orch, ws, "u1", ["user"],
        _payload(base_url="https://x.test/v1", api_key=SECRET, model="m-b"),
    ))
    assert surface == "llm"
    assert calls == {"base_url": "https://x.test/v1", "api_key": SECRET}
    assert params["models"] == ["m-a", "m-b"] and params["model"] == "m-b"
    assert "Loaded 2 models" in notice
    html = render(orch, params=params)
    assert '<option value="m-b" selected>' in html


def test_models_failure_renders_error_class(monkeypatch):
    async def fake_list_models(**kwargs):
        return ListModelsResponse(
            ok=False, models=[], probed_at="t",
            error_class="transport_error", upstream_message="dns <fail>",
        )

    monkeypatch.setattr("llm_config.api.list_models", fake_list_models)
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    _surface, params, notice = run(llm_surface.HANDLERS["chrome_llm_models"](
        orch, ws, "u1", ["user"], _payload(base_url="https://x.test/v1", api_key=SECRET),
    ))
    assert "transport_error" in notice
    assert "&lt;fail&gt;" in notice and "<fail>" not in notice  # upstream text escaped
    assert "models" not in params


def test_models_invalid_base_url_skips_probe(monkeypatch):
    async def boom(**kwargs):
        raise AssertionError("probe must not run on invalid input")

    monkeypatch.setattr("llm_config.api.list_models", boom)
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    _surface, _params, notice = run(llm_surface.HANDLERS["chrome_llm_models"](
        orch, ws, "u1", ["user"], _payload(base_url="ftp://x.test", api_key=SECRET),
    ))
    assert "astral-chrome-notice" in notice and "base_url" in notice


def test_models_requires_key_when_none_saved():
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    _surface, _params, notice = run(llm_surface.HANDLERS["chrome_llm_models"](
        orch, ws, "u1", ["user"], _payload(base_url="https://x.test/v1", api_key=""),
    ))
    assert "required" in notice


def test_models_blank_key_uses_saved_session_key(monkeypatch):
    seen = {}

    async def fake_list_models(*, body, request, user_id, user_payload):
        seen["api_key"] = body.api_key
        return ListModelsResponse(ok=True, models=["m"], probed_at="t")

    monkeypatch.setattr("llm_config.api.list_models", fake_list_models)
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    orch._session_llm_creds.set(id(ws), SECRET, "https://x.test/v1", "m")
    run(llm_surface.HANDLERS["chrome_llm_models"](
        orch, ws, "u1", ["user"], _payload(base_url="https://x.test/v1", api_key=""),
    ))
    assert seen["api_key"] == SECRET


def test_test_success_renders_latency_verdict(monkeypatch):
    async def fake_test(*, body, request, user_id, user_payload):
        assert request.app.state.orchestrator is orch  # probe audit reaches the orch
        return TestConnectionResponse(ok=True, model=body.model, probed_at="t", latency_ms=123)

    monkeypatch.setattr("llm_config.api.test_connection", fake_test)
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    _surface, _params, notice = run(llm_surface.HANDLERS["chrome_llm_test"](
        orch, ws, "u1", ["user"],
        _payload(base_url="https://x.test/v1", api_key=SECRET, model="gpt-x"),
    ))
    assert "Connection OK" in notice and "gpt-x" in notice and "123 ms" in notice


def test_test_failure_renders_error_class_and_message(monkeypatch):
    async def fake_test(**kwargs):
        return TestConnectionResponse(
            ok=False, model="gpt-x", probed_at="t",
            error_class="auth_failed", upstream_message="401 <unauthorized>",
        )

    monkeypatch.setattr("llm_config.api.test_connection", fake_test)
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    _surface, params, notice = run(llm_surface.HANDLERS["chrome_llm_test"](
        orch, ws, "u1", ["user"],
        _payload(base_url="https://x.test/v1", api_key=SECRET, model="gpt-x"),
    ))
    assert "auth_failed" in notice
    assert "&lt;unauthorized&gt;" in notice and "<unauthorized>" not in notice
    assert params == {"base_url": "https://x.test/v1", "model": "gpt-x"}


def test_test_requires_all_fields():
    orch = make_orch()
    ws = FakeWS()
    register(orch, ws)
    _surface, _params, notice = run(llm_surface.HANDLERS["chrome_llm_test"](
        orch, ws, "u1", ["user"], _payload(base_url="https://x.test/v1", api_key=SECRET, model=""),
    ))
    assert "required" in notice
