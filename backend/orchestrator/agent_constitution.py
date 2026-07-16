"""User Agent Constitution loader (feature 057).

Reads the baked ``backend/agent_constitution/agent_constitution.md`` asset at
runtime — the authoritative copy that the Analyze gate checks a drafted agent
against. Resolved ``__file__``-relative (mirrors the feature-040 skill-pack
loader; ``.specify/``/``specs/`` are not in the image). The constitution text is
NEVER hand-copied into a Python literal — that drifts (see ``mcp_tools_dev.py``).

Exposes:
- ``AGENT_CONSTITUTION_VERSION`` — the semver from the ``**Version**:`` header.
- ``load_checklist()`` — the A–L Analyze Gate Checklist items, parsed from the
  markdown, as an ordered list of ``ConstitutionPrinciple``.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List

_CONSTITUTION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "agent_constitution", "agent_constitution.md",
)

_VERSION_RE = re.compile(r"^\*\*Version\*\*:\s*(\S+)", re.MULTILINE)
_STRICT_SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_POSITIVE_INTEGER_RE = re.compile(r"^[1-9][0-9]*$")
# A checklist line: "- [ ] **A** — No self-authority: the spec requests ..."
_CHECK_RE = re.compile(r"^-\s*\[[ xX]\]\s*\*\*([A-Z])\*\*\s*[—-]\s*(.+)$")


@dataclass(frozen=True)
class ConstitutionPrinciple:
    """One A–L principle from the Analyze Gate Checklist."""

    letter: str          # "A".."L"
    title: str           # short lead phrase (before the first ':' or dash)
    text: str            # the full check description


@dataclass(frozen=True)
class UserAgentPolicyOutcome:
    """Non-sensitive result of one exact policy-marker startup check."""

    policy_revision: str
    marker_changed: bool
    agents_marked_for_revalidation: int

    def __post_init__(self) -> None:
        if not self.policy_revision or len(self.policy_revision) > 128:
            raise ValueError("policy revision is invalid")
        if not isinstance(self.marker_changed, bool):
            raise TypeError("marker_changed must be boolean")
        if (
            isinstance(self.agents_marked_for_revalidation, bool)
            or not isinstance(self.agents_marked_for_revalidation, int)
            or self.agents_marked_for_revalidation < 0
        ):
            raise ValueError("revalidation count must be non-negative")

    def public_fields(self) -> Dict[str, object]:
        """Return bounded aggregate fields suitable for logs/startup output."""

        return {
            "policy_revision": self.policy_revision,
            "marker_changed": self.marker_changed,
            "agents_marked_for_revalidation": (
                self.agents_marked_for_revalidation
            ),
        }


def _read_text() -> str:
    with open(_CONSTITUTION_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def _parse_version(text: str) -> str:
    m = _VERSION_RE.search(text)
    if not m:
        raise ValueError("agent constitution is missing a **Version** SemVer header")
    version = m.group(1)
    if _STRICT_SEMVER_RE.fullmatch(version) is None:
        raise ValueError("agent constitution version is not strict SemVer")
    return version


def load_version() -> str:
    """The agent-constitution semver (raises if the asset is malformed)."""
    return _parse_version(_read_text())


def load_checklist() -> List[ConstitutionPrinciple]:
    """The ordered A–L Analyze Gate Checklist items parsed from the markdown.

    Only lines inside the ``## Analyze Gate Checklist`` section are considered,
    so the Principles section's prose is not mistaken for checklist items.
    """
    text = _read_text()
    lines = text.splitlines()
    principles: List[ConstitutionPrinciple] = []
    in_checklist = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_checklist = stripped.lower().startswith("## analyze gate checklist")
            continue
        if not in_checklist:
            continue
        m = _CHECK_RE.match(stripped)
        if m:
            letter, body = m.group(1), m.group(2).strip()
            title = re.split(r"[:—-]", body, maxsplit=1)[0].strip()
            principles.append(ConstitutionPrinciple(letter=letter, title=title, text=body))
    if not principles:
        raise ValueError("agent constitution has no parseable Analyze Gate Checklist")
    return principles


def _build_user_agent_policy_revision(constitution_version: str) -> str:
    """Return the canonical combined Analyze policy marker or fail closed."""
    from orchestrator.agent_analyze import ANALYZE_POLICY_REVISION

    if _STRICT_SEMVER_RE.fullmatch(constitution_version) is None:
        raise RuntimeError("agent constitution policy version is not strict SemVer")
    if _POSITIVE_INTEGER_RE.fullmatch(ANALYZE_POLICY_REVISION) is None:
        raise RuntimeError("Analyze policy revision must be a positive integer")
    return (
        f"constitution={constitution_version};"
        f"analyze={ANALYZE_POLICY_REVISION}"
    )


#: Both values are resolved at import time. Missing/malformed policy inputs
#: raise and prevent startup rather than silently skipping revalidation.
AGENT_CONSTITUTION_VERSION: str = load_version()
USER_AGENT_POLICY_REVISION: str = _build_user_agent_policy_revision(
    AGENT_CONSTITUTION_VERSION
)
