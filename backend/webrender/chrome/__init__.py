"""Feature 027 — server-rendered application chrome for the web target.

The chrome layer (top bar, settings menu, modal surfaces) is orchestrator
render-layer output for the web client (Constitution II: the orchestrator
renders). It is intentionally NOT expressed as astralprims primitives —
astralprims stays a general-purpose primitive library; app chrome is
web-specific HTML built with the same escape-by-default discipline as
``webrender.renderer`` (every text interpolation goes through ``esc()``).

Chrome HTML never enters the ROTE/astralprims pipeline; canvas/chat content
continues to flow astralprims → ROTE → ``render_for_target`` unchanged.
Surfaces MAY embed rendered primitives via ``render_one`` (e.g. color
pickers in the Theme surface) so client-side side effects stay wired.
"""
from webrender import esc, render_one, safe_url  # noqa: F401  (re-exported for surfaces)

from .topbar import render_topbar  # noqa: F401


def render_modal_shell(title: str, body_html: str, surface: str = "") -> str:
    """Wrap a surface body in the standard chrome modal (backdrop + card).

    ``body_html`` is trusted, already-escaped chrome output from a surface
    renderer; ``title`` and ``surface`` are escaped here.
    """
    return (
        f'<div class="astral-modal-backdrop fixed inset-0 z-50 bg-black/60 backdrop-blur-sm '
        f'flex items-start justify-center overflow-y-auto py-10" data-surface="{esc(surface)}">'
        f'<div class="astral-modal-card relative bg-astral-surface border border-white/10 rounded-xl '
        f'shadow-2xl w-full max-w-3xl mx-4 my-auto" role="dialog" aria-modal="true" '
        f'aria-label="{esc(title)}" tabindex="-1">'
        f'<div class="flex items-center justify-between px-5 py-4 border-b border-white/5">'
        f'<h2 class="text-base font-semibold text-astral-text">{esc(title)}</h2>'
        f'<button type="button" class="astral-modal-close text-astral-muted hover:text-astral-text '
        f'rounded-lg p-1.5 hover:bg-white/5" aria-label="Close">'
        f'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button></div>'
        f'<div class="px-5 py-4 max-h-[70vh] overflow-y-auto space-y-4">{body_html}</div>'
        f'</div></div>'
    )


def chrome_error_block(message: str, retry_surface: str = "") -> str:
    """In-modal error notice (never a silent drop — contract failure section)."""
    retry = ""
    if retry_surface:
        retry = (
            f'<button type="button" class="mt-2 px-3 py-1.5 rounded-lg text-xs font-medium '
            f'bg-astral-primary/20 text-astral-primary border border-astral-primary/30" '
            f'data-ui-action="chrome_open" '
            f"data-ui-payload='{{\"surface\": \"{esc(retry_surface)}\"}}'>Retry</button>"
        )
    return (
        f'<div class="astral-chrome-error border border-red-500/20 bg-red-500/10 rounded-lg p-3">'
        f'<div class="text-sm text-red-400">{esc(message)}</div>{retry}</div>'
    )


def notice_block(kind: str, message: str) -> str:
    """Inline success/error/info notice rendered at the top of a surface."""
    styles = {
        "success": "border-green-500/20 bg-green-500/10 text-green-400",
        "error": "border-red-500/20 bg-red-500/10 text-red-400",
        "info": "border-astral-primary/20 bg-astral-primary/10 text-astral-primary",
    }
    cls = styles.get(kind, styles["info"])
    return (
        f'<div class="astral-chrome-notice border rounded-lg p-3 text-sm {cls}" role="status">'
        f"{esc(message)}</div>"
    )
