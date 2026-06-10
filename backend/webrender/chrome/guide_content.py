"""Feature 027 — static User-guide content for the ``guide`` chrome surface.

Ported from the former React panel
(``frontend/src/components/guide/UserGuidePanel.tsx`` at commit ``29de624``).
Every section of the source panel is carried over; wording that described
React-era chrome that no longer exists (the left sidebar, draggable floating
chat, URL-persisted filters, instant-save permissions) is adapted to the
current server-rendered UI (top-bar Settings menu, fixed chat panel,
explicit-save surfaces).

The guide is intentionally static content (no live data, no DB access).
``SECTIONS`` is an ordered list of ``{"slug", "title", "body_html"}`` dicts
(the admin section additionally carries ``"admin_only": True``). ``body_html``
is built exclusively from the literal strings below via the escape-by-default
helpers in this module — all plain text passes through ``esc()``; only the
helpers themselves emit markup.
"""
from webrender import esc


class _H(str):
    """Marker type for an already-escaped, trusted HTML fragment.

    ``_frag`` passes ``_H`` instances through verbatim and escapes every other
    value, which keeps the escape-by-default discipline mechanical: helpers
    return ``_H``; raw strings are always escaped.
    """


def _frag(parts) -> str:
    """Join mixed parts, escaping anything that is not a trusted fragment.

    Args:
        parts: Iterable of strings; ``_H`` members are trusted HTML, all
            other values are escaped via ``esc()``.

    Returns:
        The concatenated HTML string.
    """
    return "".join(p if isinstance(p, _H) else esc(p) for p in parts)


def _h1(text) -> _H:
    """Section heading (one per section)."""
    return _H(f'<h1 class="text-xl font-semibold mb-3 leading-tight text-astral-text">{esc(text)}</h1>')


def _h2(text) -> _H:
    """Sub-heading within a section body."""
    return _H(
        f'<h2 class="text-base font-semibold mt-6 mb-2 text-astral-text border-b border-white/5 pb-1">'
        f"{esc(text)}</h2>"
    )


def _p(*parts) -> _H:
    """Body paragraph; plain-string parts are escaped, ``_H`` parts trusted."""
    return _H(f'<p class="text-sm text-astral-muted leading-relaxed mb-3">{_frag(parts)}</p>')


def _li(*parts) -> _H:
    """List item for use inside :func:`_ul`."""
    return _H(f"<li>{_frag(parts)}</li>")


def _ul(*items) -> _H:
    """Bulleted list of :func:`_li` items."""
    return _H(
        '<ul class="text-sm text-astral-muted leading-relaxed mb-3 list-disc pl-5 space-y-1">'
        + "".join(items)
        + "</ul>"
    )


def _tip(*parts) -> _H:
    """Highlighted tip callout (the panel's ``Tip`` block)."""
    return _H(
        '<div class="my-3 border border-astral-primary/20 bg-astral-primary/5 rounded-lg p-3 '
        f'text-sm text-astral-muted leading-relaxed">{_frag(parts)}</div>'
    )


def _strong(text) -> _H:
    """Inline emphasis rendered in the primary text color."""
    return _H(f'<strong class="text-astral-text font-semibold">{esc(text)}</strong>')


def _em(text) -> _H:
    """Inline italics (UI labels, entry names)."""
    return _H(f"<em>{esc(text)}</em>")


def _kbd(text) -> _H:
    """Inline keyboard-key chip."""
    return _H(
        '<kbd class="bg-white/5 border border-white/10 rounded px-1.5 py-0.5 text-[10px] '
        f'font-mono text-astral-text">{esc(text)}</kbd>'
    )


def _code(text) -> _H:
    """Inline code token."""
    return _H(
        '<code class="bg-white/5 border border-white/10 rounded px-1 py-0.5 text-[11px] '
        f'font-mono text-astral-text">{esc(text)}</code>'
    )


