"""Server-side content-type allow-list and sniffing helpers.

Mirrors the client-side allow-list in
``frontend/src/lib/attachmentTypes.ts``. The two MUST stay in sync.

Per FR-001/FR-008 the system rejects:
  * extensions that are not in :data:`ACCEPTED_EXTENSIONS`, and
  * uploads where the sniffed content type is inconsistent with the extension.

Feature: 002-file-uploads.
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

# Optional dep: python-magic / python-magic-bin. Imported lazily so unit tests
# that don't exercise sniffing don't need the libmagic binary present.
try:  # pragma: no cover - import guard
    import magic  # type: ignore
    _HAS_MAGIC = True
except Exception:  # pragma: no cover
    magic = None  # type: ignore
    _HAS_MAGIC = False


AttachmentCategory = str  # one of: document, spreadsheet, presentation, text, image


ACCEPTED_EXTENSIONS: Dict[str, AttachmentCategory] = {
    # Documents
    "pdf": "document",
    "docx": "document",
    "doc": "document",
    "rtf": "document",
    "odt": "document",
    # Spreadsheets
    "xlsx": "spreadsheet",
    "xls": "spreadsheet",
    "ods": "spreadsheet",
    "tsv": "spreadsheet",
    "csv": "spreadsheet",
    # Presentations
    "pptx": "presentation",
    "ppt": "presentation",
    "odp": "presentation",
    # Structured text & config
    "txt": "text",
    "md": "text",
    "json": "text",
    "yaml": "text",
    "yml": "text",
    "xml": "text",
    "html": "text",
    "htm": "text",
    "log": "text",
    # Code
    "py": "text",
    "js": "text",
    "ts": "text",
    "tsx": "text",
    "jsx": "text",
    "sql": "text",
    "sh": "text",
    "ps1": "text",
    "css": "text",
    # Images
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "webp": "image",
}


# Content-type families that are "compatible" with each declared extension.
# We deliberately accept generic text/* for anything in the text category and
# accept octet-stream for office formats that libmagic sometimes misidentifies.
_EXTENSION_TO_MIME_PREFIXES: Dict[str, Tuple[str, ...]] = {
    "pdf": ("application/pdf",),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",  # docx is a zip; libmagic may return zip
        "application/octet-stream",
    ),
    "doc": ("application/msword", "application/x-ole-storage", "application/octet-stream"),
    "rtf": ("application/rtf", "text/rtf", "text/plain"),
    "odt": ("application/vnd.oasis.opendocument.text", "application/zip", "application/octet-stream"),
    "xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
    ),
    "xls": ("application/vnd.ms-excel", "application/x-ole-storage", "application/octet-stream"),
    "ods": ("application/vnd.oasis.opendocument.spreadsheet", "application/zip", "application/octet-stream"),
    "tsv": ("text/", "application/octet-stream"),
    "csv": ("text/", "application/csv", "application/octet-stream"),
    "pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
        "application/octet-stream",
    ),
    "ppt": ("application/vnd.ms-powerpoint", "application/x-ole-storage", "application/octet-stream"),
    "odp": ("application/vnd.oasis.opendocument.presentation", "application/zip", "application/octet-stream"),
    # text & code: any text/* family is fine
    "txt": ("text/",), "md": ("text/",), "json": ("text/", "application/json"),
    "yaml": ("text/",), "yml": ("text/",),
    "xml": ("text/", "application/xml"),
    "html": ("text/",), "htm": ("text/",), "log": ("text/",),
    "py": ("text/",), "js": ("text/", "application/javascript"),
    "ts": ("text/", "application/typescript"),
    "tsx": ("text/",), "jsx": ("text/",),
    "sql": ("text/",), "sh": ("text/",), "ps1": ("text/",), "css": ("text/",),
    # Images
    "png": ("image/png",),
    "jpg": ("image/jpeg",), "jpeg": ("image/jpeg",),
    "gif": ("image/gif",),
    "webp": ("image/webp",),
}


# Legacy binary office formats: surfaced at upload time with an actionable error
# rather than relying on the parser to fail. (See research.md §2.)
LEGACY_BINARY_FORMATS = frozenset({"doc", "ppt"})


def normalise_extension(filename: str) -> str:
    """Return the lower-cased extension for *filename*, no leading dot."""
    _, ext = os.path.splitext(filename)
    return ext[1:].lower() if ext else ""


def category_for_extension(extension: str) -> Optional[AttachmentCategory]:
    """Return the category for *extension*, or ``None`` if unsupported."""
    return ACCEPTED_EXTENSIONS.get(extension.lower())


def sniff_content_type(blob_path_or_bytes) -> str:
    """Sniff the MIME content type via libmagic, falling back to ``"application/octet-stream"``.

    Accepts either a filesystem path (``str``/``os.PathLike``) or a small
    ``bytes`` buffer. Returns ``"application/octet-stream"`` if libmagic is
    unavailable on this host (e.g., bare unit-test environments without the
    system package installed).
    """
    if not _HAS_MAGIC:
        return "application/octet-stream"
    try:
        if isinstance(blob_path_or_bytes, (bytes, bytearray)):
            return magic.from_buffer(bytes(blob_path_or_bytes), mime=True)
        return magic.from_file(str(blob_path_or_bytes), mime=True)
    except Exception:  # pragma: no cover - libmagic edge cases
        return "application/octet-stream"


def is_consistent(extension: str, sniffed_mime: str) -> bool:
    """Return True iff *sniffed_mime* is plausible for *extension*.

    Used by the upload endpoint to enforce FR-008 (extension/content-type
    consistency). The check is deliberately permissive — false rejections are
    worse than false acceptances at this gate, because the parser tools will
    still surface a structured error if they can't actually read the file.
    """
    extension = extension.lower()
    if not sniffed_mime:
        return True
    prefixes = _EXTENSION_TO_MIME_PREFIXES.get(extension)
    if not prefixes:
        return False
    sniffed_lower = sniffed_mime.lower()
    return any(sniffed_lower.startswith(p) for p in prefixes)


__all__ = [
    "ACCEPTED_EXTENSIONS",
    "AttachmentCategory",
    "LEGACY_BINARY_FORMATS",
    "category_for_extension",
    "is_consistent",
    "normalise_extension",
    "sniff_content_type",
]
