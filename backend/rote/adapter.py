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
        return result

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
        chart_type = comp.get("type", "chart")
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
        # Voice: remove all buttons (no visual UI)
        if profile.device_type == DeviceType.VOICE:
            return None
        # TV: keep only primary buttons (user can select with remote/D-pad)
        if profile.device_type == DeviceType.TV:
            if comp.get("variant", "primary") != "primary":
                return None
        # Watch: keep only primary buttons
        if profile.device_type == DeviceType.WATCH:
            if comp.get("variant", "primary") != "primary":
                return None
        return comp

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
