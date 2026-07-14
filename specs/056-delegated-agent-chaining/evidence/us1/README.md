# US1 evidence — agents chain on my behalf, safely (T021)

Recorded 2026-07-14 in the `astraldeep` container against the REAL in-process
built-in agents, the real dispatch path, the real 048 mint/verify functions,
and the real hash-chained `audit_events` table. `FF_RECURSIVE_DELEGATION=1`.

## What was driven

`summarizer.summarize_url` — a real product tool — now asks the orchestrator
for `web_research.fetch_page` instead of maintaining a second copy of the
product's page-retrieval capability (egress policy, redirect re-validation,
readability extraction). That request goes out as an `agent_hop_request`
control frame through the agent's own loopback, is mediated by the
orchestrator, and re-enters the full single-path gate stack under a freshly
minted child delegation. This is the feature's first production hop call site;
it falls back to the summarizer's local fetch whenever chaining is unavailable
or the hop is refused, so flag-off behavior is unchanged.

## What the run proves (`live-verify-output.txt`)

**The hop executed under strictly-narrower authority** — read back from the
audit log alone, no other data source:

| field | value |
|---|---|
| human authorizer | the driving user (`actor_user_id`) |
| acting agent | `agent:web-research-1` |
| parent actor | `agent:summarizer-1` |
| actor chain | `["agent:web-research-1", "agent:summarizer-1"]` → terminates at the human |
| delegation depth | 1 (parent + 1) |
| granted scopes | ⊆ the parent's scopes (asserted) |
| enforce outcome | `success` |

- **Paired provenance + correlation (SC-003)**: each hop emits
  `delegation.hop.mint` → `delegation.hop.enforce`, and the hop's own
  `tool.fetch_page.start` / `.end` pair shares the SAME correlation id — the
  whole hop reconstructs from one id.
- **Tamper evidence**: `verify_chain` returns intact across every hop record
  (and `tests/test_chain_audit_reconstruction.py` proves it *detects* a
  tampered row via a raw superuser write with triggers disabled — the table
  itself is trigger-protected append-only).
- **Explicit opt-out wins, per-call, audited (SC-002)**: revoking the user's
  `web-research-1` permission and re-driving denies the hop; the denial is
  recorded as a `delegation.hop.mint` failure carrying the gate's reason; the
  summarizer got an honest error, fell back to its own fetch, and the session
  stayed alive.
- **Credentials never cross agents**: the callee receives its own
  per-(user, callee) credentials (pinned in `tests/test_chain_hop.py`).

The summarize step itself fails on this machine ("No LLM credentials are
configured") — this box has no LLM provider, which is expected and unrelated;
the hop it depends on completed successfully before that step ran.

## Test suites backing this

`tests/test_agent_runtime_call_agent_tool.py` (frame shape, correlation,
error-return-not-raise), `tests/test_chain_hop.py` (child invariants, meta-tool
ids structurally unreachable, initiator-spoof refusal, disabled callee,
security-flag block, over-depth, empty intersection, out-of-scope, tampered
chain, budget stop, single-path refusal parity),
`tests/test_chain_audit.py` (paired records, no token bytes, audited gate
denials), `tests/test_chain_audit_reconstruction.py` (two-hop
human→a→b→c reconstruction + tamper detection — closes 048 T018),
`tests/test_chain_flag_off_equivalence.py` (SC-009),
`tests/test_peer_path_retired.py` (SC-010).

Full container suite: **3686 passed, 3 skipped**.
