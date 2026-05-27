# Contract: Personalization & Personality ("Soul") API

REST endpoints under `backend/personalization/api.py`. All require authentication; `user_id = require_user_id(request)` (Keycloak `sub`). All responses scoped strictly to the caller. Every mutation emits an audit event (`event_class="personalization"`).

Surfaces are rendered server-side via primitives; these endpoints back the ParamPicker submits and the editor panels.

## GET `/api/personalization/profile`
Returns the caller's profile + personality.
```json
{
  "profession": "Clinical researcher",
  "goals": ["Track NSF grant deadlines", "Summarize study cohorts"],
  "personality": { "tone": "concise", "directness": "high", "humor": "light", "verbosity": "low", "notes": "No corporate filler." },
  "dreaming_enabled": true
}
```

## PUT `/api/personalization/profile`
Upsert profile fields (partial allowed). Body mirrors the GET shape (any subset). `personality.notes` and all string values pass the PHI gate; rejected values return `422` with a non-PHI reason. Emits `personalization.profile_update` / `personalization.personality_update`.
- **200** → updated profile (GET shape).
- **422** → `{ "error": "value_rejected", "field": "personality.notes", "reason": "looks like protected health information" }`

## DELETE `/api/personalization/profile`
Resets profile + personality to defaults (does not delete the user). Emits `personalization.profile_update` (outcome=success, detail="reset").

## Validation rules
- `goals`: array of ≤140-char strings, ≤20 items.
- `personality.*`: enum-ish short values (`tone`, `directness`, `humor`, `verbosity`) + optional `notes` (≤500 chars), all PHI-gated.
- Personality is **style only** and is injected subordinate to compliance (FR-015) — the API stores it but the prompt assembly enforces precedence.

## Prompt-injection behavior (not an endpoint, documented for tests)
On each chat turn the orchestrator composes: compliance preamble → tool/process rules → memory recall → skill guidance → **personality block (subordinate)**. Verified by integration test asserting a personality instruction cannot override a refusal/compliance rule.
