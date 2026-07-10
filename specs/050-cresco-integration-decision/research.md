# Research: Cresco Integration (Bridge Agent)

**Feature**: 050-cresco-integration-decision | **Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)
**Retrieved / verified**: 2026-07-06. Cresco is under active development (whole org pushed 2026-07-05/06); every repository fact below is pinned by commit SHA so drift is auditable.

This document records the evaluation that produced the GO/NO-GO/DEFER decision and the technical facts the bridge implementation is pinned against. It is the long-form backing for the condensed "Evaluation findings" section of [spec.md](spec.md).

## Decision recap

| Track | Decision | Rationale |
|---|---|---|
| Platform-level adoption (JVM in image, ActiveMQ bus, protocol replacement, `pycrescolib` runtime dep) | **NO-GO** | Constitution I (Python-only backend) + V (no unapproved deps); the two systems are complementary layers, not substitutes. |
| First-party Python bridge agent over `wsapi` | **GO** | Zero new deps proven live; fabric treated as external infrastructure (Keycloak posture); inherits all existing gates. |
| Cresco-side Java bridge plugin (presents an AgentCard to AstralDeep) | **DEFER** | Only needed if the fabric must *initiate* toward AstralDeep; no current requirement. |

## R1 — Cresco architecture (what we are integrating with)

**Sources**: `CrescoEdge/agent` @ `4093d7d`, `CrescoEdge/controller` @ `1b3cc3c`, `CrescoEdge/library` docs @ `826df9c`.

- **Topology**: global controller → regional controllers → agents. Each controller embeds an ActiveMQ broker; agents connect to their regional broker. Addressing is `region_agent[_plugin]` (a three-tuple identifying a plugin instance on an agent in a region).
- **Planes**: a `MsgEvent` control plane over ActiveMQ plus a pub/sub dataplane for streams.
- **Runtime**: JDK 21, Apache Felix OSGi, a single executable JAR (`agent-1.3-SNAPSHOT.jar`); the controller additionally embeds ActiveMQ + Apache Derby.
- **Identity**: mutual-TLS X.509 with a structured DN (`CN=<agent>, OU=<region>, O=<tenant>`); broker roles `SUPERUSER` / `TENANT`; tenant isolation is enforced at the broker.
- **Consequence for us**: principals are **machines/tenants**, not humans. Cresco has no LLM layer, no per-user consent, no per-tool permission model, no human-anchored delegation, and no per-user tamper-evident audit chain. Everything user-facing and safety-relevant is contributed by AstralDeep (see R5).

## R2 — External seam: `wsapi`

**Source**: `wsapi` @ `d5b4bcd`; wire shape cross-read from `pycrescolib` 1.3.0 source.

