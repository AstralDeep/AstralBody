# Research: Bring-Your-Own Client-Side Agents (Feature 057)

**Method**: six parallel codebase deep-dives (registration/transport, authoring-lifecycle reuse, boundary security, desktop hosting, constitution delivery + data model, cross-client chrome). Each decision below is grounded in the actual code, cited by `path:symbol (line)`.

## Consolidated architecture decision

A user's agent is **generated server-side (the LLM lives there) but runs on the user's desktop client**, which **dials in** to the orchestrator and **tunnels agent frames over its already-authenticated UI WebSocket**. The orchestrator treats it as a normal networked agent facing the **existing, unchanged gate stack** — which already re-derives the acting principal from its own record, checks live per-user grants, and mints an RFC 8693 delegation token. The feature adds four things on top: **owner-binding at connect**, a **pre-generation Analyze gate** against a baked-in agent constitution, a **code-delivery seam** (push the bundle to the host instead of `Popen` on the server), and a small set of **owner-isolation hardenings** the research found are missing today.

---

## D1 — Transport: agent-dials-in, tunneled over the authenticated UI socket

**Decision**: The desktop host connects **inward** and its agent frames ride the client's existing authenticated UI WebSocket (a relay), rather than the orchestrator dialing out. The owner principal is inherited from `ui_sessions[ws]` (already the validated OIDC `sub`), so no second auth handshake and no shared-secret exposure. Agent liveness is tied to the UI socket — which makes **offline-on-client-close automatic** (FR-010). A standalone authenticated inbound `/agent` WS route (mirroring `handle_ui_connection_fastapi`) is the documented alternative if decoupling is later wanted.

**Rationale**: Today an external agent connects **only via outbound discovery** — `_monitor_agents (orchestrator.py:11156)` polls localhost and `discover_agent (orchestrator.py:1145)` dials `ws://.../agent` on the agent's own uvicorn server (`BaseA2AAgent.run() base_agent.py:712` is a server). `windows-client/win_agent/agent.py` binds `0.0.0.0:8771` and only works because dev co-locates the orchestrator (Docker `host.docker.internal`); **the orchestrator cannot reach a user's home laptop behind NAT in production** (`sandbox.ai.uky.edu`). So transport must invert. `handle_agent_message (orchestrator.py:1292)` already routes `RegisterAgent`/`MCPResponse`/`AgentHopRequest` regardless of socket origin, so feeding those frames from a UI-socket relay is a small, well-fitting addition. Tying liveness to the UI socket is exactly the offline-on-close semantics the spec wants.

**Alternatives rejected**: keep outbound-dial (fails across NAT — the reason `win_agent` is dev-only); run the agent as an orchestrator `Popen` subprocess (`agent_lifecycle.start_draft_agent:468` — this is exactly what 057 eliminates, SC-002); A2A JSON-RPC (also outbound/card-polled).

**Reuse**: `handle_ui_connection_fastapi (10555)` accept+disconnect pattern; `handle_agent_message (1292)` router; `shared/local_transport.py:LoopbackSocket` send-shaped adapter; `_agent_listen_loop finally (1272–1286)` deregister-on-disconnect.

---

## D2 — Boundary security: reuse the gate stack; add owner-isolation the code lacks today

**Decision**: The per-action re-verification core is **already built and reused unchanged**. Bind each user agent to exactly one owner at connect, then let the existing stack refuse anything outside that owner's live grants. Add the missing owner-isolation pieces the research surfaced.

**What already holds (reuse verbatim, FR-014/015/018, SC-003)**:
- `_authorize_and_prepare/_run_gate_stack (orchestrator.py:6252/6282)` run on **every** dispatch path and **overwrite `args[user_id]` with the session principal (:6470)** — agent-supplied identity is discarded.
- `tool_permissions.is_tool_allowed (:272)` reads live per-`(user,agent)` grant rows = the owner's **current** grants; `_safe_flip_allowed (:365)` already denies the safe-baseline flip for private (`is_public=False`) agents.
- The 056 confused-deputy closure: `_register_dispatch_context (:6960)` + `_handle_agent_hop_request (:7161)` resolve authority from the orchestrator's own record and refuse `ctx.agent_id != initiator`; `mint_child_delegation (delegation.py:549)` intersects scopes and `verify_delegation_chain (:602)` requires a human-terminated actor chain.

