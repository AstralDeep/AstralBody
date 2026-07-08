# Specification Quality Checklist: Native Apple Clients (iOS, macOS, watchOS SDUI Targets)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-07-06
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details beyond the platform/contract facts the feature is defined by
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain (four open questions resolved in Clarifications,
      Session 2026-07-06)
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (bounds, counts, and time budgets)
- [x] All acceptance scenarios are defined (Given/When/Then per story)
- [x] Edge cases are identified (sign-in code lifecycle, degraded delivery, mixed-profile
      fanout, forward compatibility)
- [x] Scope is clearly bounded (explicit out-of-scope list in Assumptions)
- [x] Dependencies and assumptions identified (IdP device-grant capability, client ids,
      minimum OS versions, CI runners)

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows (each of the six stories independently testable;
      iOS alone is a viable MVP)
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] Constitution touchpoints honored in-spec: II/XII (single SDUI contract + manifest),
      V (zero new deps, toolchain approval recorded), VII (IdP-native auth posture),
      IX (no schema change anticipated; guarded migration if needed), XI (additive CI gate)

## Notes

- Server-side head starts intentionally reused, not rebuilt: `watch` ROTE profile, `voice`
  spoken-rendition render target, per-socket fanout adaptation, `POST /api/auth/logout`
  client-id revocation, 041 named-profile pattern.
- Plan-time verifications called out in Assumptions: realm device-grant enablement, final
  client id naming, macOS CI runner selection.
