# Implementation Plan: Cross-Client Chrome & Settings Parity

**Branch**: `042-cross-client-chrome-parity` | **Date**: 2026-07-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/042-cross-client-chrome-parity/spec.md`

## Summary

Make the Windows (PySide6/Qt) and Android (Kotlin/Compose) clients present the **same** application chrome (top-bar controls + Settings menu) and the **same** settings surfaces as the web, and remove the Android Settings-page duplication. The mechanism is a **single server-owned menu model** (extracted from the existing data-driven `webrender/chrome/topbar.py:_menu_entries`) that every client renders, plus **settings surfaces delivered as server-driven UI** (composed from `astralprims` primitives, rendered by the orchestrator, adapted per device by ROTE) so native clients render them through their existing SDUI renderers with no web view and no per-client surface reimplementation. Role-gating (admin-only ADMIN TOOLS) is derived from the verified session role on every client and enforced server-side. Delivered in three independently shippable slices: **P1** the menu model + top-bar/dropdown parity + role-gating + real sign-out (+ Android de-dup), **P2** the SDUI settings surfaces natively on both clients, **P3** admin surfaces + the flag-gated Pulse control + full theme-preset parity.

## Technical Context

**Language/Version**: Python 3.11 (backend, in Docker image); Kotlin 2.0.x / JVM 17 (Android `:core` + `:app`); Python 3.11 + PySide6 ≥6.6 (Windows client); ES5 vanilla JS/CSS (web render layer, no build step).
**Primary Dependencies**: FastAPI, websockets, psycopg2, `astralprims` (UI primitives), the `webrender` render layer + `rote` adapter (existing); Jetpack Compose + OkHttp + kotlinx.serialization (Android, existing); PySide6/Qt (Windows, existing). **No new third-party runtime dependency** (Constitution V).
**Storage**: PostgreSQL via `shared/database.py::_init_db()` idempotent guarded startup migrations. No new tables expected; theme preference already lives in `user_preferences`. Any addition ships as an idempotent `_init_db` delta with rollback.
**Testing**: pytest (backend, changed-line coverage ≥90% via diff-cover); Kotlin JUnit in `:core` (Kover ≥90% on pure logic) + Compose UI/instrumented tests in `:app`; manual/live verification of Windows via launch+screenshot and Android via emulator.
**Target Platform**: Web (browser), Windows desktop, Android phone/tablet/foldable; the design must extend to a future iOS client with no menu re-specification (Constitution XII).
**Project Type**: Server-driven-UI system with a shared backend and multiple thin native clients.
**Performance Goals**: Menu renders with zero extra round-trips on the web (static shell) and within the existing register handshake on native clients; a settings surface opens within ~1s of selection.
**Constraints**: Match the web exactly (item set, order, grouping, admin-gating, red Sign out, Theme-in-menu not a top-bar toggle, flag-gated Pulse). Thin clients (Constitution II/XII): no parallel per-client menu definition, no native reimplementation of surfaces that can diverge.
**Scale/Scope**: 1 top bar (5 controls) + 3 menu groups (9 items) + ~10 settings surfaces × 3 client targets.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

- **I. Primary Language (Python backend)**: PASS — backend changes are Python; client changes are in the clients' own sanctioned languages (Kotlin, PySide6), not new backend languages.
- **II. UI Delivery Architecture (SDUI; astralprims defines → orchestrator renders → ROTE adapts; new targets are additive renderers; chrome described once server-side; minimal client wrapping)**: PASS — this feature *implements* the expanded Principle II: it makes the chrome a single server-owned description and delivers settings surfaces as orchestrator-rendered, ROTE-adapted SDUI. No SPA reintroduced.
- **III. Testing Standards (≥90% changed-line)**: PASS — backend menu-model + serialization + role-gating covered by pytest; Android menu-model/gating/mapping in `:core` covered by Kover ≥90%; diff-cover gate honored.
- **IV. Code Quality (ruff; client lint)**: PASS — ruff for Python, ktlint + Android Lint for Kotlin, all in CI.
- **V. Dependency Management (no new third-party runtime dep w/o approval)**: PASS — reuses existing stacks; **zero new runtime dependencies** planned. Any exception documented in the PR.
- **VI. Documentation**: PASS — menu-model schema documented in `contracts/`; new primitives (if any) documented in `astralprims` before use; renderer targets documented.
- **VII. Security (Keycloak roles; server-side authz; in-process agent posture unchanged)**: PASS — admin gating uses the existing verified-role source (`web_auth.session_roles` / `chrome_events._roles`) and stays server-enforced (`ADMIN_ONLY`); native clients receive role info only to *hide* UI, never as the authority.
- **VIII. User Experience (consistent design language; astralprims-driven)**: PASS — strengthens consistency; all surfaces astralprims-driven.
- **IX. Database Migrations (idempotent guarded startup)**: PASS — no schema change expected; if one is needed it ships as an `_init_db` delta with rollback.
- **X. Production Readiness (no stubs; verify every affected client)**: PASS — each slice is production-ready and is verified on web + Windows + Android before it is declared done (Principle X as amended).
- **XI. Continuous Integration (gate set green)**: PASS — backend `ci.yml` (lint/build/test/coverage/smoke/secret-scan) and `android-ci.yml` (ktlint/lint/unit/Kover/assemble) must pass; the Windows release workflow builds on tag/dispatch.
- **XII. Cross-Client Consistency (NEW — shared server-owned definitions; thin consumers; role-gating from one source; new targets are thin consumers)**: PASS — this feature is the first realization of Principle XII: one menu model + one SDUI surface path consumed by all clients.

**Result: PASS. No violations; Complexity Tracking not required.**

## Project Structure

### Documentation (this feature)

```text
specs/042-cross-client-chrome-parity/
├── plan.md              # This file
├── research.md          # Phase 0 — decisions & alternatives
├── data-model.md        # Phase 1 — the menu model + wire shapes
├── quickstart.md        # Phase 1 — how to run & verify across clients
├── contracts/
│   └── chrome-menu.md    # Phase 1 — menu-model serialization + delivery contract (WS + REST)
├── checklists/
│   └── requirements.md   # Spec quality checklist (from /speckit-specify)
└── tasks.md             # Phase 2 — /speckit-tasks output
```

### Source Code (repository root)

```text
backend/
├── webrender/chrome/
│   ├── menu_model.py         # NEW — canonical server-owned chrome model (top-bar controls + groups + items + gating); to_dict() serialization
│   ├── topbar.py             # REFACTOR — render web top bar + dropdown FROM menu_model (single source; no visual change to web)
│   ├── surfaces/             # settings surfaces — gain a components() SDUI path (P2)
│   │   ├── __init__.py       # SURFACE_MODULES registry (unchanged keys)
│   │   ├── _sdui.py          # NEW (P2) — helpers to build astralprims component surfaces + action bindings
│   │   ├── theme.py, guide.py, audit.py, agents.py, llm.py, personalization.py, tour.py, admin_tools.py, workspace_timeline.py, pulse.py
│   └── __init__.py
├── orchestrator/
│   ├── chrome_events.py      # EXTEND — deliver surfaces as SDUI components to native targets (ROTE-adapted), HTML to web; keep server-side admin gate
│   ├── web_auth.py           # role source (reused)
│   └── api.py / async_tasks.py  # ADD — chrome-menu delivery on register_ui (native) + GET /api/chrome/menu (role-aware)
├── rote/                     # windows/android profiles already exist; ensure surface components flow through the adapter
└── tests/ (per-module)       # pytest for menu_model, serialization, gating, delivery

