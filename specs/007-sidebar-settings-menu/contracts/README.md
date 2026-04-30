# Contracts

**Feature**: 007-sidebar-settings-menu

This directory is **intentionally empty**.

This feature is a pure frontend refactor: it introduces no new external interfaces. Specifically:

- **No new REST endpoints.** Existing endpoints (`/api/audit*`, `/api/llm/test`, `/api/feedback/*`, `/api/onboarding/*`) are unchanged. Their request/response shapes, auth, and authorization rules are unaffected.
- **No new WebSocket messages.** Existing WS message types (`register_ui`, `ui_event`, `ui_render`, `chat_status`, `audit_append`, `llm_config_set`/`clear`/`ack`, `llm_usage_report`, etc.) are unchanged.
- **No new audit event classes.** The existing `EVENT_CLASSES` tuple in `backend/audit/schemas.py` is not extended. Item activations inside the Settings menu emit the same audit events the original sidebar buttons emit today (e.g., clicking "Audit log" in the Settings menu produces the same `ws.<action>` audit event the previous sidebar button produced).
- **No new database tables or columns.** No migration. No `Database._init_db()` change.
- **No new env vars.** No new feature flags.
- **No new IPC / process boundaries.** The orchestrator–agent–frontend topology is unchanged.

Per Constitution Principle V (lead-developer approval for new dependencies): zero new third-party libraries are introduced — `lucide-react`, React, Vite, Vitest, Testing Library are already approved and in use.

If a future change to this feature *does* introduce an external interface (e.g., persisting menu preferences server-side, adding admin-only telemetry on menu opens, etc.), document the contract in this directory at that time.
