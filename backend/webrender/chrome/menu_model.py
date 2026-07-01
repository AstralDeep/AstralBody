"""Feature 042 — the server-owned chrome model: the single source of truth for
the top bar + settings menu that EVERY client renders.

Constitution II/XII: the application chrome is described ONCE, here. The web
renderer (``topbar.render_topbar``) turns this model into HTML; the
``chrome_menu`` WS frame and ``GET /api/chrome/menu`` serialize the SAME model
(``ChromeModel.to_dict``) for the native Windows/Android clients (and any future
client, e.g. iOS). There is no second menu definition anywhere — a client is a
thin consumer of this model, never a parallel reimplementation.

The model is role-filtered and feature-flag-resolved BEFORE serialization, so a
client renders exactly what it receives and never sees an item it must not (the
admin group is simply absent for non-admins). Server-side authorization
(``chrome_events`` + surface ``ADMIN_ONLY``) stays authoritative regardless of
what any client displays.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Bumped when the wire shape changes; clients ignore unknown fields and degrade
# gracefully rather than fail (data-model.md forward-compat rule).
MODEL_VERSION = 1


@dataclass(frozen=True)
class SurfaceRef:
    """A reference to a settings surface opened via the ``chrome_open`` action."""

    surface: str
    params: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {"surface": self.surface, "params": dict(self.params)}


@dataclass(frozen=True)
class TopBarControl:
    """One control in the top bar. ``kind`` is one of brand|status|action|menu.

    ``brand``/``status`` are non-interactive; ``action`` opens ``action``'s
    surface via ``chrome_open``; ``menu`` (the gear) toggles the client's local
    settings dropdown (no server round-trip).
    """

    key: str
    kind: str
    label: Optional[str] = None
    icon: Optional[str] = None  # semantic id (gear|history|sparkle); clients map to their own asset
    action: Optional[SurfaceRef] = None

    def to_dict(self) -> Dict:
        d: Dict = {"key": self.key, "kind": self.kind}
        if self.label is not None:
            d["label"] = self.label
        if self.icon is not None:
            d["icon"] = self.icon
        if self.action is not None:
            d["action"] = self.action.to_dict()
        return d


@dataclass(frozen=True)
class MenuItem:
    """One selectable Settings entry."""

    key: str
    label: str
    surface: str
    params: Dict = field(default_factory=dict)
    admin_only: bool = False

    def to_dict(self) -> Dict:
        return {
            "key": self.key,
            "label": self.label,
            "surface": self.surface,
            "params": dict(self.params),
            "admin_only": self.admin_only,
        }


@dataclass(frozen=True)
class MenuGroup:
    """A labeled, ordered group of items (rendered heading + items)."""

    key: str
    label: str
    items: Tuple[MenuItem, ...]
    admin_only: bool = False

    def to_dict(self) -> Dict:
        return {
            "key": self.key,
            "label": self.label,
            "admin_only": self.admin_only,
            "items": [i.to_dict() for i in self.items],
        }


@dataclass(frozen=True)
class SignOutItem:
    """The always-last, visually-distinct (red) sign-out entry.

    ``action="logout"`` — clients perform a real server logout then return to
    the sign-in entry point (web: ``GET /auth/logout``; native: the equivalent
    logout round-trip).
    """

    key: str = "signout"
    label: str = "Sign out"
    style: str = "danger"
    action: str = "logout"

    def to_dict(self) -> Dict:
        return {"key": self.key, "label": self.label, "style": self.style, "action": self.action}


@dataclass(frozen=True)
class ChromeModel:
    """The complete chrome description a client needs to render."""

    topbar: Tuple[TopBarControl, ...]
    menu: Tuple[MenuGroup, ...]
    signout: SignOutItem
    version: int = MODEL_VERSION

    def to_dict(self) -> Dict:
        return {
            "version": self.version,
            "topbar": [c.to_dict() for c in self.topbar],
            "menu": [g.to_dict() for g in self.menu],
            "signout": self.signout.to_dict(),
        }


# ---------------------------------------------------------------------------
# The ONE canonical inventory. Order here IS the order on every client. These
# are the exact labels/surfaces the web has shipped (topbar._menu_entries), now
# promoted to the single source of truth all clients consume.
# ---------------------------------------------------------------------------
_ACCOUNT_ITEMS: Tuple[MenuItem, ...] = (
    MenuItem("agents", "Agents & permissions", "agents"),
    MenuItem("llm", "LLM settings", "llm"),
    MenuItem("personalization", "Personalization", "personalization"),
    MenuItem("audit", "Audit log", "audit"),
    MenuItem("theme", "Theme", "theme"),
)
_HELP_ITEMS: Tuple[MenuItem, ...] = (
    MenuItem("tour", "Take the tour", "tour"),
    MenuItem("guide", "User guide", "guide"),
)
_ADMIN_ITEMS: Tuple[MenuItem, ...] = (
    MenuItem("tool-quality", "Tool quality", "admin_tools", {"tab": "quality"}, admin_only=True),
    MenuItem("tutorial-admin", "Tutorial admin", "admin_tools", {"tab": "tutorial"}, admin_only=True),
)


def _resolve_pulse(pulse_enabled: Optional[bool]) -> bool:
    if pulse_enabled is not None:
        return bool(pulse_enabled)
    try:  # lazy import keeps this module import-cheap and easy to unit-test
        from dreaming.pulse import pulse_enabled as _pe
        return bool(_pe())
    except Exception:
        return False


def build_menu_model(roles: Optional[List[str]] = None, *, pulse_enabled: Optional[bool] = None) -> ChromeModel:
    """Build the role-filtered, flag-resolved chrome model.

    Args:
        roles: the session's verified roles. ``"admin"`` unlocks the ADMIN TOOLS
            group. Anything falsy ⇒ no admin group.
        pulse_enabled: override for the Pulse control's presence (tests). When
            ``None``, resolved from ``FF_PULSE_DIGEST`` via ``dreaming.pulse``.

    Returns:
        A :class:`ChromeModel` ready to render (web) or serialize (native).
    """
    roles = roles or []
    is_admin = "admin" in roles
    show_pulse = _resolve_pulse(pulse_enabled)

    topbar: List[TopBarControl] = [
        TopBarControl("brand", "brand"),
        TopBarControl("status", "status"),
    ]
    if show_pulse:
        topbar.append(
            TopBarControl("pulse", "action", label="Pulse digest", icon="sparkle",
                          action=SurfaceRef("pulse"))
        )
    topbar.append(
        TopBarControl("timeline", "action", label="Workspace timeline", icon="history",
                      action=SurfaceRef("workspace_timeline"))
    )
    topbar.append(TopBarControl("settings", "menu", label="Settings", icon="gear"))

    groups: List[MenuGroup] = [
        MenuGroup("account", "Account", _ACCOUNT_ITEMS),
        MenuGroup("help", "Help", _HELP_ITEMS),
    ]
    if is_admin:
        groups.append(MenuGroup("admin", "Admin tools", _ADMIN_ITEMS, admin_only=True))

    return ChromeModel(topbar=tuple(topbar), menu=tuple(groups), signout=SignOutItem())


def menu_model_dict(roles: Optional[List[str]] = None, *, pulse_enabled: Optional[bool] = None) -> Dict:
    """Convenience: ``build_menu_model(...).to_dict()`` for the REST/WS channels."""
    return build_menu_model(roles, pulse_enabled=pulse_enabled).to_dict()
