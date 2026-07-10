# Implementation Plan: Bring-Your-Own-LLM — Mandatory Provider Setup & Shipped-Credential Removal

**Branch**: `054-byo-llm-setup` | **Date**: 2026-07-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/054-byo-llm-setup/spec.md`

## Summary

Remove the operator-default LLM credential mechanism entirely (the
`OPENAI_API_KEY`/`OPENAI_BASE_URL`/`LLM_MODEL` env trio and every code path
that consumes it), persist per-user LLM provider configuration server-side
(new `user_llm_config` table, API key Fernet-encrypted under the existing
`CREDENTIAL_ENCRYPTION_KEY` posture), and gate every unconfigured user behind
a mandatory, non-dismissible provider-setup dialog — the first thing after
login on web, Windows, Android, iOS, and macOS — offering a server-owned
catalog of popular providers plus a custom OpenAI-compatible endpoint.
Server-initiated/background LLM work (scheduled jobs, parser codegen,
knowledge synthesis, job narration — plus, by explicit owner decision,
compaction and workspace combine/condense) moves to a single admin-managed
`system_llm_config` credential with honest degradation when absent. Delivery
reuses the existing SDUI machinery end-to-end: the `llm` chrome surface
(extended with the provider dropdown), `chrome_render` for web,
`chrome_surface` with its reserved `mode` field (`"mandatory"`) for natives —
zero new frame types, zero manifest edits, zero new dependencies.

## Technical Context

**Language/Version**: Python 3.11 (backend, production image; local `.venv`
3.13); ES5 vanilla JS/CSS for the web render layer (`backend/webrender/static/`,
no build step); PySide6/Python (Windows client); Kotlin 2.0.21 + Compose
(Android); Swift/SwiftUI (Apple).

**Primary Dependencies**: Existing only — FastAPI, `websockets`, psycopg2, the
OpenAI-compatible client (`openai` package, already present) resolved through
`llm_config/client_factory.py`, `cryptography` (Fernet, already used by the
credential manager / session store), `astralprims` (consumed unchanged),
existing `audit`, `chrome_events`, `scheduler`, `agentic_creation` modules.
**Zero new third-party runtime dependencies** (Constitution V).

**Storage**: PostgreSQL via `shared/database.py::_init_db()` idempotent guarded
startup migrations. Deltas: new `user_llm_config` table (PK `user_id`,
`api_key_enc` Fernet-encrypted); new `system_llm_config` single-row table
(guarded `id=1`). No changes to existing tables. Rollback documented in
[data-model.md](data-model.md).

**Testing**: pytest + pytest-asyncio (asyncio_mode=auto) in the `astraldeep`
container; per-client drift-guard suites (backend manifest test, Windows,
Android unit, Apple XCTest); 032 in-process verification harness re-seamed to
store-backed credentials.

**Target Platform**: Linux server (Docker image); Windows 10+ desktop client;
Android 8+; iOS/macOS/watchOS per feature 051.

**Project Type**: Web service + 4 native client families (server-driven UI).

**Performance Goals**: Gate predicate adds ≤1 cached DB read per register/turn
(TTL cache; invalidated on save/clear); no measurable regression on chat-turn
latency; setup dialog round-trip (test + save) < 5 s against a healthy
provider.

**Constraints**: Fail-closed for user traffic (no configured record ⇒ refusal
+ gate, never a fallback); system credential never serves user-context calls
and vice versa; API key never in logs/audit/client payloads/plaintext at rest;
boot must succeed with zero LLM settings (no boot-gate change); watch stays
chrome-free; tutorial behavior unchanged.

**Scale/Scope**: Single-deployment user bases (≤ thousands); one config row
per user + one system row; the gate predicate is read-through cached.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|---|---|---|
| I | Python backend | PASS | All backend work in Python; client edits are in their sanctioned languages. |
| II | SDUI architecture | PASS | Dialog is the existing `llm` chrome surface composition (astralprims → orchestrator render → ROTE); web modal via `chrome_render`; natives via `chrome_surface`; no client reimplements the surface. Provider catalog is server-owned. |
| III | Testing ≥90% changed-code | PASS (planned) | New store, gate, catalog, resolver re-keying, admin surface, honest-failure paths all unit/integration tested; client drift guards stay green. |
| IV | Code quality | PASS | ruff from repo root; ES5 constraints respected in `client.js`. |
| V | Dependencies | PASS | Zero new third-party runtime deps. |
| VI | Documentation | PASS | Docstrings on new modules; deployment-doc migration note; 006 conformance note. |
| VII | Security | PASS (1 recorded risk) | Keycloak auth unchanged; admin surface server-side role-gated; Fernet at rest under boot-gated key; key-hygiene invariants preserved + `install_redaction_filter` finally wired; gate enforced server-side; audited refusals. **Conscious decision**: the server-originated connection probe (inherited from 006) becomes mandatory-on-save and reachable while gated, and the catalog suggests server-local runtime addresses — an internal-reachability oracle accepted with mitigations (authenticated, audited, per-user rate-limited probes); not routed through `shared.external_http` to avoid breaking legitimate private/self-hosted endpoints, matching 006's posture. |
| VIII | UX via astralprims | PASS | Surface composed from existing primitives (ParamPicker action-submit, password kind — feature 043 vocabulary). |
| IX | Migrations | PASS | Two new tables via idempotent `_init_db` deltas; rollback path documented. |
| X | Production readiness | PASS (planned) | Every affected client exercised live (web browser, Windows client, Android emulator, iOS/macOS sim, watch sim); honest-failure paths tested; observability: audited gate refusals + structured logs on background skip. |
| XI | CI | PASS (1 additive step) | LLM vars were never in CI, so existing gates are unaffected; **one additive step** implements FR-004's release validation: a built-image filesystem credential scan in the smoke job (T048). |
| XII | Cross-client consistency | PASS | One server-owned surface/catalog; mandatory marker on the shared frame's reserved field lands on all in-scope clients in this feature; watch divergence is a declared capability difference (chrome-free by design) with an explicit UX (spoken guidance); admin `llm_system` surface is a **declared web-only carve-out** (spec FR-018) exactly like the existing Tool quality / Tutorial admin surfaces — server-enforced (natives never receive admin menu groups; `include_admin=False` on every native channel), uniform across non-web clients. |
| XIII | Docs/research integrity | N/A | Runtime feature. |

**Post-Phase-1 re-check**: PASS — design introduces no violations; no
Complexity Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/054-byo-llm-setup/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0 (complete)
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── first-run-gate.md   # WS/REST/chrome contract deltas
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── llm_config/
│   ├── providers.py            # NEW — server-owned provider preset catalog
│   ├── user_store.py           # NEW — persisted per-user + system config store (Fernet)
│   ├── operator_creds.py       # REMOVED (env-default path deleted)
│   ├── client_factory.py       # default_creds → system/empty-sentinel semantics
│   ├── session_creds.py        # becomes user-keyed read-through cache dataclasses
│   ├── ws_handlers.py          # set/clear re-keyed to user_id + persistence
│   ├── api.py                  # /api/llm/test + /list-models unchanged; scope param for admin probe
│   ├── audit_events.py         # SYSTEM source; new provider key-prefix patterns
│   └── log_scrub.py            # new key patterns; filter INSTALLED at boot
├── orchestrator/
│   ├── orchestrator.py         # resolver re-key; gate at register_ui/chat pre-flight;
│   │                           # welcome suppression; save fan-out; operator remnants deleted
│   ├── chrome_events.py        # gate: force llm surface while unconfigured; refuse chrome_close
│   ├── compaction.py           # unchanged call shape (websocket=None ⇒ system)
│   ├── agent_generator.py      # env reads → system store
│   ├── knowledge_synthesis.py  # env reads → system store, per-cycle re-check
│   └── credential_manager.py   # unchanged (precedent only)
├── scheduler/runner.py         # LLM-unavailable ⇒ outcome="failure" (honest reporting)
├── webrender/
│   ├── chrome/__init__.py      # render_modal_shell mandatory variant (no ✕, data-mandatory)
│   ├── chrome/surfaces/llm.py  # provider dropdown (web + SDUI components()); first-run copy
│   ├── chrome/surfaces/llm_system.py  # NEW — admin-only system credential surface
│   ├── chrome/menu_model.py    # admin menu item for the system surface
│   └── static/client.js        # closeModal() mandatory guard
├── shared/database.py          # _init_db: user_llm_config + system_llm_config
├── verification/drivers/in_process.py  # env fake → store seeding
└── seeds/ (untouched)

windows-client/astral_client/app.py     # SurfaceDialog mandatory modality
android-client/core/.../Wire.kt, Messages.kt; app/.../AppViewModel.kt, RootScaffold.kt
apple-clients/AstralApp/AstralApp/AppModel.swift, Views/RootView.swift
apple-clients/AstralWatch/ (no change — server-side copy only)

.env / .env.example / docs/production-deployment.md   # scrub + migration note
specs/006-user-llm-config/spec.md                     # conformance note (superseded FRs)
```

