<!--
  Sync Impact Report
  ==================
  Version change: 1.0.0 → 1.1.0 (MINOR — two new principles added)

  Principles added:
    IX.  Database Migrations (auto-running migration scripts for any schema change)
    X.   Production Readiness (all merged changes must be production-ready & thoroughly tested)

  Principles modified: None
  Principles removed:  None

  Sections updated:
    - Technology Stack: added Database Migrations entry
    - Development Workflow: added migration-script and production-readiness gates
    - Governance footer: Last Amended date bumped to 2026-05-01

  Templates requiring updates:
    ✅ .specify/templates/plan-template.md — generic Constitution Check gate, compatible
    ✅ .specify/templates/spec-template.md — generic, compatible
    ✅ .specify/templates/tasks-template.md — already includes migrations task slot (T004)
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

### II. Frontend Framework

The frontend MUST be built using Vite with React and
TypeScript.

- All frontend source files MUST use TypeScript (`.ts`/`.tsx`),
  not plain JavaScript.
- Vite MUST remain the build tool; no migration to other
  bundlers without a constitution amendment.

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
- TypeScript code MUST pass standard ESLint rules. Linting
  MUST be enforced in CI.
- No linting exceptions without inline justification comments.

### V. Dependency Management

No new third-party library may be added without explicit
approval from a lead developer.

- Proposed dependencies MUST be documented in the PR
  description with rationale.
- Lead developer approval MUST be recorded in the PR review.
- Transitive dependency impact MUST be considered.

### VI. Documentation

All public APIs and complex functions MUST be documented.

- Python functions MUST have docstrings following Google or
  NumPy style.
- TypeScript exports MUST have JSDoc comments.
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

- The frontend MUST use the predefined set of primitive
  components for all UI rendering.
- The backend MAY dynamically generate frontend layouts by
  composing these primitive components.
- New primitive components MUST be approved and documented
  before use.

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
- UI/frontend changes MUST be exercised in a real browser
  against the running backend before being declared complete;
  type-checks and unit tests do not verify feature
  correctness.

**Rationale**: A change that is "almost done" is a future
incident. Setting the merge bar at production-ready — not
"works on my machine" — keeps the main branch continuously
deployable and prevents stub code from rotting in place.

## Technology Stack

- **Backend**: Python (FastAPI or equivalent ASGI framework)
- **Frontend**: Vite + React + TypeScript
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

**Version**: 1.1.0 | **Ratified**: 2026-03-11 | **Last Amended**: 2026-05-01
