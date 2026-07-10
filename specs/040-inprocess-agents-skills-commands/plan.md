# Implementation Plan: In-Process Built-In Agents, Owner-Safe Marking, and Skills + Slash Commands

**Branch**: `040-inprocess-agents-skills-commands` | **Date**: 2026-06-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/040-inprocess-agents-skills-commands/spec.md`

## Summary

Collapse the nine bundled first-party agents from per-agent OS processes (each a uvicorn server on its own TCP port, reached over a WebSocket round-trip) into **in-process execution inside the orchestrator**, by branching the existing dispatch seam (`_execute_via_websocket`) to call a registered local agent's MCP server directly through a loopback transport — preserving every behavior (streaming, progress, long-running jobs, per-agent ECIES credential decryption inside each agent's own boundary, concurrency caps, retry/timeout, and full audit attribution). Externally-hosted A2A agents keep their networked path; user-created drafts keep their subprocess + self-test isolation. Mark the bundled fleet **safe** (an audited, owner-approved trust record that flips the per-call permission baseline from deny to allow for those agents at check time — never writing per-user rows, never overriding an explicit user opt-out or a hard security block). Remove the `etf_tracker_1` agent and clean up its orphaned data idempotently. Add Claude-Code-style **skills** (authored, version-controlled, progressively-disclosed capability/technique packs loaded by relevance, including wiring the currently-dormant per-agent technique loader) and a user-typed **/slash-command** surface routed through the existing permission/audit/PHI rails. Everything is feature-flagged, fail-open for UI niceties and fail-closed for security, uses zero new third-party runtime dependencies, and ships its schema deltas as idempotent guarded `_init_db` migrations.

## Technical Context

**Language/Version**: Python 3.11+ (production image); local `.venv` 3.13. ES5-compatible vanilla JS/CSS for the orchestrator render layer (`backend/webrender/static/`, no build step) where the slash-command UI touches the chat input.
**Primary Dependencies**: Existing only — FastAPI, websockets, psycopg2, the OpenAI-compatible LLM client (`_call_llm` via `llm_config.client_factory`), `cryptography` (ECIES/Fernet), `python-jose` (JWT/RFC 8693), `astralprims` (consumed unchanged), `shared.external_http` (egress-gated HTTP), and the existing `audit`, `tool_permissions`, `tool_security`, `knowledge_synthesis`, `agentic_creation`, `concurrency_cap`, `stream_manager`, `job_poller`, and `agent_runtime` modules. **No new third-party runtime libraries** (Constitution V).
**Storage**: PostgreSQL via `shared/database.py::_init_db()` idempotent, guarded startup migrations. Deltas: new `agent_trust` table (per-agent safe/owner-approval record); a one-time guarded cleanup of orphaned permission/credential/chat rows for retired `etf-tracker-1-1`. No schema needed for skill packs (filesystem, committed) or the curated slash-command set (in-code registry). Rollback documented in [data-model.md](data-model.md).
**Testing**: `pytest` + `pytest-asyncio` (asyncio_mode=auto). In-process dispatch is validated with the existing in-process `Orchestrator` + `VirtualWebSocket` harness plus parity tests against the prior WebSocket path; permission/audit/credential invariants via targeted unit + integration tests against a real `postgres:17-alpine` service (per CI).
**Target Platform**: Linux server container (`astraldeep`), single orchestrator process on `:8001`; web client target via server-rendered HTML/CSS/JS, ROTE-adapted.
**Project Type**: Server-driven web application (single backend; no separate SPA).
**Performance Goals**: Eliminate the per-call network/WS round-trip for the nine built-in agents (local in-process dispatch), with no latency regression on any built-in tool path and no event-loop stalls (blocking tools stay offloaded to worker threads). Per-turn injected knowledge stays bounded and request-relevant (no baseline context growth on unrelated turns).
**Constraints**: Fail-closed security posture (`ASTRAL_ENV` unset == production); orchestrator MUST never hold plaintext per-user secrets; audit hash-chain integrity per user MUST hold; zero new runtime dependencies; all new behavior behind feature flags with exact legacy behavior when off.
**Scale/Scope**: 9 in-process built-in agents (etf_tracker_1 removed from the prior 10), an unbounded number of per-user chats, the existing audit/permission/credential surfaces, ~4 new feature flags, 1 new table, 1 cleanup migration, a curated initial slash-command set, and authored skill packs for the built-in capabilities.

## Constitution Check

*GATE: evaluated before Phase 0 and re-checked after Phase 1 design. Result: PASS (with two tracked posture notes, neither a violation).*

| # | Principle | Verdict | Evidence |
|---|-----------|---------|----------|
| I | Primary Language (Python) | PASS | All backend work is Python; the only client-side code is the existing orchestrator render-layer JS/CSS for the chat input's command menu. |
| II | UI Delivery (astralprims defines → orchestrator renders → ROTE adapts) | PASS | Agent tool outputs remain astralprims primitive dicts, unchanged by the transport move. The slash-command menu/help and skill surfacing use the existing server-rendered chrome + astralprims primitives and ROTE adaptation — no new SPA, no new astralprims primitive required. |
| III | Testing (≥90% changed-code coverage) | PASS | Each pillar ships unit + integration tests (parity, permission baseline, credential confidentiality, audit attribution, migration idempotency, command parsing); changed-code coverage gate enforced in CI. |
| IV | Code Quality (PEP 8 / ruff; lint emitted JS) | PASS | Ruff clean from repo root; any chat-input JS passes the existing lint; no exceptions without inline justification. |
| V | Dependency Management (no new third-party deps) | PASS | Zero new runtime dependencies (FR-035); all work reuses existing modules. |
| VI | Documentation (docstrings; primitive/renderer docs) | PASS | Google/NumPy docstrings on new functions; no new astralprims primitive is introduced; any new render-layer behavior documented; `/docs` unaffected. |
| VII | Security (Keycloak, RFC 8693, input validation, no secrets) | PASS | Safe-marking is admin/owner-gated server-side and audited; in-process agents keep per-agent ECIES decryption (no orchestrator plaintext) and act under the same RFC 8693 delegated authority; slash-command input is validated and treated as untrusted; no secrets committed. See posture notes below. |
| VIII | User Experience (consistent design via astralprims) | PASS | Command menu/help and skill cues reuse the existing design language and primitives; behavior degrades gracefully (friendly messages, fail-open). |
| IX | Database Migrations (idempotent guarded `_init_db`) | PASS | `agent_trust` table and the etf cleanup ship as idempotent/guarded `_init_db` deltas with documented rollback; tested against a representative dataset. |
| X | Production Readiness (no stubs; observability; staged) | PASS | No stubs; observability via the audit chain + structured logs (a `*.fallback{reason}`-style marker on each fail-open path); the in-process transport change is runtime infra and is validated end-to-end against the running container before merge; UI exercised in a real browser. |
| XI | Continuous Integration (named gate set) | PASS | Changes pass lint / full suite vs real DB / ≥90% changed-code coverage / image build / boot smoke incl. production fail-closed exit / secret scan; publish on main unaffected. |

**Gate result: PASS.**

**Posture notes (now codified in Principle VII as of constitution v2.2.0; deliberate, audited, not violations):**

1. **In-process agents bypass the WebSocket `AGENT_API_KEY` handshake.** That key authenticates *external* agent transport connections (028 fail-closed). The nine built-ins are first-party code executing inside the orchestrator's own trust boundary, so there is no transport to authenticate; every *runtime* control (per-user permission gate, security-flag blocks, taint, policy, egress gating, PHI, audit) and the RFC 8693 delegated-authority attribution are preserved on the in-process path. External A2A agents still require their api_key.
2. **Safe agents flip the per-call permission baseline from deny to allow.** This is an owner-approved posture change (Clarifications Session 2026-06-24), recorded in `agent_trust`, applied only at check time (no per-user rows written), and strictly bounded: an explicit user opt-out always wins and hard security-flag blocks are never cleared by "safe." It changes a default, not a control.

## Project Structure

### Documentation (this feature)

```text
specs/040-inprocess-agents-skills-commands/
├── plan.md              # This file
├── spec.md              # Feature specification (with Clarifications)
├── research.md          # Phase 0 — design decisions & alternatives
├── data-model.md        # Phase 1 — schema deltas + rollback
├── quickstart.md        # Phase 1 — how to validate each pillar in the running container
├── contracts/           # Phase 1 — interface contracts
│   ├── inprocess-dispatch.md     # local-agent registry + loopback transport contract
│   ├── safe-marking.md           # agent_trust + admin verb + permission-baseline contract
│   ├── skill-packs.md            # authored-pack format + on-demand loading contract
│   └── slash-commands.md         # command registry + parse/expand/flow + discovery contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # Phase 2 — /speckit-tasks output (not created by /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── shared/
│   ├── base_agent.py                    # CHANGE: factor handle_mcp_request pre-steps (credential decrypt + _runtime build) so they are reusable by an in-process caller; add an in-process entrypoint that does NOT require a real WS server
│   ├── local_transport.py               # NEW: LoopbackSocket (send_text/send_json route ToolProgress/ToolStreamData into the orchestrator handlers; captures the running loop for cross-thread emits)
│   ├── database.py                      # CHANGE: _init_db deltas — create agent_trust; one-time guarded etf-tracker-1-1 orphan cleanup; remove 'etf-tracker-1-1' from _FIRST_PARTY_PUBLIC_AGENT_IDS; agent_trust CRUD helpers
│   └── feature_flags.py                 # CHANGE: FF_INPROCESS_AGENTS, FF_SAFE_AGENTS, FF_SKILL_PACKS, FF_SLASH_COMMANDS
├── orchestrator/
│   ├── orchestrator.py                  # CHANGE: local-agent registry (self.local_agents); instantiate+register built-ins in-process at boot; branch _execute_via_websocket → in-process executor on positive registry check; preserve streaming/progress/jobs via LoopbackSocket; add 'etf-tracker-1-1' to RETIRED_AGENT_IDS; doc-comment fix at _is_draft_agent
│   ├── local_agents.py                  # NEW: LocalAgentRegistry — discover/import the bundled agent classes, instantiate (no uvicorn), own their crypto keys, register cards/tool-scope maps/security_flags/ownership in-process; unary + streaming + long-running in-process executors
│   ├── tool_permissions.py              # CHANGE: is_tool_allowed honors the safe-agent baseline (allow unless explicit opt-out / hard block), behind FF_SAFE_AGENTS; explicit-disable representation
│   ├── agent_trust.py                   # NEW: mark_safe/unmark_safe (admin/owner-gated), is_safe lookups, reset-on-revision hook, audited transitions
│   ├── agentic_creation.py              # CHANGE: apply_revision resets agent_trust.is_safe for a revised safe agent (re-approval required)
│   ├── chrome_events.py                 # CHANGE: dispatch the mark-safe admin action + slash-command discovery/help surfaces
│   ├── slash_commands.py                # NEW: curated command registry {name, kind, description, required_scopes, expand/flow}; parser; unknown/malformed → friendly chrome message
│   ├── skill_packs.py                   # NEW: load authored packs (protected dir) + wire get_techniques_for_agent into the turn; relevance selection + bounded digest; authored-over-synthesized precedence
│   ├── knowledge_synthesis.py           # CHANGE: KnowledgeIndex reads the authored-pack dir with 'authored' provenance; synthesizer never writes there
│   └── api.py / chat_steps.py           # CHANGE: detect a leading /command at chat ingress; expand-to-prompt or trigger flow through the normal gates; structured untrusted-arg handling
├── agents/
│   └── etf_tracker_1/                   # DELETE: entire directory (agent removed)
├── knowledge_packs/                     # NEW: committed, version-controlled authored skill packs (separate from the gitignored, auto-synthesized backend/knowledge/)
│   └── techniques/<agent>.md            # authored technique packs the synthesizer cannot overwrite
├── webrender/
│   ├── templates/shell.html             # CHANGE: chat input gains a /command typeahead/menu affordance (server-rendered)
│   ├── static/client.js                 # CHANGE: '/' typeahead menu; render command list/help; ROTE-safe
│   ├── static/astral.css                # CHANGE: command-menu styles
│   └── chrome/surfaces/                 # CHANGE/NEW: a commands/help surface; mark-safe admin control on the agents surface
└── tests/
    ├── test_inprocess_dispatch.py       # NEW: parity (unary/stream/job), no-port, event-loop non-blocking, error classification
    ├── test_inprocess_credentials.py    # NEW: ECIES decrypt stays inside agent; no orchestrator plaintext
    ├── test_inprocess_audit.py          # NEW: start/end events, correct actor/agent/correlation; parallel-path audit (FR-032)
    ├── test_agent_trust.py              # NEW: safe baseline allow, explicit opt-out wins, hard-block stays, admin-gating, reset-on-revision, audit
    ├── test_etf_removal.py              # NEW: absent everywhere; idempotent orphan cleanup; retired-agent transcript handling
    ├── test_skill_packs.py              # NEW: relevance-only loading, no baseline growth, authored-not-clobbered, fail-open
    ├── test_slash_commands.py           # NEW: known command expand/flow, permission gate not bypassed, unknown→friendly, untrusted args
    ├── test_agent_retirement.py         # CHANGE: drop etf_tracker_1 from expected set
    ├── test_no_behavior_change.py       # CHANGE: drop agents.etf_tracker_1.mcp_tools
    └── test_wiring_030.py               # CHANGE: re-point the public-agent assertion off the retired etf id
