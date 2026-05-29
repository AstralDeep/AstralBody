# Quickstart: FastAPI-Delivered UI & `astralprims`

## Prerequisites
- Python 3.11+, PostgreSQL (existing), a Keycloak realm (existing).
- `pip install -r backend/requirements.txt` (now includes `astralprims`).

## Run (dev)
```bash
cd backend
python start.py            # starts orchestrator (:8001) + agents (:8003+)
# open http://localhost:8001/  → server-rendered UI (no separate frontend server)
```
There is **no** `npm run dev` / Vite server and **no** `:5173` anymore — the UI is served from `:8001`.

## Verify the core swap
```python
# Agent tools now import primitives from the package, not shared.primitives:
from astralprims import Text, Card, Table, create_ui_response
resp = create_ui_response([Card(title="Hi").add(Text(content="<b>safe</b>"))])
# resp == {"_ui_components": [ {...} ], "_data": None}   # identical envelope
```
- Note the base styling field is **`css`** (not `style`): `Text(content="x", css={"color": "#fff"})`.

## Add / change a primitive's web rendering
1. Add/edit the render function for the type in `backend/webrender/renderer.py` (escape text via `esc()`).
2. Register it in `backend/webrender/registry.py` (`type -> render fn`). Unregistered types render a
   placeholder (never crash a response).
3. Keep autoescape ON; for rich text/markdown route through `webrender/sanitize.py`.
4. Add a golden-HTML test (see below).

## Add a future client target (proves FR-011 / SC-005)
- Create a sibling renderer (e.g., `backend/<target>render/renderer.py`) implementing
  `render(components, profile) -> <target output>`. Do **not** touch astralprims primitive definitions or any
  agent code. ROTE already produces a device-appropriate dict tree to render from.

## Tests
```bash
cd backend && pytest                 # renderer golden HTML, protocol, auth, agent migration
ruff check .
```
- **Golden HTML**: each primitive type + a nested tree → stable HTML fragment.
- **Escaping (SC-008)**: feed `<script>`/markup into text fields → asserted inert in output.
- **ROTE**: adapt-then-render for browser/mobile/watch/voice profiles.
- **Parity (Constitution X)**: end-to-end in a **real browser** against the running backend — sign in, chat,
  exercise every primitive type, streaming, interaction, upload/download, audio, table pagination, audit /
  feedback / tutorials / settings.

## Cutover checklist (test-gated — do the deletes LAST)
**Gate — must be green before any deletion:**
- [ ] `pip install astralprims` present in `backend/requirements.txt` and importing in all ~30 sites.
- [ ] All importers use `astralprims`; the one `style=` site → `css=`.
- [ ] `pytest` ≥90% on changed code; renderer golden-HTML + protocol + auth tests pass.
- [ ] Real-browser end-to-end parity pass across every surface (SC-002, SC-006).

**Only after the gate is green:**
- [ ] Delete `frontend/` (entire directory).
- [ ] Delete `backend/shared/primitives.py`; confirm **zero** references remain (SC-003).
- [ ] `Dockerfile`: remove Stage-1 Node/Vite build, the `COPY --from=frontend-builder … dist`, and `EXPOSE 5173`.
- [ ] `docker-compose.yml`: remove the `"127.0.0.1:5173:5173"` port mapping (keep `8001`).
- [ ] `backend/start-docker.sh`: remove the `python3 -m http.server 5173 …` line.
- [ ] `/` serves the shell; `/static/*` serves client assets; `/auth/*` server-side OIDC works with 365-day resume.
- [ ] UI served only from `:8001`; no separate SPA build (SC-004). Rebuild image and smoke-test.
