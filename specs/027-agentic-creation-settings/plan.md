# Implementation Plan: Agentic Agent/Tool Creation & Top-Bar Settings Menu

**Branch**: `027-agentic-creation-settings` | **Date**: 2026-06-10 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/027-agentic-creation-settings/spec.md`

## Summary

Two coordinated deliverables on top of the 026 server-driven UI:

1. **Agentic creation** — orchestrator meta-tools (`create_capability`, `extend_agent`) injected
   into the chat LLM's tool list let the assistant act on capability gaps autonomously: create a
   draft agent (or a revision draft of a live owned agent) through the existing 012 lifecycle,
   self-test it against the user's originating request on a `VirtualWebSocket`, and present
   approve / refine / discard in-chat. Approval runs the existing security gate; live-agent
   revisions re-pass the gate before a backed-up, rollback-safe swap.
2. **Top-bar settings menu** — a persistent, role-gated top bar + grouped settings menu rendered
   server-side into the shell at `GET /`, with every management surface (Agents & permissions,
   Drafts, LLM, Personalization, Audit, Theme, Tour, User guide, Admin tools, Sign out) rendered
   by a new `backend/webrender/chrome/` layer and delivered over a new additive `chrome_render`
   WS message; surface interactions round-trip as `ui_event` actions handled by a dedicated
   `chrome_events.py` dispatcher calling the same internals as the existing REST routers.

Design decisions and their evidence are in [research.md](research.md) (D1–D10).

## Technical Context

**Language/Version**: Python 3.11 (container runtime; ruff pinned `target-version=py311`), plain ES5-compatible JS for the thin client (no build step)
**Primary Dependencies**: FastAPI, websockets, astralprims (defines primitives), existing OpenAI-compatible LLM client (`_call_llm`), Presidio (existing, 025 PHI gate). **No new third-party dependencies** (Constitution V).
**Storage**: PostgreSQL — existing tables; schema delta: 5 nullable/defaulted columns on `draft_agents` (idempotent `ALTER ... IF NOT EXISTS` in `_init_db()`, Constitution IX)
**Testing**: pytest (in-container against Postgres; skip-if-no-DB markers locally), webrender golden/structural tests, FastAPI TestClient, Playwright real-browser E2E (Constitution X)
**Target Platform**: Linux container (single deployable on `:8001`), browsers via server-rendered web target
**Project Type**: web service (backend-only; UI delivered by backend)
**Performance Goals**: settings menu opens with zero server round-trip; surface open p95 < 1s on LAN; auto-create+self-test within SC-001's 10-minute budget (LLM-bound)
**Constraints**: chrome must not enter the ROTE/astralprims pipeline (web-only); FR-018 wire contract untouched; escape-by-default everywhere (esc()); admin gating server-side
**Scale/Scope**: ~10 chrome surfaces, ~25 new ui_event actions, 2 meta-tools, 1 WS message type, ~5 draft_agents columns

## Constitution Check

*GATE: passed pre-Phase-0; re-checked post-design.*

| Principle | Status | Notes |
|---|---|---|
| I Python backend | PASS | All new backend code Python; client.js additions are render-layer output assets (explicitly permitted by II) |
| II UI delivery architecture | PASS | astralprims defines (unchanged) → orchestrator renders (webrender + new chrome layer) → ROTE adapts content per device; chrome is orchestrator render-layer output for the web target; no SPA reintroduced |
| III Testing ≥90% changed code | PASS (planned) | Golden/structural tests per chrome renderer; dispatcher unit tests per action; lifecycle integration tests; coverage measured in-container |
| IV Code quality | PASS | ruff (py311 target) over all new Python; client.js kept lint-clean ES5 style |
| V Dependencies | PASS | Zero new third-party deps |
| VI Documentation | PASS (planned) | Docstrings on every render fn + handler; chrome renderer documents its target (web) |
| VII Security | PASS | Admin role enforced server-side at shell render AND per handler; meta-tool dispatch behind ownership checks; revisions re-pass security gate; esc() everywhere; secrets untouched |
| VIII UX consistency | PASS | Astral theme tokens reused; primitives embedded in surfaces rendered by the existing renderer |
| IX DB migrations | PASS | Idempotent ALTERs in `_init_db()` (established pattern), rollback documented in data-model.md |
| X Production readiness | PASS (planned) | Real-browser E2E gate before completion; structured logs on every chrome/creation failure path; no stubs |

## Project Structure

### Documentation (this feature)

```text
specs/027-agentic-creation-settings/
├── plan.md              # This file
├── research.md          # Phase 0 (D1–D10)
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── chrome-ws-protocol.md    # chrome_render + ui_event action contracts
│   ├── agentic-creation.md      # meta-tool schemas + lifecycle/audit contract
│   └── settings-surfaces.md     # per-surface data + action contract
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── webrender/
│   ├── chrome/
│   │   ├── __init__.py          # render_topbar(), render_menu(), render_modal_shell()
│   │   ├── topbar.py            # top bar + static settings menu (role-gated)
│   │   ├── surfaces/
│   │   │   ├── __init__.py      # SURFACE_RENDERERS registry {key -> render fn}
│   │   │   ├── agents.py        # Agents & permissions (list, tabs, permissions, credentials, visibility)
│   │   │   ├── drafts.py        # drafts list + create-agent flow + revision review
│   │   │   ├── llm.py           # LLM settings (form, test, models)
│   │   │   ├── personalization.py  # soul / memory / skills / schedule / dreaming tabs
│   │   │   ├── audit.py         # audit list + detail
│   │   │   ├── theme.py         # presets + per-key color pickers (embeds primitives)
│   │   │   ├── tour.py          # tour payload renderer
│   │   │   ├── guide.py         # user guide (TOC + sections)
│   │   │   └── admin_tools.py   # tool quality + tutorial admin
│   │   └── guide_content.py     # ported static user-guide content
│   ├── templates/shell.html     # + #astral-topbar (server-filled) + #astral-modal root
│   └── static/client.js         # + chrome runtime (menu kbd/close, chrome_render, data-ui-action, tour)
├── orchestrator/
│   ├── chrome_events.py         # ui_event dispatcher: chrome_open/chrome_close + surface actions
│   ├── agentic_creation.py      # meta-tools, gap dedup, auto-create + self-test, revision flow
│   ├── orchestrator.py          # hook lines only: meta-tool injection, dispatch intercept, chrome_events hook, shell topbar fill
│   ├── agent_lifecycle.py       # + revise_live_agent() / apply_revision() (clone, gate, swap, rollback)
│   └── api.py                   # (unchanged routes; internals reused by chrome_events)
├── shared/
│   ├── protocol.py              # + ChromeRender message
│   ├── database.py              # + draft_agents ALTERs (origin, source_chat_id, gap_fingerprint, revises_agent_id, self_test)
│   └── feature_flags.py         # + agentic_creation (FF_AGENTIC_CREATION, default on)
├── audit/schemas.py             # + 'agent_lifecycle' event class
└── tests/
    ├── chrome/                  # golden/structural tests per surface + topbar + menu gating
    ├── test_chrome_events.py    # dispatcher unit tests (each action; admin rejection)
    ├── test_agentic_creation.py # meta-tool injection, dedup, self-test, approve/refine/discard, revision swap+rollback
    └── test_ws_chrome_protocol.py  # chrome_render message shape; FR-018 untouched
