"""Tests for the shared perf_span timing helper (feature 052, T001)."""

import logging
import re

import pytest

from shared.perf import perf_span


def test_perf_span_emits_structured_line(caplog):
    """A completed span logs `perf <name> duration_ms=<int>` plus context pairs."""
    with caplog.at_level(logging.INFO, logger="astral.perf"):
        with perf_span("surface.render.agents", surface="agents", user="u1"):
            pass
    line = caplog.records[-1].getMessage()
    assert re.fullmatch(
        r"perf surface\.render\.agents duration_ms=\d+ surface=agents user=u1", line
    )


def test_perf_span_duration_reflects_elapsed_time(caplog):
    """The logged duration is a plausible millisecond integer for the block."""
    with caplog.at_level(logging.INFO, logger="astral.perf"):
        with perf_span("t"):
            pass
    match = re.search(r"duration_ms=(\d+)", caplog.records[-1].getMessage())
    assert match is not None
    assert 0 <= int(match.group(1)) < 10_000


def test_perf_span_logs_even_when_block_raises(caplog):
    """The span logs on exception and the exception still propagates."""
    with caplog.at_level(logging.INFO, logger="astral.perf"):
        with pytest.raises(ValueError):
            with perf_span("boom", chat="c9"):
                raise ValueError("x")
    line = caplog.records[-1].getMessage()
    assert line.startswith("perf boom duration_ms=")
    assert line.endswith(" chat=c9")


def test_perf_span_without_context_has_no_trailing_space(caplog):
    """No context kwargs means the line ends at the duration field."""
    with caplog.at_level(logging.INFO, logger="astral.perf"):
        with perf_span("bare"):
            pass
    assert re.fullmatch(r"perf bare duration_ms=\d+", caplog.records[-1].getMessage())