_INTRO = "".join([
    _h1("Welcome to AstralBody"),
    _p(
        "AstralBody is a chat-first workspace where you collaborate with intelligent agents "
        "that can use tools, look things up, run small tasks, and render rich interactive "
        "components back to you. Everything an agent does on your behalf is recorded in your "
        "private audit log so you can verify what happened.",
    ),
    _p(
        "This guide explains every part of the workspace you'll use day to day. Use the table "
        "of contents on the left to jump between topics. Press ",
        _kbd("Esc"),
        " at any time to close this guide.",
    ),
    _h2("How to use this guide"),
    _ul(
        _li(
            _strong("New here?"), " Start with ", _em("Signing in"), ", then ",
            _em("Dashboard tour"), ", then ", _em("Chatting with agents"), ".",
        ),
        _li(
            _strong("Want a hands-on walkthrough?"), " Use ", _em("Take the tour"),
            " in the top-bar Settings menu to launch the interactive getting-started tour.",
        ),
        _li(
            _strong("Looking for something specific?"), " Browse the table of contents, or "
            "hover any control on the dashboard for a short tooltip.",
        ),
    ),
])

_SIGNING_IN = "".join([
    _h1("Signing in"),
    _p(
        "AstralBody uses your organisation's single sign-on (SSO) provider. When you visit the "
        "site you'll be redirected to the sign-in page; after you authenticate, you're returned "
        "to the dashboard.",
    ),
    _h2("Roles"),
    _ul(
        _li(
            _strong("User"),
            " — chat with agents, give feedback, view your own audit log, replay the tutorial.",
        ),
        _li(
            _strong("Admin"),
            " — everything users can do, plus the admin tools (tool quality, knowledge "
            "proposals, quarantine, tutorial editor).",
        ),
    ),
    _p(
        'If you sign in but see an "Unauthorized access" page, your account doesn\'t have '
        "either role yet — contact an administrator.",
    ),
    _h2("Signing out"),
    _p(
        "Open the ", _strong("Settings"), " menu in the top bar and choose ",
        _strong("Sign out"),
        ". Your session ends both in AstralBody and at your SSO provider.",
    ),
])

_DASHBOARD = "".join([
    _h1("Dashboard tour"),
    _p(
        "The dashboard is a single screen: a top bar across the top, the main canvas on the "
        "left, and the chat panel on the right.",
    ),
    _h2("Top bar"),
    _ul(
        _li(
            _strong("Brand & status"),
            " — shows the AstralBody mark and whether your connection to the orchestrator "
            "is live.",
        ),
        _li(
            _strong("Settings menu"),
            " — the gear button opens a grouped menu with everything configurable: ",
            _em("Agents & permissions"), ", ", _em("LLM settings"), ", ",
            _em("Personalization"), ", ", _em("Audit log"), ", and ", _em("Theme"),
            " under Account; ", _em("Take the tour"), " and ", _em("User guide"),
            " under Help; and ", _em("Sign out"), " at the bottom.",
        ),
        _li(
            _strong("Admin entries"),
            " — administrators also see an Admin tools group (see ",
            _em("For administrators"), ").",
        ),
    ),
    _tip(
        "Hover any control for about half a second to see a short tooltip describing what it "
        "does. The same tooltips appear when you Tab through the controls with the keyboard.",
    ),
    _h2("Main canvas"),
    _p(
        "When agents render rich components — tables, charts, file downloads, forms — they "
        "appear on the canvas. You can save individual components for later, combine or "
        "condense groups of them, and provide feedback on each one.",
    ),
    _h2("Chat panel"),
    _p(
        "The chat panel on the right is your primary input. Type a message and press ",
        _kbd("Enter"), " or click ", _strong("Send"), " to talk to an agent.",
    ),
])

_CHAT = "".join([
    _h1("Chatting with agents"),
    _p(
        "Type a message in the chat input and press ", _kbd("Enter"),
        " (or click the send button) to start a conversation. Behind the scenes, the "
        "orchestrator routes your request to the right agent, which may run several tools to "
        "build its answer.",
    ),
    _h2("What you can ask"),
    _ul(
        _li(_strong("Questions"), " — agents will use search, lookup, and knowledge tools to answer."),
        _li(
            _strong("Tasks"),
            ' — "summarise this PDF", "draft an email", "render a chart of …".',
        ),
        _li(
            _strong("Follow-ups"),
            " — every chat keeps context, so you can refine without restating everything.",
        ),
    ),
    _h2("While the agent is thinking"),
    _p(
        "A status indicator shows the current step — searching, calling a tool, rendering "
        "output. You can cancel a long-running task at any time.",
    ),
    _h2("Multiple chats"),
    _p(
        "Start a new chat to begin a fresh conversation. Each chat is independent — agents "
        "can't see other chats' history.",
    ),
])