**Structure Decision**: All new backend logic stays inside the existing
`backend/llm_config/` module (store, catalog) and the established chrome/
orchestrator seams; client edits are the minimal mandatory-marker handling in
each client's existing frame-reduction path. No new top-level modules.

## Design Decisions (Phase 1 digest)

1. **Store** (`llm_config/user_store.py`): `UserLLMConfigStore` with
   `get(user_id) -> PersistedLLMConfig | None`, `set(user_id, cfg)`,
   `clear(user_id)`, `get_system()/set_system()/clear_system()`; Fernet
   encrypt/decrypt of `api_key` only; undecryptable row ⇒ audited discard +
   `None` (re-gate, FR-010); in-process TTL cache with invalidation on
   set/clear; `__repr__` elides the key everywhere.
2. **Resolution rule** (single choke point, `_resolve_llm_client_for`):
   user socket ⇒ user record (else `LLMUnavailable`); `None`/VirtualWebSocket
   ⇒ system record (else `LLMUnavailable`). No cross-fallback in either
   direction. `CredentialSource.SYSTEM` replaces `OPERATOR_DEFAULT` for new
   audit rows.
3. **Gate** (`orchestrator` + `chrome_events`): predicate = decryptable user
   record exists. At `register_ui`: unconfigured ⇒ push mandatory dialog
   (web `chrome_render` modal, natives `chrome_surface mode="mandatory"`),
   suppress welcome; configured ⇒ today's flow byte-for-byte. While
   unconfigured: chat pre-flight refuses (existing `llm_unconfigured` audit +
   Alert), `chrome_open`≠`llm` forced to `llm`, `chrome_close` refused,
   `component_action`/combine/condense refused. On save: close gate + welcome
   render fanned out to all the user's sockets. Kill switch
   `FF_LLM_FIRST_RUN` (default on) covers only the register-time push.
