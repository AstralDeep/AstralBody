# Quickstart: Feature 029 — Agent Catalog Overhaul, Adaptive UI Designer & Production CI

## Prereqs

- Docker Desktop running; stack up: `docker compose up -d` (postgres + astraldeep).
- `.env` has `ASTRAL_ENV=development` plus the standard dev block (see `.env.example`).
- Sync edits into the baked image: `make sync-backend` (whole tree + restart) or `docker cp <file> astraldeep:/app/<repo-rel-path>`.

## See the adaptive designer work (P1)

1. Open http://localhost:8001/ and sign in (dev mock auth).
2. Ask something that fans out to ≥ 2 rich tools in one round, e.g. *"Compare the weather in Lexington and Louisville this week and show system status."*
3. Expect: a designed arrangement (grid/cards/tabs + a headline garnish) instead of a vertical stack. The chat panel carries the narrative under a contextual title (no constant "Analysis" card).
4. Prove identity survives: paginate any table inside the arrangement; ask a follow-up that updates one component ("refresh the Louisville forecast") — it morphs in place.
5. Prove fail-open: `docker exec astraldeep bash -c "FF_UI_DESIGNER=false ..."` — or set `FF_UI_DESIGNER=false` in `.env` and restart — same question renders as the legacy append with zero errors. Also verify timeline (history slider) and re-opening the chat restore the designed state.
6. Designer knobs: `FF_UI_DESIGNER` (default on), `UI_DESIGNER_TIMEOUT_SECONDS` (default 8). Logs: `docker logs astraldeep | grep ui_designer`.

## Verify the catalog (P2)

```bash
docker exec astraldeep bash -c "cd /app/backend && python - <<'EOF'
import os, json, urllib.request
for port in range(8003, 8014):
    try:
        card = json.load(urllib.request.urlopen(f'http://localhost:{port}/.well-known/agent-card.json', timeout=2))
        print(port, card.get('name'))
    except Exception: pass
EOF"
```

Expect exactly: classify/forecaster/llm_factory replaced by **ML Services**; **Web Research** and **Summarizer** present; none of email_tracker / grant_budgets / grants / linkedin / nefarious / nocodb. Dangling-reference check: `git grep -l "nefarious\|grant_budgets\|email_tracker\|nocodb" backend/` returns only intentional English-word usages documented in the spec.

## Run the suites

```bash
docker exec astraldeep bash -c "cd /app/backend && python -m pytest -q -m 'not integration'"
docker exec astraldeep bash -c "cd /app/backend && python -m pytest audit/tests llm_config/tests orchestrator/tests onboarding/tests personalization/tests scheduler/tests dreaming/tests -q"
docker exec astraldeep bash -c "cd /app/backend && python -m ruff check ."   # config-aware lint runs on host/CI from repo root
```

## CI / production

- Pipeline: `.github/workflows/ci.yml` — lint, build, test (in-image vs postgres service), changed-code coverage ≥ 90 (diff-cover), smoke (healthz/readyz + exit-78 fail-closed proof), gitleaks, GHCR publish on main.
- Deploy artifact: `ghcr.io/<owner>/<repo>:sha-<commit>`; sandbox.ai.uky.edu pull path documented in `docs/production-deployment.md` (Keycloak: `https://iam.ai.uky.edu/realms/<realm>` per `docs/keycloak-realm-settings.md`).

## New-agent smoke prompts

- *"Research the current state of small modular reactors and give me a brief."* → web_research: cited brief + sources table.
- *"Summarize https://en.wikipedia.org/wiki/Server-driven_user_interface"* → summarizer: TL;DR / Key points / Quotes tabs.
- *"Check my ML service credentials."* → ml_services `_credentials_check`: three per-bundle verdicts.