_ATTACHMENTS = "".join([
    _h1("Attachments & files"),
    _p(
        "Use the paperclip control next to the chat input to attach files to a message. "
        "AstralBody supports common document, image, and data formats up to 30 MB per file. "
        "Files are stored privately to your account and persist across chats — you can re-use "
        "an attachment from the library without re-uploading.",
    ),
    _h2("Attachment library"),
    _p(
        "Open the attachment library to see every file you've uploaded, when, and what type it "
        "is. Files you delete from the library are removed from future use, but historical "
        "chats that referenced them still record the fact (without the bytes) in your audit log.",
    ),
    _h2("Files an agent gives you"),
    _p(
        "When an agent generates a file (a CSV, an image, a PDF), the canvas shows a download "
        "component with a button. Click ", _strong("Download"),
        " to save it locally. The orchestrator records the download in your audit log.",
    ),
    _tip(
        "Don't attach files containing secrets you wouldn't want logged. AstralBody redacts "
        "known PHI/PII patterns from audit-event metadata, but the safest data is data you "
        "never upload.",
    ),
])

_VOICE = "".join([
    _h1("Voice in & out"),
    _p(
        "If your device exposes a microphone, the microphone button next to the chat input "
        "lets you dictate a message instead of typing. You'll see a live transcript while you "
        "speak; press the stop icon when you're done. Your speech is sent to the orchestrator "
        "for transcription and does not leave your audit log unaudited.",
    ),
    _h2("Spoken responses"),
    _p(
        "Toggle the speaker button to have the agent's text response read aloud. The toggle "
        "remembers its setting between sessions.",
    ),
    _p(
        "Voice is optional and gracefully disabled on devices without microphone or audio "
        "support.",
    ),
])

_AGENTS = "".join([
    _h1("Browsing agents"),
    _p(
        "Open ", _strong("Agents & permissions"),
        " from the top-bar Settings menu to see every agent the orchestrator can route "
        "requests to. Each agent advertises a set of ", _em("tools"),
        " — small functions it can call — and a set of ", _em("scopes"),
        " that gate which categories of tools you've granted it.",
    ),
    _h2("Three tabs"),
    _ul(
        _li(_strong("My agents"), " — agents you own or have configured."),
        _li(
            _strong("All agents"),
            " — every agent registered with the orchestrator, including public ones from "
            "other users.",
        ),
        _li(
            _strong("Drafts"),
            " — agents you've created but not yet finalised. Click a draft to resume "
            "editing it.",
        ),
    ),
    _h2("Permissions"),
    _p(
        "Click an agent to open its permissions view. Toggle each scope on or off; for finer "
        "control, override individual tools within an enabled scope. Click ",
        _strong("Save"),
        " to apply your changes — they affect your account only and don't change other users' "
        "permissions for the same agent.",
    ),
    _h2("Credentials"),
    _p(
        "Some agents need external API keys (e.g. for a third-party service). The permissions "
        "view shows which keys an agent expects and lets you save them encrypted server-side, "
        "or kick off an OAuth flow when supported.",
    ),
    _h2("Public vs. private"),
    _p(
        "If you own an agent, you can toggle it public or private from its permissions view. "
        "Public agents appear in ", _em("All agents"),
        " for every user; private ones are visible only to you.",
    ),
    _h2("Creating a new agent"),
    _p(
        "From the ", _em("Drafts"),
        " tab, describe a new agent in plain language. The system generates the code, "
        "packages, and skill tags, and submits the draft for security review. You can resume "
        "or delete drafts from the same tab.",
    ),
])

