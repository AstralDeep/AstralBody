# Implementation Plan: FastAPI-Delivered UI & `astralprims` Primitive Package

**Branch**: `026-frontend-removal-astralprims` | **Date**: 2026-05-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/026-frontend-removal-astralprims/spec.md`
**Re-plan note**: Regenerated against **Constitution v2.0.1** (astralprims **defines**; orchestrator
**renders**; ROTE **adapts**) and three operator directives: (1) install `astralprims` via pip,
(2) update the docker-compose/Docker deploy, (3) delete `frontend/` **only after tests pass**, then let the
backend drive the UI.

## Summary

Remove the standalone React/Vite SPA and drive the UI from the backend. UI primitives move from in-repo
`backend/shared/primitives.py` to the published first-party pip package **`astralprims`** (`pip install
astralprims`, 0.1.0) — a near field-for-field port of the current catalog and the canonical *structured*
representation (FR-018). The **orchestrator** gains a server-side web render layer (`backend/webrender/`,
pure-Python render functions) that turn **ROTE-adapted** primitive dicts into HTML/CSS/JS, served over the *existing* orchestrator
WebSocket protocol to a thin browser client. ROTE (`backend/rote/`) is reused unchanged as the
device-adaptation layer. This matches Constitution v2.0.1 exactly: **astralprims defines → orchestrator
renders → ROTE adapts**.

**Operator directives baked into this plan**:
- **pip**: add `astralprims` to `backend/requirements.txt`; install via pip in dev and in the Docker image.
- **Docker**: drop the Node/Vite build stage and the `:5173` static frontend server; serve everything from
  `:8001`. Concretely edit `Dockerfile`, `docker-compose.yml`, and `backend/start-docker.sh`.
- **Test-gated cutover**: `frontend/` is deleted **only after** the backend-driven UI passes the full test
  suite + real-browser parity pass. Until that gate, `frontend/` stays in place (safe rollback).

## Technical Context

**Language/Version**: Python 3.11+ (backend). Browser client: minimal vanilla JS/CSS (no SPA framework, no
build step).
**Primary Dependencies**: FastAPI, uvicorn, websockets (existing); **`astralprims` (new, first-party, pip)**;
Jinja2 (already in `backend/requirements.txt`); pydantic (transitive via FastAPI — astralprims is
Pydantic-based). **No net-new third-party dependency** beyond first-party `astralprims`.
**Storage**: PostgreSQL (existing). **No schema change**.
**Testing**: pytest (≥90% on changed code, Constitution III); renderer golden-HTML tests; WS-protocol tests;
auth tests; **end-to-end parity pass in a real browser** (Constitution X). React/Vitest suite removed at the
cutover gate (FR-016).
**Target Platform**: Linux server (Docker), single deployable; web browsers as the only client target now.
**Project Type**: Web service with server-side-rendered UI (one app; no separate frontend).
**Performance Goals**: No regression — incremental streaming, no full-page reload (SC-007). The normative bar
is **parity** ("match prior responsiveness", per the spec clarification). The "per-fragment render ≤ ~50ms
p95 typical" figure below is an **illustrative, non-normative** plan-level target to guide implementation, not
a spec Success Criterion.
**Constraints**: Escape-by-default HTML (FR-017/SC-008); ROTE stays a pure dict→dict transform; astralprims
dict tree stays readable by programmatic consumers (FR-018); cutover ordering (tests before deletion).
**Scale/Scope**: ~30 backend modules import `shared.primitives`; 25 primitive types to render; all
user-facing surfaces at full parity; 3 Docker/deploy files to edit; `frontend/` removed at the gate.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Primary Language (Python) | ✅ Pass | Backend + renderer are pure Python. |
| II. UI Delivery Architecture (v2.0.1) | ✅ Pass | astralprims **defines**; orchestrator (`backend/webrender/`) **renders**; ROTE **adapts**. Exactly the amended principle — no deviation. |
| III. Testing Standards (≥90%) | ✅ Pass (planned) | Renderer/protocol/auth covered; coverage gate enforced; cutover gated on green. |
| IV. Code Quality | ✅ Pass | ruff/PEP8; the small vanilla-JS client linted. |
| V. Dependency Management | ✅ Pass | `astralprims` is first-party — document in PR; installed via pip. Jinja2 already present. |
| VI. Documentation | ✅ Pass | astralprims primitives documented upstream; each renderer documents supported targets; FastAPI `/docs` kept. |
| VII. Security | ✅ Pass | Keycloak retained (server-side OIDC code flow); escape-by-default output; RFC 8693 agent delegation unaffected. |
| VIII. User Experience | ✅ Pass | All rendering driven by `astralprims` primitives; Astral theme moves into renderer templates/CSS. |
| IX. Database Migrations | ✅ Pass (N/A) | No schema change. |
| X. Production Readiness | ✅ Pass (planned) | Real-browser parity verification before cutover; no stubs; observability on render/auth failures; clean, test-gated removal of React. |

**Gate result**: PASS — no deviations. (The v2.0.0 Principle II wording concern was resolved by the v2.0.1
amendment, which this plan matches.)

## Project Structure

### Documentation (this feature)

```text
specs/026-frontend-removal-astralprims/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions & rationale (D1–D9)
├── data-model.md        # Phase 1 — primitive catalog, device profile, render/response contracts
├── quickstart.md        # Phase 1 — run, add a renderer, verify parity, test-gated cutover
├── contracts/
│   ├── websocket-protocol.md
│   ├── renderer-interface.md
│   └── http-routes.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
backend/
├── webrender/                  # NEW — orchestrator's server-side web render layer (pure-Python)
│   ├── __init__.py  renderer.py  registry.py  sanitize.py
│   ├── renderer.py             # one render function per primitive type (25); explicit html.escape
│   ├── templates/              # static shell.html (token substituted in)
│   └── static/                 # client.js (thin WS client), astral.css, self-hosted plotly/vendor
├── orchestrator/
│   ├── orchestrator.py         # MODIFY: serve shell + StaticFiles; render in send_ui_render path; OIDC routes
│   └── api.py                  # MODIFY: server-side OIDC login/callback/logout/session routes
├── rote/                       # UNCHANGED — adapts dicts per device (no `style` dependency)
├── shared/
│   └── primitives.py           # DELETE at cutover gate — replaced by `astralprims`
├── agents/**/mcp_tools.py      # MODIFY: import from astralprims; `style=`→`css=` (1 file)
└── requirements.txt            # MODIFY: add `astralprims`

