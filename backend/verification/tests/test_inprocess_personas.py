"""US1 — tangible, server-driven UI across personas (T018).

Drives all four personas in-process and asserts the acceptance criteria:
every scenario reaches a verdict (SC-001); UI-warranting queries yield
file-derived, persisted, re-executable components (SC-002/004); a prose answer is
a legitimate outcome (FR-015); coverage spans >= 3 file categories (SC-003); and a
dual run record is written.
"""
from __future__ import annotations

from verification.checks.tangible_ui import build_us1_checks
from verification.drivers.in_process import InProcessDriver
from verification.report import build_record, write_report
from verification.runner import Runner
from verification.scenarios import TANGIBLE_UI, build_scenarios
from verification.verdict import Outcome
from verification.tests.conftest import INTEGRATION, run_async

pytestmark = INTEGRATION

_TABULAR = {"everyday", "government"}
_STRONG_CHECKS = {
    "us1.component_present",
    "us1.component_from_file",
    "us1.persisted_with_identity",
    "us1.re_executable",
    "us1.reader_dispatched",
    "vocabulary_ok",
}


def _run_all(run_config):
    async def _go():
        driver = InProcessDriver(run_config)
        await driver.setup()
        try:
            scenarios = build_scenarios(
                run_config.run_id, "mock_inprocess", properties=[TANGIBLE_UI]
            )
            runner = Runner(driver, run_config)
            checks = build_us1_checks()
            await runner.run(scenarios, checks)
            return runner, scenarios
        finally:
            await driver.teardown()

    return run_async(_go())


def test_us1_personas_tangible_ui(run_config):
    runner, scenarios = _run_all(run_config)

    # SC-001: every scenario reached at least one verdict.
    persona_keys = {s.persona.key for s in scenarios}
    verdict_personas = {v.refs.get("persona") for v in runner.verdicts}
    assert persona_keys <= verdict_personas, (
        f"missing verdicts for {persona_keys - verdict_personas}"
    )

    # No outright failures anywhere (PASS or UNCERTAIN only).
    failures = [v for v in runner.verdicts if v.outcome == Outcome.FAIL]
    assert not failures, "FAIL verdicts: " + "; ".join(
        f"{v.refs.get('persona')}/{v.refs.get('check')}: {v.reason}" for v in failures
    )

    # SC-002/004: tabular personas carry the full tangible-UI proof.
    for persona in _TABULAR:
        passed = {
            v.refs.get("check")
            for v in runner.verdicts
            if v.refs.get("persona") == persona and v.outcome == Outcome.PASS
        }
        missing = _STRONG_CHECKS - passed
        assert not missing, f"{persona}: expected PASS on {sorted(missing)} (got {sorted(passed)})"

    # SC-003: >= 3 file categories exercised across the catalogue.
    record = build_record(
        run_config, runner.verdicts, runner.evidence,
        auth_mode="mock_inprocess", personas=sorted(persona_keys),
    )
    cats = record["coverage"]["file_categories"]
    assert len(cats) >= 3, f"expected >=3 file categories, got {cats}"

    # Dual run record is produced and the differentiation claim is grounded.
    paths = write_report(record, run_config.run_dir)
    assert paths["json"].endswith("verdicts.json")
    assert record["differentiation"], "differentiation claim should be non-empty"


def test_us1_every_scenario_terminates(run_config):
    """SC-001: bounded — no scenario is left without a definite verdict."""
    runner, scenarios = _run_all(run_config)
    for scenario in scenarios:
        outcomes = [
            v.outcome for v in runner.verdicts
            if v.refs.get("scenario") == scenario.scenario_id
        ]
        assert outcomes, f"{scenario.scenario_id} produced no verdict"
        assert all(o in (Outcome.PASS, Outcome.FAIL, Outcome.UNCERTAIN) for o in outcomes)