- **Endpoint**: a secure WebSocket gateway on `wss://<host>:8282` with three paths:
  - `/api/apisocket` — control / RPC (the bridge's primary seam)
  - `/api/dataplane` — stream subscriptions
  - `/api/logstreamer` — log streaming
- **Authentication**: clients present a `cresco_service_key` HTTP header on the WebSocket upgrade. This is a **single, all-or-nothing fabric credential** — there is no per-caller scoping at the fabric.
- **Wire format** (implementation-defined; no published protocol spec — pinned from the evaluated shape):
  - JSON envelope: `{"message_info": {…}, "message_payload": {"action": <verb>, …}}`.
  - `message_info` carries routing/type fields (message type, event type, RPC flag/id) used to correlate an RPC request with its reply.
  - Bulk parameters are **gzip-compressed then base64-encoded** inside the payload.
  - Read verbs observed live: `listregions`, `listagents`; other control verbs (`getagentinfo`, `getsysinfo`, filerepo put/get, executor submit) follow the same envelope.
- **Stability posture**: because the format is implementation-defined and the org is under active development, the bridge **pins to the evaluated shape** and **fails safe** on unexpected frames with a diagnostic rather than mis-parsing (spec Edge Cases; FR referencing drift handling).

## R3 — The `executor` risk center

**Source**: `executor` @ `8e9020e`.

- The `executor` plugin **"runs arbitrary shell commands by design — a remote execution surface."**
- Authorization is delegated to the broker/tenant layer only; combined with the all-or-nothing `cresco_service_key`, this means **any LLM-facing wrapper concentrates the entire per-user safety case in AstralDeep's gates**.
- `executor` is **enabled by default on a global node**.
- **Consequence for us**: the executor-wrapping tool must be the most tightly gated surface in the feature — system-scoped, default-deny, hard security-flagged, never flipped on by the safe-agent baseline, and only reachable via an explicit per-user override (spec FR-006; Constitution VII Cresco clause).

## R4 — Zero-new-dependency feasibility (proven live)

A single-node fabric was brought up from the released `agent-1.3-SNAPSHOT.jar` (JDK 21+, `-Dis_global=true -Denable_wsapi=true`) and driven end-to-end from Python **twice**:

1. With `pycrescolib` 1.3.0 (the vendor client) — baseline that the fabric answers.
2. With a **raw client using only the `websockets` library already in `backend/requirements.txt`** (`websockets>=12.0`) plus stdlib (`json` / `gzip` / `base64` / `ssl`), round-tripping `listregions` / `listagents`.

**Conclusion**: the bridge needs **no new third-party libraries**.

**Why `pycrescolib` is deliberately NOT adopted at runtime**:
- It would add `backoff` (absent from `backend/requirements.txt`) — a new transitive dependency barred by Constitution V.
- It **disables TLS verification globally by default** — incompatible with FR-007 (verified TLS, no global bypass). Adopting it would regress the platform's egress-security posture.

Reconnect/backoff that the bridge needs is implemented with **stdlib** (bounded sleeps / retry counter), not the `backoff` package.

## R5 — What the bridge inherits (nothing new to build on the safety side)

Cresco supplies none of the following; AstralDeep already supplies all of them, and the bridge inherits them by being a normal first-party in-process agent:

| Safety property | AstralDeep mechanism (already exists) |
|---|---|
| Fail-closed agent registration | `orchestrator/auth.py::validate_agent_api_key` (`AGENT_API_KEY`) |
| Per-tool scopes | `tool_permissions.register_tool_scopes` + `is_tool_allowed` |
| Hard security flags (deny surfaces) | `tool_security` (proactive security analyzer flags on the card) |
| Owner/admin trust marking | `agent_trust` (`seed_safe` / `mark_safe`); bridge seeded **not** safe |
| Human-anchored delegation | `orchestrator/delegation.py` (RFC 8693 `act` chains; recursive behind `FF_RECURSIVE_DELEGATION`) |
| Per-user tamper-evident audit | `audit/repository.py::verify_chain` (hash-chained `agent_tool_call`) |
| Egress control + verified TLS | `shared/external_http.py::validate_egress_url` |

Cross-fabric provenance: a spec-048 recursive delegation chain terminating in a Cresco tool call is fully attributable end-to-end via FR-008 (audit rows carry `region_agent[_plugin]`).

## R6 — Alternatives considered

| Option | Verdict | Why |
|---|---|---|
| Adopt Cresco as the platform agent mesh (replace A2A/WS) | Rejected | Constitution I; ActiveMQ + JVM in image; loses per-user consent/audit model. |
| Add `pycrescolib` as a runtime dep | Rejected | New `backoff` dep (Constitution V) + global TLS-verify-off (FR-007). |
| Cresco-side Java bridge plugin (fabric → AstralDeep) | Deferred | No requirement for the fabric to initiate; revisit if that changes. |
| Hand-rolled `websockets`+stdlib bridge (this feature) | **Chosen** | Zero new deps (proven live), fabric external, inherits all gates. |

## R7 — Open items carried into implementation (not blockers)

- **Live E2E environment** — the ≥90% coverage gate is met with mocked-socket unit/integration tests; the live single-node round-trip (tasks T018) requires a JDK 21 fabric and is run as the documented verification step (see [quickstart.md](quickstart.md)).
- **Private-host egress override** — on-prem fabrics may resolve to private addresses; `validate_egress_url` needs a documented, operator-scoped allowance for the configured `CRESCO_WSAPI_URL` host (FR-007), not a blanket private-host bypass.
- **Pinned wire fixtures** — the evaluated `listregions` / `listagents` frame shapes are the golden fixtures for the client unit tests; the client rejects frames that do not match the pinned envelope.
