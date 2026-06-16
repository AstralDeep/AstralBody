# Contract: Run Record & Report

**Feature**: 032 | Phase 1 | Authoritative for the dual artifact (FR-008/028/029) and its location (FR-031).

## Location

`<artifacts_root>/<run_id>/` where `artifacts_root` is gitignored (default `backend/verification/.runs/`, overridable via `--out`). Per-run namespacing → repeatable runs never collide or pollute the repo (FR-031). `run_id` = `__verif__<stamp>` (stamp passed in by the caller; scripts cannot read the clock).

Files: `verdicts.json` (machine-readable) and `report.md` (generated from it).

## `verdicts.json` (RunRecord)

```json
{
  "run_id": "__verif__20260616T101500Z_ab12",
  "started_at": "2026-06-16T10:15:00Z",
  "finished_at": "2026-06-16T10:16:21Z",
  "mode": "in_process",
  "auth_mode": "mock_inprocess",
  "personas": ["everyday", "researcher", "medical", "government"],
  "coverage": {
    "file_categories": ["spreadsheet", "document", "image"],
    "component_types": ["table", "metric", "bar_chart", "tabs", "alert", "keyvalue"]
  },
  "verdicts": [ /* Verdict objects (see check-and-verdict.md) */ ],
  "uncertain_ratio": 0.0,
  "differentiation": [
    "Interactive table + category chart + metric tiles built from the uploaded statement's real rows",
    "Components persisted under stable identity and re-executable via the permission-gated action path",
    "Every action recorded on-behalf-of the user by a scoped delegate agent in an unbroken audit chain",
    "Safe on-demand parser drafting (held for admin approval) for an unknown file type"
  ],
  "flags": []
}
```

Rules:
- `coverage` lists ONLY what was actually observed — no unsubstantiated claims (SC-003).
- `differentiation` entries are each grounded in a specific verdict/evidence (FR-029); none asserted beyond the evidence.
- `auth_mode` echoed at run level and on every verdict; a `mock_inprocess` run MUST NOT contain any real-realm guarantee language (SC-010).
- `flags` includes `credential_near_exposure` (forces non-zero exit) and `keycloak_unreachable_degraded` when applicable.

## `report.md` (stakeholder-readable)

Generated from the RunRecord. Structure:
1. **Header** — run id, mode, auth_mode (with an explicit "mock run — not a real-realm guarantee" banner when applicable), personas, time window.
2. **Per-persona × per-property table** — verdict + one-line evidence each (tangible UI / delegated authority / backend-only UI).
3. **Coverage** — file categories + component types actually exercised.
4. **Differentiation** — the evidence-backed "what a text-only assistant can't do" list.
5. **Uncertain & flags** — uncertain_ratio and any flags, plainly stated.

## Exit code (CLI)

`0` only if zero `fail` verdicts AND no `credential_near_exposure` flag. `uncertain` verdicts do not fail the process by default but are surfaced; `--strict` promotes any `uncertain` to a non-zero exit.