4. **Catalog** (`llm_config/providers.py`): ordered presets (R7 table) with
   `key_required` flags; composed into the surface for web and native SDUI
   from the one definition; "Custom" = free-form base URL. **Preset base
   URLs are server-derived**: for non-custom presets the editable base_url
   field is omitted (display-only copy shows the endpoint) and the save
   handler derives `base_url` from the provider key — so prefill/lock
   behavior needs zero client logic and cannot diverge between web and
   native SDUI. Validation: preset key requirements and per-field
   missing-value messages enforced server-side at save.
5. **Save flow** (dialog and settings surface identical): fields → optional
   "Load models" (`POST /api/llm/list-models`) → mandatory successful
   "Test" (`POST /api/llm/test`, real chat-completion `max_tokens:1`) →
   `chrome_llm_save`/`llm_config_set` persists via the store. The server
   re-runs the probe on save (a save without a fresh passing probe is
   refused server-side) so the client-side test button is UX, not the gate.
6. **Admin system surface** (`llm_system`): same field set + probe, admin
   role-gated server-side (`session_roles`/JWT per handler, existing
   pattern); **web-only** per the declared Constitution XII carve-out (spec
   FR-018) — web `render()` only, no native `components()`, and the menu
   item lives in the admin group the server already omits from native menu
   channels; audited `llm_config_change{scope:"system"}`. Gate escape:
   sign-out stays reachable while gated (spec FR-013) — the mandatory
   dialog variant carries a sign-out affordance and the server gate exempts
   logout routes/actions.
7. **Honest degradation** (FR-020): scheduler records
   `outcome="failed", error="llm_unavailable"` and the notification says the
   AI was unavailable; knowledge synthesis logs+skips per cycle; autoparse
   marks parser prep failed (existing path); combine/condense return their
   existing error frame; compaction keeps its non-AI fallback note.
8. **Removal**: delete `operator_creds.py` and all env reads (R4 inventory);
   scrub `.env`/`.env.example`/docs with a migration note; retarget affected
   suites; wire `install_redaction_filter` at boot; fix the stale
   `guide_content.py` tour-copy claim.
9. **006 conformance note**: prepend an "Amended by 054" block to
   `specs/006-user-llm-config/spec.md` enumerating superseded FRs (FR-022).

## Complexity Tracking

No constitution violations to justify.
