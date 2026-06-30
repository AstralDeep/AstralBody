"""Feature 028 — Constitution-III source-level contract tests for the web client.

The server-driven UI client (``backend/webrender/static/client.js``) has no
build step and no JS test runner, so its 028 auth/workspace obligations are
pinned here as pure-text assertions over the shipped sources:

* ``client.js``   — auth_required recovery, gotoLogin/next preservation,
  component-identity injection on delegated actions, timeline read-only
  guards, resumed semantics, chat_deleted handling, reconnect re-auth.
* ``shell.html``  — the bootstrap script must inject both server placeholders.
* ``web_auth.py`` — FR-010: no local credential UI ("Remember me", biometric,
  WebAuthn) anywhere in the error/no-access pages or the client surfaces.

No JS runtime is involved; helpers below slice ``switch`` cases and function
bodies textually (safe here: none of the inspected functions contain string
literals with unbalanced braces).
"""
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
CLIENT_JS = BACKEND / "webrender" / "static" / "client.js"
SHELL_HTML = BACKEND / "webrender" / "templates" / "shell.html"
WEB_AUTH_PY = BACKEND / "orchestrator" / "web_auth.py"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    src = path.read_text(encoding="utf-8")
    assert len(src) > 500, f"{path} unexpectedly small — wrong file?"
    return src


def _norm(s: str) -> str:
    """Collapse all whitespace so multi-line statements match as substrings."""
    return re.sub(r"\s+", " ", s)


def _case_block(src: str, name: str) -> str:
    """Slice one ``case "<name>":`` block out of the onMessage switch."""
    marker = f'case "{name}":'
    assert marker in src, f"client.js has no {marker} handler"
    start = src.index(marker)
    nxt = src.find('case "', start + len(marker))
    assert nxt != -1, f"could not bound the {name} case"
    return src[start:nxt]


