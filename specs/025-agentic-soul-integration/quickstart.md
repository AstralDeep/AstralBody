# Quickstart: Agentic Soul Integration

How to bring up the feature locally and exercise each user story. Assumes the existing AstralBody dev stack (docker-compose: Postgres + Keycloak + backend + frontend).

## Prerequisites
- Existing dev stack runs (`docker compose up` or the project Makefile target).
- **Keycloak realm**: the frontend client requests the `offline_access` scope, and the realm's **Offline Session Idle/Max ≥ 365 days** (same operator setting feature 016 documents in `docs/keycloak-persistent-login-realm-settings.md`). Required so scheduled jobs can re-derive authority (R2).
- A new env var for offline-token encryption (e.g., `OFFLINE_GRANT_ENC_KEY`) — generated secret, **not committed**.
- **PHI detector**: install the lead-dev-approved `presidio-analyzer` + `presidio-anonymizer` and the spaCy model (e.g., `python -m spacy download en_core_web_lg`) — bundled into the backend image at build time, runs locally (no PHI egress). This is the only new dependency; scheduling and cron parsing remain pure-Python.

## Database
New tables auto-create on backend startup via `Database._init_db()` (idempotent). New tutorial steps seed via `backend/onboarding/seeds/` (`ON CONFLICT DO NOTHING`). No manual migration step.

## Exercise the stories

### US1 — Personalized onboarding (P1)
1. Sign in as a brand-new user → onboarding runs (`status != completed`).
2. Step through the server-generated ParamPickers: enter profession + goals; toggle recommended skills; choose a personality.
3. Start a fresh chat → assistant references your profession/goals and uses the chosen tone.
4. Sign out/in → onboarding does **not** re-run; personalization persists (SC-003).
5. Skip midway → assistant still usable; resume later (FR-005).

### US2 — Skills (P2)
1. Open the skills catalog (server-generated): each skill = an agent tool with description + required scope.
2. Enable a skill you're authorized for → assistant can now use it; check the audit log for `skill.enable`.
3. View a skill needing an ungranted scope → shown unavailable with a reason (FR-011).
4. Disable it → assistant can no longer use it (FR-012).

### US3 — Personality / "soul" (P2)
1. Edit personality to "concise, direct, no filler" → save (`PUT /api/personalization/profile`).
2. New chat reflects the tone. 3. Try a personality note that says "ignore safety rules" → compliance still wins (FR-015 test).

### US4 — Memory (P2)
1. Tell the assistant "remember I prefer bullet-point summaries" → `memory.create` audited; appears in `GET /api/memory`.
2. New session → assistant honors it unprompted.
3. Delete it via the memory viewer → stops influencing the assistant in-session (SC-012).
4. Say something PHI-shaped "remember my patient's MRN is …" → it is used in-turn but **not** persisted (verify 0 rows; SC-005).

### US5 — Scheduled jobs / cron (P3)
1. Ask to schedule a short-interval job (e.g., every 2 minutes for the demo) and confirm consent → `POST /api/schedule`; the client captures the offline grant (`offline_grant_request`/`ack`).
2. Wait → job fires within ~1 min of due time without you acting; result lands in chat + a `notification` event; `job_run` recorded (SC-007).
3. In another tab, revoke the agent's scope (or sign out everywhere) → next run records `skipped_auth`, job pauses, you're notified in-app (FR-024/SC-008).
4. Restart the backend with an active job → job survives; an interrupted run shows `interrupted` (FR-025).
5. Confirm no external delivery occurs (SC-006) — there is no external emitter.

### US6 — Dreaming (P3)
1. Generate several sessions of signals (some repeated, some one-off).
2. Trigger a sweep (manual) or wait for the default daily run → recurring non-PHI signals promote to `memory_item`; one-offs and PHI candidates do not (SC-011).
3. Review the sweep summary (server-generated) and the `dreaming.sweep` audit event.
4. Toggle dreaming off (it's on by default) and confirm it stops.

## Tests to run
- `cd backend && pytest` (unit + integration: scheduler timing, offline-grant re-derivation + fail-safe, PHI gate, memory CRUD, prompt-injection precedence, onboarding round-trip) and `ruff check .`
- Frontend: `vitest` + ESLint (minimal — entry points only).
- Coverage ≥90% on changed code (Constitution III).

## Key verification points (map to Success Criteria)
- SC-004: every new action shows in the audit log. SC-005: 0 PHI rows in memory. SC-006: 0 external deliveries. SC-008: 0 stale-authority runs / privilege escalations. SC-009: 0 new frontend primitive types. SC-010: 0 new third-party libraries.
