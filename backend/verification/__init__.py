"""Feature 032 — Agentic File-Upload SDUI & Delegated-Authority Verification.

An autonomous, closed-loop verification *harness* that drives the existing
AstralDeep upload -> parse -> server-driven-UI -> delegated-authority -> audit
pipeline and proves three differentiating properties across four personas:

1. **Tangible UI** — file-upload queries yield interactive, file-derived,
   persisted, re-executable server-driven components (not prose).
2. **Delegated authority** — every interaction runs on behalf of the user under
   scoped delegation, with cross-user isolation, admin-only parser approval, and
   an unbroken tamper-evident audit chain.
3. **Backend-only UI** — every component is from the backend's published
   vocabulary, arrives as server-produced markup, and the client only injects
   output and forwards actions.

The harness is *agentic in structure and judgment but deterministic in its
verdict gate*: pass/fail/uncertain rests on structural + authority assertions
that need no model call. It runs in-process (scripted LLM via the client-factory
seam, the CI merge gate) and as an opt-in external client (real Keycloak).

This package adds NO product behaviour and NO new runtime dependency
(Constitution V, FR-032). It is an observer and driver, not a modification of the
system under test.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
