# Pre-Change Baselines (FR-032) — captured 2026-07-08

Environment: dev reference (docker compose on the dev machine, same-host postgres),
container running the pre-052 baked image; measurements taken BEFORE any 052 code
change reached the container. Method: timed in-container Python against
`shared.database.Database` plus wall-clock compose boot; browser-side figures are
structural estimates from the Phase 0 code investigation (interactive sign-in was not
automated pre-change) and will be contrasted with post-change measured values using the
same quickstart protocol.

## Measured (in-container, pre-change)

| Metric | Baseline | Notes |
|---|---|---|
| Container cold boot → `/readyz` | **16 s** | `docker compose up -d` to first successful readyz (2s poll granularity) |
| `_init_db` full idempotent run | **114 ms** | warm same-host postgres; runs on EVERY `Database()` construction |
| Single-query round trip (new connection per call) | **~5 ms avg** (25×) | connect+auth+query+close on the docker network |
| Recent-chats list, N+1 (20 chats = 21 queries) | **173 ms** | `chats` LIMIT 20 + per-chat last-message lookup |
| `agent_ownership` full-table scan | **8 ms** (31 rows) | per agents-list open |
| Effective-permissions two-query pattern | **14 ms** | per agent-detail open (one of ~7 round trips) |

## Structural baselines (verified in code, not timed here)

| Behavior | Pre-change state |
|---|---|
| Web component delivery on designed turns | Gated on `design_round` — up to 3×8 s before ANY component frame (`orchestrator.py:6892-6988`); native clients get immediate `ui_upsert` |
| Narrative delivery | Whole-message only; no `stream=True` anywhere |
| Static assets | `Cache-Control: no-cache` on all of `/static`; plotly.min.js 4,558,696 B + tailwind.js 451,131 B render-blocking in `<head>`; fonts from googleapis.com via CSS `@import`; only client.js+astral.css hash-versioned |
| WS connect | fixed 200 ms `setTimeout` before `connect()` |
| JWKS | no boot warm; first validation after each 600 s TTL pays the IdP round trip |
| Event loop | all repository DB calls except audit-insert and readyz run synchronously on the loop |
| Windows launch | no window until OIDC completes (loopback wait ≤300 s); modal pickers pre-paint |
| Android | zero stability annotations; unchanged components recompose |
| First-login web (estimate) | ~1.1–2.3 s+ to example cards, warm; worse cold (Phase 0 analysis) |
| PHI analyzer | 2–5 s lazy load on first personalization use |

## Targets referenced against these baselines

- SC-010 boot: 16 s → **≤ 9.6 s** (≥40% improvement).
- SC-002 budgets: recent-chats 21 queries → **1**; agent detail ~7 → **≤3**; agents list → **≤2**.
- Remaining SC targets per spec.md; post-change values recorded in `verification.md`.