def _js_function(src: str, name: str) -> str:
    """Extract ``function <name>(...) {...}`` by brace counting."""
    sig = f"function {name}("
    assert sig in src, f"client.js has no function {name}"
    start = src.index(sig)
    depth = 0
    for i in range(src.index("{", start), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    raise AssertionError(f"unbalanced braces extracting function {name}")


def _py_function(src: str, name: str) -> str:
    """Extract a top-level ``def <name>`` body (up to the next top-level def)."""
    sig = f"def {name}("
    assert sig in src, f"web_auth.py has no {sig}"
    start = src.index(sig)
    nxt = re.compile(r"\n(?:def |async def |class |@)").search(src, start + 1)
    return src[start : nxt.start()] if nxt else src[start:]


@pytest.fixture(scope="module")
def client_js() -> str:
    return _read(CLIENT_JS)


@pytest.fixture(scope="module")
def shell_html() -> str:
    return _read(SHELL_HTML)


@pytest.fixture(scope="module")
def web_auth_src() -> str:
    return _read(WEB_AUTH_PY)


# ---------------------------------------------------------------------------
# (1) no 'dev-token' literal in executable code
# ---------------------------------------------------------------------------

def test_no_dev_token_literal_in_executable_code(client_js):
    """028: the hardcoded dev-token fallback is gone. The phrase survives in
    one explanatory comment ("The 'dev-token' literal fallback is gone"), so
    the contract is: never outside a full-line comment, and never as a JS
    string literal."""
    for lineno, line in enumerate(client_js.splitlines(), 1):
        if "dev-token" in line:
            assert line.lstrip().startswith("//"), (
                f"client.js:{lineno} carries 'dev-token' outside a comment: {line.strip()!r}"
            )
    assert '"dev-token"' not in client_js, "dev-token JS string literal resurfaced"
    # the old fallback shape specifically must not return in any quoting style
    assert not re.search(r"""\|\|\s*['"]dev-token['"]""", client_js)


# ---------------------------------------------------------------------------
# (2) auth_required → refreshToken, falling back to gotoLogin
# ---------------------------------------------------------------------------

def test_auth_required_case_refreshes_then_falls_back_to_login(client_js):
    block = _norm(_case_block(client_js, "auth_required"))
    assert "refreshToken(" in block, "auth_required must try a silent session refresh"
    assert "gotoLogin()" in block, "auth_required must fall back to interactive login"
    # one silent retry per connection: the redirect sits on the already-retried branch
    assert "authRetried" in block
    assert "else { gotoLogin(); }" in block
    assert block.index("refreshToken(") < block.index("gotoLogin()")
    # the successful refresh re-registers with the fresh token
    assert 'type: "register_ui"' in block and "token: token" in block


# ---------------------------------------------------------------------------
# (3) gotoLogin preserves the destination via encodeURIComponent
# ---------------------------------------------------------------------------

def test_gotologin_builds_next_from_current_location(client_js):
    fn = _norm(_js_function(client_js, "gotoLogin"))
    assert "encodeURIComponent(location.pathname + location.search)" in fn
    assert '"/auth/login?next=" + next' in fn
    assert "location.href" in fn


# ---------------------------------------------------------------------------
# (4) delegated .astral-action clicks inject the component identity (FR-034)
# ---------------------------------------------------------------------------

def _astral_action_handler(client_js: str) -> str:
    """Slice the delegated click handler from its .astral-action lookup to the
    next listener registration."""
    start = client_js.index('closest(".astral-action")')
    end = client_js.index("document.addEventListener", start)
    return client_js[start:end]


def test_astral_action_click_injects_component_identity(client_js):
    block = _norm(_astral_action_handler(client_js))
    assert 'closest("[data-component-id]")' in block, (
        "action clicks must resolve their enclosing workspace component"
    )
    assert 'payload.component_id = compHost.getAttribute("data-component-id")' in block
    # an explicit payload.component_id from the server wins over the DOM host
    assert "!payload.component_id" in block
    # chat context rides along too
    assert "payload.chat_id = activeChatId" in block


# ---------------------------------------------------------------------------
# (5) timelineMode guards — deferred upserts + inert canvas actions
# ---------------------------------------------------------------------------

def test_apply_upsert_defers_dom_in_timeline_mode(client_js):
    fn = _norm(_js_function(client_js, "applyUpsert"))
    guard = fn.index("if (timelineMode)")
    indicator = fn.index("Live workspace updated")
    assert "Back to live" in fn, "indicator must point users back to the live view"
    ret = fn.index("return;", indicator)
    ops = fn.index("msg.ops")
    # guard → indicator → early return, all BEFORE any op is applied to the DOM
    assert guard < indicator < ret < ops, (
        "applyUpsert must show the live-has-moved-on indicator and bail before "
        "touching the DOM while viewing history"
    )
    assert "setStatus(" in fn[guard:ret]


def test_canvas_actions_inert_in_timeline_mode(client_js):
    block = _norm(_astral_action_handler(client_js))
    guard = block.index("if (timelineMode && compHost && act")
    # chrome actions stay live; component actions are read-only in history view
    assert 'act.indexOf("chrome_") !== 0' in block
    assert 'setStatus("Read-only history view' in block
    ret = block.index("return;", guard)
    dispatch = block.index("if (act) action(act, payload)")
    assert guard < ret < dispatch, (
        "the timeline guard must return before dispatching the ui_event"
    )


def test_pagination_inert_in_timeline_mode(client_js):
    # paginate + paginateSize each carry their own guard; with the action
    # handler that is three occurrences of the read-only indicator string
    assert client_js.count("Read-only history view") >= 3
    for name in ("paginate", "paginateSize"):
        fn = _norm(_js_function(client_js, name))
        assert "if (timelineMode)" in fn, f"{name} lacks the timeline guard"
        assert "Read-only history view" in fn
        assert fn.index("Read-only history view") < fn.index('action("table_paginate"')
        # FR-038: pagination routes through component_action with the table identity
        assert "component_id: paginateComponentId(el)" in fn


# ---------------------------------------------------------------------------
# (6) register_ui resumed semantics (FR-011)
# ---------------------------------------------------------------------------

def test_register_ui_resumed_semantics(client_js):
    assert "var serverResumed = (window.__ASTRAL_RESUMED__ !== false);" in client_js, (
        "serverResumed must derive from the shell-injected window.__ASTRAL_RESUMED__"
    )
    fn = _norm(_js_function(client_js, "connect"))
    assert "resumed: firstConnect ? serverResumed : true" in fn, (
        "only the first register_ui of a page load may report resumed=false"
    )
    # firstConnect flips after the initial registration, so reconnects resume
    assert fn.index("resumed: firstConnect ? serverResumed : true") < fn.index(
        "firstConnect = false;"
    )


# ---------------------------------------------------------------------------
# (7) chat_deleted clears the canvas when it targets the active chat
# ---------------------------------------------------------------------------

def test_chat_deleted_clears_canvas_when_active(client_js):
    block = _norm(_case_block(client_js, "chat_deleted"))
    assert "data.chat_id === activeChatId" in block, (
        "chat_deleted must only act on the currently active chat"
    )
    assert "activeChatId = null" in block
    assert 'setHTML(canvas, "")' in block, "deleting the active chat must clear the canvas"
    assert "timelineMode = false" in block
    assert "This chat was deleted." in block


# ---------------------------------------------------------------------------
# (8) reconnect re-fetches /auth/session before registering (D4)
# ---------------------------------------------------------------------------

def test_reconnect_refetches_session_before_register(client_js):
    fn = _norm(_js_function(client_js, "connect"))
    onclose = fn[fn.index("ws.onclose") :]
    # pinned current behavior: bounded retries, each reconnect wrapped in a
    # refreshToken(false, …) → connect() chain (no redirect from the retry path)
    assert "refreshToken(false, function () { connect(); })" in onclose
    assert "attempts <= 10" in onclose
    # refreshToken IS the /auth/session round-trip (server refreshes silently)
    rt = _norm(_js_function(client_js, "refreshToken"))
    assert 'fetch(API_URL + "/auth/session"' in rt
    assert '"same-origin"' in rt
    assert "j.authenticated && j.access_token" in rt
    # the fresh token is what the next register_ui sends
    assert "token = j.access_token" in rt


# ---------------------------------------------------------------------------
# (9) shell.html bootstrap placeholders
# ---------------------------------------------------------------------------

def test_shell_injects_token_and_resumed_placeholders(shell_html):
    assert 'window.__ASTRAL_TOKEN__ = "%%ASTRAL_TOKEN%%"' in shell_html
    assert "window.__ASTRAL_RESUMED__ = %%ASTRAL_RESUMED%%" in shell_html
    # both live in ONE inline bootstrap script…
    m = re.search(r"<script>([^<]*__ASTRAL_TOKEN__[^<]*)</script>", shell_html)
    assert m is not None, "no inline bootstrap script found"
    assert "__ASTRAL_RESUMED__" in m.group(1)
    # …which precedes the client so the globals exist before client.js runs.
    # The client.js URL now carries a ?v=<hash> cache-busting query (feature 040),
    # so match the tag prefix rather than the exact (now stale) quoted URL.
    assert shell_html.index("%%ASTRAL_RESUMED%%") < shell_html.index(
        'src="/static/client.js'
    )


# ---------------------------------------------------------------------------
# (10) FR-010 negatives — no local credential UI anywhere
# ---------------------------------------------------------------------------

FORBIDDEN_FR010 = ("remember me", "remember-me", "biometric", "webauthn")


@pytest.mark.parametrize(
    "path", [CLIENT_JS, SHELL_HTML, WEB_AUTH_PY], ids=lambda p: p.name
)
def test_fr010_no_local_credential_ui(path):
    low = _read(path).lower()
    for term in FORBIDDEN_FR010:
        assert term not in low, f"{path.name} contains forbidden FR-010 term {term!r}"


def test_fr010_error_pages_offer_no_local_credential_capture(web_auth_src):
    """The bounded sign-in error page and the FR-005 no-access page must offer
    only a link back to /auth/login — no input fields, no persistence opt-ins."""
    no_access = _py_function(web_auth_src, "_no_access_page")
    error_page = _py_function(web_auth_src, "_error_page")
    assert "No access" in no_access  # extraction sanity
    assert "Sign-in problem" in error_page
    for name, fn in (("_no_access_page", no_access), ("_error_page", error_page)):
        low = fn.lower()
        for term in FORBIDDEN_FR010:
            assert term not in low, f"{name} contains forbidden FR-010 term {term!r}"
        assert "/auth/login" in fn, f"{name} must route recovery through /auth/login"
        assert "<input" not in low and "<form" not in low, (
            f"{name} must not render local credential inputs"
        )
