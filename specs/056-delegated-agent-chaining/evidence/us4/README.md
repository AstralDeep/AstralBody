# US4 evidence — plans decompose without losing control (T037)

Recorded 2026-07-14 in the `astraldeep` container. Real `Orchestrator`, real
`BackgroundTask`/`VirtualWebSocket` substrate, real `ChainBudget`, real MAS
scanner, real hash-chained `audit_events`. `FF_RECURSIVE_DELEGATION=1`.

The sub-turn's LLM step is stood in for (this box has no provider), so each
sub-task deterministically produces a result; everything the feature actually
builds — isolated chat creation, concurrent spawn, budget slicing and charging,
digest distillation, the MAS scan, quarantine, progress frames, orphan
handling, and audit — is the real code path.

## What the run proves (`live-verify-output.txt`)

1. **Bounded, isolated, concurrent decomposition** (FR-020). A broad request
   ("audit my grant budget across these programs") spawns 3 sub-tasks, each in
   its **own fresh chat** (never the parent's), running concurrently, each
   restricted to the tools the parent turn offered, returning a **bounded,
   provenance-tagged digest** (which sub-task, which agent) — never a raw
   transcript.
2. **The MAS scan is ENFORCED on inter-agent payloads** (FR-007). A sub-task
   whose result carried prompt-injection markers was **quarantined**: its
   digest is empty, the payload never reached the planner's context (asserted
   against the full serialized result), the requester got an honest error, and
   the reason is audited with the markers found. On the tool path this scanner
   is still advisory (log-only); on a hop or digest it now blocks.
3. **Hierarchical progress rides EXISTING frames** (FR-022, Constitution XII).
   Progress reached the originating chat as `chat_status` frames attributed
   per sub-task ("Program A — running/done"). Comparing every emitted frame
   type against `shared/ui_protocol.json`: **zero unmanifested frame types**.
   No client change, no manifest edit, no drift-guard impact.
4. **The global chain budget bounds the tree** (FR-021). With `max_hops=2`, a
   3-way decomposition ran 2 and stopped 1 with an honest
   `chain budget exhausted (hop_budget_exhausted)` — partial results, never
   runaway recursion. Sub-task slices debit the parent, so breadth × depth ×
   wall clock can't exceed the turn ceiling however the tree is shaped.
5. **The unattenuated peer path is gone** (SC-010). `call_peer_tool`,
   `_call_peer_via_ws`, `_call_peer_via_a2a`, `connect_to_peer`,
   `_peer_listen_loop` — all removed from `BaseA2AAgent`. An agent cannot
   bypass orchestrator mediation.
6. **The whole sub-task lifecycle is on the hash chain**: `spawned` →
   `completed` / `quarantined` / `budget_stop`, and `verify_chain` is intact.

## Test suites backing this

`tests/test_subtask_decomposition.py` (isolation, concurrency, parent-tool
ceiling, session-claims inheritance + release, fan-out bounds, honest failure
reporting), `tests/test_chain_budget.py` (partial results on exhaustion, wall
clock, per-turn scoping, turn-start reset, composition with the 048 depth
bound), `tests/test_hop_payload_scan.py` (hop-result and digest quarantine, no
teardown, scanner fail-open), `tests/test_subtask_orphan.py` (parent
cancellation cancels children; partials discarded; timeout; no socket leak),
`tests/test_hop_progress_attribution.py` (existing frames only; manifest
unchanged), `tests/test_peer_path_retired.py`.

Full container suite: **3741 passed, 3 skipped**.
