"""Feature 043 — surface components() builders (US1 render).

DB-free: each surface's components() returns valid astralprims dicts using only
renderable types; actions bind to the existing chrome_* handlers; admin/audience
filtering matches render(). The web render() HTML path is untouched (D6).
"""
import asyncio
import types

from webrender.chrome.surfaces import collect_handlers
from webrender.renderer import allowed_primitive_types

ALLOWED = set(allowed_primitive_types()) | {"color_picker", "theme_apply"}


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _flat(components):
    """All component dicts, recursing into children/content/tabs."""
    out = []

    def walk(c):
        if not isinstance(c, dict):
            return
        out.append(c)
        for k in (c.get("children") or c.get("content") or []):
            walk(k)
        for t in (c.get("tabs") or []):
            for k in (t.get("content") or []):
                walk(k)
    for c in components:
        walk(c)
    return out


def _types(components):
    return [c["type"] for c in _flat(components) if "type" in c]


def _actions(components):
    acts = []
    for c in _flat(components):
        if c.get("action"):
            acts.append(c["action"])
        if c.get("submit_action"):
            acts.append(c["submit_action"])
        for a in (c.get("actions") or []):
            if isinstance(a, dict) and a.get("action"):
                acts.append(a["action"])
    return acts


class _PrefsDB:
    def __init__(self, prefs=None):
        self._p = prefs or {}

    def get_user_preferences(self, user_id):
        return dict(self._p)


def _orch(prefs=None):
    return types.SimpleNamespace(history=types.SimpleNamespace(db=_PrefsDB(prefs)))


# --- theme (T020) ------------------------------------------------------------

def test_theme_components_valid_and_actionable():
    from webrender.chrome.surfaces import theme
    comps = run(theme.components(_orch(), "u1", ["user"], {}))
    assert set(_types(comps)) <= ALLOWED
    assert _types(comps).count("color_picker") == 7
    assert "chrome_theme_preset" in _actions(comps)
    assert "chrome_theme_preset" in collect_handlers()  # resolves to a real handler


def test_theme_components_marks_active_preset():
    from webrender.chrome.surfaces import theme
    comps = run(theme.components(_orch({"theme": {"preset": "ocean"}}), "u1", ["user"], {}))
    labels = [c.get("label") for c in _flat(comps)]
    assert "Applied" in labels  # the ocean preset card is marked active


# --- guide (T019) ------------------------------------------------------------

def test_guide_components_valid_with_toc_and_body():
    from webrender.chrome.surfaces import guide
    comps = run(guide.components(_orch(), "u1", ["user"], {}))
    assert set(_types(comps)) <= ALLOWED
    assert "chrome_open" in _actions(comps)          # TOC navigation
    assert "text" in _types(comps)                    # section body rendered
    # no HTML leaked into a text node
    assert not any("<" in (c.get("content") or "") for c in _flat(comps) if c.get("type") == "text")


def test_guide_admin_section_filtered_for_non_admin():
    from webrender.chrome.surfaces import guide

    def toc_count(comps):
        return len([c for c in _flat(comps) if c.get("action") == "chrome_open"])
    non_admin = run(guide.components(_orch(), "u1", ["user"], {}))
    admin = run(guide.components(_orch(), "a1", ["admin"], {}))
    assert toc_count(admin) > toc_count(non_admin)   # admin sees the extra admin section


# --- llm (T022) --------------------------------------------------------------

def test_llm_components_form_multi_action():
    from webrender.chrome.surfaces import llm
    orch = types.SimpleNamespace(_session_llm_creds=None, ui_sessions={})
    comps = run(llm.components(orch, "u1", ["user"], {}))
    assert set(_types(comps)) <= ALLOWED
    forms = [c for c in _flat(comps) if c.get("type") == "param_picker"]
    assert len(forms) == 1
    acts = [a["action"] for a in forms[0]["actions"]]
    assert acts == ["chrome_llm_models", "chrome_llm_test", "chrome_llm_save"]
    kinds = {f["name"]: f["kind"] for f in forms[0]["fields"]}
    assert kinds["api_key"] == "password"           # write-only key
    handlers = collect_handlers()
    for a in ("chrome_llm_models", "chrome_llm_test", "chrome_llm_save", "chrome_llm_clear"):
        assert a in handlers


# --- personalization (T023) --------------------------------------------------

class _PznRepo:
    def get_profile(self, user_id):
        return {"profession": "researcher", "goals": ["ship"],
                "personality": {"notes": "concise"}, "dreaming_enabled": True}

    def list_memory(self, user_id):
        return [{"id": "m1", "category": "fact", "value": "likes tea", "created_at": 0}]

    def list_sweeps(self, user_id):
        return []


class _TP:
    _tool_scope_map = {"weather-1": {}}

    def get_tool_scope_map(self, agent_id):
        return {"get_forecast": "weather:read"}

    def is_tool_allowed(self, u, a, t):
        return True

    def is_scope_enabled(self, u, a, s):
        return True


def _porch():
    return types.SimpleNamespace(
        personalization_service=types.SimpleNamespace(repo=_PznRepo()),
        tool_permissions=_TP(),
    )


def test_personalization_soul_tab_and_bar():
    from webrender.chrome.surfaces import personalization
    comps = run(personalization.components(_porch(), "u1", ["user"], {"tab": "soul"}))
    assert set(_types(comps)) <= ALLOWED
    # 5 tab-bar buttons re-open the surface on a tab
    tab_opens = [c for c in _flat(comps)
                 if c.get("action") == "chrome_open"
                 and (c.get("payload") or {}).get("surface") == "personalization"]
    assert len(tab_opens) == 5
    assert "chrome_profile_save" in _actions(comps)
    assert "chrome_profile_save" in collect_handlers()


def test_personalization_skills_and_dreaming_actions():
    from webrender.chrome.surfaces import personalization
    skills = run(personalization.components(_porch(), "u1", ["user"], {"tab": "skills"}))
    assert "chrome_skill_toggle" in _actions(skills)
    dreaming = run(personalization.components(_porch(), "u1", ["user"], {"tab": "dreaming"}))
    assert {"chrome_dreaming_toggle", "chrome_dreaming_trigger"} <= set(_actions(dreaming))
    handlers = collect_handlers()
    for a in ("chrome_skill_toggle", "chrome_dreaming_toggle", "chrome_dreaming_trigger"):
        assert a in handlers


def test_personalization_memory_actions_and_types():
    from webrender.chrome.surfaces import personalization
    comps = run(personalization.components(_porch(), "u1", ["user"], {"tab": "memory"}))
    assert set(_types(comps)) <= ALLOWED
    assert {"chrome_memory_update", "chrome_memory_delete"} <= set(_actions(comps))
