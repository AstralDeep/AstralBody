# Phase 1 Data Model — External AI Service Agents

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-05-07

This feature **introduces zero new persistent tables**. Storage requirements are met by the existing `user_credentials` PostgreSQL table; runtime state is held in process memory. This document catalogs the entities the feature touches and the in-memory shapes the new code maintains.

---

## 1. Persistent Entities (existing — referenced, not changed)

### 1.1 `user_credentials`

Defined in [backend/shared/database.py](backend/shared/database.py) (per `Database._init_db`).

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PRIMARY KEY | |
| `user_id` | TEXT | From the JWT `sub` claim. |
| `agent_id` | TEXT | Stable identifier (e.g. `"classify-1"`). |
| `credential_key` | TEXT | E.g. `"CLASSIFY_URL"` or `"CLASSIFY_API_KEY"`. |
| `encrypted_value` | TEXT | ECIES-encrypted blob (or Fernet fallback) — orchestrator cannot decrypt the API key when E2E is active. |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**Constraints**:
- `UNIQUE (user_id, agent_id, credential_key)`. This already enforces FR-005 (per-user isolation) at the database layer.
- No foreign key to `users` because user identity is JWT-driven; no users table is owned by this app.

**Rows added per agent per user (when fully configured)**: 2 rows (URL + API key). Three agents × N users → 6N rows. Negligible at any plausible scale.

**Migration impact**: **None.** No DDL changes required.

### 1.2 Audit-event tables (existing)

Audit rows are written by the existing [backend/audit/](backend/audit/) recorders for:
- Tool dispatch (in_progress + success/failure pair, per existing hooks).
- Credential mutation (the existing credentials endpoint already records).

