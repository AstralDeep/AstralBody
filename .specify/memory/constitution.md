<!--
Sync Impact Report
==================
Version change: (template) → 1.0.0
Modified principles: None (all newly defined)
Added sections:
  - Core Principles: Visual Parity, Logic Mirror, API Integrity, Asset, Execution Protocol
  - Project Context & Constraints
  - Architecture & State Management
Removed sections: None
Templates requiring updates:
  - .specify/templates/plan-template.md: Constitution Check references constitution file (✅ aligned)
  - .specify/templates/spec-template.md: No direct references (✅ aligned)
  - .specify/templates/tasks-template.md: No direct references (✅ aligned)
Follow-up TODOs:
  - RATIFICATION_DATE: Original adoption date unknown; set to first commit date of migration effort
-->
# AstralBody Migration Constitution

## Core Principles

### I. Visual Parity Law

If a UI element has specific styling (border-radius, colors, spacing, shadows) in the React implementation, the Flutter widget MUST replicate those properties exactly. Use Flutter's BoxDecoration, TextStyle, and Padding/EdgeInsets to match CSS values pixel-perfect.

### II. Logic Mirror Law

Business logic, validation rules, and state transitions MUST be identical between React and Flutter. Copy validation regex patterns, conditional logic, and error handling verbatim from the source React components.

### III. API Integrity Law

API endpoints, request/response schemas, headers, and authentication tokens MUST match exactly what the React app sends. Inspect React network calls or service files; do not assume backend flexibility. Use the same HTTP client configuration (Dio/http) with identical interceptors.

### IV. Asset Law

All static assets (images, icons, fonts) MUST be copied from `frontend/public` or `frontend/src/assets` to `flutter/assets` and registered in `pubspec.yaml`. Preserve directory structure and naming.

### V. Execution Protocol

Follow the four‑step migration sequence for every feature: 1. **Analyze** the React component and its CSS/Tailwind. 2. **Map** React elements to equivalent Flutter widgets. 3. **Implement** in `flutter/lib/` with proper separation of concerns (UI, Model, Controller). 4. **Verify** payloads against backend API expectations.

## Project Context & Constraints

- **Source of Truth**: The `frontend/` directory contains the current React implementation, defining expected behavior, styling, and API interactions.
- **Target Directory**: All new Flutter code MUST be generated within the `flutter/` directory.
- **Immutable Backend**: The `backend/` directory is strictly READ‑ONLY. Do not modify backend logic, API routes, or database schemas.
- **Styling Standard**: Replicate CSS styling (Flexbox/Grid layouts, colors, fonts, spacing, shadows) using Flutter Widgets.

## Architecture & State Management

- **State Management**: Use Riverpod or Provider to replicate React's `useState`/`useContext` or Redux/Zustand logic.
- **Navigation**: Implement a robust routing solution (GoRouter) that mirrors React Router paths (`/dashboard`, `/login`, `/settings`).
- **Networking**: Use Dio or `http` for API calls. Create a dedicated API service layer mirroring the structure of React Axios/Fetch services.
- **Separation of Concerns**: Organize code into `lib/ui/`, `lib/models/`, `lib/services/`, `lib/controllers/` (or equivalent).

## Governance

This constitution supersedes all other practices for the migration effort. Amendments require:
1. Documentation of the change rationale.
2. Approval via the project's designated governance process.
3. A migration plan for any affected components.

All PRs and code reviews MUST verify compliance with these principles. Complexity must be justified with reference to the source React implementation. Use `.specify/memory/constitution.md` for runtime development guidance.

**Version**: 1.0.0 | **Ratified**: TODO(RATIFICATION_DATE): Original adoption date unknown; set to first commit date of migration effort | **Last Amended**: 2026-02-27