frontend/                       # DELETE at cutover gate (only after tests pass)

Dockerfile                      # MODIFY: remove Stage-1 Node/Vite build + COPY dist + EXPOSE 5173
docker-compose.yml              # MODIFY: remove the "127.0.0.1:5173:5173" port mapping
backend/start-docker.sh         # MODIFY: remove the `python3 -m http.server 5173 …` line
```

**Structure Decision**: Single deployable web service. New rendering code is isolated in
`backend/webrender/` so a future client target is a sibling renderer with no change to astralprims
definitions or agent code (FR-011, SC-005).

## Phased rollout (test-gated cutover per operator directive)

1. **Add package & renderer (non-destructive)** — `pip install astralprims`; build `backend/webrender/`
   (renderer + 25 templates + thin `client.js`); add orchestrator shell/static routes and server-side OIDC;
   wire `send_ui_render` → ROTE → renderer to emit `html` alongside `components`. `frontend/` still present.
2. **Migrate primitive usage** — switch the ~30 `shared.primitives` importers to `astralprims`; fix the one
   `style=`→`css=`; keep `shared/primitives.py` temporarily for safe diffing.
3. **Verify (the gate)** — run `pytest` (≥90% changed-code), renderer golden-HTML + protocol + auth tests,
   and a **real-browser** end-to-end parity pass across every surface (SC-002, SC-006, Constitution X).
4. **Cutover (only if step 3 is green)** — delete `frontend/` and `backend/shared/primitives.py`; edit
   `Dockerfile`/`docker-compose.yml`/`start-docker.sh` to drop the Node build + `:5173`; confirm zero
   references to the old module (SC-003) and that the app is served solely from `:8001` (SC-004).

## Complexity Tracking

No constitution violations. The web renderer lives in the orchestrator (`backend/webrender/`), matching
Constitution v2.0.1 (astralprims defines, orchestrator renders, ROTE adapts).
