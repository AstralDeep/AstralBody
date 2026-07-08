# Contract: Database Async Facade, Pool, and Event-Loop Detector

## Async facade (`shared/database.py::Database`)

| Method | Contract |
|---|---|
| `afetch_one(q, p)` / `afetch_all(q, p)` / `aexecute(q, p)` | `await`-able twins of the sync methods; execute the sync body via `asyncio.to_thread`; identical results, exceptions, and SQL translation |
| `fetch_one/fetch_all/execute` (existing) | unchanged signatures; MUST NOT be called on the event-loop thread in request/WS/chat paths (enforced below) |

Call-site rule: code that runs on the loop (FastAPI handlers, WS handlers, chrome
surface `render()`, chat-turn code, repositories invoked from those) uses the `a*`
facade; thread-side/sync contexts (scripts, tests, audit repo internals, in-thread
workers) keep the sync methods.

## Connection pool

- `ThreadedConnectionPool(minconn=DB_POOL_MIN(2), maxconn=DB_POOL_MAX(10))`, borrowed in
  `_get_connection()`, returned via `putconn` in `finally` (never `close()` on the
  connection object directly).
- Stale recovery: `OperationalError`/`InterfaceError` on a borrowed connection ⇒
  `putconn(close=True)` + one retry on a fresh connection; second failure propagates.
- `DB_POOL_DISABLE=1` ⇒ verbatim legacy connect-per-call (kill switch / rollback).
- Shutdown closes the pool; leak test: after the suite, borrowed count == 0.

## Event-loop blocking detector (CI-enforced)

- Pytest fixture (auto-use for orchestrator/webrender suites): wraps the sync DB methods;
  on call, `asyncio.get_running_loop()` — success (i.e., caller is ON the loop thread) ⇒
  raise `BlockingDBOnEventLoop(stack)`.
- Allowlist: a single checked-in module-level list for transitional exemptions;
  **must be empty at feature completion** (SC-005). Each entry requires a comment-free
  justification string (it is data, not a comment).
- Dev aid (non-gating): `ASTRAL_DEBUG_SLOW_CALLBACKS=1` sets
  `loop.slow_callback_duration` and logs offenders.

## Query-count assertions (SC-002 guard)

- Test helper `count_queries()` (fixture wrapping `Database.execute/fetch_*`) asserts:
  recent-chats list == 1 query; agent-detail render ≤ 3; agents-list render ≤ 2;
  chat-load attachment hydration == 1 bulk query regardless of message count.
- These run in the normal CI test job; a regression fails the build.
