# Implementation Plan: Bring-Your-Own Client-Side Agents

**Branch**: `057-byo-client-agents` | **Date**: 2026-07-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/057-byo-client-agents/spec.md`; agent contracts from [agent-constitution.md](agent-constitution.md); grounded research in [research.md](research.md).

## Summary

Move user-created agents **off the orchestrator and onto the user's desktop client**, authored through a guided, hybrid Specify→Clarify→Plan→Tasks→Analyze flow that is validated against a dedicated **agent constitution** before any code is generated. The agent is generated server-side but **runs on the user's desktop host as a client-supervised, isolated child process** (not in-process — so a buggy/malicious generated agent cannot reach the client's own memory/tokens/files); it goes offline when the client closes. The persistent connection is a **pluggable transport**: v1 default is the direct tunnel over the client's already-authenticated connection (zero new dependency); a **Cresco edge-mesh** transport is the sanctioned alternative for the broader cross-device/edge-compute scenario, under feature 050's external-infrastructure posture (no JVM/broker in the product image; the orchestrator reaches the fabric via the Python `wsapi` bridge) — FR-032. The security model is **untrusted-at-the-boundary**: the orchestrator's existing gate stack (which already discards agent-supplied identity, checks live per-user grants, and mints RFC 8693 delegation) re-verifies every action against the owning user, supplemented by owner-binding at registration, a fixed private-agent grant hole, and a per-owner ingress bound. Agents are private by construction; the only public path is a manually-approved repo contribution. All non-watch clients author + manage; Windows is the v1 execution host (macOS gated behind the non-sandboxed build; mobile/web bind to a desktop host).

**Technical approach**: reuse feature 012/027 draft lifecycle + code-gen + static gates and feature 043 device-target chrome plumbing; add (1) a pre-generation Analyze gate against a baked-in agent constitution, (2) an inbound agent-frame tunnel + owner binding, (3) a code-delivery seam to the desktop host, (4) owner-isolation hardenings, and (5) a `user_agent` registry table. Zero new backend runtime dependencies; Windows host uses already-pinned deps.

## Technical Context

**Language/Version**: Python 3.11 (backend, production image; local `.venv` 3.13); Python 3.10+/PySide6 (windows-client host); Swift/SwiftUI (apple-clients); Kotlin/Compose (android-client); ES5 vanilla JS/CSS (webrender chrome). Generated user agents: Python (`BaseA2AAgent` shape) run on the desktop host.

**Primary Dependencies**: Existing only — FastAPI, `websockets`, psycopg2, the OpenAI-compatible client (`llm_config.client_factory`), `python-jose` (JWT/RFC 8693), `cryptography` (ECIES/Fernet), `astralprims` (unchanged), and the existing `agentic_creation`, `agent_lifecycle`, `agent_generator`, `code_security`, `agent_validator`, `delegation`, `tool_permissions`, `chain_authority`, `concurrency_cap`, `chrome_events`, `webrender.chrome` modules. Windows host: `aiohttp`/`websockets` (already in `windows-client/requirements.txt`). **Zero new third-party runtime dependencies** (Constitution V). macOS host (deferred/gated): a bundled python-build-standalone framework, direct-download build only.

**Storage**: PostgreSQL via `shared/database.py::_init_db()` idempotent guarded migrations. Delta: new `user_agent` table + one `agent_ownership` row per user agent; `SCHEMA_REVISION 055.002 → 057.001`; additive `draft_agents` columns for the 5-phase authoring state; guarded `_migrate_revalidate_on_constitution_change`. Agent liveness is **in-memory** (socket presence), never a persisted column. Rollback documented in [data-model.md](data-model.md).

**Testing**: pytest (container, both invocations vs postgres:17-alpine) for backend; adversarial US3 suite driving a tampered user agent against the boundary; byte-identity test for the two agent-constitution copies; existing windows-client pytest for the host; chrome parity/drift-guard suites per client (Constitution XII).

**Target Platform**: Linux server (orchestrator, Docker); Windows 10+ (v1 agent host); macOS (author-only in MAS build, host in direct-download build); Android, iOS, web (author + manage). watchOS excluded.

**Project Type**: Server-driven multi-client system (orchestrator + native/web clients) with a new client-hosted agent runtime.

**Performance Goals**: SC-001 first working agent < 10 min; SC-005 offline reported within a few seconds (liveness tied to UI socket + heartbeat); no measurable cross-user degradation under a flooding agent (SC-008).

**Constraints**: Fail-closed production posture (`FF_BYO_AGENTS` default off; unverifiable step refuses); untrusted-at-the-boundary; zero new backend runtime deps; server-driven UI + cross-client parity (Constitution II/XII); idempotent guarded migrations (Constitution IX); agent-channel frames stay off `ui_protocol.json` (Constitution XII).

**Scale/Scope**: Per-user personal agents (modest scope, not HA services). ~6 backend modules touched/added, 1 new table, 1 new chrome surface, 1 desktop-host runtime generalization, 1 baked agent-constitution asset.

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1 design (below).*

| Principle | Status | Note |
|-----------|--------|------|
| I. Primary Language (Python backend) | PASS | Backend Python; generated agents Python; no language change. |
| II. UI Delivery (astralprims → orchestrator renders → ROTE) | PASS | Authoring is a server-driven chrome surface with `render()`+`components()`; no client-side wizard; no astralprims change. |
| III. Testing Standards | PASS | pytest + adversarial US3 suite + byte-identity + parity suites planned. |
| IV. Code Quality | PASS | Reuse-first; new modules small and single-purpose. |
| V. Dependency Management | PASS | Zero new backend runtime deps; Windows host uses already-pinned deps. macOS bundled-Python is a **client packaging** concern in a deferred/gated build, not a backend runtime dep. |
| VI. Documentation | PASS | Agent constitution + data-model + contracts + quickstart authored. |
| VII. Security | PASS (strengthened) | Reuses RFC 8693 + the gate stack; **fixes** a pre-existing private-agent grant hole; adds owner-binding + per-owner ingress bound; no secrets to untrusted agents. |
| VIII. User Experience | PASS | Guided hybrid flow; honest offline; plain-language Analyze violations. |
| IX. Database Migrations | PASS | Idempotent guarded `_init_db` delta; `SCHEMA_REVISION` bump; documented rollback. |
| X. Production Readiness | PASS | Fail-closed; `FF_BYO_AGENTS` default off; constitution baked into image. |
| XI. Continuous Integration | PASS | New tests fit the existing lint/build/test/coverage/smoke/secret-scan gates. |
| XII. Cross-Client Consistency | PASS | One surface, dual render/native; watch excluded structurally; agent-channel frames off `ui_protocol.json`; UI-facing `agent_offline`/`host_status` frame added to the manifest. |
| XIII. Documentation & Research Integrity | PASS | Research grounded in cited code; no fabricated APIs. |

**Result**: no violations requiring justification. Complexity Tracking below is empty.

## Project Structure

### Documentation (this feature)

```text
specs/057-byo-client-agents/
├── plan.md                 # This file
├── spec.md                 # Feature spec (done)
├── agent-constitution.md   # Contracts user agents must satisfy (done; source of truth for the baked copy)
├── research.md             # Phase 0 (done)
├── data-model.md           # Phase 1
├── quickstart.md           # Phase 1
├── contracts/              # Phase 1
│   ├── agent-tunnel.md         # inbound agent-frame tunnel + owner binding
│   ├── authoring-surface.md    # the agent_authoring chrome surface + phase handlers
│   ├── analyze-gate.md         # deterministic constitution checker contract
│   └── user-agent-registry.md  # user_agent table + lifecycle state machine
├── checklists/
│   └── requirements.md
└── tasks.md                # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
backend/
├── agent_constitution/
│   ├── agent_constitution.md          # NEW — baked runtime copy (byte-identical to specs/)
│   └── README.md                      # NEW — provenance + byte-identity note
├── orchestrator/
│   ├── agent_constitution.py          # NEW — loader: version + A–L checklist parse
│   ├── agent_analyze.py               # NEW — deterministic pre-generation Analyze gate
│   ├── agent_authoring.py             # NEW — 5-phase authoring state machine (or folded into agentic_creation.py)
│   ├── agentic_creation.py            # EDIT — insert Analyze before generate_code; byo_client origin; deliberate entry
│   ├── agent_lifecycle.py             # EDIT — code-delivery seam replacing Popen for byo; ephemeral self-test only
│   ├── orchestrator.py                # EDIT — UI-socket agent tunnel, owner binding, honest-offline, per-owner ingress bound, can_user_use_agent
│   ├── api.py                         # EDIT — close set_agent_permissions ownership hole
│   ├── tool_permissions.py            # EDIT — owner==user structural visibility filter
│   └── auth.py                        # EDIT — owner-token binding alongside AGENT_API_KEY
├── webrender/chrome/surfaces/
│   └── authoring.py                   # NEW — agent_authoring surface (render() + components())
├── shared/
│   ├── database.py                    # EDIT — user_agent table, SCHEMA_REVISION bump, guarded migration
│   ├── protocol.py                    # EDIT — owner-auth on register handshake; code-delivery frame
│   ├── feature_flags.py               # EDIT — FF_BYO_AGENTS (default off)
│   └── ui_protocol.json               # EDIT — UI-facing agent_offline / host_status frame
└── tests/                             # NEW — analyze gate, owner-isolation adversarial (US3), tunnel/offline, byte-identity

