<!--
  Sync Impact Report
  ==================
  Version change: 2.0.0 → 2.0.1 (PATCH — Principle II render-ownership clause corrected)

  Amendment (2026-05-29, v2.0.1):
    II. UI Delivery Architecture — corrected the render-ownership clause. The
        prior wording ("astralprims defines AND renders") was inaccurate: the
        published `astralprims` package is schema-only. Now: `astralprims`
        DEFINES primitives (+ their structured representation) only; the
        ORCHESTRATOR renders them; ROTE adapts that rendering per device.
        Propagated to Principle IV (lint clause), Principle VI (primitive vs
        renderer docs), Principle VIII (rendering wording), Technology Stack
        (UI Delivery), and Development Workflow (primitive vs renderer PRs).
        Classified PATCH: no principle added/removed; Principle II's name,
        SDUI mandate, and intent are unchanged — only the internal
        responsibility for rendering is corrected to match reality.
    Resolves the tracked Principle II deviation noted in
    specs/026-frontend-removal-astralprims/plan.md (Complexity Tracking).

  -- Prior amendment (2026-05-29, v2.0.0) --------------------------------
  Version change: 1.1.0 → 2.0.0 (MAJOR — Principle II redefined; React/Vite SPA mandate removed)

  Principles modified:
    II. Frontend Framework → II. UI Delivery Architecture
        (was: "frontend MUST be Vite + React + TypeScript SPA")
        (now: backend delivers server-driven UI via FastAPI; ROTE adapts to the
         connecting device/client; `astralprims` defines AND renders all primitives)
    IV.  Code Quality — TypeScript/ESLint clause generalized to "any client-side
         TypeScript/JavaScript emitted or maintained" (no standalone SPA assumed)
    VI.  Documentation — generalized TS-export clause; added astralprims primitive
         documentation requirement
    VIII. User Experience — primitives now sourced from the `astralprims` package
         rather than a predefined frontend component set

  Principles added:   None
  Principles removed: None (II redefined, not removed)

  Sections updated:
    - Technology Stack: replaced "Frontend: Vite + React + TypeScript" with the
      SDUI delivery model (FastAPI + ROTE + astralprims)
    - Governance footer: Last Amended date bumped to 2026-05-29; version → 2.0.0

  Templates requiring updates:
    ✅ .specify/templates/plan-template.md — generic Constitution Check gate + generic
       "frontend/" example dir, compatible (no React/Vite mandate referenced)
    ✅ .specify/templates/spec-template.md — generic, compatible
    ✅ .specify/templates/tasks-template.md — generic "frontend/src/" example, compatible
    ✅ No command templates require changes
    ✅ No runtime guidance docs require changes (CLAUDE.md is auto-generated)

  Follow-up TODOs: None
-->

# AstralBody Constitution

## Core Principles

### I. Primary Language

All backend code MUST be written in Python.

- No other backend languages are permitted without a
  constitution amendment.
- Python version MUST be kept current with the project's
  declared minimum (see `pyproject.toml` or equivalent).

### II. UI Delivery Architecture

The user interface MUST be server-driven. The backend composes
and delivers UI to clients; there is no standalone single-page
application framework acting as the source of truth for UI.

- The backend MUST deliver server-driven UI (SDUI) to clients
  via FastAPI.
- The ROTE layer MUST adapt delivered UI to the connecting
  device/client target. Each target receives the format it
  expects (e.g., web → HTML/CSS/JS; future desktop, native
  phone, or native watch clients receive their own appropriate
  format).
- All UI primitives MUST be **defined** by the `astralprims`
  package. It is the single source of truth for primitive
  definitions and their serializable structured representation.
  `astralprims` does NOT render; it only defines.
- The **orchestrator** MUST render those primitives into the
  client-appropriate format. The ROTE layer MUST adapt that
  rendering to the connecting device/client target. Rendering
  and per-device adaptation are orchestrator responsibilities,
  not `astralprims` responsibilities.
- Adding a new client target MUST be achievable by adding a
  renderer within the orchestrator's render layer — without
  changing `astralprims` primitive definitions or agent
  response-building code.
