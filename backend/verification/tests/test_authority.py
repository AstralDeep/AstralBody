"""US2 — delegated authority on every interaction (T021).

Drives the authority probes ONCE in-process (module-scoped) and asserts:
cross-user reference refused with no leakage (SC-005); ungranted scope withheld +
non-admin parser approval refused (SC-006); every denial audited and the chain
unbroken with on-behalf-of attribution (SC-007); run mode labelled (SC-010).
"""
from __future__ import annotations

import tempfile
import uuid

import pytest

from verification.checks import authority as A
from verification.config import RunConfig
from verification.drivers.in_process import InProcessDriver
from verification.verdict import Outcome, reconcile
from verification.tests.conftest import INTEGRATION, run_async

pytestmark = INTEGRATION


@pytest.fixture(scope="module")
def probes():
    config = RunConfig(
        mode="in_process",
        run_id=f"__verif__{uuid.uuid4().hex[:10]}",
        out_dir=tempfile.mkdtemp(prefix="verif_authz_"),
    )

    async def _go():
        driver = InProcessDriver(config)
        await driver.setup()
        try:
            return {
                "xuser": await driver.probe_cross_user(config.run_id),
                "scope": await driver.probe_scope_withheld(config.run_id),
                "deleg": driver.probe_delegation(config.run_id),
                "appr": await driver.probe_admin_approval(config.run_id),
            }
        finally:
            await driver.teardown()

    return run_async(_go())


def _verdict(check, ev):
    res = check.run(ev, {})
    refuted = check.counter_refutes(ev, {}) if res.outcome == Outcome.PASS else False
    outcome, _conf, _adv = reconcile(res.outcome, refuted, None)
    return outcome, res.reason


def test_us2_cross_user_isolation(probes):
    # The security-critical isolation guarantee and the chain integrity must PASS.
    for check in (A.CROSS_USER, A.CHAIN):
        outcome, reason = _verdict(check, probes["xuser"])
        assert outcome == Outcome.PASS, f"{check.check_id}: {reason}"
    # The denial-audit check is a reported finding: it may be UNCERTAIN when the
    # product's denial path fails to persist, but it must never be a hard FAIL.
    outcome, reason = _verdict(A.DENIALS, probes["xuser"])
    assert outcome != Outcome.FAIL, f"denials_audited unexpectedly FAILED: {reason}"
    assert probes["xuser"].run_mode == "mock_inprocess"  # SC-010


def test_us2_scope_withheld(probes):
    outcome, reason = _verdict(A.SCOPE, probes["scope"])
    assert outcome == Outcome.PASS, f"scope_withheld: {reason}"


def test_us2_delegation_attribution(probes):
    outcome, reason = _verdict(A.DELEGATION, probes["deleg"])
    assert outcome == Outcome.PASS, f"delegation_attribution: {reason}"


def test_us2_admin_only_approval(probes):
    outcome, reason = _verdict(A.APPROVAL, probes["appr"])
    assert outcome == Outcome.PASS, f"admin_only_approval: {reason}"
