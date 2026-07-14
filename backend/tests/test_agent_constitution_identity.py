"""Feature 057 — the baked agent-constitution copy must match the specs source.

The runtime Analyze gate reads ``backend/agent_constitution/agent_constitution.md``
(baked into the image); the authoritative source is
``specs/057-byo-client-agents/agent-constitution.md``. They MUST be byte-identical.

The ``specs/`` copy is NOT present in the runtime image (Dockerfile bakes only
``backend/``), so this test skips when the source is absent (in-image pytest) and
enforces identity on host / CI checkout, where both exist.
"""
from __future__ import annotations

import os

import pytest

_BACKEND_COPY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "agent_constitution", "agent_constitution.md",
)
_SPECS_COPY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "specs", "057-byo-client-agents", "agent-constitution.md",
)


def test_baked_copy_exists_and_loads():
    assert os.path.exists(_BACKEND_COPY), "baked agent constitution missing from backend/"
    from orchestrator.agent_constitution import AGENT_CONSTITUTION_VERSION, load_checklist
    assert AGENT_CONSTITUTION_VERSION, "version must parse"
    assert [p.letter for p in load_checklist()] == list("ABCDEFGHIJKL")


def test_baked_copy_byte_identical_to_specs_source():
    if not os.path.exists(_SPECS_COPY):
        pytest.skip("specs/ source not present (runtime image) — enforced on host/CI checkout")
    with open(_BACKEND_COPY, "rb") as a, open(_SPECS_COPY, "rb") as b:
        assert a.read() == b.read(), (
            "backend/agent_constitution/agent_constitution.md has drifted from the "
            "specs/057-byo-client-agents/agent-constitution.md source — re-copy so they match")
