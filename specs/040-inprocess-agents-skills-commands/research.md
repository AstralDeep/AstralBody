# Research & Design Decisions: 040-inprocess-agents-skills-commands

Phase 0 output. Each decision records what was chosen, why, and the alternatives rejected. Findings are grounded in the discovery pass over the live codebase (file:line references are the seams the implementation touches).

## D1 — In-process dispatch seam

**Decision**: Add a positive-registry branch inside `_execute_via_websocket` (orchestrator.py ~5808-5844). When `agent_id` is a registered built-in, run the agent-side pre-steps (credential decrypt + `_runtime` build) and call `await asyncio.to_thread(agent_obj.mcp_server.process_request, request)`, returning the resulting `MCPResponse` directly. Leave `execute_single_tool` and the whole gate stack (5072-5410) untouched as the entry point.

**Rationale**: Every security/permission/policy/taint/credential/audit/concurrency control already wraps `_execute_with_retry`; replacing only the innermost transport call preserves them with no duplication. `asyncio.to_thread` keeps synchronous tool bodies off the event loop (matching today's `base_agent.py:357`). The `MCPResponse` shape (result, ui_components, error{code,message,retryable}, correlation_id) is identical to the WS path, so all downstream renderers/audit are unaffected.

**Alternatives rejected**: (a) Reuse `VirtualWebSocket` as the live transport — it buffers instead of correlating, is one-directional, and cannot deliver progress/streaming to a live UI or return an `MCPResponse`. (b) Rewrite the MCP dispatch in the orchestrator — duplicates the per-agent MCP server (kwarg filtering, error classification, ui-component packing) and risks drift. (c) Keep the WS but loop back over localhost — retains the network/serialization cost we are trying to remove.

## D2 — Loopback transport for progress / streaming / jobs

**Decision**: New `shared/local_transport.py::LoopbackSocket` implementing the subset of the WS interface the agent side uses (`send_text`, `send_json`, `client`). Its `send_*` decode the agent's `ToolProgress`/`ToolStreamData`/`ToolStreamEnd` frames and call the orchestrator's existing handlers directly (`_handle_tool_progress` ~6952, `StreamManager.handle_agent_chunk`/`handle_agent_end`). It captures the orchestrator's running loop so worker-thread emitters (`agent_runtime.start_long_running_job`, `stream_sdk` `StreamCtx.emit`) can `run_coroutine_threadsafe` safely.

**Rationale**: The agent side already emits structured frames over `ws.send_text`; routing those frames into the same handlers the WS listen loop calls reuses all fan-out, coalescing, FPS clamp, terminal-progress workspace-persist, and concurrency-cap release logic unchanged. Long-running jobs keep returning a prompt "started" unary response while the poller continues — the loopback only carries the later progress frames.

**Alternatives rejected**: Direct callback injection into each tool — would require touching every streaming/long-running tool and breaks the uniform frame contract.

## D3 — Per-user credential confidentiality (Clarifications Q4)

**Decision**: Keep end-to-end ECIES. The orchestrator continues to inject *encrypted* per-user credentials (`get_agent_credentials_encrypted`, orchestrator.py ~5211); the in-process agent object owns its P-256 private key (`backend/data/agent_keys/<agent_id>.pem`) and decrypts inside its own boundary via the existing `_decrypt_with_fallbacks` (predecessor-key fallback preserved). The `_credentials_stale` flag on decrypt failure is preserved.

**Rationale**: Negligible cost beside eliminating the network hop; preserves the threat model (orchestrator never materializes plaintext secrets) even though there is no longer a transport boundary. Honors the owner's explicit choice.

**Alternatives rejected**: Plaintext passing in-process — faster by an immeasurable margin but makes per-user secrets plaintext-resident in the orchestrator; rejected by the owner.

## D4 — Audit attribution on the in-process path (FR-029, FR-032)

**Decision**: Because the in-process branch sits *inside* `_execute_via_websocket`, which is reached through `execute_single_tool`, the `ToolDispatchAudit` wrapper still reads real claims from `ui_sessions.get(websocket)` for normal chat turns — attribution is preserved automatically (correct actor user, agent_id column, conversation id, shared correlation id). Separately, wrap the parallel-tool dispatch (`execute_parallel_tools` ~5467, which today bypasses `ToolDispatchAudit`) so every tool call is audited regardless of path.

**Rationale**: The single biggest audit regression risk identified in discovery is a non-real socket (VirtualWebSocket) yielding `legacy` claims and silently dropping tool audit. Keeping the real-turn entry point avoids it; the parallel-path wrap closes a pre-existing gap so the "every tool call auditable" guarantee in the spec is actually true.

**Alternatives rejected**: Re-deriving claims inside the in-process executor — unnecessary for real turns and risks divergent attribution.

## D5 — Safe-marking storage and check-time baseline (Clarifications Q1/Q2)

**Decision**: New `agent_trust` table keyed by `agent_id` (`is_safe`, `marked_by`, `marked_at`, `prior_state`). `tool_permissions.is_tool_allowed` consults it (behind `FF_SAFE_AGENTS`): resolution order becomes (1) explicit per-(tool,kind) override → honor it; (2) explicit scope grant/deny → honor it; (3) if the agent is safe AND there is no explicit negative record → ALLOW; (4) else deny. No per-user rows are written; the safe verdict is computed at check time. A user "explicitly disabling" a scope/tool is represented as an explicit negative record (an override deny or a scope row marked disabled) that the gate honors over the safe default. Hard security-flag blocks (`tool_security` `blocked=True`) are an independent veto and are never cleared by safe.

**Rationale**: Matches the owner's choice (all scopes allowed by default for trusted agents, but explicit opt-out wins, applied without rewriting everyone's permissions). Keeps `is_public` (visibility) distinct from trust. Avoids a mass migration and preserves user choices.

