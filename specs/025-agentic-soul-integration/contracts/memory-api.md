# Contract: Memory API + memory tools

Durable, non-PHI, per-user memory. REST under `backend/personalization/api.py`; orchestrator-callable tools in `backend/personalization/memory_tools.py`. Every create/view/update/delete is audited (`event_class="memory"`, FR-019) and strictly user-scoped.

## REST — user-facing memory viewer/editor

### GET `/api/memory`
List the caller's durable memory items.
```json
{ "items": [
  { "id": "uuid", "category": "preference", "value": "Prefers bullet-point summaries", "source": "explicit", "created_at": 1748300000000 }
] }
```

### DELETE `/api/memory/{id}`
Delete one item. Takes effect immediately; assistant stops relying on it in the same session (SC-012). **204** on success, **404** if not owned. Emits `memory.delete`.

### PUT `/api/memory/{id}`
Correct an item's `value` (PHI-gated). **200** updated item / **422** rejected. Emits `memory.update`.

## Memory tools (LLM-invoked, gated like any tool)

| Tool | Args | Behavior |
|---|---|---|
| `remember` | `{ category, value }` | Explicit user request → writes a `memory_item(source='explicit')` after PHI gate. Rejected content is **not** written; the tool returns a clear non-PHI notice. Emits `memory.create`. |
| `memory_search` | `{ query }` | Returns matching durable items + recent signals for recall; emits `memory.view`. |
| `memory_get` | `{}` | Returns the caller's durable items (for the prompt-injection recall block). |

## Capture & promotion (documented for tests)
- Auto-capture writes **`short_term_signal`** rows (PHI-gated), never durable memory directly (R5/FR-016).
- Promotion to durable `memory_item(source='promoted')` happens only via the consolidation sweep (see dreaming contract).
- **PHI gate invariant (SC-005)**: any value flagged by the local PHI detector (Presidio — names, SSN, MRN/encounter ID, DOB, phone, email, location, etc.) or failing structured-category validation is dropped from both `short_term_signal` and `memory_item`. The gate is **fail-closed** (if the detector is unavailable, the write is blocked). Integration test feeds PHI-shaped input and asserts 0 rows persisted while the live turn still used the value.