```

**Structure Decision**: Single server-driven backend (no SPA). The transport change is intentionally surgical — a new `LocalAgentRegistry` + `LoopbackSocket` plus a single positive-registry branch at the existing dispatch seam — so the entire gate stack (permission, policy, taint, supervisor, credential injection, **audit**) that already wraps `_execute_with_retry` is preserved unchanged. New modules (`local_agents.py`, `agent_trust.py`, `slash_commands.py`, `skill_packs.py`, `local_transport.py`) keep each pillar isolated and individually testable; existing modules receive minimal, flag-gated edits.

## Key Design Decisions (detail in [research.md](research.md))

- **In-process seam**: branch `_execute_via_websocket` on `agent_id in self.local_agents`; run the agent-side pre-steps (credential decrypt + `_runtime` build) against a `LoopbackSocket`, then `await asyncio.to_thread(agent_obj.mcp_server.process_request, request)`; return the `MCPResponse` directly. Keep `execute_single_tool` as the entry so all gates + `ToolDispatchAudit` are unchanged.
- **Streaming/progress/jobs** ride the `LoopbackSocket` back into `_handle_tool_progress` / `StreamManager.handle_agent_chunk` exactly as the WS listen loop did; the loopback captures the orchestrator loop for thread-safe emits.
- **Credentials**: orchestrator keeps injecting *encrypted* per-user creds; the in-process agent decrypts with its own key inside its boundary — no orchestrator plaintext (Clarifications Q4).
- **Safe baseline**: `agent_trust.is_safe` consulted in `is_tool_allowed`; baseline flips deny→allow for safe agents, explicit opt-out (an explicit negative record) and hard security-flag blocks always win; nothing written per-user (Clarifications Q1/Q2).
- **etf removal** follows the 9-item discovery checklist incl. an idempotent `_init_db` orphan purge and `RETIRED_AGENT_IDS` membership for graceful old-transcript handling.
- **Skills**: authored packs in a committed `backend/knowledge_packs/` dir the synthesizer never writes; wire `get_techniques_for_agent` into per-turn prompt assembly with relevance selection and a bounded digest; fail-open.
- **Slash commands**: a curated in-code registry; parse a leading `/` at ingress; expand-to-prompt or trigger a flow, always through `is_tool_allowed` + audit + PHI/taint; unknown/malformed → friendly message; discovery via server-rendered chrome.

## Complexity Tracking

> No constitution violations require justification. The two posture notes above are tracked deliberate decisions (audited, owner-approved, bounded), not deviations — recorded here for reviewer visibility rather than as exceptions.

| Item | Why tracked | Why not a violation |
|------|-------------|---------------------|
| In-process agents skip the WS `AGENT_API_KEY` handshake | Removes a transport-auth step for built-ins | The key authenticates external transport; in-process first-party code is inside the trust boundary, and all runtime gates + delegated-authority attribution + audit are preserved |
| Safe agents flip the permission baseline to allow | Changes the default-deny posture for the trusted fleet | Owner-approved + audited; check-time only (no per-user writes); explicit opt-out and hard blocks always win — a default change, not a control bypass |