**Gaps this feature MUST close (new work)**:
1. **Owner-binding at registration** — `register_agent (:932)` stores `self.agents[agent_id]=ws` unconditionally and auto-assigns ownership only if none exists (`:1079`) with **no check that the connecting principal owns the id**; combined with `AGENT_API_KEY` being a **single shared secret (auth.py:584)**, any keyholder could register/overwrite any agent id. Bind owner from the authenticated socket; refuse an id owned by a different principal; namespace user-agent ids to the owner (Constitution H).
2. **`set_agent_permissions` visibility hole** — `api.py:651` validates only that the agent+tools exist, **not that the caller may see the agent**, so user B could grant *themselves* scopes on user A's private agent and invoke it (a concrete SC-003 break, exploitable today for any private agent). Add a shared `can_user_use_agent(user_id, agent_id) = is_public OR caller-is-owner` enforced at the **grant endpoint, the dispatch gate, and tool-list build** (defense in depth, FR-016/019).
3. **Per-owner ingress bound** — no rate/in-flight cap exists in `handle_agent_message (:1292)`, where each `AgentHopRequest` spawns a task before any budget charge. Add a per-owner rate/in-flight bound scoped to externally-connected user-agent sockets (FR-017/SC-008), extending `concurrency_cap.py`/`chain_authority.ChainBudget`.
4. **No secrets to untrusted agents** — do **not** hand a user-hosted agent the `_delegation_token` bytes (:6555) or per-user secrets on the direct dispatch path; mirror the 054 in-process-only credential rule (:6494). The orchestrator re-authorizes at dispatch, so the agent never needs to hold them.
5. **Honest offline** — replace the `agent_urls` reconnect + retryable "not connected" fallback (`:7806–7828`, wrong for a NAT'd agent) with a prompt honest-offline `MCPResponse` (FR-011).

**Alternatives rejected**: trust the local sandbox for ownership (violates Constitution E — boundary must hold alone); rely on tool-list invisibility (a UI property; the grant endpoint/dispatch have no ownership check); a parallel authz path (FR-007 — reuse the one gate stack).

---

## D3 — Authoring lifecycle: reuse 012/027; add one pre-generation Analyze gate

**Decision**: Map Specify→Clarify→Plan→Tasks→Analyze onto the existing draft machinery (FR-007) — **not** a parallel pipeline. Reuse `AgentLifecycleManager.create_draft/generate_code/refine_agent/approve/apply_revision (agent_lifecycle.py)` and its static code gates (`code_security.CodeSecurityAnalyzer`, `agent_validator.AgentSpecValidator`) **unchanged**. Add: a **5-phase state machine** over `draft_agents` (additive columns), and **one new deterministic Analyze gate** (`orchestrator/agent_analyze.py`) that checks the *drafted spec* against the agent constitution's A–L checklist **immediately before `generate_code`** — the current gates check *generated code*, post-generation, which is too late for FR-003/SC-004. On any violation Analyze refuses and does not call `generate_code`, making "no code while Analyze fails" structural.

**Critical change**: the runtime **must not** run on the orchestrator. `start_draft_agent (agent_lifecycle.py:468)` does `subprocess.Popen` on the server — reused only for an **ephemeral, clearly-bounded authoring-time self-test**, never the live agent. The live agent is delivered to the desktop host (D5) and run there (SC-002).

**Reuse**: `agentic_creation._create_capability` + `HANDLERS` (`_h_draft_approve/_refine/_discard/_revision_apply`, `_owned_draft/_decidable_draft`); `apply_revision` (rollback-safe swap = FR-026) + `agent_trust.reset_on_revision` (= Constitution L / FR-028); `agent_generator.AGENT_PY_TEMPLATE/MCP_SERVER_TEMPLATE` (the 3-file `BaseA2AAgent` bundle a host runs). Keep `origin='byo_client'` distinct from `auto_chat` so gap-dedup and chat tool-injection (`should_inject`) never conflate the deliberate flow.

**Integration risk flagged**: generated bundles `import shared.base_agent`, but the desktop host vendors `astral_client`, not the backend `shared` package (`win_agent` uses a self-contained aiohttp form). Codegen must target the **desktop runtime shape** (a self-contained bundle) or the host ships a compatible shim — resolved in Phase 1 contracts.

---

## D4 — Agent-constitution runtime home + data model

**Decision (home)**: Bake the agent constitution as a versioned markdown asset under **`backend/agent_constitution/agent_constitution.md`**, because `Dockerfile:49` copies **only `backend/`** into the image — `.specify/` and `specs/` are not present at runtime, so the Analyze gate cannot read `specs/057.../agent-constitution.md`. Add loader `backend/orchestrator/agent_constitution.py` that resolves the path `__file__`-relative (mirroring `knowledge_synthesis.py:49 AUTHORED_KNOWLEDGE_DIR`, the feature-040 skill-pack precedent), parses the semver from the header into `AGENT_CONSTITUTION_VERSION`, and parses the Analyze Gate Checklist into a structured A–L list. **Do not** hand-copy the text into a Python literal — `mcp_tools_dev.py:231 CONSTITUTION_PRINCIPLES` already drifted to an unrelated old constitution (proof the copy-into-code approach rots). Keep the `specs/` copy as a review pointer with a **byte-identity test** between the two copies.

**Decision (data model)**: Add one guarded `user_agent` table + one `agent_ownership` row per user agent (so existing routing/permission code treats it uniformly). Bump `SCHEMA_REVISION 055.002 → 057.001`. Add `FF_BYO_AGENTS` (default **off**, fail-closed FR-029). Full schema in [data-model.md](data-model.md).

**Key modeling calls**: `status` is a **durable lifecycle** state (`authoring|validated|live|disabled`), **distinct** from running/offline, which stays **derived from socket presence** (`self.agents` + fresh `host_last_seen_at`) — persisting liveness invites drift on crash. `is_public BOOLEAN CHECK(is_public=FALSE)` makes privacy-by-construction structural (FR-019/020, Constitution K). `constitution_version` + `revalidation_required` implement Constitution L / FR-028 (a MAJOR bump forces re-Analyze before routing resumes).

**Reconciliation risk (highest-detail)**: `agent_ownership` keys on **`owner_email`** while permissions/dispatch key on **`user_id`** — the owner-binding check must reconcile these with an explicit canonical key (`owner_user_id`), or a mismatch could lock owners out or mis-bind an agent.

---

## D5 — Desktop hosting: Windows first (in-process, zero deps); macOS gated

**Decision**: Two asymmetric platform stories; ship **Windows as the v1 host**.
- **Windows (feasibility HIGH, zero new deps)**: the client is a frozen CPython/PySide6 process; run the generated agent as an **in-process daemon thread** exactly like `win_agent.agent.start_agent_thread` (or a child worker re-invoking `sys.executable`). `aiohttp/websockets` are already pinned in `windows-client/requirements.txt`.
- **macOS (feasibility LOW–MODERATE, App-Store blocker)**: SwiftUI has no embedded Python; hosting needs a **bundled signed Python framework** (~30–40 MB, python-build-standalone) run as a subprocess relayed over the existing `WSClient`. Viable **only** in a Developer-ID-signed, notarized, **direct-download** build — the Mac App Store build's entitlements grant no `network.server` and Hardened Runtime + library validation (feature 053) make a dlopen-heavy Python fragile. **Recommendation**: MAS macOS build behaves as an author-only client (FR-024); desktop hosting on macOS is gated behind the non-sandboxed channel or deferred.
- **Mobile/web (Android, iOS, browser)**: author + manage only; execution binds to the user's desktop host, online while it runs (spec Clarification; FR-024).

---

## D6 — Authoring chrome: one server-driven surface, dual web+native rendering

**Decision**: Deliver authoring + management as **one** new server-driven chrome surface `backend/webrender/chrome/surfaces/authoring.py` (surface key `agent_authoring`), reusing the feature-043 device-target-aware plumbing verbatim — no client-side wizard. Register it in `surfaces/__init__.py::SURFACE_MODULES`. `chrome_events._render_surface` already branches on `_device_type`: web gets `ChromeRender` HTML from `render()`, native SDUI gets `ChromeSurface` from `components()` (ROTE-adapted). Unlike today's HTML-only `drafts.py`/`agents.py` (which degrade to `_sdui.placeholder()` on native), the authoring surface **must ship both `render()` and `components()` from day one** so cross-client parity (FR-022, Constitution XII) holds.

The 5-phase wizard **is** the existing re-render-on-handler-return contract: `chrome_author_specify/_clarify/_plan/_tasks/_analyze/_generate` handlers (in the `chrome_*` namespace so `chrome_events._is_chrome_action` auto-dispatches) each validate+persist the phase's edited artifact, advance, and return `("agent_authoring", {session_id}, notice)` to re-render at the next phase. **Clarify and Analyze are hard gates**: their handlers decline to advance (re-return the same phase + a plain-language violation notice) until resolved, so an Analyze failure **structurally cannot reach `_generate`** (FR-003). The **watch is excluded for free** — it is absent from `_NATIVE_SDUI_DEVICE_TYPES=(windows,android,ios,macos)` and the native `menu_model` channels (FR-023, zero new code). FR-024's "runs on your desktop host / offline when none online" state is a surface-level notice driven by `host_last_seen_at`.

---

## Cross-cutting risks carried into the plan

- **Transport reachability / NAT** — the single biggest architectural change; the inbound-tunnel decision (D1) owns it.
- **Owner identity reconciliation** (`owner_email` vs `user_id`) — pick a canonical key before any owner-binding code (D2/D4).
- **`set_agent_permissions` hole is exploitable today** — closing it (D2) must not break legitimate owner/admin management on the agents surface.
- **Codegen target mismatch** — generated bundle imports vs the desktop host's vendored packages (D3); contracts must pin the bundle shape.
- **Self-test location** — must not run the live agent on the server; keep any self-test ephemeral/host-side (D3).
- **macOS hosting** is gated/deferred; Windows is the v1 host (D5).