No `event_class` extension is needed (see [research.md §R-010](research.md#r-010-audit-events-fr-019-fr-020)).

---

## 2. In-Process Runtime State (new)

### 2.1 `ConcurrencyCap` (orchestrator-side)

Defined in `backend/orchestrator/concurrency_cap.py` (NEW).

```python
@dataclass
class ConcurrencyCap:
    max_per_user_agent: int = 3
    _inflight: Dict[Tuple[str, str], Set[str]] = field(default_factory=lambda: defaultdict(set))
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def acquire(self, user_id: str, agent_id: str, job_id: str) -> bool: ...
    async def release(self, user_id: str, agent_id: str, job_id: str) -> None: ...
    def inflight_count(self, user_id: str, agent_id: str) -> int: ...
    def inflight_jobs(self, user_id: str, agent_id: str) -> List[str]: ...
```

**Lifecycle**:
- One instance owned by `Orchestrator`, created in `__init__`.
- `acquire` is called immediately before forwarding any tool listed in the agent's `LONG_RUNNING_TOOLS` allow-list.
- `release` is called by the agent's job poller on terminal job state, AND by the orchestrator's `finally` block on dispatch error (so a tool that fails before the poller even starts does not orphan a slot).
- State does NOT survive process restart; this is intentional (see [research.md §R-007](research.md#r-007-concurrency-cap-resolves-fr-026--fr-027)).

**Validation rules**:
- `acquire` returns `False` if `len(_inflight[(user_id, agent_id)]) >= max_per_user_agent`. The 4th attempt yields the FR-026 alert.
- `release` is idempotent (releasing an unknown `job_id` is a silent no-op).

### 2.2 `JobPoller` (per-agent, for CLASSify and Forecaster only)

Defined in each agent's `job_poller.py`.

```python
@dataclass
class PollerJob:
    user_id: str
    agent_id: str
    job_id: str            # upstream task id
    tool_name: str
    started_at: datetime
    last_status: str       # "started" | "in_progress" | "succeeded" | "failed" | "status_unknown"
    last_progress: int | None  # 0-100 or None
    failure_streak: int    # consecutive transport failures; capped at 5 → status_unknown
```

**State transitions**:

```
   started ──(poll ok, in progress)──> in_progress ──(poll ok, terminal)──> succeeded | failed
      │                                     │
      │                                     ├──(5 consecutive transport failures)──> status_unknown
      │                                     │
      └──(poll ok, terminal)────────────────┘
```

Transitions to `succeeded` / `failed` / `status_unknown` are terminal — the poller emits a final `ToolProgress` and calls `ConcurrencyCap.release`. The job is then dropped from the poller's tracking dict.

### 2.3 Per-WebSocket session (existing, referenced)

The orchestrator's existing `_session_llm_creds` (introduced in feature 006) is **not** reused — agent credentials live in `user_credentials`, not in WebSocket-session memory. No new WebSocket-scoped state is added by this feature.

---

## 3. Declarative Schemas Carried in Code (new)

### 3.1 Agent `card_metadata.required_credentials`

Each new agent declares one of these on the agent class. Schema mirrors [backend/agents/nocodb/nocodb_agent.py:31-55](backend/agents/nocodb/nocodb_agent.py#L31-L55) with one additive optional field:

```python
{
    "key": str,            # e.g. "CLASSIFY_URL"
    "label": str,          # human-readable label (modal renders this)
    "description": str,    # tooltip text
    "required": bool,      # always True for the URL + API key fields
    "type": "api_key",     # the only type currently supported by AgentPermissionsModal
    "placeholder": str | None,  # NEW (additive) — production-URL hint, frontend renders into <input placeholder=...>
}
```

Backwards compatibility: existing agents that omit `placeholder` continue to render exactly as before (modal falls back to default `placeholder=""`).

### 3.2 MCP tool `input_schema`

Each tool exposed by each agent carries a JSON Schema in `TOOL_REGISTRY[tool_name]["input_schema"]`. Format and conventions match every existing agent. Sketches per agent are listed in [contracts/classify-tools.md](contracts/classify-tools.md), [contracts/forecaster-tools.md](contracts/forecaster-tools.md), and [contracts/llm-factory-tools.md](contracts/llm-factory-tools.md).

### 3.3 Per-agent `LONG_RUNNING_TOOLS` allow-list

Each agent's `mcp_tools.py` exposes:

```python
LONG_RUNNING_TOOLS: Set[str] = {...}   # e.g. {"train_classifier", "retest_model"} for CLASSify
```

The orchestrator imports this (or reads it via a new MCP capability message — TBD in tasks) and consults it before invoking `ConcurrencyCap.acquire`. For LLM-Factory the set is empty.

---

## 4. Validation Rules Summary

| Source | Rule | Enforced At |
|--------|------|-------------|
| FR-005 | `(user_id, agent_id, credential_key)` is unique | DB unique constraint (existing) |
| FR-006 | API key plaintext never persisted server-side | ECIES encryption (existing) |
| FR-007 | API key never returned to frontend after save | `GET /api/agents/{agent_id}/credentials` already returns only metadata, not values |
| FR-019 | API key not in audit payloads | Audit redactor in [backend/audit/pii.py](backend/audit/pii.py) (existing); new tool `_credentials_check` records only verdict |
| FR-023 | URL normalized regardless of scheme/trailing slash | `backend/shared/external_http.py::normalize_url` (NEW) |
| FR-026 | ≤ 3 concurrent jobs per `(user, agent)` | `ConcurrencyCap.acquire` (NEW) — orchestrator gate |
| SSRF (R-004) | Reject loopback / RFC1918 / non-http schemes | `backend/shared/external_http.py::validate_egress_url` (NEW) |
| Response cap | Reject responses > 50 MB | Same helper |

---

## 5. Entity Relationships

```text
            ┌──────────────────┐
            │  user_credentials│ (existing)
            └────────┬─────────┘
                     │ key=("user_id","classify-1","CLASSIFY_URL")
                     │ key=("user_id","classify-1","CLASSIFY_API_KEY")
                     │ ... etc for forecaster, llm-factory
                     ▼
       ┌──────────────────────────────┐
       │ Orchestrator (in-process)     │
       │ ┌──────────────────────────┐ │
       │ │ ConcurrencyCap           │ │ (NEW, in-memory)
       │ │   _inflight[(uid, aid)]  │ │
       │ │     = {job_id, ...}      │ │
       │ └──────────────────────────┘ │
       └──────────────┬───────────────┘
                      │  injects "_credentials" + "_credentials_encrypted" on every tool call
                      ▼
       ┌──────────────────────────────┐
       │ Agent process (e.g. classify) │
       │ ┌──────────────────────────┐ │
       │ │ JobPoller (NEW)          │ │  spawns asyncio task per long-running call
       │ │   tracks PollerJob list  │ │  emits ToolProgress every 5s
       │ └────────────┬─────────────┘ │
       │              │               │
       │              ▼               │
       │ ┌──────────────────────────┐ │
       │ │ http_client / SSRF guard │ │  (NEW, per agent; thin wrapper over shared helper)
       │ └────────────┬─────────────┘ │
       └──────────────┼───────────────┘
                      │
                      ▼
                External service (HTTPS, Bearer auth)
```
