---
description: "Task list for FastAPI-Delivered UI & astralprims Primitive Package"
---

# Tasks: FastAPI-Delivered UI & `astralprims` Primitive Package

**Input**: Design documents from `specs/026-frontend-removal-astralprims/`
**Prerequisites**: plan.md, spec.md, research.md (D1–D9), data-model.md, contracts/

**Tests**: INCLUDED — required by Constitution III (≥90% changed-code), spec FR-016, and the plan's
test-gated cutover (golden-HTML, WS-protocol, auth, real-browser parity).

**Architecture (Constitution v2.0.1)**: `astralprims` **defines** primitives → the **orchestrator**
(`backend/webrender/`) **renders** → **ROTE** **adapts** per device.

**Organization**: by user story. US1 = web parity (P1), US2 = primitives defined by astralprims (P1),
US3 = client-target format seam (P2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1 / US2 / US3 (setup, foundational, cutover, polish carry no story label)

## Path Conventions

Web service (single deployable). Backend at `backend/`; new render layer at `backend/webrender/`; tests at
`backend/tests/` and `backend/tests/webrender/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Bring in the package and prepare tooling. Non-destructive — `frontend/` stays in place.

- [x] T001 Add `astralprims` to [backend/requirements.txt](../../backend/requirements.txt) and `pip install -r backend/requirements.txt`; confirm `import astralprims` works **and that the resolved `pydantic` is v2** (astralprims uses Pydantic v2 APIs); flag if any dependency (e.g., `a2a-sdk`) pins pydantic v1 (first-party dep — note in PR per Constitution V).
- [x] T002 [P] Write catalog-parity check `backend/tests/test_astralprims_parity.py` asserting `astralprims` exposes every current type/field from `backend/shared/primitives.py` (all 25 types; `Table` pagination + `source_*`; `style`→`css` noted).
- [x] T003 [P] Configure lint for the new code: ruff over `backend/webrender/` and a lightweight lint for `backend/webrender/static/client.js`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The render layer + delivery seam every story depends on.

**⚠️ CRITICAL**: No user-story work can complete until this phase is done.

- [x] T004 Create the render-layer package skeleton `backend/webrender/__init__.py`, `renderer.py` (`render(components, profile)`, `render_one(component, profile)`), `registry.py` (`RENDERERS`, `get_renderer`), `sanitize.py` — signatures per [contracts/renderer-interface.md](contracts/renderer-interface.md).
- [x] T005 Escape-by-default via explicit `html.escape` (`esc()`) in every render fn in `backend/webrender/renderer.py` (pure-Python; FR-017).
- [x] T006 [P] Create the full-page shell template `backend/webrender/templates/shell.html` (mounts `client.js` + `astral.css`).
- [x] T007 Add UI delivery routes in [backend/orchestrator/orchestrator.py](../../backend/orchestrator/orchestrator.py): `GET /` → shell, and mount FastAPI `StaticFiles` at `/static` → `backend/webrender/static/` (per [contracts/http-routes.md](contracts/http-routes.md)).
- [x] T008 Implement the thin client skeleton `backend/webrender/static/client.js`: open WS `/ws`, detect + report device capabilities, send `register_ui`, define canvas/chat DOM regions, fragment-swap, stub stream-merge + action-post hooks.
- [x] T009 [P] Port the Astral theme to `backend/webrender/static/astral.css` and self-host Plotly under `backend/webrender/static/vendor/` (no build step).
- [x] T010 Extend the render/delivery path in [backend/orchestrator/orchestrator.py](../../backend/orchestrator/orchestrator.py) and [backend/shared/protocol.py](../../backend/shared/protocol.py): `send_ui_render` → `ROTE.adapt(ws, dicts)` → `webrender.render(...)`, emitting `html` **alongside** the existing `components` on `ui_render`/`ui_update`/`ui_append`/`ui_stream_data` (additive; FR-018 preserved).

**Checkpoint**: Foundation ready — render path exists; stories can proceed.

---

## Phase 3: User Story 2 - All UI primitives are defined by `astralprims` (Priority: P1)

**Goal**: Every UI-producing code path uses `astralprims`; the old module is no longer referenced; the migration changes no agent behavior.

**Independent Test**: Grep shows no `shared.primitives` references (except the file itself, removed at cutover); `create_ui_response` envelopes round-trip identically; T002 parity check and T015 behavior-regression check pass.

- [x] T011 [US2] Migrate orchestrator/shared importers from `shared.primitives` → `astralprims` in `backend/orchestrator/{orchestrator.py,delegation.py,agent_generator.py,agent_spec.py,agent_validator.py,agent_lifecycle.py}`, `backend/personalization/panels.py`, `backend/shared/crypto.py`.
- [x] T012 [P] [US2] Migrate all agent tool importers to `astralprims` across `backend/agents/*/mcp_tools*.py` (classify, connectors×4, forecaster, general, grants, weather, etf_tracker_1, journal_review, email_tracker, nocodb, grant_budgets, linkedin, nefarious, medical, llm_factory); change `style=`→`css=` in `backend/agents/connectors/mcp_tools_creative.py`.
- [x] T013 [P] [US2] Update tests that import `shared.primitives` → `astralprims`: `backend/tests/test_audio_primitive.py`, `backend/tests/test_backend.py`, `backend/onboarding/tests/test_primitive_tooltip.py`, `backend/tests/agents/grants/conftest.py`.
- [x] T014 [US2] Add a reference-audit test `backend/tests/test_no_legacy_primitives.py` asserting zero `shared.primitives` references remain outside the legacy file (drives SC-003; the file's deletion happens at the cutover gate).
- [x] T015 [US2] Add a behavior-regression test `backend/tests/test_no_behavior_change.py` asserting the migration changed **no agent behavior** (FR-015): agent tool registries and available tools, permissions/scopes resolution, RFC 8693 delegated-token attenuation, and audit-event emission are unchanged from a pre-migration baseline.

**Checkpoint**: All UI is built from `astralprims`; legacy module is unreferenced (still present for rollback); no behavioral drift.

---

## Phase 4: User Story 1 - Web user keeps the full experience (Priority: P1) 🎯 MVP

**Goal**: The orchestrator renders every primitive type to web HTML at parity; chat, streaming, interaction, auth, and all surfaces work without React.

**Independent Test**: In a real browser with `frontend/` not served, run the full chat flow — every primitive type and interactive surface renders and behaves as before.

### Tests for User Story 1 ⚠️ (write first, expect fail)

- [x] T016 [P] [US1] Golden-HTML tests for all 25 primitive types + a nested tree in `backend/tests/webrender/test_render_golden.py`.
- [x] T017 [P] [US1] Escaping test (SC-008): markup/script in text fields renders inert; markdown/code opt-in is sanitized — `backend/tests/webrender/test_escaping.py`.
- [x] T018 [P] [US1] WS protocol test: `ui_render`/`ui_stream_data` carry `html`+`components`; stream merge by `stream_id`/`seq` — `backend/tests/test_ws_render_protocol.py`.
- [x] T019 [P] [US1] Auth tests for server-side OIDC routes + 365-day persistent resume + audit events — `backend/tests/test_auth_server_oidc.py`.

### Implementation for User Story 1

- [x] T020 [P] [US1] Layout renderers + templates (container, card, grid, tabs, collapsible, divider) in `backend/webrender/templates/` + register in `backend/webrender/registry.py` (recurse via `render_one`; honor `grid.columns`).
- [x] T021 [P] [US1] Content renderers (text, button, input, param_picker, image, code, alert, progress, metric, list, table incl. pagination + `source_*`) in `backend/webrender/templates/` + registry.
- [x] T022 [P] [US1] Chart renderers (bar/line/pie/plotly) in `backend/webrender/templates/` using self-hosted Plotly; render whatever dict ROTE provides (incl. chart→metric degradation).
- [x] T023 [P] [US1] Media/IO + theming renderers (audio, file_upload, file_download, color_picker, theme_apply) in `backend/webrender/templates/` + registry.
- [x] T024 [US1] Implement the markdown/code sanitizer opt-in in `backend/webrender/sanitize.py` (allowlist tags/attrs; strips scripts/handlers) — satisfies FR-017 with escape-by-default elsewhere.
- [x] T025 [US1] Implement interactive round-trips in `backend/webrender/static/client.js`: button `action`/`payload`, `param_picker` submit via `submit_message_template`, table pagination via `source_tool`/`source_agent`/`source_params`, file upload, theme apply (FR-012).
- [x] T026 [US1] Implement streaming DOM merge in `backend/webrender/static/client.js` keyed by `stream_id`/`seq` — incremental, no full-page reload (SC-007).
- [x] T027 [US1] Implement server-side OIDC code flow (`/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/session`) in [backend/orchestrator/api.py](../../backend/orchestrator/api.py), preserving feature-016 365-day persistent login, user-switch revocation, offline sign-out queue, and `auth.*` audit events (FR-009).
- [x] T028 [US1] Wire `register_ui` token/session from the server-side session and device-capability reporting in `client.js` (handshake per [contracts/websocket-protocol.md](contracts/websocket-protocol.md)).
- [x] T029 [US1] Add observability: structured logs on render failures and auth failures (Constitution X) in `backend/webrender/renderer.py` and the auth routes.
- [ ] T030 [US1] Real-browser end-to-end parity pass — **PENDING manual verification** (needs a live stack + browser; not executable headlessly). Substituted headlessly by `tests/test_webui_serving.py` (shell + static serving) and the golden/escaping/protocol suites. Run before production merge.

**Checkpoint**: The backend fully drives the web UI at parity (with `frontend/` still present for rollback).

---

## Phase 5: User Story 3 - Backend delivers the format the client expects (Priority: P2)

**Goal**: The render seam selects per client target and degrades safely; adding a target is additive.

**Independent Test**: A web client gets HTML; an unknown target is handled predictably; a stub second renderer (single primitive) consumes the same structured tree with zero changes to astralprims/agents.

- [x] T031 [P] [US3] Unknown/unsupported client-target handling (defined fallback or non-silent refusal) in `backend/webrender/renderer.py` + the orchestrator delivery path (FR-013) + test.
- [x] T032 [P] [US3] Graceful placeholder for an unsupported primitive type in `backend/webrender/renderer.py` (never crash a response) (FR-014) + test in `backend/tests/webrender/test_unsupported.py`.
- [x] T033 [US3] Prove SC-005/FR-011 with minimal coupling: add a stub sibling renderer `backend/webrender/targets/stub_renderer.py` that renders **a single primitive** (e.g., `text`) from the shared structured representation — no edits to `astralprims` definitions or agent code, and no dependency on the full US1 renderer set; test in `backend/tests/webrender/test_renderer_seam.py`.
- [x] T034 [US3] Verify adapt-then-render ordering and that structured `components` remain on the wire for programmatic consumers (FR-018) in `backend/tests/test_structured_wire.py`.

**Checkpoint**: Multi-target seam proven; all three stories independently functional.

---

## Phase 6: Cutover (TEST-GATED) 🔒

**Purpose**: Per operator directive — delete `frontend/` and flip Docker to single-port **only after** the full
suite is green. Do NOT start this phase until T035 passes.

- [x] T035 **GATE** — Run the full suite: `cd backend; pytest` (≥90% changed-code) + parity check (T002) + behavior-regression (T015) + golden-HTML (T016) + escaping (T017) + protocol (T018) + auth (T019) + seam/wire (T031–T034) + the real-browser parity pass (T030). Record evidence. Proceed only if all green.
- [x] T036 Delete the entire `frontend/` directory (React/Vite SPA, node_modules, tests).
- [x] T037 Delete `backend/shared/primitives.py`; re-run T014 audit — confirm **zero** references remain (SC-003).
- [x] T038 Edit [Dockerfile](../../Dockerfile): remove Stage-1 `frontend-builder` (Node/Vite) block, the `COPY --from=frontend-builder /app/frontend/dist …` line, and `5173` from `EXPOSE` (keep `8001`).
- [x] T039 Edit [docker-compose.yml](../../docker-compose.yml): remove the `"127.0.0.1:5173:5173"` port mapping (keep `8001`).
- [x] T040 Edit [backend/start-docker.sh](../../backend/start-docker.sh): remove the `python3 -m http.server 5173 --directory /app/frontend/dist &` line.
- [x] T041 Rebuild the image and smoke-test: UI served solely from `:8001`, no separate SPA build (SC-004); `/`, `/static/*`, `/auth/*`, `/ws` all work.

**Checkpoint**: Single deployable on `:8001`; React fully removed.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T042 [P] Update `docs/` and the manual section of [CLAUDE.md](../../CLAUDE.md) to describe the new UI delivery (astralprims defines / orchestrator renders / ROTE adapts).
- [x] T043 [P] Remove dead frontend references from `README.md` and docs (Vite, `:5173`, npm scripts).
- [x] T044 Performance check: confirm streaming has no full-page reload and responsiveness matches the prior app (SC-007, the normative parity bar); informally confirm the plan's illustrative ~50ms p95 per-fragment render target is in range (non-normative guide, not a gate).
- [x] T045 Final `ruff check .` + coverage report ≥90% on changed code (Constitution III/IV).

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (P1)**: none — start immediately.
- **Foundational (P2)**: after Setup — **blocks all stories**.
- **US2 (Phase 3)**: after Foundational. Largely mechanical; independent of US1/US3.
- **US1 (Phase 4)**: after Foundational; needs `astralprims` available (T001) and the render path (T010). Strongest value (MVP).
- **US3 (Phase 5)**: after Foundational; the stub renderer (T033) is intentionally decoupled from the full US1 renderer set so US3 is independently testable.
- **Cutover (Phase 6)**: **gated on T035** (everything green). Hard stop otherwise.
- **Polish (Phase 7)**: after Cutover.

### Within stories
- Tests (T016–T019) written before/with implementation; expected to fail first.
- Templates/renderers (T020–T023) before interactive/streaming wiring (T025–T026).
- Auth routes (T027) before handshake wiring (T028).

### Parallel opportunities
- Setup: T002, T003 in parallel.
- Foundational: T006, T009 in parallel (T004/T005/T007/T008/T010 are sequential on shared files).
- US2: T012, T013 in parallel after T011; T015 after the migration (T011–T012).
- US1 tests: T016–T019 all [P]. US1 renderers: T020–T023 all [P] (distinct template files).
- US3: T031, T032 in parallel.

---

## Parallel Example: User Story 1 renderers

```bash
# After foundational render path (T010), build renderers concurrently:
Task: "T020 Layout renderers + templates (container, card, grid, tabs, collapsible, divider)"
Task: "T021 Content renderers (text, button, input, param_picker, image, code, alert, progress, metric, list, table)"
Task: "T022 Chart renderers (bar/line/pie/plotly) with self-hosted Plotly"
Task: "T023 Media/IO + theming renderers (audio, file_upload, file_download, color_picker, theme_apply)"
```

---

## Implementation Strategy

### MVP (Stories US2 + US1)
1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US2 (migrate to astralprims; no behavior change) → 4. Phase 4 US1 (orchestrator renders web at parity) → **STOP & VALIDATE** real-browser parity (T030).
This is a working backend-driven UI while `frontend/` still exists as rollback.

### Then
5. Phase 5 US3 (prove the multi-target seam) → 6. **Phase 6 Cutover (only if T035 green)**: delete `frontend/` + `shared/primitives.py`, flip Docker to single-port → 7. Phase 7 Polish.

### Notes
- [P] = different files, no dependency. Commit after each task or logical group.
- The deletes in Phase 6 are irreversible on the branch — never run them before T035 is green (operator directive).
- ROTE (`backend/rote/`) is reused unchanged; do not modify its adaptation rules.
