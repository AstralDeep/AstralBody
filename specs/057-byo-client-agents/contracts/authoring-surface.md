# Contract: `agent_authoring` Chrome Surface

**Purpose**: deliver the guided, hybrid 5-phase authoring + management experience as **one** server-driven chrome surface with cross-client parity (FR-001/002/022/031, Constitution II/XII). No client-side wizard.

## Surface

- Module `backend/webrender/chrome/surfaces/authoring.py`, surface key `agent_authoring`, registered in `surfaces/__init__.py::SURFACE_MODULES`.
- Exports **both** `render(orch, user_id, roles, params)` (web `ChromeRender` HTML) **and** `components(...)` (native `ChromeSurface` SDUI, ROTE-adapted) — from day one, so parity holds on web/Windows/Android/Apple. (Contrast `drafts.py`/`agents.py`, which are HTML-only and degrade to a placeholder on native.)
- `chrome_events._render_surface` already branches on `_device_type`; `_NATIVE_SDUI_DEVICE_TYPES = (windows, android, ios, macos)` **excludes the watch** → FR-023 needs zero new code (just: add no watch entry).

## Phase state machine (re-render-on-handler-return)

Phases: `specify → clarify → plan → tasks → analyze → generate`. State persists on the `draft_agents` row (see data-model). Each phase submit is a `chrome_*` action auto-dispatched by `chrome_events._is_chrome_action`:

| Handler | Effect |
|---------|--------|
| `chrome_author_specify` | Persist edited Specify artifact; advance to `clarify`. |
| `chrome_author_clarify` | Persist answers. **Hard gate**: if unresolved ambiguity remains, re-return `clarify` + plain-language notice; else advance to `plan`. |
| `chrome_author_plan` | Persist the tool/scope/data mapping; advance to `tasks`. |
| `chrome_author_tasks` | Persist the task breakdown; advance to `analyze`. |
| `chrome_author_analyze` | Run `agent_analyze.check`. **Hard gate**: on violations, re-return `analyze` + per-principle plain-language notices; on pass, stamp `constitution_version`, advance to `generate`. |
| `chrome_author_generate` | Only reachable after Analyze passes. Calls `generate_code`, then the delivery seam (contracts/agent-tunnel + registry). |

- **Hybrid authoring**: each phase renders an **assistant-drafted, user-editable** artifact (the assistant proposes; the user edits before submit).
- Every handler returns `("agent_authoring", {session_id, ...}, notice)` → the surface re-renders at the current/next phase (native: fresh `chrome_surface` with the notice as a prepended Alert; web: `chrome_render` HTML).
- **Structural gate guarantee**: because `chrome_author_generate` is reachable only from a passed `analyze`, an Analyze failure cannot produce code (FR-003).

## Management (US5)

- The same surface lists the user's agents with derived `running/offline` status (FR-025), and offers revise (re-enters authoring at `specify`, prior version keeps running until re-validated — FR-026) and delete (stops the host agent, removes routing — FR-027).
- **No share/publish control exists** on the surface (FR-020, Constitution K).

## Non-host clients (FR-024)

- On web/Android/iOS (and the MAS macOS build), the surface authors + manages fully, and shows an explicit **"runs on your desktop host; offline when none is online"** state driven by `host_last_seen_at` — including an honest "no desktop host connected" state.

## Reuse

- Feature-043 device-target surface plumbing (`chrome_events._render_surface`, `ChromeRender`/`ChromeSurface`, `_sdui` helpers, `notice_block`), the `chrome_*` dispatch namespace, and `drafts.py`/`agents.py` as structural references (extended, not forked).