```

**Structure Decision**: Backend-only web service. New code is isolated in `webrender/chrome/`,
`chrome_events.py`, and `agentic_creation.py`; `orchestrator.py` gains only small hook points
(meta-tool injection in the tools_desc build, a `__orchestrator__` dispatch intercept, one
dispatcher hook in `handle_ui_message`, topbar injection in `serve_shell`) to minimize contention
with the 5,600-line module.

## Phase 1 highlights (details in contracts/)

- **WS protocol**: one additive message `chrome_render {type, region: "modal"|"topbar", html, mode:
  "replace"}`. Existing `ui_render`/`ui_update`/`ui_stream_data` untouched (FR-018).
- **ui_event actions** (new, all handled in `chrome_events.py`): `chrome_open {surface, params?}`,
  `chrome_close`, plus surface actions enumerated in contracts/settings-surfaces.md
  (e.g. `chrome_perms_save`, `chrome_visibility_set`, `chrome_credentials_save`,
  `chrome_llm_test`, `chrome_llm_models`, `chrome_profile_save`, `chrome_memory_delete`,
  `chrome_skill_toggle`, `chrome_job_pause`, `chrome_dreaming_toggle`, `chrome_audit_page`,
  `chrome_theme_preset`, `chrome_tour_event`, `chrome_admin_step_save`, …) and creation actions
  (`draft_approve`, `draft_refine`, `draft_discard`, `revision_apply`, `revision_discard`).
- **Meta-tools** (contracts/agentic-creation.md): `create_capability {name, description,
  tools_spec[]}` and `extend_agent {agent_id, instruction}`; injected when
  `flags.is_enabled("agentic_creation")` and not a draft-test session; dispatch intercepts
  pseudo-agent `__orchestrator__`.
- **Roles**: shell render reads roles from the server session (mock-auth admin path preserved);
  every admin handler re-checks via the existing `_extract_roles` pattern.

## Complexity Tracking

No constitutional violations. The one structural liberty — chrome rendered outside the
astralprims primitive system — is the constitution-sanctioned division of labor (the orchestrator
renders; astralprims only defines primitives, and app chrome is not a reusable primitive), as
recorded in research.md D4 and the chrome spec's recommendation.
