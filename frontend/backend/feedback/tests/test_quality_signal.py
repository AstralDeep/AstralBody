"""Tests for feedback.quality — status thresholds + transition events."""
from __future__ import annotations

import asyncio

import pytest

from feedback.quality import classify_status


def test_insufficient_data_below_min_dispatch():
    assert classify_status(
        dispatch_count=10, failure_rate=0.5, negative_feedback_rate=0.5,
        min_dispatch=25,
    ) == "insufficient-data"


def test_underperforming_when_failure_rate_high():
    assert classify_status(
        dispatch_count=100, failure_rate=0.21, negative_feedback_rate=0.0,
        min_dispatch=25, fail_rate_threshold=0.20, neg_fb_rate_threshold=0.30,
    ) == "underperforming"


def test_underperforming_when_negative_feedback_rate_high():
    assert classify_status(
        dispatch_count=100, failure_rate=0.0, negative_feedback_rate=0.31,
        min_dispatch=25, fail_rate_threshold=0.20, neg_fb_rate_threshold=0.30,
    ) == "underperforming"


def test_healthy_when_under_thresholds():
    assert classify_status(
        dispatch_count=100, failure_rate=0.05, negative_feedback_rate=0.05,
        min_dispatch=25, fail_rate_threshold=0.20, neg_fb_rate_threshold=0.30,
    ) == "healthy"


def test_threshold_boundary_exact_match_triggers_underperforming():
    """≥ thresholds should flag — boundary is inclusive."""
    assert classify_status(
        dispatch_count=100, failure_rate=0.20, negative_feedback_rate=0.0,
        min_dispatch=25, fail_rate_threshold=0.20, neg_fb_rate_threshold=0.30,
    ) == "underperforming"
