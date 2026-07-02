"""Security-Benchmark Harness (spec 047) — ASB / AgentDojo / InjecAgent against the trust envelope.

**Eval/test-only. NEVER import this package from product runtime code**
(``backend/orchestrator``, ``backend/agents``, ``backend/shared``). The
dependency-isolation guard in ``isolation_check.py`` asserts this (SC-004).

The harness drives Astral's *real* orchestrator dispatch + permission path
(token exchange, scope check, PHI gate, red-team verdict, audit chaining)
through the existing LLM client-factory seam — the same architectural posture
as the feature-032 verification harness — records deterministic per-case
outcomes, and produces an Attack-Success-Rate (ASR) report with defense-ablation
columns.

It measures the enforcement behaviour; it never modifies it (FR-011).
"""
from __future__ import annotations

# Bump when the adjudication point, ASR definition, or record schema changes.
# ASR numbers are only comparable within a fixed (model, benchmark, harness)
# triple, so this string is stamped into every run record (FR-005).
HARNESS_VERSION = "0.1.0"

__all__ = ["HARNESS_VERSION"]
