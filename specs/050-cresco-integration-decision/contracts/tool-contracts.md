# Contract: Cresco bridge tools (`backend/agents/cresco/mcp_tools.py`)

**Feature**: 050-cresco-integration-decision | [spec.md](../spec.md) · [data-model.md](../data-model.md)

Tools are entries in `TOOL_REGISTRY` (`{function, description, input_schema, scope}`), dispatched by the `MCPServer.process_request(**arguments)` path. Every handler MUST accept `**kwargs` (the base class injects `_runtime`, `_credentials`, etc.) and return astralprims primitives via `create_ui_response([...])` or `{"_ui_components": [c.to_dict() …], "_data": {…}}`. Handlers translate every `wsapi_client` typed error into an `Alert(variant="error", …)` result — never an unhandled exception.

Common precondition for all tools: if the client is unconfigured (`CRESCO_WSAPI_URL` / `CRESCO_SERVICE_KEY` unset) the tool returns the "Cresco fabric not configured" Alert and does not dial (FR-003).

## Read tier — `tools:read` (US1)

| Tool | wsapi action | Args (schema) | SDUI output |
|---|---|---|---|
| `cresco_list_regions` | `listregions` | — | `Table` of regions (+ counts) |
| `cresco_list_agents` | `listagents` | `region?` | `Table` of agents (`region_agent`, status) |
| `cresco_agent_info` | `getagentinfo` | `region`, `agent` | `Card` + plugin `Table`/health |
| `cresco_get_sysinfo` | `getsysinfo` | `region`, `agent` | `Card`/`KeyValue` host sysinfo |
| `cresco_read_logs` | log/metric read | `region`, `agent`, `limit` (bounded) | `Table`/`Text`, capped window |

Read-tier acceptance:
- Returns **live** values from the fabric, rendered as SDUI (SC-003).
- Bounded reads (`cresco_read_logs`) MUST cap the window and note truncation; never stream unbounded.
- Each call is audited with fabric identifiers (see [audit-contract.md](audit-contract.md)).

## Write tier — `tools:write` (US2)

| Tool | wsapi action | Args | SDUI output |
|---|---|---|---|
| `cresco_file_put` | filerepo put | `region`, `agent`, `path`, `content`/attachment ref | `Alert(success)` + `Card` receipt |
| `cresco_file_get` | filerepo get | `region`, `agent`, `path` | `Card`/`Text` (bounded size) with content |

Write-tier acceptance:
- Round-trips through the fabric under **write scope** and is audited (SC per US2-AC1).
- Denied for users without write scope by the standard permission gate.

## System tier — `cresco_run_process` (executor) — **`tools:system`, hard-flagged, default-deny** (US2)

The executor wraps Cresco's **arbitrary-shell** surface (research.md R3). It is the most tightly gated tool in the feature.

| Property | Requirement |
|---|---|
| Scope | `tools:system` (system resources / arbitrary execution). |
| Security flag | Carries a **hard `tool_security` flag** so no scope/baseline path can silently enable it. |
| Default posture | **Default-deny** for every user (FR-006). |
| Safe baseline | The safe-agent baseline flip **MUST NEVER** turn it to allow — hard flag wins (US2-AC3, SC-004). |
| Enablement | Runs **only** after an **explicit per-user permission override** for `cresco_run_process`. |
| Audit | **Every** attempt — allowed or denied — is audited; a denial writes the denial audit (US2-AC2). |
| Args | `region`, `agent`, `command`/`args`, bounded timeout. |
| Output | `Card`/`Text` of stdout/stderr/exit (bounded), or the denial `Alert`. |

Acceptance (SC-004): a normal user is **denied by default**; the tool runs **only** via explicit override; every attempt is audited; the safe baseline never enables it.

## Cross-cutting handler contract

- No handler dials until the client is configured (FR-003).
- No handler leaks `CRESCO_SERVICE_KEY` into output or logs (Constitution VII).
- Every typed `wsapi_client` error maps to a user-legible `Alert` (see the wsapi client contract error table), with `retryable` set to match.
- Handlers surface the fabric identifiers (`region`, `agent`, `plugin`) for the audit path (audit-contract.md).
- Tool output is astralprims primitives only (`css`, not `style`; `.to_dict()`, not `.to_json()`).
