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


AttachmentCategory = str  # one of: document, spreadsheet, presentation, text, image, medical


# Compound suffixes we recognize as a single logical extension. Order matters
# only within this tuple: ``normalise_extension`` checks these *before* the
# usual last-dot split, so ``report.nii.gz`` → ``"nii.gz"`` and not ``"gz"``.
_COMPOUND_EXTENSIONS: Tuple[str, ...] = (
    "nii.gz",
    "ome.tif",
    "ome.tiff",
)


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
    # Medical imaging (feature: medical-file-uploads)
    "dcm": "medical",
    "dicom": "medical",
    "nii": "medical",
    "nii.gz": "medical",
    "czi": "medical",
    "nrrd": "medical",
    "mha": "medical",
    "mhd": "medical",
    "raw": "medical",  # MetaImage (.mhd) sidecar; accepted alongside .mhd
    "ome.tif": "medical",
    "ome.tiff": "medical",
    "tif": "medical",
    "tiff": "medical",
    "svs": "medical",
    "ndpi": "medical",
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
    # Medical formats. Most lack a registered MIME; libmagic commonly returns
    # ``application/octet-stream`` for them, with an occasional ``image/tiff``
    # for SVS/NDPI/OME-TIFF (which are TIFF-based). Be permissive — the reader
    # tool will surface a structured parse error if the file is truly broken.
    "dcm": ("application/dicom", "application/octet-stream"),
    "dicom": ("application/dicom", "application/octet-stream"),
    "nii": ("application/octet-stream",),
    "nii.gz": ("application/gzip", "application/x-gzip", "application/octet-stream"),
    "czi": ("application/octet-stream",),
    "nrrd": ("application/octet-stream", "text/plain"),  # NRRD header is ASCII
    "mha": ("application/octet-stream", "text/plain"),  # MetaImage header is ASCII
    "mhd": ("application/octet-stream", "text/plain"),
    "raw": ("application/octet-stream",),
    "ome.tif": ("image/tiff", "application/octet-stream"),
    "ome.tiff": ("image/tiff", "application/octet-stream"),
    "tif": ("image/tiff", "application/octet-stream"),
    "tiff": ("image/tiff", "application/octet-stream"),
    "svs": ("image/tiff", "application/octet-stream"),
    "ndpi": ("image/tiff", "application/octet-stream"),
}


# Legacy binary office formats: surfaced at upload time with an actionable error
# rather than relying on the parser to fail. (See research.md §2.)
LEGACY_BINARY_FORMATS = frozenset({"doc", "ppt"})


# Per-category upload size caps. Medical imaging files routinely exceed the
# 30 MB cap that's fine for docs/images — whole-slide SVS/NDPI and multi-series
# CZI files can run into several GB. Keep the existing categories at 30 MB and
# open up "medical" to 2 GiB.
_MB = 1024 * 1024
_GB = 1024 * _MB

MAX_BYTES_BY_CATEGORY: Dict[AttachmentCategory, int] = {
    "document": 30 * _MB,
    "spreadsheet": 30 * _MB,
    "presentation": 30 * _MB,
    "text": 30 * _MB,
    "image": 30 * _MB,
    "medical": 2 * _GB,
}


def normalise_extension(filename: str) -> str:
    """Return the lower-cased extension for *filename*, no leading dot.

    Recognizes the compound suffixes listed in :data:`_COMPOUND_EXTENSIONS`
    (e.g. ``.nii.gz``, ``.ome.tif``) as single logical extensions; otherwise
    falls back to the usual last-dot split.
    """
    lower = filename.lower()
    for compound in _COMPOUND_EXTENSIONS:
        if lower.endswith("." + compound):
            return compound
    _, ext = os.path.splitext(lower)
    return ext[1:] if ext else ""


def category_for_extension(extension: str) -> Optional[AttachmentCategory]:
    """Return the category for *extension*, or ``None`` if unsupported."""
    return ACCEPTED_EXTENSIONS.get(extension.lower())


def max_bytes_for_category(category: AttachmentCategory) -> int:
    """Return the upload-size cap for *category*.

    Unknown categories fall back to the strictest (smallest) known cap so a
    misconfiguration never silently widens the upload ceiling.
    """
    cap = MAX_BYTES_BY_CATEGORY.get(category)
    if cap is None:
        return min(MAX_BYTES_BY_CATEGORY.values())
    return cap


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
    "MAX_BYTES_BY_CATEGORY",
    "category_for_extension",
    "is_consistent",
    "max_bytes_for_category",
    "normalise_extension",
    "sniff_content_type",
]
