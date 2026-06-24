# Quickstart: validating 068-inprocess-agents-skills-commands

How to exercise each pillar against the running container. Dev posture requires `ASTRAL_ENV=development`. The backend needs Python 3.11 (run inside the `astralbody` container).

## Build / run

```bash
docker compose up -d                                   # postgres + astralbody
docker cp <edited-file> astralbody:/app/<repo-rel>     # sync an edit (source is baked)
docker exec astralbody bash -c "cd /app/backend && python -m pytest -q"        # full suite
docker exec astralbody bash -c "cd /app/backend && python -m ruff check ."     # lint
```

## US1 — In-process built-in agents

1. **No per-agent ports**: with `FF_INPROCESS_AGENTS` on, start the system and confirm only the orchestrator (`:8001`) is listening — no `:8003+` agent ports. `docker exec astralbody bash -c "ss -ltnp | grep -E ':80(0[3-9]|1[0-9])' || echo 'no agent ports'"` → `no agent ports`.
2. **Parity**: in a chat, run a unary tool (weather `get_current_weather`), a streaming tool (`live_temperature`), a long-running job (ml_services training), and a credentialed tool. Confirm results, UI components, streamed chunks, progress, and the prompt "started" response match the pre-change behavior.
3. **Cancellation**: start `live_temperature`, cancel it; confirm the stream stops.
4. **Non-blocking**: trigger a slow tool for user A and a normal turn for user B concurrently; confirm B is not stalled.
5. **External A2A unaffected**: if an external A2A agent is configured, confirm its tool still routes over the network.
6. **Kill-switch**: set `FF_INPROCESS_AGENTS` off; confirm built-ins fall back to the WS path with identical behavior.

## US2 — Safe built-ins out of the box

1. As a brand-new user (no grants), invoke a safe agent's tool; confirm it runs with no manual enable step.
2. Explicitly disable a scope/tool for that agent; re-invoke; confirm the explicit opt-out wins (now gated).
3. Confirm a hard-blocked tool stays blocked for the safe agent.
4. As a non-admin, attempt to mark an agent safe; confirm server-side refusal.
5. Revise a safe agent via the revision path; confirm `is_safe` resets and re-approval is required.
6. `docker exec astralbody bash -c "cd /app/backend && python -c \"from audit... verify\""` — confirm `marked_safe` events exist and the per-user audit chain verifies (no divergence).

## US3 — etf_tracker_1 removed

1. Confirm `etf_tracker_1` and its tools appear nowhere (agents surface, new chat tool list, history glyphs).
2. Seed a representative DB with `etf-tracker-1-1` ownership/scope/override/chat rows; boot twice; confirm the orphan rows are gone after the first boot and the second boot is a clean no-op.
3. Open an old transcript that used a retired tool; confirm a graceful retirement notice, not an error.
4. `python -m pytest -q` is green (incl. updated `test_agent_retirement`, `test_no_behavior_change`, `test_wiring_030`).

## US4 — On-demand skill packs

1. Issue a request clearly tied to one capability; confirm only that capability's authored pack is injected (inspect the assembled system prompt / debug log).
2. Issue an unrelated request; confirm no pack is injected and the baseline per-turn context size is unchanged.
3. Run the knowledge synthesizer; confirm the authored pack under `backend/knowledge_packs/` is not overwritten.
4. Force a skill-load error; confirm the turn proceeds normally (fail-open).

## US5 — Slash commands

1. Type a known `/command` (e.g. `/summarize <url>`); confirm it expands/triggers as specified.
2. Use a command whose flow calls a gated tool while lacking the scope; confirm the normal consent gate applies (no bypass).
3. Type `/`; confirm typeahead/help is shown; type an unknown command; confirm a friendly message, not an error.
4. Confirm the command menu renders via server-rendered chrome and adapts across device targets (browser checked in a real browser per Principle X).
5. Confirm command invocations appear in the audit log and that arguments are treated as untrusted (PHI/taint handling applies).

## Cross-cutting

- **Audit coverage**: run a turn that dispatches tools in parallel; confirm each parallel tool emits start/end audit events (FR-032).
- **Credential confidentiality**: confirm no plaintext per-user secret is observable in the orchestrator process for an in-process credentialed tool (test/inspection).
- **CI**: confirm lint, full suite vs real DB, ≥90% changed-code coverage, image build, boot smoke (incl. production fail-closed exit), and secret scan all pass.
