"""Lightweight performance timing for feature 052.

perf_span emits one structured log line per measured span so the measurement
protocol in specs/052-perf-comment-hygiene/quickstart.md can compute
percentiles straight from the orchestrator log. Context values must be short
identifiers (surface keys, chat ids) — never message content or PHI.
"""

import logging
import time
from contextlib import contextmanager

logger = logging.getLogger("astral.perf")


@contextmanager
def perf_span(name, **ctx):
    """Time the wrapped block and log ``perf <name> duration_ms=<int> k=v ...``.

    The line is emitted even when the block raises, so failed operations are
    measured too; the exception always propagates.
    """
    start = time.monotonic()
    try:
        yield
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        extra = "".join(f" {k}={v}" for k, v in ctx.items())
        logger.info("perf %s duration_ms=%d%s", name, duration_ms, extra)