- No standalone React/Vite (or other SPA) frontend may be
  (re)introduced as the primary UI source of truth without a
  constitution amendment. Client-side assets emitted by the
  orchestrator's render layer for a target (e.g., HTML/CSS/JS
  for the web) are permitted and expected.

**Rationale**: Separating primitive **definition** (in the
`astralprims` package) from **rendering** (in the orchestrator,
adapted per device by ROTE) keeps the wire-level primitive
contract stable and reusable while letting the orchestrator
evolve presentation without coordinated client releases. New
device targets stay additive — a new orchestrator renderer over
the same primitives — rather than a parallel reimplementation.

### III. Testing Standards

Every new feature MUST include unit and integration tests with
a minimum of 90% code coverage.

- Tests MUST be written for all new code paths.
- Coverage MUST be measured and enforced in CI.
- No feature branch may merge without meeting the 90%
  threshold on changed code.

### IV. Code Quality

All code MUST adhere to established style standards.

- Python code MUST comply with PEP 8. Linting MUST be enforced
  via tooling (e.g., ruff, flake8).
- Any client-side TypeScript/JavaScript emitted or maintained
  (including the orchestrator render layer's output assets) MUST
  pass standard lint rules. Linting MUST be enforced in CI.
- No linting exceptions without inline justification comments.

### V. Dependency Management

No new third-party library may be added without explicit
approval from a lead developer.

- Proposed dependencies MUST be documented in the PR
  description with rationale.
- Lead developer approval MUST be recorded in the PR review.
- Transitive dependency impact MUST be considered.
- First-party packages owned by the project (e.g.,
  `astralprims`) are not third-party dependencies, but their
  introduction MUST still be documented in the PR.

### VI. Documentation

All public APIs and complex functions MUST be documented.

- Python functions MUST have docstrings following Google or
  NumPy style.
- Any client-side TypeScript/JavaScript exports MUST have JSDoc
  comments.
- Every `astralprims` primitive MUST be documented — its data
  shape and serialization — before use. Each orchestrator
  renderer MUST document the client targets it supports and its
  rendering behavior.
- Backend APIs MUST expose interactive documentation at the
  `/docs` URL (e.g., via FastAPI's built-in Swagger UI).

### VII. Security

Standard security practices MUST be implemented across all
system boundaries.

- Input validation MUST be applied to all external inputs.
- Authentication MUST use the project's Keycloak IAM instance.
  No alternative auth providers without a constitution
  amendment.
- Authorization MUST be enforced at the API layer via
  Keycloak roles/scopes.
- Agents MUST use RFC 8693 delegated tokens with attenuated
  scopes. Scopes are automatically set by the system for
  security; users MAY override or set scopes explicitly.
- Secrets MUST NOT be committed to version control.

### VIII. User Experience

The UI MUST maintain a consistent design language while
supporting backend-driven dynamic generation.

- All UI rendering MUST be driven by primitives defined in the
  `astralprims` package (the orchestrator renders them).
- The backend MAY dynamically generate layouts by composing
  `astralprims` primitives, rendered by the orchestrator as SDUI
  and adapted to the client target by ROTE.
- New primitives MUST be added to `astralprims`, approved, and
  documented before use.

### IX. Database Migrations

Any change to the database schema MUST ship with a migration
script that runs automatically; ad-hoc SQL against deployed
environments is prohibited.

- Schema changes (adding/removing tables, columns, indexes,
  constraints, enums, or types) MUST include a migration
  script committed in the same pull request as the change.
- Migrations MUST execute automatically — either on
  application startup or as a dedicated step in the deployment
  pipeline. Manual DBA intervention MUST NOT be required for
  routine schema evolution.
- The project's migration framework (e.g., Alembic for
  SQLAlchemy) MUST be the single source of truth for schema
  state. Direct ALTER/CREATE statements applied outside the
  migration framework are prohibited.
- Migrations MUST be idempotent or guarded against
  re-execution so that repeated deploys are safe.
- Migrations MUST provide a documented rollback path (down
  migration or recovery procedure) unless the change is
  intentionally destructive AND approved by a lead developer
  in the PR review.
- Migrations MUST be tested against a representative dataset
  before merge; a passing migration on an empty database is
  not sufficient evidence.

**Rationale**: Schema drift between code and database is the
most common cause of production outages after a deploy.
Treating migrations as code — versioned, reviewed, and
auto-applied — keeps every environment reproducible and makes
rollbacks deterministic.

### X. Production Readiness

Every change merged to the main branch MUST be production-ready
and thoroughly tested. "Done" means deployable, not "compiles
and the happy path works."

- No work-in-progress, stubbed, mocked, hard-coded, or
  debug-only code may be merged. `TODO`/`FIXME` markers MUST
  reference a tracked issue.
- Tests MUST exercise the golden path, edge cases, and error
  conditions for the changed behavior — in addition to
  satisfying the 90% coverage gate from Principle III.
- New features MUST include observability appropriate to their
  surface area (structured logs for failures, metrics for
  user-visible operations) sufficient to diagnose production
  incidents without code changes.
- Configuration MUST support production environments. No
  hard-coded localhost URLs, developer credentials, dev-only
  feature flags, or environment-specific branches in code.
- Changes that affect runtime infrastructure (database,
  authentication, deployment topology, container images,
  background workers) MUST be validated end-to-end in a
  staging environment before merge.
- UI changes MUST be exercised against a real client target
  (e.g., a real browser for the web) running against the live
  backend before being declared complete; type-checks and unit
  tests do not verify feature correctness.

**Rationale**: A change that is "almost done" is a future
incident. Setting the merge bar at production-ready — not
"works on my machine" — keeps the main branch continuously
deployable and prevents stub code from rotting in place.

## Technology Stack

- **Backend**: Python (FastAPI or equivalent ASGI framework)
- **UI Delivery**: Server-driven UI (SDUI) delivered via
  FastAPI; UI primitives **defined** by the `astralprims`
  package; **rendered** by the orchestrator and **adapted**
  per device by the ROTE layer (web target → HTML/CSS/JS;
  future native targets additive via new orchestrator renderers)
- **Authentication**: Keycloak IAM
- **Agent Auth**: RFC 8693 token exchange with attenuated scopes
- **Database Migrations**: Automated migration framework
  (e.g., Alembic for SQLAlchemy) executed on deploy/startup
- **Containerization**: Docker / Docker Compose
- **License**: Apache 2.0

## Development Workflow

- All changes MUST go through pull requests.
- PRs MUST pass CI checks (linting, tests, coverage) before
  merge.
- PRs introducing new dependencies MUST include lead developer
  approval.
- PRs that modify the database schema MUST include the
  corresponding migration script and evidence that it ran
  successfully against a representative dataset.
- PRs that add or change UI primitives MUST do so within
  `astralprims` (definitions + serialization, documented). PRs
  that add or change how primitives are presented MUST do so in
  the orchestrator's render layer, with a renderer for each
  supported client target and per-device adaptation via ROTE.
- PRs MUST be production-ready before merge — reviewers MUST
  reject changes that contain stubs, debug-only code, missing
  observability for new features, or untested error paths.
- Constitution compliance MUST be verified during code review.
- Each PR MUST reference relevant spec/task IDs when
  applicable.

## Governance

This constitution is the highest-authority document governing
AstralBody development practices. It supersedes all other
guidance when conflicts arise.

- **Amendments**: Any change to this constitution MUST be
  proposed via PR, reviewed by at least one lead developer,
  and documented with rationale.
- **Versioning**: This document follows semantic versioning.
  MAJOR for principle removals/redefinitions, MINOR for new
  principles or material expansions, PATCH for clarifications
  and wording fixes.
- **Compliance**: All PRs and code reviews MUST verify
  adherence to these principles. Violations MUST be resolved
  before merge.

**Version**: 2.0.1 | **Ratified**: 2026-03-11 | **Last Amended**: 2026-05-29