_COMPONENTS = "".join([
    _h1("Saved components"),
    _p(
        "When an agent renders something useful — a table of results, a chart, a metric card "
        "— you can pin it for later. Hover a component to surface the ",
        _strong("Save"), " button.",
    ),
    _h2("Where saved items live"),
    _p(
        "Open the saved-components view to see everything you've pinned, grouped by chat. "
        "From there you can re-open the originating chat, delete an item, or combine several "
        "into a single condensed view.",
    ),
    _h2("Combine & condense"),
    _ul(
        _li(
            _strong("Combine"),
            " — selects multiple saved components and asks the orchestrator to merge them "
            "into a single richer component.",
        ),
        _li(
            _strong("Condense"),
            " — produces a shorter summary version of a long or noisy component.",
        ),
    ),
])

_FEEDBACK = "".join([
    _h1("Giving feedback"),
    _p(
        "Every component an agent renders has a small ", _strong("feedback control"),
        " you can use to tell us whether it was useful. Your feedback shapes how the system "
        "improves over time and helps administrators identify underperforming tools.",
    ),
    _h2("How it works"),
    _ul(
        _li(_strong("Thumbs up"), " — record that this component was useful."),
        _li(
            _strong("Thumbs down"),
            " — flag the component, optionally with a category (wrong data, irrelevant, "
            "layout broken, too slow) and a short comment.",
        ),
    ),
    _h2("Privacy"),
    _p(
        "Your feedback is associated with your account and the specific component you rated. "
        "Comments are scanned for unsafe content; flagged comments are quarantined for admin "
        "review and don't influence the system's learning until released.",
    ),
    _h2("Editing or retracting"),
    _p(
        "Within 24 hours of submitting, you can amend or retract a feedback entry. After that "
        "window, the original record is preserved (with a new amendment record if you "
        "change it).",
    ),
])

_AUDIT = "".join([
    _h1("Your audit log"),
    _p(
        "The audit log records every action an agent takes on your behalf, every tool call, "
        "every file download, and every authentication event. It is strictly per-user — you "
        "only ever see your own entries, and not even administrators can read them through "
        "the UI.",
    ),
    _h2("What you'll see"),
    _ul(
        _li(
            _strong("Action type"), " — the operation (e.g. ", _code("auth.login"), ", ",
            _code("agent.tool_call"), ", ", _code("file.download"), ").",
        ),
        _li(_strong("Outcome"), " — in progress, success, failure, or interrupted."),
        _li(_strong("Description"), " — a short human-readable summary."),
        _li(
            _strong("Inputs / outputs metadata"),
            " — non-sensitive context (e.g. tool name, file extension, conversation id) — "
            "never the raw payload.",
        ),
        _li(
            _strong("Artifact pointers"),
            " — links to the underlying file or chat the row references; click to open if "
            "still available.",
        ),
        _li(_strong("Recorded at"), " — server-side timestamp."),
    ),
    _h2("Filtering & search"),
    _p(
        "Open ", _strong("Audit log"),
        " from the top-bar Settings menu, then use its filters to narrow by event class "
        "(auth, conversation, tool call, file, settings) or outcome. New entries appear as "
        "new actions occur.",
    ),
    _h2("Detail drawer"),
    _p(
        "Click any row to open a detail view with full metadata, correlated paired entries "
        "(a tool call typically has an ", _code("in_progress"), " followed by a ",
        _code("success"), " or ", _code("failure"), "), and the artifact pointers.",
    ),
    _tip(
        "The audit log is append-only and signed. If you ever need to verify integrity over "
        "time, support staff can run an offline chain-verification check; the result is "
        "cryptographic, not just visual.",
    ),
])

