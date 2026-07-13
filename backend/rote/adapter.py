"""
ROTE Adapter — Stateless component transformation engine.

Takes a list of raw component dicts (as produced by the orchestrator)
and a DeviceProfile, returns a new list adapted for that device.
All transformation is rule-based and synchronous.
"""
from typing import Any, Dict, List, Optional

from rote import fallback, lod
from rote.capabilities import DeviceProfile, DeviceType


class ComponentAdapter:
    """Stateless, recursive component transformer."""

    @classmethod
    def adapt(cls, components: List[Dict], profile: DeviceProfile) -> List[Dict]:
        """Adapt a top-level list of components for the given device profile."""
        # Level-of-detail ladder (C-D10): when FF_LOD_LADDER is on, collapse any
        # component that authored an L1/L2/L3 ``lod`` ladder down to the rung the
        # surface warrants (watch/voice → L1, mobile → L2, browser/tablet/tv →
        # L3) BEFORE the per-type adaptation runs, so the rest of the pipeline
        # sees only the level-appropriate content. Default OFF → untouched.
        if lod.lod_enabled():
            try:
                device = cls._lod_device(profile)
                components = [cls._apply_lod(c, device) for c in components]
            except Exception:
                # Fail-open: never let LOD resolution break adaptation.
                pass

        result = []
        for comp in components:
            adapted = cls._adapt_component(comp, profile)
            if adapted is not None:
                result.append(adapted)
        # Substitute any primitive the target can't render down the fallback
        # ladder (timeline→list, chart→table→text, …). No-op when
        # supported_types is None (full support).
        supported = getattr(profile, "supported_types", None)
        if supported:
            result = [cls._degrade_unsupported(c, supported) for c in result]
        # Apply declarative host bounds last — strip interactivity on read-only
        # surfaces and cap action-buttons. No-op under the default host-config
        # (interactive, unlimited actions).
        return cls._enforce_host_limits(result, profile)

    # Capability fallback ladder

    @classmethod
    def _carry_identity(cls, src: Dict, out: Dict) -> Dict:
        """Copy identity fields onto a rebuilt/substituted component (055 US1):
        a degraded component must stay addressable — clients key canvases and
        purge welcome content by ``component_id ?? id``, and upsert morphs
        target the same identity. ``provenance`` is a preserved field too
        (055 US4, wire-contract §6): a degrade/collapse must never strip the
        server-stamped trust mark."""
        for key in ("id", "component_id", "provenance"):
            if comp_val := src.get(key):
                out.setdefault(key, comp_val)
        return out

    @classmethod
    def _degrade_unsupported(cls, comp: Dict, supported) -> Dict:
        """Render ``comp`` as a type the target supports, substituting down the
        fallback ladder when its own type is unsupported. Recurses so a
        supported container with an unsupported child still degrades. Pure.
        Identity fields survive substitution (_carry_identity)."""
        if not isinstance(comp, dict):
            return comp
        ctype = str(comp.get("type", "")).strip().lower()
        target = fallback.first_supported(ctype, supported)
        if target == ctype:
            return cls._degrade_children(comp, supported)
        if target == "text":
            return cls._carry_identity(comp, {
                "type": "text",
                "content": cls._extract_text(comp) or str(comp.get("title") or ""),
                "variant": "body"})
        if target == "list":
            return cls._carry_identity(comp, cls._to_list(comp))
        if target == "table":
            return cls._carry_identity(comp, cls._to_table(comp, supported))
        if target in ("container", "card"):
            wrapped = {"type": target,
                       "content": comp.get("content") or comp.get("children") or []}
            if comp.get("title"):
                wrapped["title"] = comp["title"]
            return cls._carry_identity(comp, cls._degrade_children(wrapped, supported))
        return cls._carry_identity(
            comp, {"type": "text", "content": cls._extract_text(comp) or "", "variant": "body"})

    @classmethod
    def _degrade_children(cls, comp: Dict, supported) -> Dict:
        out = dict(comp)
        for key in ("content", "children"):
            kids = comp.get(key)
            if isinstance(kids, list):
                out[key] = [cls._degrade_unsupported(c, supported)
                            for c in kids if isinstance(c, dict)]
        tabs = comp.get("tabs")
        if isinstance(tabs, list):
            out["tabs"] = [
                ({**t, "content": [cls._degrade_unsupported(c, supported)
                                   for c in t["content"] if isinstance(c, dict)]}
                 if isinstance(t, dict) and isinstance(t.get("content"), list) else t)
                for t in tabs
            ]
        return out

    @classmethod
    def _to_list(cls, comp: Dict) -> Dict:
        ctype = str(comp.get("type", "")).strip().lower()
        items: List[str] = []
        if ctype == "timeline":
            for it in (comp.get("items") or []):
                if isinstance(it, dict):
                    parts = [str(it[k]) for k in ("time", "title", "description") if it.get(k)]
                    if parts:
                        items.append(" — ".join(parts))
        elif ctype == "table":
            headers = comp.get("headers") or []
            for row in (comp.get("rows") or []):
                if isinstance(row, list):
                    cells = [f"{headers[i]}: {c}" if i < len(headers) else str(c)
                             for i, c in enumerate(row)]
                    items.append(" | ".join(cells))
        elif ctype == "keyvalue":
            for it in (comp.get("items") or []):
                if isinstance(it, dict):
                    items.append(f"{it.get('label', '')}: {it.get('value', '')}".strip(": "))
        if not items:
            t = cls._extract_text(comp)
            if t:
                items = [t]
        out: Dict[str, Any] = {"type": "list", "ordered": False, "items": items}
        if comp.get("title"):
            out["title"] = comp["title"]
        return out

    @classmethod
    def _to_table(cls, comp: Dict, supported) -> Dict:
        ctype = str(comp.get("type", "")).strip().lower()
        if ctype == "keyvalue":
            rows = [[it.get("label", ""), it.get("value", "")]
                    for it in (comp.get("items") or []) if isinstance(it, dict)]
            out: Dict[str, Any] = {"type": "table", "headers": ["", ""], "rows": rows}
            if comp.get("title"):
                out["title"] = comp["title"]
            return out
        # Charts: only a recognizably-shaped {labels, series} degrades cleanly to
        # a table; otherwise drop to the next rung (list/text).
        data = comp.get("data") if isinstance(comp.get("data"), dict) else comp
        labels = data.get("labels")
        series = data.get("series") or data.get("datasets")
        if isinstance(labels, list) and isinstance(series, list) and series:
            names = [s.get("name") or s.get("label") or f"series {i}" if isinstance(s, dict)
                     else f"series {i}" for i, s in enumerate(series)]
            rows = []
            for ri, lab in enumerate(labels):
                row = [lab]
                for s in series:
                    vals = s.get("data") if isinstance(s, dict) else s
                    row.append(vals[ri] if isinstance(vals, list) and ri < len(vals) else "")
                rows.append(row)
            out = {"type": "table", "headers": ["label", *names], "rows": rows}
            if comp.get("title"):
                out["title"] = comp["title"]
            return out
        if "list" in supported:
            return cls._to_list(comp)
        return {"type": "text", "content": cls._extract_text(comp) or "", "variant": "body"}

    @classmethod
    def _enforce_host_limits(cls, components: List[Dict], profile: DeviceProfile) -> List[Dict]:
        """Bound what a surface renders, per the declarative host-config. On a
        non-interactive (read-only) surface every action-button is dropped;
        otherwise, when ``max_actions`` is set, action-buttons past the budget
        are dropped (deepest-tree order preserved). This is a security bound: a
        compromised agent cannot exceed the host's action budget on a given
        surface. Returns the components unchanged when nothing applies."""
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

    # Level-of-detail ladder (C-D10)

    #: Component types small enough that their primary text lives in ``content``
    #: (so an authored ``lod`` rung overwrites ``content``). Everything else
    #: writes the resolved rung to ``content`` too — a text node is the universal
    #: carrier — and the LOD ladder is opt-in per component (only acts when an
    #: ``lod`` dict is present), so non-text components are unaffected unless the
    #: author explicitly attached a ladder.
    _LOD_CONTENT_KEY = "content"

    @classmethod
    def _lod_device(cls, profile: DeviceProfile) -> Dict[str, Any]:
        """Bridge a :class:`DeviceProfile` to the plain device model the ``lod``
        module reads (``{device_type, is_small}``). The small-screen surfaces
        (watch, mobile) also set ``is_small`` so the ladder's ``is_small``
        fallback / modality routing stays consistent for callers that omit an
        explicit ``device_type``."""
        dt = profile.device_type.value if profile.device_type else "browser"
        is_small = profile.device_type in (DeviceType.WATCH, DeviceType.MOBILE)
        return {"device_type": dt, "is_small": is_small}

    @classmethod
    def _apply_lod(cls, comp: Any, device: Dict[str, Any]) -> Any:
        """Recursively collapse any ``lod`` ladder on ``comp`` (or its
        descendants) to the rung ``device`` warrants. A component without an
        ``lod`` dict is returned structurally unchanged (children still
        recursed). The resolved rung is written to ``content`` and the consumed
        ``lod`` key is dropped so it never reaches the renderer. Pure."""
        if not isinstance(comp, dict):
            return comp
        out = dict(comp)
        if isinstance(out.get("lod"), dict):
            resolved = lod.pick_content(out, device)
            out.pop("lod", None)
            # Only overwrite when the ladder produced something AND ``content``
            # is not a child list (a container's children must survive). An
            # empty resolution leaves the component's existing content intact.
            if resolved != "" and not isinstance(out.get(cls._LOD_CONTENT_KEY), list):
                out[cls._LOD_CONTENT_KEY] = resolved
        for key in ("content", "children"):
            kids = out.get(key)
            if isinstance(kids, list):
                out[key] = [cls._apply_lod(c, device) for c in kids]
        tabs = out.get("tabs")
        if isinstance(tabs, list):
            new_tabs = []
            for tab in tabs:
                if isinstance(tab, dict) and isinstance(tab.get("content"), list):
                    tab = {**tab, "content": [cls._apply_lod(c, device) for c in tab["content"]]}
                new_tabs.append(tab)
            out["tabs"] = new_tabs
        return out

    # Internal helpers

    @classmethod
    def _adapt_component(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
        """Adapt a single component dict. Returns None to remove the component.

        Identity fields survive every per-type rebuild (055 US1): a chart
        condensed to a metric, a collapsible flattened to a card, etc. must
        stay addressable — clients key canvases (and purge wel_ welcome
        components) by ``component_id ?? id`` and upsert morphs target it.
        """
        result = cls._adapt_component_typed(comp, profile)
        if isinstance(result, dict) and result is not comp and isinstance(comp, dict):
            cls._carry_identity(comp, result)
        return result

    @classmethod
    def _adapt_component_typed(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
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

        if comp_type == "download_card":
            return cls._adapt_download_card(comp, profile)

        # Recurse into known container types
        if comp_type in ("container", "card"):
            return cls._adapt_container(comp, profile)

        # Everything else passes through
        return comp

    # Per-type adaptation

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
            degraded = {"type": "list", "items": items, "ordered": False}
            # Keep the table's name — an anonymous bulleted list gives the
            # wearer no idea what the data is (parity with _to_list).
            if comp.get("title"):
                degraded["title"] = comp["title"]
            return degraded

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
            # Collapse to a container — identity survives (055 US1: the watch
            # purges wel_ welcome components by id, and upsert morphs need the
            # collapsed grid to stay addressable).
            return cls._carry_identity(comp, {"type": "container", "children": adapted_children})
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
        """Cap the loading-skeleton's placeholder row count on small surfaces
        so it fits a watch/phone (VOICE is handled earlier by text collapse).
        Other targets pass through unchanged."""
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
        """Condense the recent-chats surface on small screens.

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
    def _adapt_download_card(cls, comp: Dict, profile: DeviceProfile) -> Optional[Dict]:
        """Adapt the desktop-app download card per surface.

        browser/tablet/TV — full card (button + integrity block).
        mobile — compact card (button + version; drop the collapsible note +
                 the SHA block — the link still carries the verified asset).
        watch — collapse to a single text + link (version only).
        VOICE is handled earlier by text collapse (``_extract_text``).
        """
        if profile.device_type == DeviceType.MOBILE:
            trimmed = {k: v for k, v in comp.items()
                       if k not in ("description", "sha256", "sigstore_bundle_url")}
            return trimmed
        if profile.device_type == DeviceType.WATCH:
            version = comp.get("version") or ""
            url = comp.get("download_url") or comp.get("html_url") or ""
            label = f"Download Astral desktop v{version}" if version else "Download Astral desktop"
            return {"type": "button", "label": label, "url": url} if url else {
                "type": "text", "content": label, "variant": "body"}
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

    # Text extraction (for VOICE profile)

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

        elif comp_type == "image":
            # An image degraded to text must say SOMETHING — without this the
            # watch receives {"type":"text","content":""} and draws nothing.
            alt = comp.get("alt") or comp.get("caption") or comp.get("title") or ""
            parts.append(f"Image: {alt}" if alt else "An image (view it on another device)")

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

        elif comp_type == "download_card":
            title = comp.get("title") or "Astral desktop app"
            version = comp.get("version") or ""
            ver = f", version {version}" if version else ""
            parts.append(
                f"{title}{ver}. Download it from GitHub. Integrity is verified "
                "with a SHA-256 hash and a sigstore signature.")

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
            # Voice surfaces speak the recent-chats list so the user hears which
            # conversations they can reopen.
            parts.append(str(comp.get("title") or "Recent chats"))
            titles = [str(it.get("title")).strip()
                      for it in (comp.get("items") or [])
                      if isinstance(it, dict) and it.get("title")]
            if titles:
                parts.append(": " + "; ".join(titles))
            else:
                parts.append(": no conversations yet")

        elif comp_type == "skeleton":
            # Voice surfaces speak the loading state.
            parts.append(str(comp.get("label") or "Loading"))

        elif comp_type == "button":
            # Speak actionable labels (e.g. chat-history items) so voice users
            # hear what they can open.
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
