# T001 Baseline — captured 2026-06-11 (branch point: main @ 20d5215)

## Test suites (in container, live Postgres)

- Default suite: `python -m pytest -q -m "not integration"` → **1262 passed, 1 skipped, 2 deselected** (44 s)
- Module suites: `python -m pytest audit/tests llm_config/tests orchestrator/tests onboarding/tests personalization/tests scheduler/tests dreaming/tests -q` → **316 passed** (4 s)
- Lint: repo ruff-clean at branch point (commit ca364cf established 0 violations)

## Live agent registry (ports 8003-8018)

CLASSify(8003), Claude Connectors(8004), Dice Roller(8005), Email Tracker(8006), ETF Tracker(8007), Forecaster(8008), General(8009), Grant Searching(8010), Grant Budgets(8011), Journal Review(8012), LinkedIn Engagement Driver(8013), LLM-Factory(8014), Medical(8015), Nefarious(8016), NocoDB(8017), Weather(8018).

## Declared agent ids (class attrs) vs. ownership-table rows

`agent_ownership` contains BOTH the declared hyphenated ids and legacy underscore directory-name rows (seeded by start.py from dir names in an earlier scheme). Migrations must cover both forms.

| Concern | Ids to handle |
|---|---|
| Remap → `ml-services-1` | `classify`, `classify-1`, `forecaster`, `forecaster-1`, `llm_factory`, `llm-factory-1` |
| Delete (retired) | `email_tracker`, `email-tracker-1`, `grant_budgets`, `grant-budgets-1`, `grants`, `grants-1`, `linkedin`, `linkedin-1`, `nefarious`, `nefarious-1`, `nocodb`, `nocodb-1` |
| Leave untouched (unknown/draft provenance) | `email-helper-1`, `etf-1`, `etf-agent-1`, `etf-tracker-1`, `test-agent-1` |

New agent ids follow the existing hyphenation convention: `ml-services-1`, `web-research-1`, `summarizer-1`.

## Retired-id set for the runtime retirement guard (FR-004)

`{"email-tracker-1", "grant-budgets-1", "grants-1", "linkedin-1", "nefarious-1", "nocodb-1", "classify-1", "forecaster-1", "llm-factory-1"}` — the three merged ids also route to retirement messaging if a stale transcript references them directly (their tools now answer under `ml-services-1`).