_TUTORIAL = "".join([
    _h1("Getting-started tour"),
    _p(
        "The first time you sign in, AstralBody walks you through the core workflow as a "
        "guided overlay: starting a chat, opening agents, reviewing the audit log, and giving "
        "feedback. The overlay highlights the relevant control on the dashboard for each step.",
    ),
    _h2("Controls"),
    _ul(
        _li(_strong("Next / Back"), " — advance or go back through the steps."),
        _li(
            _strong("Skip tour"), " or ", _kbd("Esc"),
            " — close the overlay; the system remembers you skipped and won't auto-launch "
            "again.",
        ),
        _li(
            _strong("Replay"), " — open ", _em("Take the tour"),
            " in the top-bar Settings menu to relaunch the overlay any time.",
        ),
    ),
    _h2("Resume on reload"),
    _p(
        "If you refresh the browser part-way through the tour, you resume on the same step "
        "(or the next still-applicable step if a step has been archived). State follows your "
        "account, so signing in from a different device or browser preserves your progress.",
    ),
    _h2("Admins see extra steps"),
    _p(
        "Admin users see the same user-flow tour with admin-specific steps appended at the "
        "end (covering the tool-quality surfaces and the tutorial editor).",
    ),
])

_TOOLTIPS = "".join([
    _h1("Tooltips & hints"),
    _p(
        "Almost every interactive control on the dashboard has a contextual tooltip. Tooltips "
        "reduce trial-and-error — hover or keyboard-focus a control to learn what it does "
        "without opening this guide.",
    ),
    _h2("How to trigger a tooltip"),
    _ul(
        _li(_strong("Mouse"), " — hover the control for about 500 ms."),
        _li(
            _strong("Keyboard"), " — press ", _kbd("Tab"),
            " until the control is focused; the tooltip appears immediately.",
        ),
        _li(_strong("Touch"), " — long-press the control."),
        _li("Press ", _kbd("Esc"), " at any time to dismiss the active tooltip."),
    ),
    _h2("Server-rendered tooltips"),
    _p(
        "Some components an agent renders carry their own tooltip text from the backend — "
        "usually for buttons or actions inside a complex card. They behave the same as "
        "static-UI tooltips.",
    ),
    _tip(
        "If a control doesn't show a tooltip, it doesn't have help text — that's intentional, "
        "not a bug. Empty tooltip frames are never displayed.",
    ),
])

_PREFERENCES = "".join([
    _h1("Theme & preferences"),
    _p(
        "Open ", _strong("Theme"),
        " from the top-bar Settings menu to restyle the workspace. Pick one of the preset "
        "palettes or fine-tune individual colors with the per-key pickers; changes apply "
        "instantly once saved and follow your account across devices.",
    ),
    _h2("Other preferences"),
    _p(
        "The same Settings menu holds your other per-account configuration: ",
        _em("LLM settings"), " for your model connection and ", _em("Personalization"),
        " for profile, memory, skills, schedules, and dreaming.",
    ),
    _h2("Resetting"),
    _p(
        "Sign out and back in to re-fetch preferences from the server. Local-only state "
        "(e.g. an unsubmitted draft message) is discarded on sign-out.",
    ),
])

_DEVICE = "".join([
    _h1("Mobile, tablet & touch"),
    _p(
        "The dashboard reflows to smaller viewports automatically, and what agents render is "
        "adapted to your device class server-side, so the same content stays usable on a "
        "phone, tablet, or desktop.",
    ),
    _h2("Touch interactions"),
    _ul(
        _li(_strong("Tooltips"), " appear on long-press instead of hover."),
        _li(_strong("Tutorial overlay"), " uses tap to advance — no hover required."),
        _li(
            _strong("Voice input"),
            " works wherever the device microphone is available.",
        ),
    ),
    _h2("Cross-device sync"),
    _p(
        "Anything stored on the backend — chats, audit log, onboarding progress, feedback, "
        "agent permissions — follows your account across browsers and devices. Local UI "
        "state is per-device.",
    ),
])

