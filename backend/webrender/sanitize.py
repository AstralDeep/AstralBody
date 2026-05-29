"""Feature 026 — the narrow, sanitized rich-text opt-in (FR-017 / SC-008).

Everything here is **escape-first**: input is HTML-escaped before any markdown
transform, so untrusted text can never inject markup. Only a small, fixed set of
safe inline/block markdown constructs is then re-introduced as known-safe tags.
This is the ONLY path in the renderer that emits formatting from text content;
all other text goes through ``html.escape`` directly.
"""
from __future__ import annotations

import html
import re
from typing import Any

_ALLOWED_URL = re.compile(r"^(https?://|mailto:|/)", re.IGNORECASE)


def _esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _safe_url(url: str) -> str:
    s = (url or "").strip()
    return s if _ALLOWED_URL.match(s) else "#"


# Inline patterns operate on ALREADY-ESCAPED text (so markup chars are inert).
_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_STRIKE = re.compile(r"~~([^~]+)~~")
_EM = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)|(?<!_)_([^_]+)_(?!_)")


def inline_md(text: Any) -> str:
    """Render a small set of inline markdown on escaped text:
    `code`, [text](url), **bold**/__bold__, ~~strike~~, *em*/_em_."""
    s = _esc(text)
    s = _CODE.sub(lambda m: f'<code class="text-astral-accent bg-white/5 px-1 rounded">{m.group(1)}</code>', s)

    def _link(m):
        label, url = m.group(1), _safe_url(m.group(2))
        # url came from the original (pre-escape) string already escaped by _esc; it's safe in an attr
        return (f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
                f'class="text-astral-primary hover:text-astral-secondary hover:underline">{label}</a>')

    s = _LINK.sub(_link, s)
    s = _BOLD.sub(lambda m: f'<strong class="text-astral-text">{m.group(1) or m.group(2)}</strong>', s)
    s = _STRIKE.sub(lambda m: f"<del>{m.group(1)}</del>", s)
    s = _EM.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", s)
    return s


def block_md(text: Any) -> str:
    """Render a compact, safe subset of block markdown: fenced code blocks,
    ATX headings, unordered/ordered lists, blockquotes, and paragraphs with
    inline markdown. Escape-by-default throughout."""
    if text is None or text == "":
        return ""
    src = str(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = src.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    def flush_para(buf: list[str]):
        if buf:
            joined = "<br>".join(inline_md(b) for b in buf)
            out.append(f'<p class="mb-2">{joined}</p>')
            buf.clear()

    para: list[str] = []
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # fenced code block
        if stripped.startswith("```"):
            flush_para(para)
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            lang_html = (f'<div class="px-4 py-2 border-b border-white/5 text-xs text-astral-muted">{_esc(lang)}</div>'
                         if lang else "")
            code = _esc("\n".join(code_lines))
            out.append(f'<div class="rounded-lg bg-black/40 border border-white/5 overflow-hidden my-2">{lang_html}'
                       f'<pre class="p-4 text-sm overflow-x-auto"><code class="text-green-400">{code}</code></pre></div>')
            continue

        # headings
        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            flush_para(para)
            level = len(m.group(1))
            cls = {1: "text-2xl font-bold text-astral-text",
                   2: "text-xl font-semibold text-astral-text",
                   3: "text-lg font-medium text-astral-text"}[level]
            out.append(f'<h{level} class="{cls} mb-2">{inline_md(m.group(2))}</h{level}>')
            i += 1
            continue

        # blockquote
        if stripped.startswith(">"):
            flush_para(para)
            quote_lines = []
            while i < n and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip()[1:].strip())
                i += 1
            inner = "<br>".join(inline_md(q) for q in quote_lines)
            out.append(f'<blockquote class="border-l-2 border-astral-primary/40 pl-3 text-astral-text/80 my-2">{inner}</blockquote>')
            continue

        # lists
        if re.match(r"^[-*]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            flush_para(para)
            ordered = bool(re.match(r"^\d+\.\s+", stripped))
            items = []
            while i < n:
                ls = lines[i].strip()
                mm = re.match(r"^(?:[-*]|\d+\.)\s+(.*)$", ls)
                if not mm:
                    break
                items.append(f'<li class="leading-relaxed">{inline_md(mm.group(1))}</li>')
                i += 1
            tag = "ol" if ordered else "ul"
            lcls = "list-decimal" if ordered else "list-disc"
            out.append(f'<{tag} class="space-y-1 text-sm {lcls} list-inside text-astral-text my-2">{"".join(items)}</{tag}>')
            continue

        # blank line ends a paragraph
        if stripped == "":
            flush_para(para)
            i += 1
            continue

        para.append(stripped)
        i += 1

    flush_para(para)
    return "".join(out)
