# REST Contract — Per-User Agent Credentials

**Status**: Existing endpoint, **referenced** by this feature. No changes to the contract.

This feature does **not** introduce a new credentials API. The existing endpoint already handles every requirement (FR-004 through FR-007). This file documents the contract as it relates to the three new agents so that downstream test plans know what to assert.

---

## Endpoint

```
PUT /api/agents/{agent_id}/credentials
```

Defined in [backend/orchestrator/api.py](backend/orchestrator/api.py) (function `set_agent_credentials`).

`agent_id` is one of:
- `classify-1`
- `forecaster-1`
- `llm-factory-1`

(or any other registered agent — this endpoint is generic.)

---

## Authentication

Standard AstralBody Keycloak JWT in `Authorization: Bearer <jwt>`. The `sub` claim becomes the `user_id` against which credentials are stored.

---

## Request body

```json
{
  "credentials": {
    "CLASSIFY_URL": "https://classify.ai.uky.edu/",
    "CLASSIFY_API_KEY": "user-supplied-secret"
  }
}
```

Keys MUST be drawn from the agent's declared `card_metadata.required_credentials`. Unknown keys are rejected with HTTP 400.

---

## Response (extended for this feature)

The existing response schema is preserved with one **additive** field:

```json
{
  "agent_id": "classify-1",
  "stored_keys": ["CLASSIFY_URL", "CLASSIFY_API_KEY"],
  "required_keys": ["CLASSIFY_URL", "CLASSIFY_API_KEY"],
  "ready": true,
  "credential_test": "ok"          // NEW (additive) — see below
}
```

`credential_test` is the verdict from the immediate post-save probe described in [research.md §R-005](../research.md#r-005-credential-validation-test-connection-at-save-time):

| Value | Meaning | UI behavior |
|-------|---------|-------------|
| `"ok"` | Probe succeeded — credentials accepted by the service. | Green check; tools unlocked. |
| `"auth_failed"` | Service responded 401/403. | "Credentials rejected by service." Tools remain locked. |
| `"unreachable"` | Network failure / DNS / connection refused. | "Service unreachable — check the URL." Tools remain locked. |
| `"unexpected"` | Anything else (parse error, 5xx, HTML where JSON expected). | "Unexpected response — try again or check the URL." Tools remain locked. |
| **(omitted)** | Test was not performed (e.g. agent has no `_credentials_check`). | Pre-feature behavior; agent is treated as ready. |

**Backwards compatibility**: existing agents that do not implement `_credentials_check` continue to receive a response without the `credential_test` field, exactly as today.

---

## Side-effects

- An audit event is recorded for the credential mutation (existing behavior; recorder in [backend/audit/](../../backend/audit/)). The API key value is **never** included in the event payload.
- Any existing in-memory caches of decrypted credentials for this `(user, agent)` are invalidated.

---

## Related endpoints (existing, unchanged)

- `GET /api/agents/{agent_id}/credentials` — returns the list of stored keys (without values) and the agent's required schema. **Used by the frontend modal to know whether to show "saved" indicators.**
- `DELETE /api/agents/{agent_id}/credentials` — clears all stored credentials for the agent for the calling user (FR-004 "clear" path).