windows-client/
└── win_agent/ (+ astral_client)       # EDIT — generalize start_agent_thread to host user-authored bundles; inbound tunnel; offline-on-close

apple-clients/                         # EDIT (later) — macOS host via non-sandboxed build (gated); iOS author-only
android-client/                        # EDIT — author + manage surface parity
```

**Structure Decision**: extend the existing server-driven backend + native-client layout. The new backend modules are small and single-purpose (loader, analyze gate, authoring state machine, chrome surface); everything else is an edit that reuses an existing seam. The desktop-host runtime generalizes the already-shipping `win_agent`. No new top-level project.

## Phasing (maps to spec user stories)

- **Phase A — US1 MVP (P1)**: `user_agent` table + `FF_BYO_AGENTS`; UI-socket agent tunnel + owner binding + honest-offline; code-delivery seam; Windows host runs a delivered bundle; a minimal one-shot authoring path. Delivers "create + run on my device" end-to-end with the existing gate stack as baseline safety.
- **Phase B — US3 boundary hardening (P2, co-critical)**: close the `set_agent_permissions` hole (`can_user_use_agent`), the owner==user visibility filter, per-owner ingress bound, no-secrets-to-untrusted, and the adversarial US3 test suite. Land with/next to A before any production enablement.
- **Phase C — US2 guided authoring (P2)**: agent constitution baked + loader; `agent_analyze` gate wired **pre-generation**; the 5-phase state machine; the `agent_authoring` chrome surface (dual render/native).
- **Phase D — US4 cross-client parity (P2)**: surface parity across web/Windows/Android/Apple; watch exclusion verified; FR-024 desktop-host/offline messaging on non-host clients.
- **Phase E — US5 lifecycle (P3)**: list/revise (re-Analyze + rollback)/delete; constitution-version re-validation; confirm no share/publish surface.

## Complexity Tracking

> No Constitution Check violations — this table is intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| — | — | — |

## Post-Design Constitution Re-Check

After Phase 1 design (data-model + contracts): **still PASS**. The design adds no new runtime dependency, keeps agent-channel frames off `ui_protocol.json` (only the UI-facing offline/host-status frame is added there), makes privacy structural (`is_public CHECK=FALSE`), and strengthens security by closing a pre-existing hole. The one carried risk requiring an explicit early decision — the `owner_email` vs `user_id` canonical key — is resolved in [data-model.md](data-model.md) (canonical `owner_user_id`), not deferred.
