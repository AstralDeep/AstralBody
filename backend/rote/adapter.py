"""
ROTE Adapter — Stateless component transformation engine.

Takes a list of raw component dicts (as produced by the orchestrator)
and a DeviceProfile, returns a new list adapted for that device.
All transformation is rule-based and synchronous.
"""
from typing import Any, Dict, List, Optional

from rote.capabilities import DeviceProfile, DeviceType


class ComponentAdapter:
    """Stateless, recursive component transformer."""

    @classmethod
    def adapt(cls, components: List[Dict], profile: DeviceProfile) -> List[Dict]:
        """Adapt a top-level list of components for the given device profile."""
        result = []
        for comp in components:
            adapted = cls._adapt_component(comp, profile)
            if adapted is not None:
                result.append(adapted)
        # 033 Wave-0 (C-D2): apply declarative host bounds last — strip
        # interactivity on read-only surfaces and cap action-buttons. No-op
        # under the default host-config (interactive, unlimited actions).
        return cls._enforce_host_limits(result, profile)

    @classmethod
    def _enforce_host_limits(cls, components: List[Dict], profile: DeviceProfile) -> List[Dict]:
        """Bound what a surface renders, per the declarative host-config
        (C-D2). On a non-interactive (read-only) surface every action-button is
        dropped; otherwise, when ``max_actions`` is set, action-buttons past the
        budget are dropped (deepest-tree order preserved). This is a security
        bound: a compromised agent cannot exceed the host's action budget on a
        given surface. Returns the components unchanged when nothing applies."""
        read_only = not getattr(profile, "supports_interactivity", True)
        max_actions = getattr(profile, "max_actions", 0) or 0
        if not read_only and max_actions <= 0:
            return components
        budget = [max_actions if max_actions > 0 else None]

        def walk(node):
            if not isinstance(node, dict):
                return node
            if node.get("type") == "button" and node.get("action"):
                if read_only:
                    return None
                if budget[0] is not None:
                    if budget[0] <= 0:
                        return None
                    budget[0] -= 1
                return node
            out = dict(node)
            for key in ("children", "content"):
                if isinstance(out.get(key), list):
                    out[key] = [w for w in (walk(c) for c in out[key]) if w is not None]
            if isinstance(out.get("tabs"), list):
                new_tabs = []
                for tab in out["tabs"]:
                    if isinstance(tab, dict) and isinstance(tab.get("content"), list):
                        tab = {**tab, "content": [w for w in (walk(c) for c in tab["content"]) if w is not None]}
                    new_tabs.append(tab)
                out["tabs"] = new_tabs
            return out

        return [w for w in (walk(c) for c in components) if w is not None]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _adapt_component(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
        """Adapt a single component dict. Returns None to remove the component."""
        if not isinstance(comp, dict):
            return comp

        comp_type = comp.get("type", "")

        # ---- VOICE: collapse everything to text ----
        if profile.device_type == DeviceType.VOICE:
            text = cls._extract_text(comp)
            if text:
                return {"type": "text", "content": text[:profile.max_text_chars] if profile.max_text_chars else text, "variant": "body"}
            return None

        # ---- Dispatch by component type ----
        if comp_type in ("bar_chart", "line_chart", "pie_chart", "plotly_chart"):
            return cls._adapt_chart(comp, profile)

        if comp_type == "table":
            return cls._adapt_table(comp, profile)

        if comp_type == "grid":
            return cls._adapt_grid(comp, profile)

        if comp_type == "collapsible":
            return cls._adapt_collapsible(comp, profile)

        if comp_type == "tabs":
            return cls._adapt_tabs(comp, profile)

        if comp_type == "code":
            return cls._adapt_code(comp, profile)

        if comp_type in ("file_upload", "file_download"):
            return cls._adapt_file_io(comp, profile)

        if comp_type == "text":
            return cls._adapt_text(comp, profile)

        if comp_type == "button":
            return cls._adapt_button(comp, profile)

        if comp_type == "skeleton":
            return cls._adapt_skeleton(comp, profile)

        if comp_type == "chat_history":
            return cls._adapt_chat_history(comp, profile)

        # Recurse into known container types
        if comp_type in ("container", "card"):
            return cls._adapt_container(comp, profile)

        # Everything else passes through
        return comp

    # ------------------------------------------------------------------
    # Per-type adaptation
    # ------------------------------------------------------------------

    @classmethod
    def _adapt_chart(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
        if profile.supports_charts:
            return comp

        # Degrade chart → metric card
        comp.get("type", "chart")
        title = comp.get("title", "Result")

        # Try to extract a single meaningful value
        value = cls._extract_chart_value(comp)
        return {
            "type": "metric",
            "title": title,
            "value": str(value),
            "subtitle": f"(chart condensed for {profile.device_type.value})",
        }

    @classmethod
    def _extract_chart_value(cls, comp: Dict) -> Any:
        """Pull a representative single value from a chart component."""
        comp_type = comp.get("type", "")
        if comp_type == "pie_chart":
            data = comp.get("data", [])
            labels = comp.get("labels", [])
            if data:
                idx = data.index(max(data))
                label = labels[idx] if idx < len(labels) else "value"
                return f"{label}: {data[idx]}"
        # bar/line/plotly — use first dataset first value
        datasets = comp.get("datasets", [])
        if datasets:
            first = datasets[0]
            data = first.get("data", [])
            label = first.get("label", "")
            if data:
                return f"{label}: {data[0]}" if label else data[0]
        # plotly raw data
        plotly_data = comp.get("data", [])
        if plotly_data and isinstance(plotly_data, list):
            first = plotly_data[0]
            y = first.get("y", [])
            if y:
                return y[0]
        return "N/A"

    @classmethod
    def _adapt_table(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
        if not profile.supports_tables:
            # Degrade table → list of key items
            headers = comp.get("headers", [])
            rows = comp.get("rows", [])
            max_rows = profile.max_table_rows or len(rows)
            max_cols = profile.max_table_cols or len(headers)
            trimmed = rows[:max_rows]
            items = []
            for row in trimmed:
                parts = []
                for i, cell in enumerate(row[:max_cols]):
                    if i < len(headers):
                        parts.append(f"{headers[i]}: {cell}")
                    else:
                        parts.append(str(cell))
                items.append(" | ".join(parts))
            return {"type": "list", "items": items, "ordered": False}

        # Still supports tables — trim rows/cols if needed
        headers = comp.get("headers", [])
        rows = comp.get("rows", [])

        if profile.max_table_cols and len(headers) > profile.max_table_cols:
            headers = headers[: profile.max_table_cols]
            rows = [r[: profile.max_table_cols] for r in rows]

        if profile.max_table_rows and len(rows) > profile.max_table_rows:
            rows = rows[: profile.max_table_rows]

        result = {**comp, "headers": headers, "rows": rows}
        return result

    @classmethod
    def _adapt_grid(cls, comp: Dict, profile: DeviceProfile) -> Dict:
        columns = comp.get("columns", 2)
        capped = min(columns, profile.max_grid_columns)
        children = comp.get("children", [])
        adapted_children = [
            c for c in (cls._adapt_component(ch, profile) for ch in children) if c is not None
        ]
        if capped <= 1:
            # Collapse to a container
            return {"type": "container", "children": adapted_children}
        return {**comp, "columns": capped, "children": adapted_children}

    @classmethod
    def _adapt_collapsible(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
        if not profile.supports_tabs:  # same "richness" gate as tabs
            # Flatten: return children directly as a card
            content = comp.get("content", [])
            adapted = [
                c for c in (cls._adapt_component(ch, profile) for ch in content) if c is not None
            ]
            return {
                "type": "card",
                "title": comp.get("title", ""),
                "content": adapted,
            }
        # Recurse into content
        content = comp.get("content", [])
        adapted = [
            c for c in (cls._adapt_component(ch, profile) for ch in content) if c is not None
        ]
        return {**comp, "content": adapted}

    @classmethod
    def _adapt_tabs(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
        if not profile.supports_tabs:
            # Keep only first tab, flatten to card
            tabs = comp.get("tabs", [])
            if not tabs:
                return None
            first = tabs[0]
            content = first.get("content", [])
            adapted = [
                c for c in (cls._adapt_component(ch, profile) for ch in content) if c is not None
            ]
            return {
                "type": "card",
                "title": first.get("label", ""),
                "content": adapted,
            }
        tabs = comp.get("tabs", [])
        adapted_tabs = []
        for tab in tabs:
            tab_content = tab.get("content", [])
            adapted_content = [
                c for c in (cls._adapt_component(ch, profile) for ch in tab_content) if c is not None
            ]
            adapted_tabs.append({**tab, "content": adapted_content})
        return {**comp, "tabs": adapted_tabs}

    @classmethod
    def _adapt_code(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
        if not profile.supports_code:
            return None
        return comp

    @classmethod
    def _adapt_file_io(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
        if not profile.supports_file_io:
            return None
        return comp

    @classmethod
    def _adapt_text(cls, comp: Dict, profile: DeviceProfile) -> Dict:
        if not profile.max_text_chars:
            return comp
        content = comp.get("content", "")
        if len(content) > profile.max_text_chars:
            content = content[: profile.max_text_chars - 1] + "…"
        return {**comp, "content": content}

    @classmethod
    def _adapt_button(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
        # TV and voice: remove interactive inputs
        if profile.device_type in (DeviceType.TV, DeviceType.VOICE):
            return None
        # Watch: keep only primary buttons
        if profile.device_type == DeviceType.WATCH:
            if comp.get("variant", "primary") != "primary":
                return None
        return comp

    @classmethod
    def _adapt_skeleton(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
        """Feature 037 — cap the loading-skeleton's placeholder row count on
        small surfaces so it fits a watch/phone (VOICE is handled earlier by
        text collapse). Other targets pass through unchanged."""
        try:
            count = int(comp.get("count", 4))
        except (TypeError, ValueError):
            count = 4
        caps = {DeviceType.WATCH: 3, DeviceType.MOBILE: 5}
        cap = caps.get(profile.device_type)
        if cap is not None and count > cap:
            return {**comp, "count": cap}
        return comp

    @classmethod
    def _adapt_chat_history(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
        """Feature 040 — condense the recent-chats surface on small screens.

        The full row (avatar + title + preview + time) is right for
        browser/tablet/TV; a watch has no room for previews and few rows, and a
        phone's history rail is short — so trim the item count and, on a watch,
        drop the preview snippet. The web renderer already treats ``preview`` as
        optional, so stripping it just yields a tighter row. VOICE is handled
        earlier by text collapse; other targets pass through unchanged.
        """
        items = [i for i in (comp.get("items") or []) if isinstance(i, dict)]
        caps = {DeviceType.WATCH: 4, DeviceType.MOBILE: 10}
        cap = caps.get(profile.device_type)
        if cap is None:
            return comp
        trimmed = items[:cap]
        if profile.device_type == DeviceType.WATCH:
            trimmed = [{k: v for k, v in it.items() if k != "preview"} for it in trimmed]
        return {**comp, "items": trimmed}

    @classmethod
    def _adapt_container(cls, comp: Dict, profile: DeviceProfile) -> Dict:
        """Recurse into card.content or container.children."""
        if comp.get("type") == "card":
            content = comp.get("content", [])
            adapted = [
                c for c in (cls._adapt_component(ch, profile) for ch in content) if c is not None
            ]
            return {**comp, "content": adapted}
        # container
        children = comp.get("children", [])
        adapted = [
            c for c in (cls._adapt_component(ch, profile) for ch in children) if c is not None
        ]
        return {**comp, "children": adapted}

    # ------------------------------------------------------------------
    # Text extraction (for VOICE profile)
    # ------------------------------------------------------------------

    @classmethod
    def _extract_text(cls, comp: Dict) -> str:
        """Recursively extract all human-readable text from a component."""
        parts: List[str] = []
        comp_type = comp.get("type", "")

        if comp_type == "text":
            parts.append(comp.get("content", ""))

        elif comp_type == "metric":
            title = comp.get("title", "")
            value = comp.get("value", "")
            subtitle = comp.get("subtitle", "")
            parts.append(f"{title}: {value}" + (f" ({subtitle})" if subtitle else ""))

        elif comp_type == "alert":
            title = comp.get("title", "")
            msg = comp.get("message", "")
            parts.append(f"{title}: {msg}" if title else msg)

        elif comp_type == "table":
            headers = comp.get("headers", [])
            rows = comp.get("rows", [])
            if headers:
                parts.append(", ".join(str(h) for h in headers))
            for row in rows:
                parts.append(", ".join(str(c) for c in row))

        elif comp_type in ("bar_chart", "line_chart", "pie_chart", "plotly_chart"):
            title = comp.get("title", "chart")
            value = cls._extract_chart_value(comp)
            parts.append(f"{title}: {value}")

        elif comp_type == "list":
            items = comp.get("items", [])
            for item in items:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(cls._extract_text(item))

        elif comp_type == "code":
            lang = comp.get("language", "")
            parts.append(f"[Code block: {lang}]")

        elif comp_type in ("card", "collapsible"):
            if comp.get("title"):
                parts.append(str(comp["title"]))

        elif comp_type == "badge":
            parts.append(comp.get("label", ""))

        elif comp_type == "hero":
            for key in ("eyebrow", "title", "subtitle"):
                if comp.get(key):
                    parts.append(str(comp[key]))
            badges = [b for b in comp.get("badges", []) if isinstance(b, str)]
            if badges:
                parts.append(", ".join(badges))

        elif comp_type == "keyvalue":
            if comp.get("title"):
                parts.append(str(comp["title"]))
            for item in comp.get("items", []):
                if isinstance(item, dict):
                    parts.append(f"{item.get('label', '')}: {item.get('value', '')}")

        elif comp_type == "timeline":
            if comp.get("title"):
                parts.append(str(comp["title"]))
            for item in comp.get("items", []):
                if isinstance(item, dict):
                    entry = str(item.get("title", ""))
                    if item.get("time"):
                        entry = f"{item['time']} — {entry}"
                    if item.get("description"):
                        entry = f"{entry}: {item['description']}"
                    parts.append(entry)

        elif comp_type == "rating":
            label = comp.get("label", "rating")
            value = comp.get("value", 0)
            max_value = comp.get("max_value", 5)
            parts.append(f"{label}: {value} out of {max_value} stars")

        elif comp_type == "chat_history":
            # Feature 040 — voice surfaces speak the recent-chats list so the
            # user hears which conversations they can reopen.
            parts.append(str(comp.get("title") or "Recent chats"))
            titles = [str(it.get("title")).strip()
                      for it in (comp.get("items") or [])
                      if isinstance(it, dict) and it.get("title")]
            if titles:
                parts.append(": " + "; ".join(titles))
            else:
                parts.append(": no conversations yet")

        elif comp_type == "skeleton":
            # Feature 037 — voice surfaces speak the loading state.
            parts.append(str(comp.get("label") or "Loading"))

        elif comp_type == "button":
            # Feature 037 — speak actionable labels (e.g. chat-history items)
            # so voice users hear what they can open.
            parts.append(comp.get("label", ""))

        # Recurse into children/content/tabs
        for key in ("children", "content"):
            for child in comp.get(key, []):
                if isinstance(child, dict):
                    t = cls._extract_text(child)
                    if t:
                        parts.append(t)

        for tab in comp.get("tabs", []):
            if isinstance(tab, dict):
                label = tab.get("label", "")
                if label:
                    parts.append(label)
                for child in tab.get("content", []):
                    if isinstance(child, dict):
                        t = cls._extract_text(child)
                        if t:
                            parts.append(t)

        return " ".join(p.strip() for p in parts if p.strip())