android-client/
├── core/ (:core, pure Kotlin, JVM-tested, Kover ≥90%)
│   └── src/main/kotlin/.../chrome/   # NEW — ChromeMenu model + JSON decode + role-gating + mapping to control descriptors
├── app/ (:app, Compose — thin)
│   └── src/main/kotlin/.../ui/       # REWORK — top bar (brand/status/[pulse]/timeline/gear) + Settings dropdown from ChromeMenu; DELETE duplicated Settings screen; SDUI surface host (reuse CanvasHost/Renderer)

windows-client/
└── astral_client/
    ├── app.py                # REWORK — TopBar → brand/status/[pulse]/timeline/gear; gear opens grouped dropdown from the menu model; red Sign out at bottom; role-gating; SDUI surface host (reuse renderer.py)
    ├── chrome.py             # EXTEND — consume menu model; render SDUI surfaces (replace the "not available" placeholder)
    └── theme.py              # EXTEND (P3) — theme presets consumed from the Theme surface

.github/workflows/            # ci.yml + android-ci.yml must stay green; no structural change expected
.specify/memory/constitution.md  # amended separately (v2.3.0, Principle XII)
```

**Structure Decision**: Multi-client SDUI system. The **single source of truth** is `backend/webrender/chrome/menu_model.py`; the web (`topbar.py`), Android (`:core` `ChromeMenu` + `:app` renderer), and Windows (`app.py`/`chrome.py`) are consumers. Settings surfaces converge on an SDUI component path so all clients render them through their existing component renderers.

## Architecture & Phasing

### Phase 0 — Research (see research.md)
Resolve: (a) how native clients receive the menu model (register handshake payload + REST fallback vs a dedicated WS frame); (b) how a chrome surface is delivered as SDUI vs HTML per target; (c) role source on native clients; (d) theme application on native clients; (e) sign-out semantics on native clients; (f) verification tooling available on this host.

### Phase 1 — Design (data-model.md, contracts/chrome-menu.md, quickstart.md)
Define the menu-model data shape + its JSON serialization; the `chrome_menu` delivery contract (register payload + `GET /api/chrome/menu`); the SDUI-surface delivery contract (native `chrome_surface` components frame vs web `chrome_render` HTML); and the cross-client verification quickstart.

### Phase 2 — Tasks (tasks.md via /speckit-tasks)
Dependency-ordered, priority-grouped (P1 → P2 → P3), each task independently testable, each priority independently shippable + production-ready.

### Implementation order (matches spec priorities)
- **P1 — one consistent, functional menu everywhere.** menu_model.py + topbar refactor (web parity, no visual change) + native delivery (register payload + REST) + Android/Windows top-bar & dropdown rebuilt from the model + Android de-dup + admin role-gating + real Sign out. Not-yet-SDUI surfaces open their existing native screen (agents/audit/history) or a labeled "coming to this client" placeholder (FR-013). **Independently shippable.**
- **P2 — SDUI settings surfaces.** Add a `components()` SDUI path to the surfaces + a native `chrome_surface` delivery mode (ROTE-adapted); native clients render surfaces through their existing renderer. Convert surfaces in ascending complexity (theme → guide → audit → llm → personalization → agents). Replace P1 placeholders as each lands. **Each surface independently shippable.**
- **P3 — admin + pulse + theme polish.** admin_tools (Tool quality, Tutorial admin) SDUI + gating end-to-end; flag-gated Pulse control on native top bars; theme presets applied + persisted natively across clients.

## Complexity Tracking

No constitution violations — table intentionally omitted.
