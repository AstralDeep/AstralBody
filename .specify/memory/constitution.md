<!--
  Sync Impact Report
  ==================
  Version change: 1.0.0 → 2.0.0 (MAJOR — principle redefinition)

  Modified principles:
    II. Frontend Framework (Vite + React/TypeScript) →
        II. Frontend Client (Flutter SDUI Renderer)
    IV. Code Quality — removed TypeScript/ESLint rules,
        added Dart/Flutter lint rules
    VI. Documentation — removed TypeScript JSDoc requirement,
        added Dart doc-comment requirement
    VIII. User Experience — reframed around SDUI thin-client
          architecture; backend is sole layout authority

  Technology Stack changes:
    - Removed: Vite, React, TypeScript
    - Added: Flutter (Dart), Backend-Driven SDUI

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

### II. Frontend Client

The frontend MUST be built using Flutter (Dart) as a
device-agnostic thin client that renders Server-Driven UI
(SDUI) components produced by the backend.

- The Flutter client MUST act as a passive renderer: it
  receives SDUI component trees from the backend and renders
  them without embedding business logic or layout decisions.
- All UI layout composition and business logic MUST reside in
  the backend. The client MUST NOT make autonomous layout or
  navigation decisions.
- Flutter MUST target all required platforms (mobile, web,
  desktop) from a single codebase.
- No migration to another frontend framework without a
  constitution amendment.

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
- Dart code MUST pass Flutter/Dart analyzer rules with no
  errors or warnings. Linting MUST be enforced in CI via
  `dart analyze` or equivalent.
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
- Dart public members MUST have `///` doc comments following
  Effective Dart documentation guidelines.
- Backend APIs MUST expose interactive documentation at the
  `/docs` URL (e.g., via FastAPI's built-in Swagger UI).
- The SDUI component contract (JSON schema or equivalent) MUST
  be documented and versioned so the Flutter client and backend
  stay in sync.

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

### VIII. User Experience & SDUI Architecture

The backend MUST be the sole authority for UI composition.
The Flutter client MUST render backend-produced SDUI component
trees faithfully and consistently across all target platforms.

- The backend MUST define a finite set of SDUI primitive
  components (e.g., text, button, list, form, card, layout
  containers). New primitives MUST be approved and documented
  before use.
- The Flutter client MUST implement a renderer for every
  registered SDUI primitive. Unknown component types MUST
  degrade gracefully (e.g., render a placeholder or skip).
- The backend MAY dynamically compose screens, navigation
  flows, and layouts by assembling these primitives.
- The Flutter client MUST NOT contain hard-coded screens or
  page layouts; all screens MUST be driven by backend
  responses.

## Technology Stack

- **Backend**: Python (FastAPI or equivalent ASGI framework)
- **Frontend**: Flutter (Dart) — device-agnostic thin client
- **UI Architecture**: Server-Driven UI (SDUI); backend
  composes component trees, client renders them
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

**Version**: 2.0.0 | **Ratified**: 2026-03-11 | **Last Amended**: 2026-04-03
