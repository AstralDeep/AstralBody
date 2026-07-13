# Quickstart: verifying 056-delegated-agent-chaining

Everything runs in the `astraldeep` container (`docker compose up -d`); sync
edits with `docker cp <file> astraldeep:/app/<path>` + `docker restart
astraldeep`. Web at http://localhost:8001. This is a **backend token/dispatch
mechanism** — no client renderer changes — but per Constitution X the
user-visible behaviors (attributed hop progress, honest refusals, scheduled runs
acting in production) are verified LIVE, and per Constitution XII every client is
confirmed unchanged (hop progress rides existing progress frames).

Flags: interactive chaining `FF_RECURSIVE_DELEGATION` (default off). Machine root
`FF_SCHEDULER_EXECUTION` (default off, dark until the T057 review is recorded).

## US3 — dispatch-path parity (prerequisite hardening, flag-independent)

1. Drive the same violating call down all three paths and assert identical
   refusals + equivalent audit evidence:
   `pytest tests/test_dispatch_parity.py` — for each gate (security flag,
   permission, policy, taint, supervisor, HITL, delegation-required, concurrency
   cap) the single path, the parallel batch, and a chained hop must refuse
   identically.
2. Confirm the parallel path now mints a delegation token per call (previously
   dispatched UNSCOPED): set production posture (`ASTRAL_ENV` unset), drive a
   parallel batch, verify `_delegation_required` refuses when the token exchange
   is unavailable — matching the single path (`orchestrator.py:5983-6007`).
3. Meta-tool parity: a parallel batch containing a `__scheduler__`/`__memory__`
   meta-tool dispatches correctly (today only `__orchestrator__` works in the
   parallel path).
4. The two pre-existing supervisor-gate failures
   (`test_security_gates_wiring.py::test_supervisor_off_is_noop` /
   `::test_supervisor_allows_when_intent_present`) now pass.

## US1 — agents chain on my behalf, safely (`FF_RECURSIVE_DELEGATION=1`)

