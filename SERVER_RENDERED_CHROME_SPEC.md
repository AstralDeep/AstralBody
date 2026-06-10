# Spec: Server-Rendered AstralDeep Chrome (UI parity with the former React app)

> **Status:** Specification only — *no implementation in this pass* (per user direction).
> **Delivery approach (user-selected):** **server-rendered chrome** (SDUI all the way up), not a vanilla-JS client app.
> **Recommended formalization:** turn this into a Spec Kit feature (e.g. `027-server-rendered-chrome`) via `/speckit-specify`, then `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`.

## Context

Feature 026 removed the React/Vite SPA and moved UI delivery to the backend: `astralprims` defines primitives, the orchestrator's `backend/webrender/` renders them to HTML, ROTE adapts per device. That work is **correct for the canvas *content*** — the 25 primitive renderers reproduce the live `DynamicRenderer.tsx` output (cards, tables, charts, metrics, alerts, etc.).

What it did **not** rebuild is the **application chrome** — the entire frame the user actually sees. The current `backend/webrender/templates/shell.html` is a placeholder two-pane layout (full-height canvas left, full-height chat right) with a tiny `client.js` that even **ignores** the WS messages carrying the chrome's data (`system_config`, `agent_list`, `history_list`). As a result the running UI "looks and acts nothing like" the former app (confirmed against 20 reference screenshots in `Desktop/Astral Screenshots/`).

This spec defines what must be built to restore visual + behavioral parity with the former React app, rendered server-side.

