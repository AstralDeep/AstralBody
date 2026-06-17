"""VOICE renderer — 033 Wave-3 (C-D4), the highest-novelty empty target.

ROTE has always collapsed a component tree to a flat string for audio surfaces;
this is a real renderer for the ``voice`` target that speaks the *structure* —
a metric as "Revenue: 9 million", a table row by row, a timeline as a sequence
of events — and emits well-formed **SSML** (`<speak>` with `<s>` sentences and
`<break>` between sections) so a TTS engine gets prosody and pacing.

Registered via ``webrender.register_target('voice', render_voice)`` — additive,
no change to astralprims or agents (Constitution II / FR-011). Pure, escape-by-
default, bounded. No new dependency.
"""
from __future__ import annotations

import html as _html
import re as _re
from typing import Any, Dict, List

_MAX_LIST_ITEMS = 12
_MAX_TABLE_ROWS = 8
_MAX_TIMELINE_ITEMS = 10

_CHILD_KEYS = ("content", "children")
_MD = _re.compile(r"[*_`#~\[\]]")  # strip inline markdown punctuation for speech
                                   # (NOT < or > — those must reach SSML escaping)


def _esc(value: Any) -> str:
    """SSML-escape (& < >). Quotes are fine inside text content."""
    return _html.escape("" if value is None else str(value), quote=False)


def _say(text: Any) -> str:
    """A single spoken sentence, or '' when empty."""
    t = _MD.sub("", str("" if text is None else text)).strip()
    return f"<s>{_esc(t)}</s>" if t else ""


_BREAK = '<break time="400ms"/>'


def _join(parts) -> str:
    return _BREAK.join(p for p in parts if p)


def _children_ssml(comp: Dict[str, Any]) -> str:
    out: List[str] = []
    for key in _CHILD_KEYS:
        kids = comp.get(key)
        if isinstance(kids, list):
            out.extend(_speak_one(c) for c in kids if isinstance(c, dict))
    return _join(out)


def _speak_one(comp: Dict[str, Any]) -> str:
    if not isinstance(comp, dict):
        return ""
    t = str(comp.get("type", "")).strip().lower()
    title = comp.get("title")

    if t == "text":
        return _say(comp.get("content"))
    if t == "alert":
        variant = comp.get("variant", "info")
        return _say(f"{variant}: {comp.get('message', '')}")
    if t == "metric":
        bits = [f"{title}: {comp.get('value', '')}" if title else str(comp.get("value", "")),
                comp.get("subtitle")]
        return _say(". ".join(b for b in bits if b))
    if t == "hero":
        return _join([_say(title), _say(comp.get("subtitle"))])
    if t == "badge":
        return _say(comp.get("label"))
    if t == "rating":
        val = comp.get("value", comp.get("rating", ""))
        return _say(f"{title + ': ' if title else ''}{val} out of 5")
    if t == "keyvalue":
        items = [f"{it.get('label', '')} is {it.get('value', '')}"
                 for it in (comp.get("items") or []) if isinstance(it, dict)]
        return _join([_say(title)] + [_say(i) for i in items[:_MAX_LIST_ITEMS]])
    if t == "list":
        items = [str(i.get("text") if isinstance(i, dict) else i)
                 for i in (comp.get("items") or [])]
        spoken = [_say(i) for i in items[:_MAX_LIST_ITEMS]]
        if len(items) > _MAX_LIST_ITEMS:
            spoken.append(_say(f"and {len(items) - _MAX_LIST_ITEMS} more"))
        return _join([_say(title)] + spoken)
    if t == "table":
        return _say_table(comp)
    if t == "timeline":
        rows = []
        for it in (comp.get("items") or [])[:_MAX_TIMELINE_ITEMS]:
            if isinstance(it, dict):
                rows.append(_say(". ".join(str(it[k]) for k in ("time", "title", "description")
                                           if it.get(k))))
        return _join([_say(title)] + rows)
    if t in ("bar_chart", "line_chart", "pie_chart", "plotly_chart"):
        return _say(f"A chart{': ' + str(title) if title else ''}")
    if t == "code":
        return _say(f"A code block{': ' + str(title) if title else ''}")
    if t in ("divider", "skeleton", "image"):
        return ""
    if t == "tabs":
        out = []
        for tab in (comp.get("tabs") or []):
            if isinstance(tab, dict):
                inner = _join(_speak_one(c) for c in (tab.get("content") or [])
                              if isinstance(c, dict))
                out.append(_join([_say(tab.get("label")), inner]))
        return _join(out)
    if t in ("card", "container", "collapsible", "grid"):
        return _join([_say(title), _children_ssml(comp)])
    # Unknown type: best-effort spoken title/content.
    return _join([_say(title), _say(comp.get("content"))])


def _say_table(comp: Dict[str, Any]) -> str:
    headers = comp.get("headers") or []
    rows = comp.get("rows") or []
    out = [_say(comp.get("title"))]
    for ri, row in enumerate(rows[:_MAX_TABLE_ROWS]):
        if not isinstance(row, list):
            continue
        cells = [f"{headers[i]} {c}" if i < len(headers) and headers[i] else str(c)
                 for i, c in enumerate(row)]
        out.append(_say(f"Row {ri + 1}: " + ", ".join(cells)))
    if len(rows) > _MAX_TABLE_ROWS:
        out.append(_say(f"and {len(rows) - _MAX_TABLE_ROWS} more rows"))
    return _join(out)


def render_voice(components: List[Dict[str, Any]], profile: Any = None) -> str:
    """Render a component list to an SSML document for a TTS target."""
    body = _join(_speak_one(c) for c in (components or []) if isinstance(c, dict))
    return f"<speak>{body}</speak>"
