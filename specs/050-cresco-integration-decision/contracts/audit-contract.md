# Contract: Audit (fabric-attributed `agent_tool_call`)

**Feature**: 050-cresco-integration-decision | [spec.md](../spec.md) · FR-008 / SC-007

Cresco tool calls MUST be attributable end-to-end. Auditing itself is **inherited, not built**: the orchestrator's in-process dispatch already routes every tool call through the audited retry wrapper (`_execute_with_retry_audited`), emitting a paired **start** + **finish** `agent_tool_call` row on the per-user hash-chained audit (`audit/repository.py`, `verify_chain`). The feature's obligation is narrow: ensure the **fabric identifiers** land on those rows so a delegation chain terminating in a fabric action is fully traceable.

## A1 — Every call is audited

- Every Cresco tool invocation (read, write, executor) MUST produce paired start/finish `agent_tool_call` rows via the existing dispatch path — no tool bypasses it (this is automatic for `agent_id in orch.local_agents`; the feature adds no alternate execution path). Parallel tool batches are covered by the same audited path (feature-040 FR-032).

## A2 — Fabric identifiers on the row

- The row for a Cresco call MUST carry the fabric address it acted on: `region`, `agent`, and (when applicable) `plugin` — the `region_agent[_plugin]` tuple (FR-008).
- Mechanism: the tool surfaces these identifiers through the audited tool call's recorded parameters/metadata so they are persisted on the `agent_tool_call` row. (Confirm the exact field the dispatch wrapper records — tool `arguments` vs. a result-metadata channel — against `_execute_with_retry_audited`; whichever the platform records is where the ids MUST appear. No new audit column is added — FR-009, no schema change.)

## A3 — Executor attempts (allow AND deny)

- An **allowed** executor run is audited like any tool call (A1) plus the fabric ids (A2).
- A **denied** executor invocation (default-deny / missing override) MUST also be audited — the denial is a recorded event, not a silent drop (US2-AC2, SC-004).

## A4 — Secret hygiene in audit

- The `cresco_service_key` MUST NOT appear in any audit row (params, metadata, or error). Fabric ids and verbs are recorded; the credential never is (Constitution VII, wsapi C4).

## A5 — Chain integrity

- After a sequence of Cresco calls, `audit/repository.py::verify_chain` over the affected principal MUST still verify (the feature writes through the existing chain-append path; it does not touch the chain directly).

## Acceptance (SC-007)

Every Cresco tool call writes an `agent_tool_call` audit row carrying the fabric identifiers; the hash chain verifies; the service key is absent from all rows. Verified in the mocked-socket integration test (ids present on the recorded row) and again live in Phase 4.
