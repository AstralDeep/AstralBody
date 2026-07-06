# Data Model: Cresco Integration (Bridge Agent)

**Feature**: 050-cresco-integration-decision | **Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)

**No database schema change.** This feature adds **no tables, columns, or migrations** (plan Constitution Check IX: PASS). The "data model" here is the set of in-memory / wire / configuration entities the bridge manipulates. All persistence the feature touches is the **existing** audit path (`agent_tool_call` rows via `audit/repository.py`) and the **existing** permission/trust tables (`agent_scopes`, `tool_overrides`, `agent_trust`), written through the platform's normal registration + dispatch paths — not by this feature's own code.

## Configuration entities (environment-only, runtime secrets)

| Key | Kind | Required | Meaning | Absent behavior |
|---|---|---|---|---|
| `FF_CRESCO` | feature flag | no (default **off**) | Master switch. Off ⇒ the agent is **not registered**; no Cresco code path is reachable (kill-switch, byte-identical to today). | Off. |
| `CRESCO_WSAPI_URL` | env | no | wsapi gateway URL, e.g. `wss://fabric.internal:8282`. | Tools report "Cresco fabric not configured"; no boot impact. |
| `CRESCO_SERVICE_KEY` | env, **runtime-only secret** | no | Value of the `cresco_service_key` upgrade header. Never logged, never committed. | Tools report unavailable. |
| `CRESCO_CA_BUNDLE` | env (path) | no | Path to a trusted CA bundle for the fabric's TLS (on-prem/self-signed CA). | Falls back to system trust store; self-signed rejected. |
| `CRESCO_TLS_FINGERPRINT` | env | no | Pinned SHA-256 fingerprint of the fabric's leaf/CA certificate (alternative to a CA bundle). | No pin; standard chain validation. |
| `CRESCO_ALLOW_PRIVATE_HOST` | env (bool) | no | Operator opt-in allowing `validate_egress_url` to accept the **configured** private/on-prem `CRESCO_WSAPI_URL` host. Scoped to that host only — not a global private-host bypass. | Private hosts rejected by egress validation. |

Fail-closed posture: with `FF_CRESCO` off (default) the whole feature is inert. With it on but any of `CRESCO_WSAPI_URL` / `CRESCO_SERVICE_KEY` unset, tools return an "unavailable" result and the orchestrator boots and serves normally (spec FR-003/FR-004; SC-001/SC-002).

## Agent identity

| Field | Value | Notes |
|---|---|---|
| Agent id | `cresco-1` | Convention: dir `cresco` → id `cresco-1`. Also the `orch.local_agents` dispatch key and the ECIES key path stem (`backend/data/agent_keys/cresco-1.pem`). |
| Module | `backend/agents/cresco/cresco_agent.py` | Discovery requires `<dir>/<dir>_agent.py`; **not** `agent.py`. |
| Class | `CrescoAgent(BaseA2AAgent)` | Exactly one `BaseA2AAgent` subclass in the module. |
| Trust seed | **not safe** | Owner/admin approval required before the safe baseline could ever apply; the executor tool is never safe-flippable regardless. |
| Public visibility | listed in `_FIRST_PARTY_PUBLIC_AGENT_IDS` | So the agent appears in the Agents UI when the flag is on. |
| Taint | not added to `_UNTRUSTED_AGENTS` unless it ingests untrusted external web content | Cresco topology/telemetry is fabric-internal, not open-web scraped. |

## Wire envelope (wsapi RPC)

Pinned to the evaluated `pycrescolib` 1.3.0 shape (see [research.md](research.md) R2). Implementation-defined; the client validates against this shape and fails safe on drift.

```jsonc
// Request (control plane, /api/apisocket)
{
  "message_info": {
    "message_type": "...",        // routing/type discriminator
    "message_event_type": "...",  // event discriminator
    "is_rpc": true                // request/reply correlation
    // + rpc correlation id
  },
  "message_payload": {
    "action": "listregions",      // or listagents / getagentinfo / getsysinfo / filerepo_* / executor_*
    // additional params; bulk params gzip+base64-encoded
  }
}
```

- **Encoding helper**: bulk params → `base64(gzip(json_bytes))`; decode is the inverse. Small scalar params may be inline.
- **Correlation**: `message_info` carries the RPC id that pairs a reply to its request; the client awaits the matching reply within a bounded timeout.
- **Addressing**: fabric resources are addressed by `region`, `agent`, `plugin` (the `region_agent[_plugin]` tuple) — carried in payload params and echoed into the audit row (FR-008).

## Tool catalog (risk-tiered)

Scope constants come from `tool_permissions.VALID_SCOPES` (`tools:read`, `tools:search`, `tools:write`, `tools:files`, `tools:system`, `tools:execute`). Each tool declares its tier via the `"scope"` key in `TOOL_REGISTRY`.

| Tool | Verb(s) | Scope | Gate | Story |
|---|---|---|---|---|
| `cresco_list_regions` | `listregions` | `tools:read` | standard | US1 |
| `cresco_list_agents` | `listagents` | `tools:read` | standard | US1 |
| `cresco_agent_info` | `getagentinfo` | `tools:read` | standard | US1 |
| `cresco_get_sysinfo` | `getsysinfo` | `tools:read` | standard | US1 |
| `cresco_read_logs` (bounded) | log/metric read | `tools:read` | standard, bounded window | US1 |
| `cresco_file_put` / `cresco_file_get` | filerepo put/get | `tools:write` | write scope | US2 |
| `cresco_run_process` (executor) | executor submit | **`tools:system`** | **hard security flag + default-deny + explicit per-user override; never safe-baseline-enabled** | US2 |

> Scope note: the executor wraps arbitrary shell. The spec and Constitution VII clause mandate **system scope**; `tools:system` is the declared tier and the tool additionally carries a hard `tool_security` flag so no baseline/scope path can silently enable it. (If the security analyzer classifies arbitrary-shell as `tools:execute`, that is an equivalent or stricter tier and the hard-flag/default-deny invariant still governs — see [contracts/tool-contracts.md](contracts/tool-contracts.md).)

## State & lifecycle

- **No persistent state owned by the feature.** The wsapi connection is a transient, per-process WebSocket the client opens lazily on first tool call and reuses; it reconnects (stdlib backoff) on failure and is torn down on unexpected frames.
- **Audit rows** are written by the existing orchestrator dispatch wrapper (`_execute_with_retry_audited`), not by the tool — the feature's obligation is to surface the fabric identifiers so they land on the row (FR-008). See [contracts/audit-contract.md](contracts/audit-contract.md).
- **Permission/trust rows** (`agent_scopes`, `tool_overrides`, `agent_trust`) are created by the normal `register_agent` path from the card; the feature authors none of them directly.

## Rollback

Feature-flag rollback only: set `FF_CRESCO=off` (or unset) ⇒ the agent is not registered and the system is byte-identical to pre-feature. No schema to migrate down. Removing the `backend/agents/cresco/` package and its `BUILT_IN_AGENT_DIRS` / `_FIRST_PARTY_PUBLIC_AGENT_IDS` entries fully removes the feature with no data cleanup required (no tables were added).
