"""End-to-end smoke tests for Forecaster against the live service.

These tests are skipped by default. Enable them by exporting:

    FORECASTER_E2E_URL=https://forecaster.ai.uky.edu/
    FORECASTER_E2E_API_KEY=<your real key>
    FORECASTER_E2E_CSV=/app/bikerides_day.csv   # optional; defaults to bikerides_day.csv at repo root

The pipeline test drives the full documented Forecaster API workflow:

    submit_dataset → set_column_roles → start_training_job
        → poll get_job_status until Completed (or timeout)
        → get_results
        → delete_dataset (cleanup, in finally)

The training job uses minimal parameters (linear-regression only, expanding
window off, 1 epoch) so the live run finishes in well under a minute and
respects the user's compute quota.
"""
import os
import time
from pathlib import Path

import pytest

from agents.forecaster import mcp_tools

E2E_URL = os.getenv("FORECASTER_E2E_URL")
E2E_KEY = os.getenv("FORECASTER_E2E_API_KEY")

# Caller can override the CSV with FORECASTER_E2E_CSV; default to the repo's
# canonical timeseries fixture mounted at /app inside the docker container.
DEFAULT_CSV_CANDIDATES = [
    os.getenv("FORECASTER_E2E_CSV"),
    "/app/bikerides_day.csv",
    str(Path(__file__).resolve().parents[3] / "bikerides_day.csv"),
]


def _resolve_csv_path() -> str:
    for cand in DEFAULT_CSV_CANDIDATES:
        if cand and Path(cand).exists():
            return cand
    return ""


CSV_PATH = _resolve_csv_path()


@pytest.mark.skipif(
    not E2E_URL or not E2E_KEY,
    reason="FORECASTER_E2E_URL and FORECASTER_E2E_API_KEY env vars must be set",
)
def test_credentials_check_against_live_service() -> None:
    creds = {"FORECASTER_URL": E2E_URL, "FORECASTER_API_KEY": E2E_KEY}
    result = mcp_tools._credentials_check(_credentials=creds)
    assert result["credential_test"] == "ok", (
        f"Live Forecaster probe did not return 'ok': {result}"
    )


@pytest.mark.skipif(
    not E2E_URL or not E2E_KEY or not CSV_PATH,
    reason=(
        "FORECASTER_E2E_URL, FORECASTER_E2E_API_KEY, and a CSV at "
        "FORECASTER_E2E_CSV (or /app/bikerides_day.csv) must be set."
    ),
)
def test_full_pipeline_against_live_service() -> None:
    """submit → save-columns → start-training → poll → get-results → delete."""
    creds = {"FORECASTER_URL": E2E_URL, "FORECASTER_API_KEY": E2E_KEY}
    uuid = None
    try:
        # 1. Submit the CSV.
        submit = mcp_tools.submit_dataset(
            file_handle=CSV_PATH, _credentials=creds, user_id="e2e-smoke",
        )
        assert submit["_ui_components"][0].get("variant") != "error", (
            f"submit_dataset failed: {submit}"
        )
        uuid = submit["_data"]["uuid"]
        cols = submit["_data"]["columns"]
        assert uuid, "submit_dataset returned no uuid"
        assert cols, "submit_dataset returned no columns"
        print(f"[E2E] submit_dataset → uuid={uuid} columns={cols}")

        # 2. Map columns to roles. The bikerides_day.csv fixture has:
        #    Date,Volume,Rain,Temp
        column_roles = {
            "Date": "time-component",
            "Volume": "target",
            "Rain": "past-covariates",
            "Temp": "past-covariates",
        }
        # If the column list differs, fall back to first=time, second=target,
        # rest=past-covariates so the test stays useful with other CSVs.
        if not all(c in cols for c in column_roles):
            column_roles = {cols[0]: "time-component", cols[1]: "target"}
            for extra in cols[2:]:
                column_roles[extra] = "past-covariates"
        save = mcp_tools.set_column_roles(
            uuid=uuid, column_roles=column_roles, _credentials=creds,
        )
        assert save["_ui_components"][0].get("variant") != "error", (
            f"set_column_roles failed: {save}"
        )
        print(f"[E2E] set_column_roles → {column_roles}")

        # 3. Start a minimal training job.
        options = {
            "models": ["linear-regression"],
            "expanding-window": False,
            "test-size": 0.2,
            "epochs": 1,
            "visualize": False,
        }
        start = mcp_tools.start_training_job(
            uuid=uuid, options=options, _credentials=creds,
        )
        assert start["_ui_components"][0].get("variant") != "error", (
            f"start_training_job failed: {start}"
        )
        print(f"[E2E] start_training_job → started (options={options})")

        # 4. Poll until Completed (or fail-budget exhausted).
        client = mcp_tools.ForecasterHttpClient(creds)
        poll = mcp_tools._make_status_poll(client, uuid)
        deadline = time.time() + 300  # 5 min hard cap
        terminal = None
        while time.time() < deadline:
            res = poll()
            print(f"[E2E] poll → status={res['status']} message={res.get('message')!r}")
            if res["status"] in ("succeeded", "failed"):
                terminal = res
                break
            time.sleep(5)
        assert terminal is not None, "Training did not terminate within 5 minutes"
        assert terminal["status"] == "succeeded", (
            f"Training reported terminal status {terminal}"
        )

        # 5. Fetch results.
        results = mcp_tools.get_results(uuid=uuid, _credentials=creds)
        assert results["_ui_components"][0].get("variant") != "error", (
            f"get_results failed: {results}"
        )
        metrics = results["_data"]["metrics"]
        print(f"[E2E] get_results → metrics keys={list(metrics) if isinstance(metrics, dict) else type(metrics).__name__}")
        assert metrics, "get_results returned no metrics"
    finally:
        if uuid:
            try:
                deleted = mcp_tools.delete_dataset(uuid=uuid, _credentials=creds)
                print(f"[E2E] delete_dataset → {deleted['_data'].get('response')}")
            except Exception as cleanup_err:
                print(f"[E2E] delete_dataset cleanup failed: {cleanup_err}")
