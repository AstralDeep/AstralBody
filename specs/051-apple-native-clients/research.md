# Research: Native Apple Clients (051)

## D1 — Watch sign-in: backend-brokered RFC 8628 vs. alternatives

**Decision**: Backend brokers the OAuth 2.0 Device Authorization Grant. Watch calls
`/api/auth/device/start|poll|refresh`; only the backend talks to Keycloak.

**Rationale**: (a) Spec/clarification requires the QR be *backend-generated*; (b) the watch
stays dumb — no IdP discovery, no grant plumbing, one TLS peer; (c) centralizes audit,
rate-limiting, and role gating (roleless accounts refused + grant revoked, matching the web
callback posture); (d) session/revocation semantics stay IdP-native (Constitution VII).

**Alternatives rejected**: Watch→Keycloak direct device grant (loses backend QR generation,
audit, and role gate before token release); custom one-time-code approval protocol (bespoke
auth surface, re-derives what RFC 8628 already standardizes); watchOS keychain sharing from a
paired iPhone (fails the "any other device" requirement and standalone-watch case).

## D2 — QR generation: first-party stdlib encoder

**Decision**: `backend/shared/qr.py` — QR Model 2, byte mode, ECC level M, versions 1–10,
fixed mask with standard format strings, PNG output via `zlib`/`struct` (plus raw matrix for
clients that want native rendering).

**Rationale**: Constitution V forbids new runtime deps; `qrcode`/`segno` would be new. Payload
is small (verification URI ≈ 60–120 chars → version 4–6 @ M). Correctness pinned by
known-answer tests whose matrices were cross-verified against a reference encoder on the dev
machine (never imported in repo code), plus structural invariants (size, finder/timing
patterns, format info) that run in CI.

**Alternatives rejected**: `qrcode` pip dep (Constitution V); client-side-only rendering
(violates the clarified "backend-generated" requirement; server still returns the raw matrix
so the watch MAY re-render crisply).

## D3 — Client identities

**Decision**: Three public clients — `astral-ios`, `astral-macos`, `astral-watch` — appended
to `KEYCLOAK_ALLOWED_AZP`; device grant enabled only on `astral-watch`.

**Rationale**: Follows `astral-desktop`/`astral-mobile` per-form-factor precedent; keeps
revocation-queue `client_id` attribution and audit exact; limits the device-grant surface to
the one client that needs it.

**Alternatives rejected**: One shared `astral-apple` id (blurs audit/revocation attribution);
reusing `astral-mobile` on iOS (couples two platforms' token policies).

## D4 — Spoken rendition: additive `speech` field, server-side, watch-profile sockets only

**Decision**: When the delivery socket's ROTE profile is `watch`, the orchestrator attaches
`speech: {"ssml": …, "text": …}` to `ui_render`/`ui_upsert` frames — produced by the existing
`webrender` `voice` render target from the *same adapted components* the watch displays.
Vocabulary (frame/component type lists) is unchanged, so `ui_protocol.json` needs no vocab
delta; the field is documented in [contracts/spoken-rendition.md](contracts/spoken-rendition.md).

**Rationale**: Reuses the registered voice target (bounded, tested); zero backend deps; other
clients are untouched (additive field, ignored elsewhere); the watch speaks via
`AVSpeechUtterance(ssmlRepresentation:)` (watchOS 9+) with the `text` fallback.

**Alternatives rejected**: Server-side audio synthesis (new deps, audio streaming — rejected in
clarifications); client-side text extraction from components (duplicates voice.py per client,
drifts).

## D5 — Swift packaging & project generation

**Decision**: One SPM package `AstralCore` (all protocol/transport/auth/model logic +
XCTest, headlessly testable) consumed by three thin app targets. Canonical project setup is
manual Xcode target creation (documented step-by-step in README); a `project.yml` is provided
as an optional XcodeGen convenience for the dev machine only — never required by CI or
runtime.

**Rationale**: Keeps the zero-third-party posture intact where it matters; `swift test` on a
macOS runner covers the drift guard and core logic without any project file.

**Alternatives rejected**: Committing hand-written `.xcodeproj` (merge-hostile, error-prone to
author blind); making XcodeGen mandatory (new required tool).

## D6 — CI

**Decision**: New `.github/workflows/apple-ci.yml` on `macos-14`: `swift test` for AstralCore
(includes the manifest drift guard). App-target build jobs land once the Xcode project exists
on the runner path (task-tracked, not blocking).

**Rationale**: Mirrors how `android-ci.yml` was introduced in 041 (own workflow, additive);
existing gates untouched (Constitution XI).

## D7 — Native session semantics / 365-day anchor mapping

**Decision**: Apple clients hold Keycloak tokens directly (like Windows/Android). The
interactive-anchor guarantee maps to realm policy (SSO Session Max / client session max =
operator's 365-day setting) — approval of a device grant is an interactive login; silent
refresh cannot outlive the realm cap. Watch refresh is proxied via `/api/auth/device/refresh`
so the watch keeps a single TLS peer; iOS/macOS refresh directly against the token endpoint as
Windows does.

**Rationale**: Matches 016/028 semantics without inventing native session rows; realm settings
doc gains the explicit knobs.
