"""Feature 026 — server-side web renderer.

The orchestrator renders ``astralprims`` primitive dicts (already ROTE-adapted)
into web HTML. astralprims *defines* primitives + the structured representation;
this module (in the orchestrator) *renders* them; ROTE *adapts* per device
(Constitution Principle II, v2.0.1).

Implementation note: pure-Python render functions with explicit ``html.escape``
give a hard escape-by-default guarantee (FR-017) and are deterministic /
golden-testable. Markup parity targets the live ``frontend/src/components/
DynamicRenderer.tsx`` (Tailwind class strings reproduced verbatim; the shell
self-hosts Tailwind + Plotly). Text is always escaped; rich text goes through the
narrow, sanitized markdown path in :mod:`webrender.sanitize`.
"""
from __future__ import annotations

import html
import json
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger("webrender")

# type -> render function. Populated at the bottom of this module.
PRIMITIVE_RENDERERS: Dict[str, Callable[[Dict[str, Any]], str]] = {}


# ---------------------------------------------------------------------------
# Escaping & safe helpers (escape-by-default — FR-017 / SC-008)
# ---------------------------------------------------------------------------

def esc(value: Any) -> str:
    """HTML-escape any value's string form (quotes included)."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _attr(value: Any) -> str:
    """Escape a value for use inside a double-quoted HTML attribute."""
    return html.escape(str(value), quote=True)


def safe_url(url: Any) -> str:
    """Return the URL only if its scheme is safe, else '#'. Prevents
    javascript:/data: URL injection in href/src."""
    if not url:
        return "#"
    s = str(url).strip()
    low = s.lower()
    if low.startswith(("http://", "https://", "mailto:", "/")):
        return s
    if low.startswith("data:audio/") or low.startswith("data:image/"):
        return s  # inline media payloads are allowed (audio/image primitives)
    if ":" not in low.split("/", 1)[0]:
        return s  # relative path, no scheme
    return "#"


from .sanitize import inline_md, block_md  # noqa: E402  (after esc/safe_url defined)


# ---------------------------------------------------------------------------
# Recursion
# ---------------------------------------------------------------------------

def _children(comp: Dict[str, Any]) -> List[Dict[str, Any]]:
    return comp.get("children") or comp.get("content") or []


def render_children(items: List[Any]) -> str:
    return "".join(render_one(c) for c in items if isinstance(c, dict))


def _base_attrs(comp: Dict[str, Any]) -> str:
    """Render id (the only base attr applied to the fragment root in the live app)."""
    cid = comp.get("id")
    return f' id="{_attr(cid)}"' if cid else ""


# ---------------------------------------------------------------------------
# Primitive renderers (parity with DynamicRenderer.tsx)
# ---------------------------------------------------------------------------

def render_container(c):
    # Live container emits no wrapper — just its children.
    return render_children(_children(c))


def render_text(c):
    variant = c.get("variant") or "body"
    content = c.get("content", "")
    if variant == "markdown":
        cls = ("prose prose-invert max-w-none text-sm text-astral-text leading-relaxed "
               "prose-headings:text-astral-text prose-a:text-astral-primary prose-strong:text-astral-text "
               "prose-code:text-astral-accent")
        return f'<div class="{cls}">{block_md(content)}</div>'
    classes = {
        "h1": "text-2xl font-bold text-astral-text",
        "h2": "text-xl font-semibold text-astral-text",
        "h3": "text-lg font-medium text-astral-text",
        "body": "text-sm text-astral-text leading-relaxed",
        "caption": "text-xs text-astral-muted",
    }
    tag = {"h1": "h1", "h2": "h2", "h3": "h3"}.get(variant, "p")
    cls = classes.get(variant, classes["body"])
    return f'<{tag} class="{cls}">{esc(content)}</{tag}>'


def render_button(c):
    label = c.get("label", "")
    action = c.get("action", "")
    payload = c.get("payload", {}) or {}
    variant = c.get("variant", "primary")
    vcls = {
        "primary": "bg-astral-primary hover:bg-astral-primary/80 text-white",
        "secondary": "bg-astral-secondary hover:bg-astral-secondary/80 text-white",
        "ghost": "bg-white/5 hover:bg-white/10 text-astral-text border border-white/10",
    }.get(variant, "bg-astral-primary hover:bg-astral-primary/80 text-white")
    data = _attr(json.dumps(payload))
    return (
        f'<button type="button" data-action="{_attr(action)}" data-payload="{data}" '
        f'class="astral-action px-4 py-2 rounded-lg text-sm font-medium transition-colors {vcls}">'
        f'{esc(label)}</button>'
    )


def render_input(c):
    # No live renderer; provide a basic standalone input for completeness.
    return (
        f'<input type="text" name="{_attr(c.get("name",""))}" value="{_attr(c.get("value",""))}" '
        f'placeholder="{_attr(c.get("placeholder",""))}" '
        f'class="rounded bg-white/10 border border-white/10 px-2 py-1 text-astral-text w-full">'
    )


def _param_field(field: Dict[str, Any]) -> str:
    name = field.get("name", "")
    label = field.get("label") or name
    kind = field.get("kind", "text")
    help_ = field.get("help")
    default = field.get("default")
    help_html = f'<span class="text-xs text-astral-muted">{esc(help_)}</span>' if help_ else ""
    if kind == "boolean":
        checked = " checked" if default else ""
        help_html = f'<div class="text-xs text-astral-muted">{esc(help_)}</div>' if help_ else ""
        return (
            f'<label class="flex items-start gap-3 text-sm">'
            f'<input type="checkbox" data-field="{_attr(name)}" data-kind="boolean"{checked} '
            f'class="astral-pp-field mt-1 h-4 w-4 rounded border-white/20 bg-white/10">'
            f'<div class="flex-1"><div class="text-astral-text font-medium">{esc(label)}</div>'
            f'{help_html}</div></label>'
        )
    if kind == "number":
        step = field.get("step", 1)
        val = "" if default is None else _attr(default)
        return (
            f'<label class="flex flex-col gap-1 text-sm"><span class="text-astral-text font-medium">{esc(label)}</span>'
            f'{help_html}<input type="number" step="{_attr(step)}" value="{val}" data-field="{_attr(name)}" data-kind="number" '
            f'class="astral-pp-field rounded bg-white/10 border border-white/10 px-2 py-1 text-astral-text w-40"></label>'
        )
    if kind == "checklist":
        opts = field.get("options") or []
        if not opts:
            inner = '<span class="text-xs text-astral-muted italic">(no options provided)</span>'
        else:
            sel = set(default or []) if isinstance(default, list) else set()
            btns = []
            for opt in opts:
                on = opt in sel
                ocls = ("bg-astral-primary/30 border-astral-primary text-white" if on
                        else "bg-white/5 border-white/10 text-astral-muted hover:bg-white/10")
                btns.append(
                    f'<button type="button" data-field="{_attr(name)}" data-kind="checklist" data-value="{_attr(opt)}" '
                    f'aria-pressed="{"true" if on else "false"}" '
                    f'class="astral-pp-field px-2 py-1 rounded text-xs border transition-colors {ocls}">{esc(opt)}</button>'
                )
            inner = f'<div class="flex flex-wrap gap-2 mt-1">{"".join(btns)}</div>'
        return (
            f'<div class="flex flex-col gap-1 text-sm"><span class="text-astral-text font-medium">{esc(label)}</span>'
            f'{help_html}{inner}</div>'
        )
    if kind == "select":
        opts = field.get("options") or []
        options = "".join(
            f'<option value="{_attr(o)}"{" selected" if o == default else ""}>{esc(o)}</option>' for o in opts
        )
        return (
            f'<label class="flex flex-col gap-1 text-sm"><span class="text-astral-text font-medium">{esc(label)}</span>'
            f'{help_html}<select data-field="{_attr(name)}" data-kind="select" '
            f'class="astral-pp-field rounded bg-white/10 border border-white/10 px-2 py-1 text-astral-text w-60">{options}</select></label>'
        )
    # text (default)
    val = "" if default is None else _attr(default)
    return (
        f'<label class="flex flex-col gap-1 text-sm"><span class="text-astral-text font-medium">{esc(label)}</span>'
        f'{help_html}<input type="text" value="{val}" data-field="{_attr(name)}" data-kind="text" '
        f'class="astral-pp-field rounded bg-white/10 border border-white/10 px-2 py-1 text-astral-text w-full"></label>'
    )


def render_param_picker(c):
    title = c.get("title")
    description = c.get("description")
    fields = c.get("fields") or []
    submit_label = c.get("submit_label", "Submit")
    template = c.get("submit_message_template", "")
    title_html = f'<div class="text-base font-semibold text-astral-text mb-1">{esc(title)}</div>' if title else ""
    desc_html = (f'<div class="text-sm text-astral-muted mb-3 whitespace-pre-wrap">{esc(description)}</div>'
                 if description else "")
    rows = "".join(_param_field(f) for f in fields)
    return (
        f'<div class="astral-param-picker bg-white/5 rounded-lg border border-white/10 p-4 my-2" '
        f'data-template="{_attr(template)}">{title_html}{desc_html}'
        f'<div class="flex flex-col gap-3 max-h-[28rem] overflow-y-auto pr-1">{rows}</div>'
        f'<div class="mt-4 flex items-center justify-end gap-2">'
        f'<button type="button" class="astral-pp-submit px-4 py-2 rounded-lg text-sm font-medium transition-colors '
        f'bg-astral-primary hover:bg-astral-primary/80 text-white">{esc(submit_label)}</button></div></div>'
    )


def render_card(c):
    title = c.get("title")
    title_html = ""
    if title:
        title_html = (
            '<div class="mb-3"><h3 class="text-base font-semibold text-astral-text flex items-center gap-2">'
            '<span class="w-1 h-4 rounded-full bg-astral-primary inline-block"></span>'
            f'{inline_md(title)}</h3></div>'
        )
    return f'<div{_base_attrs(c)}>{title_html}<div class="space-y-3">{render_children(_children(c))}</div></div>'


def _cell(cell: Any) -> str:
    s = str(cell) if cell is not None else ""
    if s in ("Critical", "Severe"):
        return f'<span class="px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/20 text-red-400">{esc(s)}</span>'
    if s == "Moderate":
        return f'<span class="px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-500/20 text-yellow-400">{esc(s)}</span>'
    if s in ("Mild", "Stable"):
        return f'<span class="px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/20 text-green-400">{esc(s)}</span>'
    if s.startswith("http://") or s.startswith("https://"):
        return (f'<a href="{_attr(safe_url(s))}" target="_blank" rel="noopener noreferrer" '
                f'class="text-astral-primary hover:underline inline-flex items-center gap-1">View</a>')
    return esc(s)


def render_table(c):
    headers = c.get("headers") or []
    rows = c.get("rows") or []
    if not headers and not rows:
        return ""
    title = c.get("title") or c.get("label") or "Table"
    total = c.get("total_rows")
    page_size = c.get("page_size")
    offset = c.get("page_offset") or 0
    paginated = total is not None and page_size is not None
    showing = ""
    if paginated:
        frm = offset + 1
        to = min(offset + page_size, total)
        showing = f'<div class="text-xs text-astral-muted">{frm}–{to} of {esc(total)}</div>'
    head = "".join(
        f'<th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-astral-muted whitespace-nowrap">{esc(h)}</th>'
        for h in headers)
    body = "".join(
        '<tr class="border-b border-white/5 hover:bg-white/5 transition-colors">'
        + "".join(f'<td class="px-4 py-3 text-astral-text">{_cell(cell)}</td>' for cell in row)
        + "</tr>"
        for row in rows)
    footer = ""
    if paginated and c.get("source_tool") and c.get("source_agent"):
        sizes = c.get("page_sizes") or [25, 50, 100, 200]
        opts = "".join(f'<option value="{_attr(s)}"{" selected" if s == page_size else ""}>{esc(s)}</option>' for s in sizes)
        prev_dis = " disabled" if offset == 0 else ""
        next_dis = " disabled" if (offset + page_size) >= total else ""
        ctx = _attr(json.dumps({"source_tool": c.get("source_tool"), "source_agent": c.get("source_agent"),
                                "source_params": c.get("source_params") or {}, "page_size": page_size, "page_offset": offset,
                                "total_rows": total}))
        footer = (
            f'<div class="astral-pagination p-3 border-t border-white/5 bg-astral-primary/5 flex items-center justify-between gap-4" data-ctx="{ctx}">'
            f'<div class="flex items-center gap-2"><span class="text-xs text-astral-muted">Rows per page:</span>'
            f'<select class="astral-page-size text-xs bg-astral-surface border border-white/10 rounded px-2 py-1 text-astral-text">{opts}</select></div>'
            f'<div class="flex items-center gap-2">'
            f'<button class="astral-page-prev text-xs px-3 py-1 rounded border border-white/10 text-astral-text hover:bg-white/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"{prev_dis}>Prev</button>'
            f'<button class="astral-page-next text-xs px-3 py-1 rounded border border-white/10 text-astral-text hover:bg-white/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"{next_dis}>Next</button>'
            f'</div></div>'
        )
    return (
        f'<div{_base_attrs(c)} class="rounded-lg border border-white/10">'
        f'<div class="p-3 border-b border-white/5 bg-astral-primary/5 flex items-center justify-between">'
        f'<div class="text-sm font-medium text-astral-text">{inline_md(title)}</div>{showing}</div>'
        f'<div class="overflow-x-auto"><table class="w-full text-sm">'
        f'<thead><tr class="bg-astral-primary/10 border-b border-white/5">{head}</tr></thead>'
        f'<tbody>{body}</tbody></table></div>{footer}</div>'
    )


def render_list(c):
    items = c.get("items") or []
    if not items:
        return ""
    if c.get("variant") == "detailed":
        out = ['<div class="space-y-3">']
        for it in items:
            if not isinstance(it, dict):
                it = {"title": str(it)}
            title = it.get("title", "")
            url = it.get("url")
            if url:
                title_node = (f'<a href="{_attr(safe_url(url))}" target="_blank" rel="noopener noreferrer" '
                              f'class="hover:text-astral-primary hover:underline flex items-center gap-2">{inline_md(title)}</a>')
            else:
                title_node = inline_md(title)
            sub = f'<p class="text-xs text-astral-muted">{inline_md(it.get("subtitle",""))}</p>' if it.get("subtitle") else ""
            desc = f'<div class="text-sm text-astral-text/80 line-clamp-2">{block_md(it.get("description",""))}</div>' if it.get("description") else ""
            out.append(
                '<div class="p-3 hover:bg-white/5 transition-colors"><div class="flex justify-between items-start gap-4">'
                f'<div class="space-y-1 w-full"><h4 class="text-sm font-semibold text-astral-text flex items-center justify-between">{title_node}</h4>{sub}{desc}</div></div></div>'
            )
        out.append("</div>")
        return "".join(out)
    ordered = bool(c.get("ordered"))
    tag = "ol" if ordered else "ul"
    lcls = "list-decimal" if ordered else "list-disc"
    lis = "".join(
        f'<li class="leading-relaxed">{inline_md(it) if isinstance(it, str) else esc(json.dumps(it))}</li>'
        for it in items)
    return f'<{tag} class="space-y-2 text-sm {lcls} list-inside text-astral-text">{lis}</{tag}>'


def _alert_icon(variant: str) -> str:
    # minimal inline SVGs (~16px), one per variant
    paths = {
        "info": "M12 2a10 10 0 100 20 10 10 0 000-20zm0 9v5m0-8h.01",
        "success": "M22 11.08V12a10 10 0 11-5.93-9.14M22 4L12 14.01l-3-3",
        "warning": "M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4m0 4h.01",
        "error": "M12 2a10 10 0 100 20 10 10 0 000-20zm0 6v4m0 4h.01",
    }
    d = paths.get(variant, paths["info"])
    return (f'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="{d}"></path></svg>')


def render_alert(c):
    variant = c.get("variant", "info")
    cfg = {
        "info": ("bg-blue-500/10", "border-blue-500/20", "text-blue-400"),
        "success": ("bg-green-500/10", "border-green-500/20", "text-green-400"),
        "warning": ("bg-yellow-500/10", "border-yellow-500/20", "text-yellow-400"),
        "error": ("bg-red-500/10", "border-red-500/20", "text-red-400"),
    }.get(variant, ("bg-blue-500/10", "border-blue-500/20", "text-blue-400"))
    bg, border, txt = cfg
    title = c.get("title")
    title_html = f'<p class="font-medium text-sm {txt}">{inline_md(title)}</p>' if title else ""
    msg = c.get("message", "")
    return (
        f'<div{_base_attrs(c)} class="{bg} {border} border rounded-lg p-4 flex items-start gap-3">'
        f'<span class="{txt}">{_alert_icon(variant)}</span>'
        f'<div class="flex-1"><div>{title_html}<div class="text-sm text-astral-text/80">{block_md(msg)}</div></div></div></div>'
    )


def render_progress(c):
    value = c.get("value") or 0.0
    label = c.get("label")
    show_pct = c.get("show_percentage", True)
    pct = max(0, min(value * 100, 100))
    header = ""
    if label:
        pct_span = f'<span>{round(value * 100)}%</span>' if show_pct is not False else ""
        header = (f'<div class="flex justify-between text-xs text-astral-muted w-full mb-1"><span>{inline_md(label)}</span>{pct_span}</div>')
    return (
        f'<div{_base_attrs(c)}>{header}<div class="h-2 bg-white/10 rounded-full overflow-hidden">'
        f'<div class="h-full bg-gradient-to-r from-astral-primary to-astral-secondary rounded-full" style="width:{pct}%"></div></div></div>'
    )


def render_metric(c):
    variant = c.get("variant", "default")
    vbg = {
        "default": "from-astral-primary/20 to-astral-primary/5",
        "warning": "from-yellow-500/20 to-yellow-500/5",
        "error": "from-red-500/20 to-red-500/5",
        "success": "from-green-500/20 to-green-500/5",
    }.get(variant, "from-astral-primary/20 to-astral-primary/5")
    subtitle = c.get("subtitle")
    sub_html = f'<p class="text-xs text-astral-muted mt-1">{inline_md(subtitle)}</p>' if subtitle else ""
    progress = c.get("progress")
    prog_html = ""
    if progress is not None:
        color = "bg-red-500" if progress > 0.9 else "bg-yellow-500" if progress > 0.7 else "bg-astral-primary"
        pw = max(0, min(progress * 100, 100))
        prog_html = (f'<div class="mt-3 h-1.5 bg-white/10 rounded-full overflow-hidden">'
                     f'<div class="h-full rounded-full {color}" style="width:{pw}%"></div></div>')
    return (
        f'<div{_base_attrs(c)} class="rounded-xl p-4 bg-gradient-to-br {vbg} border border-white/5 relative">'
        f'<p class="text-xs text-astral-muted font-medium uppercase tracking-wider mb-1">{inline_md(c.get("title",""))}</p>'
        f'<div class="flex-1"><p class="text-2xl font-bold text-astral-text">{esc(c.get("value",""))}</p>{sub_html}</div>{prog_html}</div>'
    )


def render_code(c):
    language = c.get("language")
    lang_html = f'<div class="px-4 py-2 border-b border-white/5 text-xs text-astral-muted">{esc(language)}</div>' if language else ""
    return (
        f'<div{_base_attrs(c)} class="rounded-lg bg-black/40 border border-white/5 overflow-hidden">{lang_html}'
        f'<pre class="p-4 text-sm overflow-x-auto" style="font-family:\'JetBrains Mono\',monospace">'
        f'<code class="text-green-400">{esc(c.get("code",""))}</code></pre></div>'
    )


def render_image(c):
    # No live renderer; basic standalone image for completeness.
    url = c.get("url")
    if not url:
        return ""
    attrs = f'src="{_attr(safe_url(url))}" alt="{_attr(c.get("alt",""))}"'
    if c.get("width"):
        attrs += f' width="{_attr(c.get("width"))}"'
    if c.get("height"):
        attrs += f' height="{_attr(c.get("height"))}"'
    return f'<img {attrs} class="max-w-full rounded-lg">'


def render_grid(c):
    cols = c.get("columns", 2)
    gap = c.get("gap", 16)
    n = min(int(cols) if isinstance(cols, (int, float)) else 2, 6)
    col_map = {
        1: "grid-cols-1",
        2: "grid-cols-1 sm:grid-cols-2",
        3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
        4: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
        5: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5",
        6: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6",
    }.get(n, f"grid-cols-1 sm:grid-cols-2 lg:grid-cols-{n}")
    return f'<div{_base_attrs(c)} class="grid {col_map}" style="gap:{int(gap)}px">{render_children(_children(c))}</div>'


def render_tabs(c):
    # No live renderer; provide a basic <details>-based fallback for completeness.
    tabs = c.get("tabs") or []
    out = ['<div class="space-y-2">']
    for i, t in enumerate(tabs):
        if not isinstance(t, dict):
            continue
        label = t.get("label", f"Tab {i+1}")
        body = render_children(t.get("content") or [])
        out.append(f'<details{" open" if i == 0 else ""}><summary class="text-sm font-medium text-astral-text cursor-pointer">{esc(label)}</summary>'
                   f'<div class="space-y-3 pt-2">{body}</div></details>')
    out.append("</div>")
    return "".join(out)


def render_divider(c):
    return '<hr class="border-white/10 my-3"/>'


def render_collapsible(c):
    title = c.get("title") or "Details"
    is_open = bool(c.get("default_open"))
    body = render_children(_children(c))
    return (
        f'<details class="overflow-hidden"{" open" if is_open else ""}>'
        f'<summary class="flex items-center w-full gap-2 px-3 py-2 hover:bg-white/[0.03] transition-colors text-left cursor-pointer list-none">'
        f'<span class="text-[11px] font-medium text-astral-muted/70 uppercase tracking-wider flex-1 truncate">{esc(title)}</span></summary>'
        f'<div class="px-3 pb-3 pt-1.5 border-t border-white/[0.04] space-y-2 max-h-[420px] overflow-y-auto scrollbar-thin">{body}</div></details>'
    )


def _chart_div(c, chart_type, payload):
    title = c.get("title")
    title_html = f'<p class="text-sm font-medium text-astral-text mb-3">{esc(title)}</p>' if title else ""
    data = _attr(json.dumps(payload))
    return (f'<div{_base_attrs(c)} class="w-full">{title_html}'
            f'<div class="astral-chart" data-chart-type="{chart_type}" data-chart="{data}" style="min-height:320px"></div></div>')


def render_bar_chart(c):
    datasets = c.get("datasets") or []
    if not datasets:
        return ""
    data = (datasets[0] or {}).get("data", []) if isinstance(datasets[0], dict) else []
    return _chart_div(c, "bar", {"labels": c.get("labels", []), "data": data})


def render_line_chart(c):
    datasets = c.get("datasets") or []
    if not datasets:
        return ""
    data = (datasets[0] or {}).get("data", []) if isinstance(datasets[0], dict) else []
    return _chart_div(c, "line", {"labels": c.get("labels", []), "data": data})


def render_pie_chart(c):
    data = c.get("data") or []
    if not data:
        return ""
    return _chart_div(c, "pie", {"labels": c.get("labels", []), "data": data, "colors": c.get("colors", [])})


def render_plotly_chart(c):
    data = c.get("data") or []
    if not data:
        return ""
    return _chart_div(c, "plotly", {"data": data, "layout": c.get("layout", {}), "config": c.get("config", {})})


def render_color_picker(c):
    label = c.get("label", "")
    key = c.get("color_key", "")
    value = c.get("value") or "#000000"
    return (
        f'<div{_base_attrs(c)} class="flex items-center gap-3 py-1">'
        f'<label class="text-sm text-astral-text font-medium min-w-[100px]">{esc(label)}</label>'
        f'<div class="relative"><input type="color" value="{_attr(value)}" data-color-key="{_attr(key)}" '
        f'class="astral-color-picker w-10 h-10 rounded-lg border-2 border-white/10 bg-transparent cursor-pointer"></div>'
        f'<span class="text-xs text-astral-muted font-mono">{esc(value)}</span></div>'
    )


def render_theme_apply(c):
    message = c.get("message") or "Theme updated"
    spec = {k: c.get(k) for k in ("preset", "colors", "color_key", "color_value") if c.get(k) is not None}
    data = _attr(json.dumps(spec))
    return (
        f'<div{_base_attrs(c)} class="astral-theme-apply bg-green-500/10 border border-green-500/20 rounded-lg p-3 flex items-center gap-2" data-theme="{data}">'
        f'<span class="text-green-400">{_alert_icon("success")}</span>'
        f'<span class="text-sm text-astral-text/80">{esc(message)}</span></div>'
    )


def render_file_upload(c):
    label = c.get("label", "Upload File")
    accept = c.get("accept", "*/*")
    return (
        f'<div{_base_attrs(c)} class="flex items-center gap-3 py-2">'
        f'<label class="cursor-pointer inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors '
        f'bg-astral-primary/20 hover:bg-astral-primary/30 text-astral-primary border border-astral-primary/30">'
        f'<span>{esc(label)}</span>'
        f'<input type="file" class="astral-file-upload hidden" accept="{_attr(accept)}"></label></div>'
    )


def render_file_download(c):
    label = c.get("label", "Download File")
    url = c.get("url")
    filename = c.get("filename")
    valid = bool(url) and url != "#" and str(url).startswith("http")
    # Built outside the f-string: escaped quotes inside an f-string expression
    # are a SyntaxError on Python <=3.11 (the container runtime).
    download_attr = f' download="{_attr(filename)}"' if filename else ""
    if valid:
        return (
            f'<div{_base_attrs(c)} class="flex items-center gap-3 py-2">'
            f'<a href="{_attr(safe_url(url))}"{download_attr} '
            f'class="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors '
            f'bg-astral-secondary/20 hover:bg-astral-secondary/30 text-astral-secondary border border-astral-secondary/30">'
            f'<span>{esc(label)}</span></a></div>'
        )
    return (
        f'<div{_base_attrs(c)} class="flex items-center gap-3 py-2">'
        f'<button disabled class="inline-flex items-center gap-2 px-4 py-2 bg-gray-500/20 text-gray-400 '
        f'border border-gray-500/30 rounded-lg text-sm font-medium cursor-not-allowed opacity-50">'
        f'<span>{esc(label or "Download File (unavailable)")}</span></button></div>'
    )


def render_audio(c):
    src = c.get("src", "")
    label = c.get("label")
    description = c.get("description")
    label_html = f'<div class="text-sm font-medium text-white/90 mb-2">{esc(label)}</div>' if label else ""
    desc_html = f'<div class="text-xs text-white/50 mt-2">{esc(description)}</div>' if description else ""
    if src:
        controls = "" if c.get("showControls") is False else " controls"
        autoplay = " autoplay" if c.get("autoplay") is True else ""
        loop = " loop" if c.get("loop") is True else ""
        ctype = c.get("contentType")
        type_attr = f' type="{_attr(ctype)}"' if ctype else ""
        media = (f'<audio{controls}{autoplay}{loop} class="w-full" style="min-height:40px">'
                 f'<source src="{_attr(safe_url(src))}"{type_attr}>Your browser does not support the audio element.</audio>')
    else:
        media = '<div class="text-white/40 text-xs italic">No audio source provided</div>'
    return (f'<div{_base_attrs(c)} class="audio-component rounded-lg border border-white/10 bg-white/5 p-3">'
            f'{label_html}{media}{desc_html}</div>')


PRIMITIVE_RENDERERS.update({
    "container": render_container, "text": render_text, "button": render_button, "input": render_input,
    "param_picker": render_param_picker, "card": render_card, "table": render_table, "list": render_list,
    "alert": render_alert, "progress": render_progress, "metric": render_metric, "code": render_code,
    "image": render_image, "grid": render_grid, "tabs": render_tabs, "divider": render_divider,
    "collapsible": render_collapsible, "bar_chart": render_bar_chart, "line_chart": render_line_chart,
    "pie_chart": render_pie_chart, "plotly_chart": render_plotly_chart, "color_picker": render_color_picker,
    "theme_apply": render_theme_apply, "file_upload": render_file_upload, "file_download": render_file_download,
    "audio": render_audio,
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_one(component: Dict[str, Any]) -> str:
    """Render a single primitive dict to an HTML fragment. Never raises on an
    unknown/unsupported type — emits a readable placeholder (FR-014)."""
    if not isinstance(component, dict):
        return ""
    ctype = component.get("type", "")
    fn = PRIMITIVE_RENDERERS.get(ctype)
    if fn is None:
        logger.warning("webrender: no renderer for primitive type %r — placeholder emitted", ctype)
        return (f'<div class="astral-unsupported text-xs text-astral-muted italic border border-white/10 '
                f'rounded p-2">[unsupported component: {esc(ctype) or "unknown"}]</div>')
    try:
        return fn(component)
    except Exception:  # pragma: no cover - defensive; a bad component must not kill the page
        logger.exception("webrender: failed rendering %r", ctype)
        return (f'<div class="astral-render-error text-xs text-red-400 border border-red-500/20 '
                f'rounded p-2">[failed to render {esc(ctype)}]</div>')


def render(components: List[Dict[str, Any]], profile: Any = None) -> str:
    """Render a list of ROTE-adapted primitive dicts into a web HTML fragment."""
    inner = "".join(render_one(c) for c in (components or []) if isinstance(c, dict))
    return f'<div class="dynamic-renderer space-y-3">{inner}</div>'


# ---------------------------------------------------------------------------
# Feature 028 — workspace fragments (contracts/ws-workspace-protocol.md)
# ---------------------------------------------------------------------------

def render_component_fragment(component: Dict[str, Any]) -> str:
    """Render one top-level workspace component wrapped in its identity anchor.

    The ``data-component-id`` wrapper is the morph target for ``ui_upsert``
    ops on the web client (replace-node-by-id, else append). Components
    without an identity render unwrapped (legacy behavior preserved).
    """
    if not isinstance(component, dict):
        return ""
    cid = component.get("component_id")
    inner = render_one(component)
    if not cid:
        return inner
    return f'<div class="astral-component" data-component-id="{_attr(cid)}">{inner}</div>'


def render_workspace(components: List[Dict[str, Any]], profile: Any = None) -> str:
    """Render the full workspace with per-component identity wrappers.

    Used for canvas-targeted full renders (re-hydration, timeline views,
    device re-adapt) so every top-level component remains an upsert target.
    Markup is identical to :func:`render` except for the wrappers.
    """
    inner = "".join(render_component_fragment(c) for c in (components or []) if isinstance(c, dict))
    return f'<div class="dynamic-renderer space-y-3">{inner}</div>'
