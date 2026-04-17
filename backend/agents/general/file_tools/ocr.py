"""PDF page rasterization for the vision-fallback path.

This module used to wrap Tesseract OCR. The feature was simplified so that
PDFs without extractable text are handed directly to the connected vision
model instead of going through OCR first. The module name is kept for import
stability; only the rasterization + base64 helpers remain.
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger("FileTools.PDFImages")


def rasterize_pdf(pdf_path: Path, *, dpi: int = 200, max_pages: int = 50) -> List["Image.Image"]:  # type: ignore[name-defined]
    """Return one PIL.Image per page (capped at *max_pages*).

    Raises :class:`RuntimeError` if poppler / pdf2image are unavailable.
    """
    try:
        from pdf2image import convert_from_path  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"pdf2image unavailable: {exc}")
    images = convert_from_path(str(pdf_path), dpi=dpi, last_page=max_pages)
    return list(images)


def encode_images_for_vision(images: List["Image.Image"], *, fmt: str = "PNG") -> List[dict]:  # type: ignore[name-defined]
    """Base64-encode each image for delivery to a vision model.

    Returns ``[{"content_type": "image/png", "image_base64": "..."}]``.
    """
    out: List[dict] = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        out.append({
            "content_type": f"image/{fmt.lower()}",
            "image_base64": base64.b64encode(buf.getvalue()).decode(),
        })
    return out


def pdf_to_vision_images(pdf_path: Path) -> List[dict]:
    """Rasterize *pdf_path* and return base64-encoded page images.

    Returns an empty list if rasterization fails (e.g., poppler missing). The
    caller decides how to surface that to the user.
    """
    try:
        images = rasterize_pdf(pdf_path)
    except RuntimeError as exc:
        logger.warning(f"PDF rasterization failed: {exc}")
        return []
    return encode_images_for_vision(images)


__all__ = [
    "encode_images_for_vision",
    "pdf_to_vision_images",
    "rasterize_pdf",
]
