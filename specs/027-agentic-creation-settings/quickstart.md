# Quickstart: 027 Agentic Creation & Top-Bar Settings Menu

## Run

```bash
docker compose up -d --build astralbody   # single deployable on :8001
# open http://localhost:8001/  → shell now has a top bar with the Settings menu
```

Mock auth (`VITE_USE_MOCK_AUTH=true`) signs you in as an admin test user — the Admin tools
group will be visible.

## Try agentic creation

1. In chat, ask for something no agent provides, e.g. *"Track my favorite stocks and show a
   daily summary table."*
2. The assistant detects the gap, auto-creates a draft agent, self-tests it against your
   request, and posts a card with the outcome and **Approve / Refine / Discard** buttons.
3. Approve → security checks run → the agent goes live and your original request now works in
   the same conversation. Settings → Agents & permissions → Drafts shows the same draft.
4. Extend a live agent you own: *"Add a CSV export tool to my stock tracker."* → revision draft
   → approve → gate re-runs → swap (rollback-safe).

Flag: `FF_AGENTIC_CREATION=false` disables meta-tool injection (chrome unaffected).

## Try the settings menu

Top bar → gear → grouped menu (Account / Help / Admin tools / Sign out). Every entry opens a
server-rendered modal surface; mutations are explicit-save and re-render with a notice.

## Add a new settings surface

1. Write `render(data, params) -> str` in `backend/webrender/chrome/surfaces/<key>.py`
   (escape via `esc()`); register in `SURFACE_RENDERERS`.
2. Add its `ui_event` actions to `backend/orchestrator/chrome_events.py` (call service/DB
   internals, re-render, push `chrome_render`).
3. Add the menu entry in `chrome/topbar.py` (group + availability rule).
4. Add a golden/structural test under `backend/tests/chrome/` + a dispatcher test.

## Tests

```bash
docker exec astralbody sh -c "cd /app/backend && python -m pytest tests/chrome tests/test_chrome_events.py tests/test_agentic_creation.py tests/test_ws_chrome_protocol.py -q"
ruff check backend/        # py311 target (root ruff.toml)
```

Real-browser gate (Constitution X): Playwright pass against the live container — menu keyboard
navigation, every surface opens, permissions save round-trip, theme apply+persist, audit paging,
tour run, sign-out, and the full create→self-test→approve→use chat flow.
