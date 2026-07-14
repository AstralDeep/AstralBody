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
from typing import List, Optional

_CONSTITUTION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "agent_constitution", "agent_constitution.md",
)

_VERSION_RE = re.compile(r"\*\*Version\*\*:\s*(\d+\.\d+\.\d+)")
# A checklist line: "- [ ] **A** — No self-authority: the spec requests ..."
_CHECK_RE = re.compile(r"^-\s*\[[ xX]\]\s*\*\*([A-Z])\*\*\s*[—-]\s*(.+)$")


@dataclass(frozen=True)
class ConstitutionPrinciple:
    """One A–L principle from the Analyze Gate Checklist."""

    letter: str          # "A".."L"
    title: str           # short lead phrase (before the first ':' or dash)
    text: str            # the full check description


def _read_text() -> str:
    with open(_CONSTITUTION_PATH, "r", encoding="utf-8") as fh:
        return fh.read()


def _parse_version(text: str) -> str:
    m = _VERSION_RE.search(text)
    if not m:
        raise ValueError("agent constitution is missing a **Version**: x.y.z header")
    return m.group(1)


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
            title = re.split(r"[:—-]", body, 1)[0].strip()
            principles.append(ConstitutionPrinciple(letter=letter, title=title, text=body))
    if not principles:
        raise ValueError("agent constitution has no parseable Analyze Gate Checklist")
    return principles


def _safe_version() -> Optional[str]:
    try:
        return load_version()
    except Exception:  # pragma: no cover — surfaced via AGENT_CONSTITUTION_VERSION default
        return None


#: The current agent-constitution version, resolved at import time. ``None`` only
#: if the asset is missing/malformed (callers treat that as fail-closed).
AGENT_CONSTITUTION_VERSION: Optional[str] = _safe_version()
