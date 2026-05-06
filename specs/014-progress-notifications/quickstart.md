# Quickstart: Verify the In-Chat Progress Notifications & Persistent Step Trail

How a developer (or reviewer) can spin up the feature locally and confirm each user story end-to-end. Aligns with the constitutional requirement (Principle X) that UI changes be exercised in a real browser before being declared complete.

---

## Prerequisites

- Repo at branch `014-progress-notifications`.
- Backend Python deps installed (`pip install -r backend/requirements.txt`).
- Frontend deps installed (`cd frontend && npm install`).
- Local SQLite DB (default) or Postgres reachable per the existing dev setup. The new `chat_steps` table and the `step_count` column on `messages` are created automatically by `Database._init_schema()` on first backend startup — no manual migration step.

## Bring the system up

```text
# Terminal 1 — backend
cd backend
python start.py

# Terminal 2 — frontend
cd frontend
npm run dev
```

Open the dev URL printed by Vite, sign in via Keycloak, and either select an existing chat or create a new one.

---

## Verifying User Story 1 — Ambient rotating progress indicator

1. Submit any query that triggers at least one tool call (e.g., a grant search via the `grants` agent).
2. **Expected**: Within 500 ms (SC-001) the loading slot under the user message shows a single rotating cosmic word from the approved 55-word list — e.g., `Astralizing…` → `Resonating…` → `Traversing…`.
3. The displayed word changes at least once per second on average and never displays a word outside the approved list (SC-002).
4. As soon as the assistant's reply completes, the indicator disappears within one render cycle (FR-005).
5. Submit a second very fast query (one that completes in <500 ms). Confirm the indicator either does not appear or appears briefly without flickering (US1 acceptance scenario 4).

**Pass criteria**: Spec acceptance scenarios US1-1 through US1-4 all observed.

---

## Verifying User Story 2 — Persistent in-chat step trail

1. Submit a query that triggers multiple tool calls (e.g., a multi-step grant agent flow that searches, fetches, and synthesizes).
2. **Expected**: As each step begins, a labeled step entry appears in the chat between your user message and the (still-pending) assistant reply. Each entry shows the step name (tool/agent/phase) and an in-progress visual indicator.
3. As each step finishes, its entry's status indicator flips to "complete" (or "errored" / "cancelled" if applicable). The entry remains visible — it is NOT removed.
4. After the assistant reply finishes delivering, scroll up and back down within the chat — every step entry from the turn is still there, in the order it began.
5. Reload the page. Open the chat again. Every step entry from prior turns is still rendered in chronological order (FR-012). Confirmed via `GET /chats/{id}/steps` populating the rendered list.
6. **Negative path**: Submit a query that triggers a tool failure. Confirm the failed entry shows a clearly distinct error state and remains in the chat (US2-5).

**Pass criteria**: Spec acceptance scenarios US2-1 through US2-5 all observed.

---

## Verifying User Story 3 — Collapsible entries with session-persistent state

1. After a turn with multiple step entries finishes:
   - Successful entries default to **collapsed** (single-line summary, FR-016).
   - Errored or cancelled entries default to **expanded** so the failure stays visible (FR-016 status-dependent).
   - In-progress entries (during a fresh turn) default to **expanded** (FR-015).
2. Manually click an expand affordance on a collapsed successful entry — it expands. Click again — it collapses (FR-014, FR-017).
3. Reload the page (same browser tab). Confirm every entry's expanded/collapsed state matches what you last set (FR-018, SC-005).
4. Switch to a different chat and back to this one within the same tab — collapse states are preserved (US3-5).
5. Close the tab entirely and open the chat in a new tab — collapse states reset to defaults (FR-019; this is correct behaviour, scoped to local session).

**Pass criteria**: Spec acceptance scenarios US3-1 through US3-6 all observed.

---

## Verifying cancellation semantics (FR-020/021)

1. Submit a query that triggers a long-running tool (or one mocked to delay).
2. While the indicator is rotating and at least one step entry is `in_progress`, click the existing cancel button.
3. **Expected**:
   - Indicator vanishes immediately.
   - The in-progress step entry transitions to `cancelled` and remains in the chat (FR-021), defaulting to **expanded** per FR-016.
   - The orchestrator structured-logs a cancellation event for any in-flight tool call whose result later arrives but is discarded (R6 best-effort path).
4. The assistant reply MUST NOT include any content derived from the cancelled step's discarded result.

---

## Verifying PHI redaction (FR-009b, SC-008)

Manual sample audit, since automated PHI validation requires production-shaped data:

1. Submit a query whose tool args or result would naturally include PHI-shaped content (e.g., a fake patient record with name, DOB, MRN).
2. After the step finishes, expand the step entry. Confirm:
   - `args_truncated` does NOT contain the PHI fields — they are masked (e.g., `[REDACTED:dob]`).
   - `result_summary` does NOT contain the PHI fields.
3. Reload the chat to fetch from `GET /chats/{id}/steps`. Confirm the persisted entry is also free of PHI (defense-in-depth read-side redaction, R4).
4. Tail backend logs for any `phi_redactor.redaction_applied` events generated during the turn.

---

## Automated checks before merge

- Backend: `cd backend && pytest tests/test_chat_steps.py tests/test_chat_steps_cancel.py tests/test_chat_steps_migration.py && ruff check .` — all pass, coverage on changed code ≥ 90%.
- Frontend: `cd frontend && npm run test && npm run lint` — Vitest + ESLint clean, coverage on changed code ≥ 90%.
- E2E: open the running app in a browser and walk through US1, US2, US3 above (Constitution X).

---

## Known visual reference points

- **Indicator**: rendered inside the existing loading slot at [`ChatInterface.tsx:715-741`](../../../frontend/src/components/ChatInterface.tsx#L715-L741). The new `<CosmicProgressIndicator>` replaces the static "Processing..." `<span>`.
- **Step entries**: rendered as new items in the message map between the user `<motion.div>` and the assistant `<DynamicRenderer>`, drawn from `chatSteps[activeChatId]` sorted by `started_at`.
- **Word list**: [`frontend/src/components/chat/chatStepWords.ts`](../../../frontend/src/components/chat/chatStepWords.ts) — single source of truth for the 55 approved words.

---

## Rollback path

- Drop `chat_steps` table.
- Drop `step_count` column on `messages`.
- Remove the `case "chat_step":` arm from `useWebSocket.ts`.
- Remove the `<CosmicProgressIndicator>` and `<ChatStepEntry>` components from `ChatInterface.tsx`.

No data loss for any existing chat — `messages` and `chats` are not touched destructively.
