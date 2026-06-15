# Contract: Orchestrator Scheduler Seams

Two async methods on `Orchestrator`, with signatures fixed by the existing caller `backend/scheduler/runner.py`.

## run_scheduled_turn (FR-001)

```python
async def run_scheduled_turn(
    self,
    *,
    user_id: str,
    chat_id: str | None,
    instruction: str,
    agent_id: str | None,
    access_token: str,
    allowed_scopes: list[str],
    correlation_id: str,
) -> str:
    """Execute a scheduled job's instruction as a background chat turn.

    Runs `instruction` through the normal chat path via BackgroundTaskManager +
    VirtualWebSocket, under the minted delegated `access_token` bounded to
    `allowed_scopes`, persisting output to chat history (in-app only). Returns a
    short human summary string used for the completion notification.
    """
```

**Behavior requirements**
- MUST use the delegated `access_token` and never exceed `allowed_scopes` (RFC 8693 attenuation; FR-006).
- MUST persist output to the target chat history (in-app delivery only; no external channel).
- MUST be safe to call from the scheduler loop (off the interactive request path).
- On internal error MUST raise (the runner catches → `outcome="failure"`); MUST NOT crash the loop.
- MUST emit a structured log/metric for the run (FR-017).

**Caller**: `runner.py:99`.

## notify_user (FR-002)

```python
async def notify_user(self, user_id: str, payload: dict) -> None:
    """Deliver an in-app notification to all of a user's connected sockets and
    persist it for delivery on next connect.

    payload shape (from runner):
      {"type": "notification", "level": "success"|"warning"|...,
       "source": "schedule", "job_id": str|None, "chat_id": str|None,
       "title": str, "body": str}
    """
```

**Behavior requirements**
- MUST fan out to every socket the user has connected (reuse `_safe_send` / `ui_clients`).
- MUST persist the notification so an offline user receives it on next connect (Edge Case: offline delivery).
- MUST be best-effort safe — failures are non-fatal to the run (runner wraps in try/except).
- MUST audit the notification (existing `conversation`/notification audit class).

**Caller**: `runner.py:44` (via `_notify`).