_PRIVACY = "".join([
    _h1("Privacy & per-user data"),
    _p(
        "AstralBody is built around strict per-user isolation. Every data store that touches "
        "your activity — chats, files, audit events, feedback, onboarding state — is scoped "
        "to your account at the API layer. There is no UI path through which one user can "
        "read another user's data, and even administrators cannot read your audit log through "
        "the dashboard.",
    ),
    _h2("What is logged"),
    _ul(
        _li(
            _strong("Recorded"),
            " — non-sensitive metadata (action type, timestamps, tool name, outcome, file "
            "extension, identifiers).",
        ),
        _li(
            _strong("Not recorded"),
            " — raw message bodies, file contents, secrets, or personally identifying "
            "information that can be redacted.",
        ),
    ),
    _h2("Retention"),
    _p(
        "Audit events are retained for compliance for several years and are then purged by an "
        "offline operator job (never the dashboard). File attachments persist until you "
        "delete them from the library.",
    ),
    _h2("Reporting a problem"),
    _p(
        "If you see something that looks like a privacy leak — a row in your audit log that "
        "shouldn't be yours, a tooltip showing private text — flag it via the feedback "
        "control on the affected component and contact your administrator immediately.",
    ),
])

_ADMIN = "".join([
    _h1("For administrators"),
    _p(
        "Admins see an extra ", _strong("Admin tools"),
        " group in the top-bar Settings menu:",
    ),
    _h2("Tutorial admin"),
    _p(
        "Edit the copy of every step in the getting-started tour without a code change. New, "
        "edited, archived, and restored steps take effect on the next user replay.",
    ),
    _ul(
        _li(
            _strong("New step"),
            " — create a step with a stable slug, audience (user or admin), display order, "
            "and target.",
        ),
        _li(
            _strong("Edit"),
            " — partial updates write a revision row with full before/after snapshots.",
        ),
        _li(
            _strong("Archive / Restore"),
            " — soft-delete keeps revision history intact and lets in-flight users resume "
            "safely.",
        ),
        _li(
            _strong("Revisions"),
            " — every change records who, when, and what; the audit log records a structured "
            "changed-fields summary.",
        ),
    ),
    _h2("Tool quality"),
    _ul(
        _li(
            _strong("Flagged tools"),
            " — tools whose recent quality signals have crossed the underperformance "
            "threshold. Click for evidence.",
        ),
        _li(
            _strong("Proposals"),
            " — system-generated knowledge-update proposals; accept (optionally with edits) "
            "or reject with a rationale. Applied changes write to ",
            _code("backend/knowledge/"), " atomically.",
        ),
        _li(
            _strong("Quarantine"),
            " — feedback flagged for unsafe content. Release back into the synthesizer pool "
            "or dismiss.",
        ),
    ),
    _h2("What admins still cannot do via the UI"),
    _ul(
        _li("Read another user's audit log entries."),
        _li("Read another user's onboarding state."),
        _li("Read another user's saved files."),
    ),
    _p(
        "These are operator-only operations and require a server-side CLI under a separate "
        "authority.",
    ),
])

#: Ordered guide sections — slug/title parity with the former React panel's
#: SECTIONS inventory; the ``admin`` section keeps its admin-only gating.
SECTIONS = [
    {"slug": "intro", "title": "Welcome", "body_html": _INTRO},
    {"slug": "signing-in", "title": "Signing in", "body_html": _SIGNING_IN},
    {"slug": "dashboard", "title": "Dashboard tour", "body_html": _DASHBOARD},
    {"slug": "chat", "title": "Chatting with agents", "body_html": _CHAT},
    {"slug": "attachments", "title": "Attachments & files", "body_html": _ATTACHMENTS},
    {"slug": "voice", "title": "Voice in & out", "body_html": _VOICE},
    {"slug": "agents", "title": "Browsing agents", "body_html": _AGENTS},
    {"slug": "components", "title": "Saved components", "body_html": _COMPONENTS},
    {"slug": "feedback", "title": "Giving feedback", "body_html": _FEEDBACK},
    {"slug": "audit", "title": "Your audit log", "body_html": _AUDIT},
    {"slug": "tutorial", "title": "Getting-started tour", "body_html": _TUTORIAL},
    {"slug": "tooltips", "title": "Tooltips & hints", "body_html": _TOOLTIPS},
    {"slug": "preferences", "title": "Theme & preferences", "body_html": _PREFERENCES},
    {"slug": "device", "title": "Mobile, tablet & touch", "body_html": _DEVICE},
    {"slug": "privacy", "title": "Privacy & per-user data", "body_html": _PRIVACY},
    {"slug": "admin", "title": "For administrators", "body_html": _ADMIN, "admin_only": True},
]