**Alternatives rejected**: (a) Reuse `is_public` for safety — it is already auto-true for shipped agents, so it cannot also mean "vetted." (b) Eagerly write default-scope grants into every user's rows — invasive, overwrites implicit state, and a privacy/data footprint the owner declined. (c) Lazy per-user grant on first encounter — still accumulates rows and complicates opt-out semantics.

## D6 — Safe marking lifecycle & gating

**Decision**: A `mark_safe(agent_id, safe)` operation in `agent_trust.py`, admin/owner-gated server-side (mirroring `_h_draft_approve`'s admin check and `set_agent_visibility`), emitting an `agent_lifecycle` audit event (`marked_safe`/`unmarked_safe`) with actor + prior_state. The bundled fleet is marked safe at boot as a system/owner action (idempotent, audited). `agentic_creation.apply_revision` resets `is_safe` to false for a revised previously-safe agent (re-approval required), since a revision can reintroduce un-reviewed code.

**Rationale**: Keeps marking auditable and owner-controlled; prevents a self-serve safety escalation; respects that revisions reintroduce risk.

## D7 — etf_tracker_1 removal (9-item checklist)

**Decision**: Delete `backend/agents/etf_tracker_1/`; remove `'etf-tracker-1-1'` from `_FIRST_PARTY_PUBLIC_AGENT_IDS` (database.py:1115); remove the `_AGENT_ICONS` entry (history_surface.py:35); fix the stale doc comment (orchestrator.py:7238); update the three catalog tests (test_agent_retirement.py:74, test_no_behavior_change.py:33, test_wiring_030.py:237); add `'etf-tracker-1-1'` to `RETIRED_AGENT_IDS` for graceful old-transcript handling; ship a one-time guarded `_init_db` migration that purges orphaned ownership/scope/override/credential rows and retires/reassigns `chats.agent_id` for the retired id.

**Rationale**: Discovery confirmed exactly these references (no seed SQL inserts it). The cleanup migration mirrors the proven 029 `_migrate_agent_catalog` pattern, so removal is complete rather than leaving orphans.

**Alternatives rejected**: Directory-only delete — leaves orphaned rows and reddens three tests.

## D8 — Skill packs: location, format, loading (US4)

**Decision**: Authored packs live in a committed `backend/knowledge_packs/techniques/<agent>.md` directory, separate from the gitignored, auto-synthesized `backend/knowledge/`. The synthesizer (`knowledge_synthesis.py`) never writes there; `KnowledgeIndex` reads it with an `authored` provenance flag and authored content takes precedence over synthesized. Wire the dormant `get_techniques_for_agent(agent_id)` (defined but never called) into per-turn system-prompt assembly (orchestrator.py ~3281-3357) so that, for the agents whose tools are in play this turn, a bounded, relevance-selected digest is injected. Gated by `FF_SKILL_PACKS`; fail-open to today's behavior on any error.

**Rationale**: Discovery found `get_techniques_for_agent` is the single highest-value dormant capability and that auto-synthesis would clobber hand-authored content. Committing packs makes them reproducible across rebuilds and version-controlled; relevance-only loading avoids the context-bloat the 033 work is reducing.

**Alternatives rejected**: (a) Treat the gitignored synthesized knowledge as the skill surface — not reproducible, telemetry-derived not instructional, gets overwritten. (b) Inject all packs every turn — regresses token budget and cache stability.

## D9 — Slash commands: surface and routing (US5)

**Decision**: A curated, first-party command registry in `orchestrator/slash_commands.py` (`{name, kind: prompt_expand|flow, description, required_scopes, handler/template}`). A leading-`/` token is detected at chat ingress (`api.py`/`chat_steps.py`); `prompt_expand` commands rewrite into a normal prefilled model turn, `flow` commands trigger a defined sequence — both always going through `is_tool_allowed` + audit + PHI/taint, never a privileged bypass. Unknown/malformed commands yield a friendly chrome message, not an error. Discovery (typeahead + a `/help`/commands surface) is server-rendered chrome in `webrender` + ROTE-adapted. Initial curated set (final list in tasks.md): `/help`, `/agents`, `/summarize`, `/research`, `/weather`. Gated by `FF_SLASH_COMMANDS`; if parsing fails, the input is treated as a normal message (fail-open).

**Rationale**: Reuses the established meta-tool/SYSTEM_PROMPT_ADDENDUM and chrome patterns; keeps untrusted input on the same rails as any chat message; SDUI-compliant (no new client framework).

**Alternatives rejected**: (a) Model-invoked only (no typed surface) — does not satisfy "user-typed /commands like Claude Code." (b) Client-only parsing — would bypass server-side permission/audit/PHI and violate the SDUI/security posture. (c) User-definable macros now — deferred (Assumptions); larger security surface, not required for v1.

## D10 — Launch model & feature-flag defaults

**Decision**: `start.py` no longer spawns the nine bundled agents as subprocesses; the orchestrator instantiates and registers them in-process at boot. Draft agents keep their on-demand subprocess + self-test path unchanged; external A2A agents keep their discovery/transport. Flag defaults: `FF_INPROCESS_AGENTS` default ON (this is the intended behavior; the flag is a kill-switch back to the WS path), `FF_SAFE_AGENTS` default ON, `FF_SKILL_PACKS` default ON, `FF_SLASH_COMMANDS` default ON — each with exact legacy behavior when off.

**Rationale**: The owner wants built-ins "built into the system" and "as performant as possible," so in-process is the default, with a documented kill-switch for safe rollout. Drafts must retain isolation because they run un-reviewed generated code.

**Alternatives rejected**: Default-off in-process — contradicts the explicit intent; retained only as the off-path/kill-switch.
