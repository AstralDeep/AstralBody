"""Parser coverage map — does *some* tool know how to read this file type?

Feature 031-attachment-upload-parsing. Single source of truth for the question
"is this attachment type parseable today?", answered from two layers:

1. **Built-in** parsers shipped by the general agent (feature 002): the
   per-category ``read_*`` tools.
2. **Globally-promoted** auto-created parsers (US2): a ``live`` row in the
   ``attachment_parser`` registry table, available to every user once an
   administrator approves it.

A category/extension that neither layer covers is what eagerly triggers the
safe auto-parser-creation lifecycle (see contracts/parser-autocreate.md).
"""

from __future__ import annotations

import hashlib
from typing import Optional, TypedDict

# Built-in category → reader tool (mirrors the general agent's file-tool
# registry; feature 002). ``medical`` is covered by the suite of medical tools
# (read_dicom/read_nifti/…) — any one of them counts as coverage here.
BUILTIN_CATEGORY_TOOL = {
    "document": "read_document",
    "spreadsheet": "read_spreadsheet",
    "presentation": "read_presentation",
    "text": "read_text",
    "image": "read_image",
    "medical": "read_dicom",
}


class Coverage(TypedDict):
    covered: bool
    tool: Optional[str]
    source: Optional[str]  # "builtin" | "global" | None


def gap_fingerprint(category: str, extension: Optional[str]) -> str:
    """Stable, format-scoped dedup key for an auto-parser gap.

    Format-scoped (NOT chat-scoped) so the same unreadable type never spawns a
    second draft while one is pending/live (FR-018).
    """
    ext = (extension or "").lower().strip()
    cat = (category or "").lower().strip()
    digest = hashlib.sha256(f"attachment_parser:{cat}:{ext}".encode()).hexdigest()
    return digest[:32]


def builtin_tool_for(category: str) -> Optional[str]:
    """Return the built-in reader tool for *category*, or ``None``."""
    return BUILTIN_CATEGORY_TOOL.get((category or "").lower())


def coverage(
    extension: Optional[str],
    category: str,
    *,
    parser_repo=None,
) -> Coverage:
    """Resolve whether *extension*/*category* can be read today.

    ``parser_repo`` is an optional :class:`AttachmentParserRepository`; when
    provided, a ``live`` registry row for this format is treated as global
    coverage. When omitted, only built-in coverage is considered.
    """
    builtin = builtin_tool_for(category)
    if builtin is not None:
        return {"covered": True, "tool": builtin, "source": "builtin"}
    if parser_repo is not None:
        fp = gap_fingerprint(category, extension)
        row = parser_repo.get_by_gap(fp)
        if row and row.get("status") == "live" and row.get("tool_name"):
            return {"covered": True, "tool": row["tool_name"], "source": "global"}
    return {"covered": False, "tool": None, "source": None}


def is_covered(extension: Optional[str], category: str, *, parser_repo=None) -> bool:
    """True iff a built-in or globally-promoted parser can read this type."""
    return coverage(extension, category, parser_repo=parser_repo)["covered"]


def covering_tool(extension: Optional[str], category: str, *, parser_repo=None) -> Optional[str]:
    """Return the tool name that can read this type, or ``None`` if uncovered."""
    return coverage(extension, category, parser_repo=parser_repo)["tool"]


__all__ = [
    "BUILTIN_CATEGORY_TOOL",
    "Coverage",
    "builtin_tool_for",
    "covering_tool",
    "coverage",
    "gap_fingerprint",
    "is_covered",
]
