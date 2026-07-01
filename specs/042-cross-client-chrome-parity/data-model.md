# Phase 1 Data Model: Cross-Client Chrome & Settings Parity

The chrome model is **computed, not stored** — there is no new table. It is a role-aware, flag-resolved projection built each time from server state. This document defines its shape and serialization so every client renders identically.

## Entity: ChromeModel

The complete description a client needs to render its top bar + Settings menu.

| Field | Type | Notes |
|-------|------|-------|
| `version` | int | Schema version for forward-compat (start at `1`). Clients ignore unknown fields. |
| `topbar` | `TopBarControl[]` | Ordered left→right. |
| `menu` | `MenuGroup[]` | Ordered; the Settings dropdown groups. |
| `signout` | `SignOutItem` | The always-last, visually-distinct sign-out entry. |

## Entity: TopBarControl

One control in the top bar. Order is significant.

| Field | Type | Notes |
|-------|------|-------|
| `key` | string | Stable id: `brand`, `status`, `pulse`, `timeline`, `settings`. |
| `kind` | enum | `brand` \| `status` \| `action` \| `menu`. |
| `label` | string? | Accessible label (e.g. "Workspace timeline", "Settings", "Pulse digest"). |
| `icon` | string? | Semantic icon id (`gear`, `history`, `sparkle`); clients map to their own asset. |
| `action` | `SurfaceRef?` | For `action`/`menu` kinds — the surface to open (e.g. `{surface:"workspace_timeline"}`). `settings` toggles the local dropdown (no server action). |
| `present` | bool | Server-resolved visibility (e.g. `pulse` present only when `FF_PULSE_DIGEST`). Absent controls are omitted entirely, so `present` is always `true` in the emitted model — the field documents intent for tests. |

Canonical order: `brand`, `status`, `pulse` (conditional), `timeline`, `settings`.

## Entity: MenuGroup

| Field | Type | Notes |
|-------|------|-------|
| `key` | string | `account` \| `help` \| `admin`. |
| `label` | string | Display heading, rendered uppercase by clients: "Account", "Help", "Admin tools". |
| `admin_only` | bool | `true` for the `admin` group. Server omits admin-only groups for non-admins, so an emitted group is always permitted for the recipient. |
| `items` | `MenuItem[]` | Ordered. |

Canonical groups/order: `account` (agents, llm, personalization, audit, theme) → `help` (tour, guide) → `admin` (tool-quality, tutorial-admin; admins only).

## Entity: MenuItem

| Field | Type | Notes |
|-------|------|-------|
| `key` | string | Stable id: `agents`, `llm`, `personalization`, `audit`, `theme`, `tour`, `guide`, `tool-quality`, `tutorial-admin`. |
| `label` | string | Exact display text ("Agents & permissions", "LLM settings", …). |
| `surface` | string | Surface module key opened via `chrome_open` (`agents`, `llm`, `personalization`, `audit`, `theme`, `tour`, `guide`, `admin_tools`). |
| `params` | object | Extra params for the surface (e.g. `{"tab":"quality"}` for Tool quality). |
| `admin_only` | bool | Convenience mirror of the group's flag for flat clients. |

## Entity: SignOutItem

| Field | Type | Notes |
|-------|------|-------|
| `key` | string | `signout`. |
| `label` | string | "Sign out". |
| `style` | enum | `danger` (clients render red). |
| `action` | string | `logout` — clients perform a real server logout then return to sign-in. |

## Entity: ChromeSurface (SDUI surface payload)

Delivered when a menu item is opened on a native SDUI target (P2). Web keeps HTML during transition; converted surfaces render from the same `components`.

| Field | Type | Notes |
|-------|------|-------|
| `surface_key` | string | Which surface (`agents`, `theme`, …). |
| `title` | string | Modal/sheet title (surface `TITLE`). |
| `components` | `Component[]` | `astralprims` component dicts (`.to_dict()`), ROTE-adapted for the device. |
| `admin_only` | bool | Echoes the surface's `ADMIN_ONLY`; server still enforces. |

`Component` is the existing SDUI wire node (`type` + attributes + children + optional `id`) already consumed by every client's renderer — **no new component contract is introduced**; surfaces compose from the existing vocabulary.

## Serialization rules

- All keys/labels/order come from the single builder in `webrender/chrome/menu_model.py`; `topbar.py`, the `chrome_menu` WS frame, and `GET /api/chrome/menu` all serialize the **same** `ChromeModel.to_dict()`.
- Labels are emitted verbatim (already-escaped only at HTML render time on the web; native clients receive raw text and escape/format per platform).
- The model is role-filtered and flag-resolved **before** serialization; clients never receive items they must not see.
- Forward-compat: clients MUST ignore unknown `topbar.kind`, `menu` keys, or `component.type` values and degrade gracefully (labeled placeholder) rather than fail.

## State & transitions

- The model is rebuilt on: initial `register_ui` (bootstrap), a role change, and a feature-flag change affecting a control (e.g. Pulse). On rebuild, the orchestrator re-emits `chrome_menu` to the affected sockets so clients re-render without a reload (SC-005).
- No persisted state for the menu itself. Theme preference persists in `user_preferences.theme` (existing).

## Migration impact

None expected (computed model). Any future stored field ships as an idempotent guarded `_init_db` delta with rollback (Constitution IX).
