# Implementation Plan: Cresco Integration (Bridge Agent)

**Branch**: `050-cresco-integration-decision` | **Date**: 2026-07-06 | **Spec**: [spec.md](spec.md)
**Decision**: GO on a first-party Python bridge agent over the Cresco `wsapi` seam; NO-GO on platform-level adoption; DEFER a Cresco-side plugin. Approved for implementation.

## Summary

Add a first-party in-process **Cresco bridge agent** (`backend/agents/cresco/`) that reaches an external Cresco fabric through its `wsapi` WebSocket gateway, using only the already-present `websockets` library plus stdlib (zero new dependencies). The agent exposes risk-tiered tools (read: topology/telemetry; write: file ops; system + hard-flagged: `executor`), behind `FF_CRESCO` (default off, fail-closed), with the fabric as external infrastructure configured by environment. All authorization, security-flag, delegation, and audit machinery is inherited from the platform — nothing new to build there.

## Technical Context

**Language/Version**: Python 3.11+ (backend). No JVM in the product; the Cresco fabric is external infrastructure.
**Primary dependencies**: existing `websockets>=12.0` + Python stdlib (`json`, `gzip`, `base64`, `ssl`, `asyncio`). **No new third-party libraries.**
**Storage**: none new (no schema change). Config is env-only (`CRESCO_WSAPI_URL`, `CRESCO_SERVICE_KEY`, `FF_CRESCO`).
**Testing**: unit tests for the wsapi client (envelope encode/decode, gzip params, TLS context, egress validation) with a mocked socket; integration tests for the agent tools; end-to-end verification against a local single-node fabric.
**Target**: the existing single-container orchestrator; the bridge is one more in-process agent.

## Constitution Check

This is **product code** (not a documentation/research feature), so the code-execution gates apply:

- **I (Python-only backend)**: PASS — the bridge is Python; the JVM fabric is external infrastructure (Keycloak posture). No JVM enters the image.
- **II (SDUI)**: PASS — tool outputs are `astralprims` primitives rendered by the orchestrator; no new client/wire change.
- **III (coverage)**: APPLIES — ≥90% changed-code coverage; the wsapi client and tools are unit- + integration-tested.
- **V (dependencies)**: PASS — zero new third-party libraries (proven feasible live); `pycrescolib` deliberately not adopted (`backoff` + global TLS-verify-off).
- **VII (security)**: PASS — inherits fail-closed `AGENT_API_KEY` registration, per-tool scopes/`is_tool_allowed`, `tool_security` hard flags, `agent_trust`, RFC 8693 delegation, hash-chained audit; executor system-scoped + hard-flagged + default-deny; egress-validated dial-out; verified TLS; env-only runtime secrets. Sanctioned by the new Cresco constitution clause.
- **IX (migrations)**: PASS — no schema change.
- **X (production readiness)**: APPLIES — flag default-off, config fail-safe (unavailable, not crashing), observability via audit; verified against a live fabric.
- **XI (CI)**: APPLIES — lint, tests, coverage, image build, boot smoke, secret scan; the secret-scan gate guards the `cresco_service_key`.

Gate result: **PASS** (build-time gates to be satisfied by the implementation + tests).

## Project Structure

Filenames follow the in-process-agent discovery convention (feature 040): the class module MUST be `<dir>/<dir>_agent.py`, and the tool registry lives in `mcp_tools.py` behind an `mcp_server.py` router — mirroring `agents/summarizer/` exactly. Agent id is pinned **`cresco-1`** (dir → id convention; it is the `local_agents` dispatch key and the ECIES key stem).

```
backend/agents/cresco/
├── __init__.py            # re-exports (class, MCPServer, tools, TOOL_REGISTRY)
├── cresco_agent.py        # class CrescoAgent(BaseA2AAgent), agent_id="cresco-1"; __init__ → super().__init__(MCPServer(), …)
├── mcp_server.py          # MCPServer: self.tools = TOOL_REGISTRY; process_request() router (copy of summarizer)
├── mcp_tools.py           # read/write/executor handlers (**kwargs, astralprims out) + TOOL_REGISTRY (function/description/input_schema/scope)
├── wsapi_client.py        # JSON-over-WSS client on `websockets` + stdlib; envelope encode/decode; verified-TLS ctx; egress-validated dial
└── tests/                 # wsapi client + tool unit/integration tests (mocked socket, pinned fixtures)

backend/orchestrator/local_agents.py   # add "cresco" to BUILT_IN_AGENT_DIRS + a FF_CRESCO `continue` guard in the register loop
backend/shared/feature_flags.py        # FF_CRESCO (default off, fail-closed)
backend/shared/database.py             # add 'cresco-1' to _FIRST_PARTY_PUBLIC_AGENT_IDS (UI visibility when flag on)
```

Supporting design artifacts: [research.md](research.md) (evaluation + pinned facts), [data-model.md](data-model.md) (config/wire/tool entities, no schema), [quickstart.md](quickstart.md) (fabric bring-up + verification runbook), [contracts/](contracts/) (wsapi-client / tool / audit contracts).

## Phased Approach

**Phase 0 — Scaffold.** `backend/agents/cresco/` package; `FF_CRESCO` (default off) in `feature_flags.py`; conditional registration in `local_agents.py` (flag-off = not registered).

**Phase 1 — wsapi client (`wsapi_client.py`).** Connect to `wss://…/api/apisocket` with the `cresco_service_key` header on `websockets`; RPC envelope `{message_info, message_payload}`; gzip+base64 param (de)coding; verified-TLS `ssl` context (no global bypass); `validate_egress_url` before dial; bounded timeouts + stdlib reconnect/backoff. Unit-tested against a mocked socket using the frame shapes captured in the evaluation.

**Phase 2 — Read tools (US1).** `cresco_list_regions`, `cresco_list_agents`, `cresco_agent_info`, `cresco_get_sysinfo`, bounded log/metric reads — read scope; rendered as SDUI; audited with fabric identifiers.

**Phase 3 — Write + executor tools (US2).** File put/get at write scope; `cresco_run_process` (executor) at **system scope + hard `tool_security` flag, default-deny**, never safe-baseline-enabled; each audited.

**Phase 4 — Verify.** Flag-off no-op (existing suite green). Flag-on + local single-node fabric (`agent-1.3-SNAPSHOT.jar`, `-Dis_global=true -Denable_wsapi=true`): read tools round-trip; executor denied by default and allowed only via explicit override; audit rows carry fabric ids; self-signed cert rejected without a configured CA/fingerprint. Record evidence.

## Notes

- The evaluation (findings in [spec.md](spec.md)) brought up a live single-node fabric and proved the zero-dependency wsapi round-trip; Phase 1 reuses those captured frame shapes as test fixtures.
- Cross-fabric provenance: a spec-048 recursive delegation chain terminating in a Cresco tool call is fully attributable via FR-008 — an available demonstration once both flags are on.

## Complexity Tracking

No entries.