**Reference screenshots** (`C:\Users\sear234\Desktop\Astral Screenshots\`): Login, Dashboard, Processing Request, UI After Finished Request (+Condense), Agents Modal, Agent Permissions Modal, Audit Log Modal, Audit Entry, LLM Settings Modal, Settings Modal, Personalization Modal (Soul/Schedule/Dreaming), Onboarding Tour 1–2, User Guide, Admin Tool Quality Modal, Admin Tutorial Editor Modal.

## Goal / Definition of Done

The web UI served on `:8001` looks and behaves like the former React app: the **AstralDeep sidebar**, **top bar**, **dashboard empty-state with suggestion cards**, **floating chat panel docked bottom-right**, the **canvas component-flow chrome** (N-components header, Compact/Condense, per-component toolbar + feedback + Pin-to-UI), and the **modal suite** (Settings → Audit / LLM / Personalization; Agents; Agent Permissions; Create-Agent wizard; Onboarding tour; User Guide; tooltips) — all server-rendered, wired to the data the backend already provides.

---

## Architecture: server-rendered chrome + thin client runtime

The chrome is **rendered server-side** by the orchestrator and **pushed as HTML**; the browser runs a **thin runtime** (not an app) that (a) swaps named regions, (b) relays user intent as WS events, and (c) handles the few behaviors that are inherently client-side (hover tooltips, onboarding spotlight geometry, drag, Plotly init, theme CSS-vars, file/mic). This honors Constitution II ("astralprims defines → orchestrator renders → ROTE adapts"): the orchestrator renders, the client is plumbing.

### Region model
The page is a fixed set of **named regions** the server renders independently and the client mounts/swaps by id:
- `#region-sidebar` — left nav
- `#region-topbar` — header
- `#region-canvas` — dashboard empty-state OR component-flow (the existing primitive renderers fill the component bodies)
- `#region-chat` — floating chat panel (collapsed FAB or expanded)
- `#region-modal` — modal layer (empty, or one modal's HTML)
- `#region-overlay` — onboarding spotlight / tooltips layer

The orchestrator renders each region from data it already holds, and pushes **region-targeted updates**.

### Protocol additions (extend `backend/shared/protocol.py`)
Add a region-scoped render message (additive; existing `ui_render`/`ui_stream_data` for the canvas content stay as-is):
```
{ "type": "chrome_render", "region": "sidebar|topbar|canvas|chat|modal|overlay", "html": "<…>", "mode": "replace|append" }
```
And new client→server `ui_event` actions the orchestrator must handle (each renders + pushes the affected region):
`open_settings`, `close_modal`, `open_modal:{audit|llm|personalization|agents|agent_permissions|create_agent|user_guide}`, `toggle_sidebar`, `new_chat`, `select_chat:{id}`, `delete_chat:{id}`, `search_chats:{q}`, `open_agents`, `tour_{start|next|back|skip|step}`, plus the **already-handled** `chat_message`, `table_paginate`, `save_component`, `combine_components`, `condense_components`, `save_theme`, `stream_subscribe`, `set_agent_permissions`, etc. (see `orchestrator.handle_ui_message`).

### Per-session view state
The orchestrator tracks light per-session UI state (which modal is open, sidebar collapsed, active chat, onboarding step) keyed by the websocket — analogous to how `ROTE` and `ui_sessions` are already keyed by `websocket`. Most chrome data (agents, tools, history) is already in `system_config` / `agent_list` / `history_list`, so regions render directly from existing data.

### Where chrome rendering lives
New server module **`backend/webrender/chrome/`** (the orchestrator's render layer), NOT new app-specific primitives in `astralprims` (astralprims stays a general primitive library):
- `chrome/layout.py` — the shell skeleton (the 6 regions) served by `GET /`.
- `chrome/sidebar.py`, `chrome/topbar.py`, `chrome/dashboard.py`, `chrome/chat_panel.py`, `chrome/component_flow.py`.
- `chrome/modals/` — `settings.py`, `audit.py`, `llm.py`, `personalization.py`, `agents.py`, `agent_permissions.py`, `create_agent.py`, `user_guide.py`, `onboarding.py`, `tooltips.py`.
Each is a pure-Python render function (same pattern + `esc()` escaping as `webrender/renderer.py`). The dynamic **content inside** canvas/chat continues to use the existing `astralprims` primitive renderers.

> **Constitution note:** This keeps astralprims general-purpose and puts app chrome in the orchestrator's render layer — consistent with Principle II ("the orchestrator renders"). If a reviewer insists chrome be expressed as astralprims primitives, an alternative is to add a small set of generic layout primitives (e.g. `Sidebar`, `Modal`, `FloatingPanel`) to astralprims; **recommended: keep chrome in webrender** to avoid bloating the shared package with app-specific UI.

---

## Chrome inventory — what to build (with structure, classes, data, interactions)

Visual spec is the former React source (now only in git: `git show HEAD:frontend/src/...`) and the screenshots. Astral theme + Tailwind classes already self-hosted in `webrender/static/`. Reuse the exact class strings below for parity.

### 1. Layout shell (`chrome/layout.py`, replaces the current `shell.html` body)
Root `div.h-dvh.flex.overflow-hidden.bg-astral-bg.relative` containing: `#region-sidebar` (aside), a `flex-1 flex flex-col` column with `#region-topbar` (header) + `#region-canvas` (main), then fixed-position `#region-chat`, `#region-modal`, `#region-overlay`. Keep the existing `<head>` (self-hosted Tailwind config + astral.css + Plotly + token injection).

### 2. Sidebar (`chrome/sidebar.py`)
`aside` `w-64` (expanded) / `w-16` (icon rail), `bg-astral-surface/30 backdrop-blur-xl border-r border-white/5`, collapsible. Sections:
- **Brand** (`h-14 border-b border-white/5`): AstralDeep logo + hamburger toggle (→ `toggle_sidebar`).
- **STATUS**: Orchestrator (Connected/Disconnected, green/red, Wifi icon), Agents N active (Bot icon, `text-astral-accent`), Tools Enabled X/Y (Wrench, `text-astral-secondary`). Data: connection state + `system_config.agents` count + `system_config.total_tools` (+ per-agent permissions for enabled count).
- **Agents N connected** row → `open_agents`.
- **Settings** row → `open_settings`.
- **+ New Chat** button → `new_chat`.
- **RECENT CHATS**: search input (→ `search_chats`) + list from `history_list` (title, date, saved-components grid icon, active highlight, delete-on-hover → `delete_chat`); click → `select_chat`.
- **Sign Out** → `/auth/logout`.

### 3. Top bar (`chrome/topbar.py`)
`header h-14 border-b border-white/5 bg-astral-bg/80 backdrop-blur-md`: mobile hamburger + `LayoutDashboard` icon + "Dashboard" label; centered logo on mobile.

### 4. Dashboard empty-state (`chrome/dashboard.py`, rendered into `#region-canvas` when no components)
Centered gradient logo tile (`Sparkles`), "AstralDeep" h2, the welcome paragraph, and the **4 suggestion cards** (hardcoded strings — they live in the frontend today, not the backend): "Get me all patients over 30 and graph their ages", "What is my system's CPU and memory usage?", "Search Wikipedia for artificial intelligence", "Show me disk usage information". Each card click → `chat_message` with that text. Grid `grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg`.

### 5. Floating chat panel (`chrome/chat_panel.py`, region `#region-chat`)
- **Collapsed**: FAB `fixed bottom-4 right-4 z-40 w-14 h-14 rounded-full bg-gradient-to-br from-astral-primary to-astral-secondary` (MessageSquare) + unread badge.
- **Expanded**: `fixed bottom-4 right-4 z-40 w-[380px] sm:w-[420px] max-h-[70vh] bg-astral-bg/95 backdrop-blur-xl border border-white/10 rounded-2xl`.
  - Header: agent/Chat title + status (`Thinking…`/`Executing…` from `chat_status`, `animate-pulse`) + minimize.
  - Messages: user bubble (`bg-astral-primary/20 border-astral-primary/30 rounded-xl rounded-tr-sm`), assistant bubble (`bg-white/5 border-white/10 rounded-tl-sm` + Bot icon), chat-step trail (`chat_step`), text-only / agent-unavailable banners.
  - Input bar: attachment (Paperclip → REST `/api/upload`), mic (Mic), tools-picker (Wrench → tool-selection), text input, send (→ `chat_message`).

### 6. Canvas component-flow chrome (`chrome/component_flow.py`, wraps the existing primitive render output)
- Toolbar (when ≥1 component): gradient Layers tile + "N component(s)"; **Compact/Expanded** toggle; **Condense** button (≥2) → `condense_components`.
- Responsive grid of component cards; "New response" dividers between `chat_id` groups.
- Per-component card: title, hover toolbar (fullscreen, delete → `delete_saved_component`), **FeedbackControl** overlay (thumbs, feature 004 → `component_feedback`), **Pin to UI** (`save_component`), drag-to-combine (→ `combine_components`). The component **body** is the existing `webrender.render(...)` output.

### 7. Modals (`chrome/modals/`, region `#region-modal`; shell `fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center`, card `bg-astral-surface border border-white/10 rounded-xl shadow-2xl`)
Each: trigger (a `ui_event`) → orchestrator renders modal HTML → pushes `chrome_render region=modal`; `close_modal` clears it. Data sources already exist (below).

| Modal | Open via | Card width | Data (existing) |
|---|---|---|---|
| Settings menu | `open_settings` | `max-w-sm` | static; sections ACCOUNT / HELP / ADMIN TOOLS |
| Audit log (+ detail drawer) | `open_modal:audit` | `max-w-5xl` | `GET /api/audit`, `GET /api/audit/{id}`; `audit_append` live |
| LLM settings | `open_modal:llm` | `max-w-2xl` | `POST /api/llm/test`, `POST /api/llm/list-models`; per-device localStorage |
| Personalization (Soul/Schedule/Dreaming) | `open_modal:personalization` | `max-w-2xl` | `GET/PUT /api/personalization/profile`, `/api/schedule*`, `/api/memory*`, `/api/dreaming*` |
| Agents list | `open_agents` | `max-w-4xl` | `agent_list` / `GET /api/agents`; tabs My/Public/Drafts |
| Agent Permissions | `open_modal:agent_permissions:{id}` | `max-w-lg` | `GET/PUT /api/agents/{id}/permissions`, credentials, oauth, visibility |
| Create-Agent wizard (4 steps + test WS) | from Agents modal | `max-w-4xl` | `POST /api/agents/drafts*` (generate/test/refine/approve) |
| User Guide (TOC + content) | `open_modal:user_guide` | `max-w-6xl` | static content (16 sections) |
| Onboarding tour (14 steps) | auto / `tour_start` | `max-w-md` popover | `GET /api/tutorial/steps`, `PUT /api/onboarding/state`, dismiss/replay |
| Tooltips | hover `data-tooltip-key` | — | static `tooltipCatalog` |

### 8. Login screen (`chrome/login.py` or static)
Centered AstralDeep card, "Sign in to access the dashboard", "Sign in with SSO" → `/auth/login`. Served when no session (server-side OIDC already exists in `web_auth.py`).

---

## Thin client runtime (`webrender/static/client.js` — expand, don't replace the protocol)
Responsibilities only:
1. **Mount + region swap**: on `chrome_render`, swap `#region-{region}` innerHTML (or append); on `ui_render`/`ui_stream_data` keep current canvas/chat behavior.
2. **Event relay**: delegate clicks/inputs on `[data-ui-action]` elements → send `{type:"ui_event", action, payload}`. (Replaces today's ad-hoc handlers with one generic delegator; keep param_picker/pagination/file-upload helpers.)
3. **Inherently-client behaviors**: hover tooltips, onboarding spotlight geometry (`clip-path` + `scrollIntoView` + `ResizeObserver` around `data-tour-target`), drag-to-combine pointer tracking, Plotly init from `.astral-chart`, theme CSS-var application (`theme_apply`/`color_picker`), file picker, mic.
4. Keep WS lifecycle (reconnect, `register_ui`, stream `seq`/`stream_id` merge).
The client must now **act on** `system_config`/`agent_list`/`history_list`/`rote_config` (today ignored) — but only insofar as the *server* re-renders regions; simplest is for the orchestrator to push `chrome_render` for sidebar/canvas after those arrive, so the client just swaps.

---

## Data contract (already provided by the backend — reuse)
On WS connect the orchestrator already sends `rote_config`, `user_preferences`, `system_config` (`agents[]`, `total_tools`, `streamable_tools`), `agent_list` (`tools_available_for_user`, `agents[]`), `history_list` (`chats[]`); during chat: `chat_status`, `chat_step`, `ui_render`/`ui_stream_data`. REST routers exist for audit, llm, personalization/schedule/memory/dreaming, agents/permissions/credentials/oauth/drafts, onboarding/tutorial, chats/steps. **Suggestion cards are hardcoded** (frontend); **status counts are derived** from `system_config`. No new endpoints needed for the core chrome; the work is rendering + wiring the new `ui_event` actions to region renders.

## Reuse (do not rebuild)
- `backend/webrender/renderer.py` (25 primitive renderers) — canvas/chat content.
- `backend/rote/` — device adaptation (unchanged).
- `backend/orchestrator/web_auth.py` — server-side OIDC (login screen + session token).
- All existing REST routers + WS message producers (`system_config`, `agent_list`, `history_list`, `chat_status`, `chat_step`).
- Self-hosted Tailwind + Plotly + `astral.css` in `webrender/static/`.
- Astral theme tokens / class strings from `git show HEAD:frontend/src/...` and `tailwind.config`.

---

## Recommended phasing (within the eventual feature)
1. **Shell + regions + sidebar + topbar + dashboard empty-state** (the recognizable frame) + thin-client region-swap + generic event delegator.
2. **Floating chat panel** (FAB/expand, bubbles, steps, status, input) replacing the current right-pane.
3. **Canvas component-flow chrome** (N-components header, Compact/Condense, per-component toolbar, feedback, Pin-to-UI, response dividers; drag-to-combine last).
4. **Settings menu + Audit + LLM + Personalization + Agents + Agent Permissions** modals.
5. **Onboarding tour (14-step) + User Guide + tooltips**.
6. **Create-Agent wizard** (4-step + live test WS) — largest; can trail.

## Key risks / open decisions
- **Per-session UI view state** server-side (open modal, sidebar, active chat, tour step) — define where it lives (keyed by websocket like `ui_sessions`).
- **Round-trip latency** for purely-visual toggles (sidebar collapse, modal open) — acceptable, but consider letting the client toggle obviously-local visual state (e.g. sidebar width, modal close) without a server round-trip while keeping data-bearing actions server-driven.
- **Onboarding spotlight + tooltips + drag** are inherently client-geometry — must live in the thin runtime even though content is server-rendered.
- **Create-Agent wizard** uses a live test WebSocket to a draft agent — heaviest piece; spec it carefully or defer.
- **Constitution II framing** — confirm chrome-in-webrender (recommended) vs chrome-as-astralprims-primitives.
- **Suggestions** stay hardcoded (parity) — or optionally move to a backend constant for future configurability.

## Verification (when implemented)
- **Golden-HTML tests** per chrome region/modal (extend `backend/tests/webrender/`), escaping included.
- **Headless serving/integration tests** (extend `tests/test_webui_serving.py`) for `GET /` shell + each `ui_event` → `chrome_render` round-trip (via FastAPI TestClient with a stubbed orchestrator session).
- **Real-browser parity pass** against each of the 20 screenshots: login, dashboard empty-state, processing, finished + condense, and every modal.
- Existing feature-026 suite (109 passing) must stay green.

## Next step
Formalize this as a Spec Kit feature: `/speckit-specify` → "Server-rendered AstralDeep chrome for UI parity" (likely `027-…`), then `/speckit-plan`, `/speckit-tasks`, `/speckit-implement`. This document is the comprehensive input for that spec.
