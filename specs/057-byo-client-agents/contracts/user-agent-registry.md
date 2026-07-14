# Contract: User-Agent Registry + Code-Delivery Seam

**Purpose**: the durable registry for user agents and the seam that delivers generated code **to the desktop host** (never runs it on the orchestrator — SC-002/FR-008).

## Registry (`user_agent` table)

Schema in [data-model.md](../data-model.md). Contract points:

- **Canonical owner** is `owner_user_id` (OIDC `sub`); the boundary binds to it, never to an email or card field.
- **Privacy is structural**: `is_public BOOLEAN CHECK (is_public = FALSE)`. No write path may make a user agent public (FR-020).
- On go-live, a companion `agent_ownership` row (`is_public=FALSE`) is inserted so existing routing/permission/visibility code treats the agent uniformly (FR-007) — no parallel path.
- `status` (`authoring|validated|live|disabled`) is durable lifecycle; `running/offline` is derived from socket presence and never persisted.

## `can_user_use_agent(user_id, agent_id)` (the isolation predicate — closes a live hole)

`can_user_use_agent(user_id, agent_id) := agent.is_public OR agent.owner_user_id == user_id`

Enforced in **three** places (defense in depth):

1. **Grant endpoint** `api.py::set_agent_permissions` — refuse if the caller cannot use the agent. (Closes the current hole where any user can grant *themselves* scopes on another user's private agent and then invoke it — a concrete SC-003 break.)
2. **Dispatch gate** — inside the existing permission check, so a crafted request can't bypass the UI list.
3. **Tool-list build** (`_collect_eligible`) — a private agent whose `owner_user_id ≠ current user` is structurally invisible, independent of any stray scope row (FR-019).

## Code-delivery seam (replaces `Popen` for user agents)

On `chrome_author_generate` (after Analyze passes):

1. `agent_lifecycle.generate_code(draft_id)` runs server-side (the LLM lives there) and returns the 3-file `BaseA2AAgent` bundle (`{slug}_agent.py`, `mcp_server.py`, `mcp_tools.py`) — the existing static gates (`code_security`, `agent_validator`) run here.
2. **Do NOT** call `start_draft_agent` (its `subprocess.Popen` runs on the orchestrator — forbidden for the live agent, SC-002).
3. Package the bundle and push it to the owner's desktop host over the tunnel (a UI-channel `agent_bundle_deliver {agent_id, files, constitution_version}` envelope). The host writes it to a local agent dir and starts it (generalizing `win_agent.start_agent_thread`), then registers inward (contracts/agent-tunnel).
4. On successful inward registration, set `user_agent.status='live'`, stamp `constitution_version`, insert the companion `agent_ownership` row.

- **Bundle target**: the generated bundle must target the **desktop-host runtime shape** (self-contained, matching what the host vendors) rather than assuming the backend `shared` package — resolved by the codegen template targeting the host or the host shipping a compatible shim.
- **Self-test**: any pre-delivery self-test must be **ephemeral and clearly bounded** on the orchestrator (or run on the host and reported back) — it must not become a persistent server-side agent process.

## Revision & re-validation (FR-026/FR-028, Constitution L)

- A revision re-enters authoring; the prior `live` agent keeps running until the revision passes Analyze and re-registers (reuse `apply_revision` rollback semantics, host-side).
- A constitution MAJOR bump sets `revalidation_required=TRUE`; the boundary refuses to route the agent until re-Analyze clears it.
