"""Feature 051 — spoken rendition for watch-profile sockets (FR-030/FR-031).

The watch shows ROTE-adapted components AND hears the same content: for every
component-bearing delivery to a socket whose profile is ``watch``, the
orchestrator attaches ``speech = {"ssml", "text"}`` produced by the existing
``webrender`` voice render target from the *same adapted components* the frame
carries — screen and speech can never diverge. Other profiles get no field at
all (additive contract: specs/051-apple-native-clients/contracts/
spoken-rendition.md).

The client speaks ``ssml`` via ``AVSpeechUtterance(ssmlRepresentation:)`` and
falls back to ``text`` (tag-stripped, entity-unescaped). Absent field ⇒ silent
delivery; the client never synthesizes speech from components on its own.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("orchestrator.watch_speech")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def build_speech(components: Optional[List[Any]]) -> Optional[Dict[str, str]]:
    """Spoken rendition of ``components`` via the voice render target, or
    ``None`` when there is nothing speakable (fail-open: a speech failure
    must never block the visual delivery)."""
    comps = [c for c in (components or []) if isinstance(c, dict)]
    if not comps:
        return None
    try:
        from webrender.voice import render_voice
        ssml = render_voice(comps)
    except Exception:
        logger.exception("watch_speech: voice rendition failed (delivery stays visual-only)")
        return None
    text = html.unescape(_WS_RE.sub(" ", _TAG_RE.sub(" ", ssml or ""))).strip()
    if not text:
        return None
    return {"ssml": ssml, "text": text}


def speech_for_profile(profile: Any, components: Optional[List[Any]]) -> Optional[Dict[str, str]]:
    """``build_speech`` gated to watch-profile sockets only."""
    try:
        from rote.capabilities import DeviceType
        if profile is None or getattr(profile, "device_type", None) != DeviceType.WATCH:
            return None
    except Exception:
        return None
    return build_speech(components)
