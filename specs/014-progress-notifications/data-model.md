# Phase 1 Data Model: In-Chat Progress Notifications & Persistent Step Trail

Schema deltas only — all entity definitions inherit from existing AstralBody tables. Idempotent migration runs in [`backend/shared/database.py`](../../backend/shared/database.py) `Database._init_schema()` per Constitution IX.

---

## New table: `chat_steps`

One row per persistent step entry. FK to the existing `chats` and `messages` tables.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | `TEXT` | NO | — | UUIDv4 generated server-side. Matches existing `id`-as-text convention (`chats.id`, `saved_components.id`). |
| `chat_id` | `TEXT` | NO | — | FK → `chats.id` ON DELETE CASCADE. |
| `user_id` | `TEXT` | NO | `'legacy'` | FK semantics match `messages.user_id`. Used for ownership scoping on the read endpoint. |
| `turn_message_id` | `INTEGER` | YES | NULL | FK → `messages.id` of the user message that initiated this turn. NULL only during the brief window between user-message commit and step start. |
| `kind` | `TEXT` | NO | — | Enum encoded as text: `tool_call`, `agent_handoff`, `phase`. Matches FR-007's three step kinds. |
| `name` | `TEXT` | NO | — | Display label (tool name, target agent name, or phase name). Already-truncated upstream; max stored length 256. |
| `status` | `TEXT` | NO | `'in_progress'` | Enum: `in_progress`, `completed`, `errored`, `cancelled`, `interrupted`. `interrupted` is set lazily by the read endpoint when an `in_progress` row is older than 30 s and the chat has no active task. |
| `args_truncated` | `TEXT` | YES | NULL | JSON-stringified, PHI-redacted, truncated to 512 chars. NULL when the step has no meaningful args (e.g., a phase). |
| `args_was_truncated` | `BOOLEAN` | NO | `FALSE` | True when the original args exceeded the truncation budget. |
| `result_summary` | `TEXT` | YES | NULL | PHI-redacted, truncated to 512 chars. NULL while in progress and for cancelled/interrupted steps that produced no result. |
| `result_was_truncated` | `BOOLEAN` | NO | `FALSE` | True when the original result exceeded the truncation budget. |
| `error_message` | `TEXT` | YES | NULL | Populated only when `status = 'errored'`. PHI-redacted, truncated to 512 chars. |
| `started_at` | `BIGINT` | NO | — | Epoch ms. Sort key for per-turn ordering (FR-013). |
| `ended_at` | `BIGINT` | YES | NULL | Epoch ms. NULL while `status = 'in_progress'`. |

**Indexes**:

- Primary key on `id`.
- `idx_chat_steps_chat_id ON chat_steps(chat_id, started_at)` — covers the chat-load read pattern (FR-012).
- `idx_chat_steps_turn ON chat_steps(turn_message_id)` — covers per-turn fetches.

**Foreign keys**:

- `chat_id REFERENCES chats(id) ON DELETE CASCADE`.
- `turn_message_id REFERENCES messages(id) ON DELETE SET NULL` — keeps step rows visible if a message row is removed by future cleanup, since the chat itself is the authoritative parent.

**Validation rules** (enforced at the recorder layer, not at SQL):

- `kind ∈ {tool_call, agent_handoff, phase}`.
- `status ∈ {in_progress, completed, errored, cancelled, interrupted}`.
- `error_message` is populated iff `status = 'errored'`.
- `ended_at IS NOT NULL` iff `status ∈ {completed, errored, cancelled, interrupted}`.
- `started_at <= ended_at` when both are non-null.

---

## Schema delta on existing `messages` table

Single new column. Idempotent — added only if absent, matching the pattern at `database.py:117–131`.

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `step_count` | `INTEGER` | NO | `0` | Cached count of step rows for the turn this message belongs to. Maintained by `ChatStepRecorder` on lifecycle transitions. Pure render optimization — chat list endpoint reads this without joining. |

---

## State transitions

Each `chat_steps` row follows this state machine:

```text
                ┌──────────────┐
   create  ───▶ │ in_progress  │ ───▶  completed
                │              │ ───▶  errored
                │              │ ───▶  cancelled       (on user-cancel of turn)
                └──────────────┘
                       │
                       └─▶ interrupted   (lazily set by read endpoint when
                                          in_progress age > 30s and no active task)
```

- Terminal states: `completed`, `errored`, `cancelled`, `interrupted`. No further transitions.
- `cancelled` ↔ `interrupted` distinction:
  - `cancelled` = user pressed cancel on a still-active turn (FR-020/021).
  - `interrupted` = the connection died, the row was abandoned, and the read endpoint healed it on next load.

---

## Existing entities — no schema change

- **`chats`** — unchanged. Step rows are scoped via `chat_id` FK.
- **`messages`** — adds `step_count` only (above). No change to `role`/`content`.
- **`saved_components`** — unchanged. Step entries are NOT components and do not flow through that table.
- **`tool_overrides` / `agent_ownership` / `tool_permissions`** — unchanged. Step events flow over the existing authenticated WebSocket; no new authz entity needed.

---

## Frontend types (mirrors backend, in [`frontend/src/types/chatSteps.ts`](../../frontend/src/types/chatSteps.ts))

```ts
export type ChatStepKind = 'tool_call' | 'agent_handoff' | 'phase';

export type ChatStepStatus =
  | 'in_progress'
  | 'completed'
  | 'errored'
  | 'cancelled'
  | 'interrupted';

export interface ChatStep {
  id: string;
  chat_id: string;
  turn_message_id: number | null;
  kind: ChatStepKind;
  name: string;
  status: ChatStepStatus;
  args_truncated: string | null;       // PHI-redacted on backend; NEVER raw
  args_was_truncated: boolean;
  result_summary: string | null;       // PHI-redacted on backend; NEVER raw
  result_was_truncated: boolean;
  error_message: string | null;
  started_at: number;                  // epoch ms
  ended_at: number | null;             // epoch ms
}
```

The collapse state is **not** part of the entity. It lives in `sessionStorage` keyed by `step.id` per R8.
