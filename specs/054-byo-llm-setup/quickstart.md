# Quickstart: Verifying Bring-Your-Own-LLM (054)

End-to-end verification script, ordered by user story. Run everything inside
the `astraldeep` container against a dev deployment whose `.env` has **no**
`OPENAI_API_KEY`/`OPENAI_BASE_URL`/`LLM_MODEL`/`KNOWLEDGE_LLM_MODEL` lines
(post-054 posture).

## 0. Boot posture (US2 / FR-003)

```bash
docker compose up -d
docker exec astraldeep bash -c 'env | grep -E "OPENAI|LLM_MODEL" || echo "no LLM env — OK"'
curl -sf localhost:8001/healthz && curl -sf localhost:8001/readyz
```

Boot succeeds with zero LLM settings. Then set the legacy vars in `.env`,
restart, and verify nothing changes (SC-007): a fresh user is still gated.

## 1. Mandatory first-run dialog (US1)

1. Sign in on the web as a **fresh user** (no `user_llm_config` row).
2. Expect: the "Set up your AI provider" modal is the first thing rendered —
   no welcome canvas behind it, no ✕ button; Escape/backdrop do nothing.
3. Try to cheat: send `chat_message` / `chrome_open {surface:"personalization"}`
   / `chrome_close` over the WS devtools — every one refused; `audit_events`
   gains `llm_unconfigured` rows.
4. Pick "OpenAI" → base URL prefilled read-only; enter a bad key → Test →
   category error `auth_failed`. Enter a valid key → Load models → pick one →
   Test → "Connected". Save.
5. Expect: modal closes, welcome canvas renders, Settings → "Take the tour"
   works exactly as before (SC-006). DB: `user_llm_config` row exists;
   `api_key_enc` is Fernet ciphertext (not the key);
   `select * from audit_events` shows `llm_config_change{action:"created"}`
   with no key material.
6. Repeat on Windows client, Android emulator, iOS sim, macOS sim: the surface
   arrives as `chrome_surface {mode:"mandatory"}`, renders full-screen,
   back/top-bar navigation is suppressed until save (SC-001).

## 2. Configure once, works everywhere (US3)

1. With the user configured on web, sign in on Android: no dialog; chat works.
2. Sign out/in on web: no dialog (survives logout).
3. Open two web tabs; clear the config in tab A (LLM settings → Clear):
   **both** tabs re-gate immediately (mandatory modal pushed); Android
   re-gates too. Reconfigure; all unblock without re-login (FR-015).
4. Cross-user isolation: user B fresh sign-in is gated even though user A is
   configured; B's calls never use A's record (assert distinct base_url in
   `llm_call` audit rows).

## 3. Admin system credential & honest degradation (US4)

1. As admin, **without** a system credential: trigger a scheduled job
   (`scheduled_job` with an LLM turn). Expect `job_run.outcome='failed'`,
   notification text says the AI was unavailable — NOT "finished" (SC-005).
   Knowledge synthesis cycle logs "system LLM not configured — skipped".
   Workspace combine returns its error frame. Compaction path: long chat still
   works, compaction skips with its non-AI fallback note.
2. Settings (admin) → "System LLM" surface: visible to admin only (non-admin
   `chrome_open {surface:"llm_system"}` refused server-side). Configure +
   Test + Save.
3. Re-trigger the scheduled job → succeeds; `llm_call` audit rows carry
   `credential_source:"system"`. Verify a **fresh unconfigured user is still
   gated** (system credential never serves user chat — FR-019).

## 4. Watch posture (US5)

1. Unconfigured user, watch sim signed in via QR: dictate a message.
2. Expect displayed AND spoken: "Set up your AI provider on your phone or the
   web first." (not a generic error).
3. Configure on web; next watch message round-trips normally (no watch-side
   steps).

## 5. Hygiene & removal sweeps (US2 / SC-004)

```bash
# no operator-default code path remains
grep -rn "OperatorDefaultCreds\|OPENAI_API_KEY\|OPENAI_BASE_URL" backend/ \
  --include='*.py' | grep -v tests | grep -v sandbox  # expect: no live reads
# key hygiene: no plaintext key anywhere
docker exec astraldeep bash -c "grep -rn '<the-test-api-key>' /app/backend/data/ || echo clean"
psql -c "select payload from audit_events where payload::text like '%<key-fragment>%';"  # expect 0 rows
# log redaction filter is installed
docker logs astraldeep 2>&1 | grep -c '<the-test-api-key>'  # expect 0
```

Also: `.env.example` has no LLM credential block (replaced by the
user/system-config note); `docs/production-deployment.md` carries the
migration note; gitleaks passes.

## 6. Test suite

```bash
docker exec astraldeep bash -c "cd /app/backend && python -m pytest -q"          # full suite
docker exec astraldeep bash -c "cd /app/backend && python -m pytest llm_config/tests -q"
ruff check .   # host/CI
```

Retargeted suites: `test_background_jobs_use_operator_default.py` → system
credential; `test_call_llm_credential_resolution.py` → user/system matrix;
drift guards on all four clients stay green (no manifest change).
