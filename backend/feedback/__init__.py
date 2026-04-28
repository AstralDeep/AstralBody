"""Component feedback & tool-improvement loop (feature 004).

User-facing feedback capture, per-tool quality computation, and admin-
reviewed knowledge-update proposals that feed the existing knowledge
synthesizer. See :mod:`backend/feedback/recorder` for the public submit
API and :mod:`backend/feedback/api` for the REST + WS surfaces.

Design notes:

* Per-user isolation mirrors the audit log substrate from feature 003 —
  every repository method takes ``actor_user_id`` and applies it to the
  query unconditionally. Cross-user reads are 404-indistinguishable from
  not-found.
* Free-text comments are untrusted user input. Two screening passes (an
  inline heuristic at submit time and an LLM pre-pass inside the
  synthesizer) jointly guarantee that no record's text reaches an LLM
  context as instructions.
* Tool source code is never modified by automated processes. Knowledge
  updates target the synthesizer's existing ``backend/knowledge/``
  artifacts, gated by admin acceptance.
"""

from .schemas import (  # noqa: F401
    Sentiment,
    Category,
    Lifecycle,
    CommentSafety,
    QualityStatus,
    ProposalStatus,
    QuarantineDetector,
    QuarantineStatus,
    ComponentFeedbackDTO,
    FeedbackSubmitRequest,
    FeedbackSubmitAck,
    FeedbackAmendRequest,
    ToolQualitySignalDTO,
    KnowledgeUpdateProposalDTO,
    QuarantineEntryDTO,
)
