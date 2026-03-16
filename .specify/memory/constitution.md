<!--
  Sync Impact Report
  ==================
  Version change: N/A → 1.0.0 (initial creation)

  Principles added:
    1. Primary Language (Python)
    2. Frontend Framework (Vite + React/TypeScript)
    3. Testing Standards (90% coverage, unit + integration)
    4. Code Quality (PEP 8, ESLint)
    5. Dependency Management (approval required)
    6. Documentation (docstrings, /docs endpoint)
    7. Security (Keycloak, RFC 8693 delegated tokens)
    8. User Experience (consistent UI, dynamic generation)

  Templates requiring updates:
    ✅ .specify/templates/plan-template.md — generic, compatible
    ✅ .specify/templates/spec-template.md — generic, compatible
    ✅ .specify/templates/tasks-template.md — generic, compatible
    ✅ No command templates found
    ✅ No runtime guidance docs require changes

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

## Technology Stack

- **Backend**: Python (FastAPI or equivalent ASGI framework)
- **Frontend**: Vite + React + TypeScript
- **Authentication**: Keycloak IAM
- **Agent Auth**: RFC 8693 token exchange with attenuated scopes
- **Containerization**: Docker / Docker Compose
- **License**: Apache 2.0

## Development Workflow

- All changes MUST go through pull requests.
- PRs MUST pass CI checks (linting, tests, coverage) before
  merge.
- PRs introducing new dependencies MUST include lead developer
  approval.
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

**Version**: 1.0.0 | **Ratified**: 2026-03-11 | **Last Amended**: 2026-03-11
