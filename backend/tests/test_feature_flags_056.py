"""T002 (056-delegated-agent-chaining): flag posture for the chaining seams.

Feature 056 introduces NO new product flag. The interactive chaining seam
(mediated agent-to-agent hops + planner sub-task decomposition) rides the
existing ``recursive_delegation`` flag (048), and the machine-turn root
authority (consent-derived offline-grant threading) rides the existing
``scheduler_execution`` flag, which stays dark pending the T057 offline-grant
security review. Both MUST default off (fail closed) so that flag-off behavior
is byte-identical to the single-hop path (FR-009, FR-016, SC-009).
"""
import importlib

import shared.feature_flags as feature_flags


def _fresh_flags(monkeypatch, **env):
    for var in ("FF_RECURSIVE_DELEGATION", "FF_SCHEDULER_EXECUTION"):
        monkeypatch.delenv(var, raising=False)
    for var, value in env.items():
        monkeypatch.setenv(var, value)
    return importlib.reload(feature_flags).flags


def test_recursive_delegation_defaults_off(monkeypatch):
    flags = _fresh_flags(monkeypatch)
    assert flags.is_enabled("recursive_delegation") is False


def test_scheduler_execution_defaults_off(monkeypatch):
    flags = _fresh_flags(monkeypatch)
    assert flags.is_enabled("scheduler_execution") is False


def test_flags_enable_via_env(monkeypatch):
    flags = _fresh_flags(
        monkeypatch,
        FF_RECURSIVE_DELEGATION="true",
        FF_SCHEDULER_EXECUTION="1",
    )
    assert flags.is_enabled("recursive_delegation") is True
    assert flags.is_enabled("scheduler_execution") is True


def test_no_new_056_flag_registered(monkeypatch):
    """056 reuses the two existing flags — no 056-specific flag exists."""
    flags = _fresh_flags(monkeypatch)
    names = set(flags._flags)
    assert "recursive_delegation" in names
    assert "scheduler_execution" in names
    assert not any("chain" in n or n.startswith("056") for n in names)


def teardown_module(module):
    # Restore the module-level singleton for later tests in the same session.
    importlib.reload(feature_flags)
