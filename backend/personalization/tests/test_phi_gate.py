"""Unit tests for the durable-memory PHI gate (feature 025, T008).

These exercise the pure-Python pre-filter and the fail-closed behavior
without loading Presidio/spaCy by injecting a fake analyzer.
"""
from __future__ import annotations

import pytest

from personalization.phi_gate import PHIGate


class _FakeAnalyzer:
    """Stand-in for Presidio's AnalyzerEngine."""

    def __init__(self, results=None, raises: bool = False):
        self._results = results or []
        self._raises = raises

    def analyze(self, text, language, entities, score_threshold):  # noqa: D401
        if self._raises:
            raise RuntimeError("analyzer boom")
        return list(self._results)


def _clean_gate() -> PHIGate:
    """Gate whose analyzer always reports no entities."""
    return PHIGate(analyzer=_FakeAnalyzer(results=[]))


@pytest.mark.parametrize(
    "text",
    [
        "Patient SSN is 123-45-6789",
        "email me at jane.doe@example.com",
        "call 555-123-4567",
        "DOB 1980-04-12",
        "born 4/12/1980",
        "MRN: 0099123",
        "medical record number 4456789",
        "account 12345678",
    ],
)
def test_prefilter_blocks_obvious_phi(text):
    """The fast-path regex blocks obvious identifiers without the analyzer."""
    gate = _clean_gate()  # analyzer returns nothing; pre-filter must catch it
    assert gate.contains_phi(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Prefers concise, bullet-point summaries",
        "Works as a clinical researcher",
        "Goal: track grant deadlines",
        "Likes dark mode and terse answers",
    ],
)
def test_clean_personalization_passes(text):
    """Non-PHI personalization text passes when the analyzer reports nothing."""
    gate = _clean_gate()
    assert gate.contains_phi(text) is False
    assert gate.filter_value(text) == text


def test_analyzer_detected_entity_blocks():
    """A name detected by the analyzer is treated as PHI."""
    gate = PHIGate(analyzer=_FakeAnalyzer(results=[object()]))
    # No pre-filter hit, but the analyzer flags an entity.
    assert gate.contains_phi("met with the new lead") is True
    assert gate.filter_value("met with the new lead") is None


def test_fail_closed_when_analyzer_unavailable():
    """If no analyzer is available, non-obvious text is blocked (fail-closed)."""
    gate = PHIGate(analyzer=None, build_if_missing=False)
    assert gate.available is False
    assert gate.contains_phi("just some preference text") is True


def test_fail_closed_when_analyzer_raises():
    """Analyzer errors fail closed."""
    gate = PHIGate(analyzer=_FakeAnalyzer(raises=True))
    assert gate.contains_phi("some non-obvious value") is True


def test_empty_is_clean():
    """Empty/whitespace/None is nothing to store, not PHI."""
    gate = PHIGate(analyzer=None, build_if_missing=False)
    assert gate.contains_phi("") is False
    assert gate.contains_phi("   ") is False
    assert gate.contains_phi(None) is False
