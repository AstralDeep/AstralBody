# Data Model: Bring-Your-Own-LLM (054)

## New tables (idempotent `_init_db` deltas — Constitution IX)

### `user_llm_config`

One row per user who has completed provider setup. Absence of a decryptable
row IS the "unconfigured" state that triggers the mandatory gate.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `user_id` | TEXT | PRIMARY KEY | Keycloak `sub` claim (same identity key as `user_preferences`) |
| `provider` | TEXT | NOT NULL | Preset key from `llm_config/providers.py` (`openai`, `anthropic`, `gemini`, `xai`, `openrouter`, `groq`, `together`, `mistral`, `ollama`, `lmstudio`, `custom`) |
| `base_url` | TEXT | NOT NULL | Normalized (trailing `/` stripped), http(s) URL |
| `model` | TEXT | NOT NULL | Model identifier at the provider |
| `api_key_enc` | TEXT | NULL | Fernet ciphertext under `CREDENTIAL_ENCRYPTION_KEY`; NULL only when the preset is keyless (`key_required=False`) |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | Bumped on every save |

Validation (store layer, mirrors 006 rules):
- Full triple required; partial submissions rejected (nothing partial stored).
- `base_url` must parse as http(s); `api_key` required unless the selected
  preset is keyless; save requires a fresh passing probe (FR-008).
- Undecryptable `api_key_enc` on read ⇒ row deleted + `llm_config_change
  {action:"discarded_undecryptable"}` audit ⇒ treated as absent (FR-010).

### `system_llm_config`

Zero-or-one row; the deployment-wide credential for system-context calls only.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | SMALLINT | PRIMARY KEY CHECK (id = 1) | Single-row guard |
| `provider` | TEXT | NOT NULL | Same preset vocabulary |
| `base_url` | TEXT | NOT NULL | |
| `model` | TEXT | NOT NULL | |
| `api_key_enc` | TEXT | NULL | Same Fernet posture |
| `updated_by` | TEXT | NOT NULL | Admin `user_id` who last saved (audit convenience; key never here) |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

Access is exclusively via the store's `*_system` accessors; the admin surface
handlers enforce the `admin` role server-side before touching them.

## Removed/retired state

- `OperatorDefaultCreds` (env trio) — code path deleted; no data migration
  (env values were never stored).
- Per-socket `SessionCredentialStore` keyed by `id(websocket)` — replaced by a
  user-keyed read-through cache over `user_llm_config`; the disconnect-time
  `clear` calls are deleted (persisted config survives sockets).
- `CredentialSource.OPERATOR_DEFAULT` — retired for NEW audit rows (historical
  rows untouched; append-only audit). New value: `SYSTEM` (`"system"`).

## In-memory dataclasses

- `PersistedLLMConfig(provider, base_url, model, api_key, updated_at)` —
  decrypted working shape; `__repr__` elides `api_key` (pattern copied from
  `SessionCreds.__repr__`). Never serialized to clients with the key: surface
  payloads carry only `provider`, `base_url`, `model`, and `has_key: bool`.
- `ProviderPreset(key, label, base_url, key_required, key_prefix_hint)` —
  static catalog entries (`llm_config/providers.py`).

## State transitions (first-run gate)

```
UNCONFIGURED --(save: probe OK + persist)--> CONFIGURED
CONFIGURED   --(clear via settings)--------> UNCONFIGURED   (immediate re-gate, all sockets)
CONFIGURED   --(key undecryptable on read)-> UNCONFIGURED   (audited discard; re-gate at next connect/turn)
CONFIGURED   --(provider failing at runtime)--> CONFIGURED  (per-call errors; NOT re-gated — gate tracks absence, not health)
```

The predicate is computed, never stored: `configured(user_id) :=
decryptable user_llm_config row exists`. A small TTL cache fronts the read;
`set`/`clear` invalidate synchronously (same-process) so the gate transition
is immediate.

## Rollback path (Constitution IX)

Both tables are additive and consumed only by feature-054 code. Rollback =
deploy the prior image (which never reads them) and, if desired,
`DROP TABLE IF EXISTS user_llm_config, system_llm_config;` — no other table
references them (no FKs). Re-running `_init_db` on any version is safe
(CREATE TABLE IF NOT EXISTS guards). Note: rolling back to a pre-054 image
restores the operator-default env path — an operator who has already scrubbed
`.env` gets the pre-054 "no operator default" behavior, which that image
already handles (LLM-unavailable alerts), so rollback is safe without
restoring the env values.
