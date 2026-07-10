# Quickstart: Cresco Integration (Bridge Agent)

**Feature**: 050-cresco-integration-decision | **Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)

This is the operator/developer runbook for exercising the bridge — including the **live end-to-end verification** (spec Phase 4 / tasks T018) that needs a real fabric, which is why it is documented here rather than run in CI. CI verifies everything reachable without a JVM fabric (flag-off no-op, mocked-socket client/tool tests, gating, audit — SC-001/002/004/007).

## 0. Prerequisites

- The AstralDeep stack running per CLAUDE.md (`docker compose up -d`; `.env` has `ASTRAL_ENV=development` for local dev).
- For **live** verification only: JDK 21+ on a host that can run the Cresco `agent-1.3-SNAPSHOT.jar`. **No JVM is added to the product image** — the fabric runs as separate external infrastructure.

## 1. Flag-off no-op (no fabric needed) — SC-001

Default posture. `FF_CRESCO` unset/off ⇒ the `cresco-1` agent is **not registered**; the system is byte-identical to before the feature.

```bash
docker exec astraldeep bash -c "cd /app/backend && python -m pytest -q"      # full suite green
# Confirm the agent is absent from the catalog while the flag is off.
```

Expected: suite passes unchanged; no `cresco-1` in `orch.local_agents`; no Cresco code path reachable.

## 2. Flag-on, no fabric configured (no fabric needed) — SC-002

```bash
# In .env (dev):
FF_CRESCO=on
# CRESCO_WSAPI_URL / CRESCO_SERVICE_KEY intentionally left unset
docker compose up -d
```

Expected: orchestrator boots and serves normally; `cresco-1` is registered and visible; invoking any Cresco tool returns a clean **"Cresco fabric not configured"** result (no crash, no boot failure).

## 3. Bring up a local single-node fabric (live only)

On the fabric host (not the product image):

```bash
# Obtain the released agent JAR (agent-1.3-SNAPSHOT.jar) per CrescoEdge/agent.
java -Dis_global=true -Denable_wsapi=true -jar agent-1.3-SNAPSHOT.jar
# Global node embeds ActiveMQ + Derby; wsapi comes up on wss://<host>:8282.
# Note the node's cresco_service_key and its TLS certificate (self-signed by default).
```

Capture, for the client fixtures / config:
- the `cresco_service_key` value,
- the leaf/CA certificate (for `CRESCO_CA_BUNDLE`) or its SHA-256 fingerprint (for `CRESCO_TLS_FINGERPRINT`).

## 4. Point the bridge at the fabric (live) — SC-003/006

```bash
# In .env (dev), runtime-only secrets — never commit these:
FF_CRESCO=on
CRESCO_WSAPI_URL=wss://<fabric-host>:8282
CRESCO_SERVICE_KEY=<service-key>
# TLS: supply exactly one of these for a self-signed single node —
CRESCO_CA_BUNDLE=/run/secrets/cresco_ca.pem      # trusted CA, OR
CRESCO_TLS_FINGERPRINT=<sha256-of-cert>          # pinned fingerprint
# On-prem private address? scope the egress allowance to this host:
CRESCO_ALLOW_PRIVATE_HOST=true
docker compose up -d
```

**TLS check (SC-006)**: with neither `CRESCO_CA_BUNDLE` nor `CRESCO_TLS_FINGERPRINT` set against a self-signed node, the dial MUST be **refused** (no global verification bypass). Configure a CA/fingerprint and it connects.

## 5. Read round-trip (live) — SC-003/007

In a chat (as a user with the agent enabled), ask for the fabric topology, e.g. *"list the Cresco regions and agents."* Expected:

- `cresco_list_regions` / `cresco_list_agents` return **live** values over `wss://…:8282`, using only `websockets` + stdlib, rendered as SDUI (Table/Card).
- Each call writes a paired start/finish `agent_tool_call` audit row carrying the fabric identifiers (`region_agent[_plugin]`).

Verify the audit rows:

```bash
docker exec astraldeep bash -c "cd /app/backend && python - <<'PY'
# inspect recent agent_tool_call rows for agent_id='cresco-1'; confirm fabric ids present
PY"
# and confirm the hash chain is intact:
# audit/repository.py::verify_chain over the affected principal
```

## 6. Executor default-deny (live) — SC-004

- As a **normal** user, invoke `cresco_run_process` ⇒ **denied** by the permission gate (default-deny + hard `tool_security` flag); the denial is audited.
- Confirm the **safe-agent baseline never flips it to allow** (hard flag wins) even if the agent were marked safe.
- Only after an **explicit per-user override** for `cresco_run_process` does the tool run — and every attempt (allowed or denied) is audited.

## 7. Coverage & CI gates — SC-005/008

```bash
docker exec astraldeep bash -c "cd /app/backend && python -m ruff check ."     # clean
docker exec astraldeep bash -c "cd /app/backend && python -m pytest -q"        # green
git diff -- backend/requirements.txt        # MUST be empty — zero new deps (SC-005)
# diff-cover ≥90% on changed lines; gitleaks green (no cresco_service_key material committed)
```

## Verification evidence to record (Phase 4)

- [ ] Flag-off: full suite green, `cresco-1` absent (SC-001).
- [ ] Flag-on/no-config: boots + serves; tools report unavailable (SC-002).
- [ ] Live read round-trip over `wss://…:8282` with `websockets`+stdlib only (SC-003).
- [ ] Self-signed rejected without CA/fingerprint; accepted with one (SC-006).
- [ ] Executor denied by default; allowed only via explicit override; all attempts audited (SC-004).
- [ ] Audit rows carry `region_agent[_plugin]`; chain verifies (SC-007).
- [ ] `requirements.txt` diff empty; coverage ≥90%; ruff + gitleaks green (SC-005/008).