1. Grant a user both `web_research` and `summarizer`. Drive a turn whose primary
   agent requests a peer tool ("research the top 3 NSF programs and summarize each
   as a comparison table"). Verify the hop `web_research → summarizer`:
   - the child token's scopes are the intersection of parent+requested, `exp ≤
     parent.exp`, `depth = parent+1`, actor chain names `web_research` and
     terminates at the user (`pytest tests/test_chain_hop.py`).
   - the full single-path gate stack ran for the hop (audit shows the tool
     start/end pair AND the `delegation.hop.mint`/`.enforce` pair under one
     correlation id).
2. **Disabled callee** (US1-AS2): disable `summarizer` for the user; any chain hop
   to it is refused (explicit opt-out wins), audited, and the parent gets an honest
   error — the session is NOT torn down.
3. **Over-depth** (US1-AS3): force a chain to depth 3, request a 4th hop; refused
   fail-closed with a depth-bound denial, audited, reported honestly.
4. **Empty intersection** (FR-005): request a hop whose scopes intersect the
   parent to nothing; refused (not a silent empty token), audited with
   requested-vs-granted scopes recorded.
5. **Credentials never forwarded** (FR-008): the callee receives its own
   per-(user, callee) credentials, never the initiator's (assert no cross-agent
   credential in the dispatched args).
6. **Two-hop reconstruction** (SC-003, closes 048 T018): from the audit log alone,
   reconstruct the full chain for a two-hop turn; tamper one record → `verify_chain`
   detects it. `pytest tests/test_chain_audit_reconstruction.py`.
7. **Flag off byte-equivalence** (SC-009): with `FF_RECURSIVE_DELEGATION=0`, the
   048 suite (`test_recursive_delegation.py`, 14), `test_delegation.py` (11), and
   `test_tool_permissions.py` (26) pass unchanged and wire/token behavior is
   byte-identical to pre-feature.

## US2 — background work acts with my real, revocable consent

*(Behavior gated on `FF_SCHEDULER_EXECUTION`; ship dark until T057 recorded.)*

1. **Consent capture** (FR-011): schedule "check arXiv for new SDUI papers every
   morning" → the consent card names the granted scopes, the durable nature, and
   how to revoke; confirming calls `OfflineGrantStore.capture` and links the
   `grant_id` onto the job (verify `scheduled_job.offline_grant_id` is set, not
   `None`).
2. **Production run under consent** (SC-004): with `FF_SCHEDULER_EXECUTION=1` and
   production posture, fire the job; verify real-agent tools dispatch under an
   authority scoped to (consented ∩ current) grants — never wider than either —
   and audit rows carry `machine:scheduled_job` + the owning human, never
   "legacy"/"unknown". `pytest tests/test_machine_turn_authority.py`.
3. **Revocation** (SC-004): log the user out (or revoke); the next run performs 0
   tool dispatches, records a `skipped_auth` outcome, and the user receives exactly
   ONE actionable notification per paused job (collapsed, not per firing).
4. **All three classes at one seam** (FR-012): parser replay
   (`auto_continue_after_go_live`) and a draft self-test both derive authority via
   the same `MachineTurnAuthority.derive`; their audit rows carry a
   `machine:<class>` principal attributable to the owning human.
5. **Cost vs authority** (US2-AS5): the run bills the SYSTEM LLM credential while
   the audit names the human authorizer — distinct in the records.

## US4 — plans decompose without losing control (`FF_RECURSIVE_DELEGATION=1`)

1. Drive a decomposable request ("audit my grant budget across these five programs
   and build me a dashboard") that spawns ≥3 sub-tasks. Verify each sub-task ran
   isolated with a child authority narrower than the parent and a per-subtree
   budget; results returned to the parent as bounded provenance-tagged digests.
   `pytest tests/test_subtask_decomposition.py`.
2. **Global budget** (FR-021, SC-007): cumulative depth + hop count + wall clock
   bound the whole tree; exhaustion yields honest partial results + an audited
   `budget_stop`. 20-run soak shows the budget never exceeded and zero orphaned
   sub-tasks attaching results after parent end.
3. **Hierarchical progress** (FR-022): the originating chat shows attributed
   hierarchical progress (which agent, which sub-task, under whose authority) over
   the EXISTING progress frames — confirm on web AND one native client that no new
   frame type appears and progress renders correctly (Constitution XII).
4. **MAS scan** (FR-007, US4-AS4): inject an injection-marker payload as a hop
   result/digest; it is quarantined (not delivered upstream) with an audited reason
   and an honest error to the requester. `pytest tests/test_hop_payload_scan.py`.
5. **Peer path retired** (SC-010): an agent attempting a direct
   `call_peer_tool`-style call fails 100% of the time with an audited refusal;
   `grep -rn "call_peer_tool" backend --include=*.py` returns no live path.
   `pytest tests/test_peer_path_retired.py`.

## US5 — chaining is measured, not assumed safe (eval-only)

1. Run the extended benchmark with chaining off then on:
   `docker exec astraldeep python -m security_benchmark --benchmarks chained
   --asr-threshold <baseline>` → comparison report with per-scenario outcomes and
   overall ASR; acceptance bar `ASR(on) ≤ ASR(off)` (no regression).
2. Confirm every confused-deputy / cross-hop-escalation / depth-violation /
   actor-chain-forgery / chained-consent-replay case is blocked by a NAMED layer,
   and each blocked attack's audit trail alone reconstructs what was attempted, by
   which principal chain, and which gate refused it (US5-AS2).
3. Isolation guard stays green (no product module imports the harness):
   `pytest security_benchmark/tests/test_isolation_check.py`.

## Cross-cutting

- **Flag-off equivalence (SC-009)**: run the full backend suite + the 048/
  delegation/permission suites with `FF_RECURSIVE_DELEGATION=0` and
  `FF_SCHEDULER_EXECUTION=0` — zero diffs from pre-feature behavior (dedicated CI
  variant).
- **Every client unchanged (Constitution XII)**: run the drift-guard suites —
  backend manifest test, Windows `tests/`, Android `ProtocolManifestTest`, Apple
  `ManifestDriftTests` — all green with no `ui_protocol.json` change (this feature
  adds none).
- **Observability (Constitution X)**: confirm structured logs exist for every
  mint/refusal/quarantine/budget-stop/machine-derive/consent-capture with
  agent/chat/correlation context and no secret token material.
- Full gate run: `docker exec astraldeep bash -c "cd /app/backend && python -m
  pytest -q"`; `ruff check .` from repo root on host; changed-code coverage ≥90%
  (diff-cover vs origin/main); production-posture boot smoke exits 78.
