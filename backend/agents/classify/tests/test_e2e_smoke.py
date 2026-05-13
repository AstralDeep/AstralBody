"""End-to-end smoke tests for CLASSify against the live service.

Skipped by default. Enable by exporting:
    CLASSIFY_E2E_URL=https://classify.ai.uky.edu/
    CLASSIFY_E2E_API_KEY=<your real key>
    CLASSIFY_E2E_CSV=/app/dataset_soft.csv   # optional; defaults shown below

The read-only tests (creds check, get_ml_options) run if just the URL/key
are set. The full-pipeline test additionally needs a CSV with a `class`
column; it submits → sets column types → starts training (randomforest only,
no tuning) → polls until Completed → fetches results → deletes the dataset
(in `finally` for cleanup).
"""
import os
import time
from pathlib import Path

import pytest

from agents.classify import mcp_tools

E2E_URL = os.getenv("CLASSIFY_E2E_URL")
E2E_KEY = os.getenv("CLASSIFY_E2E_API_KEY")

DEFAULT_CSV_CANDIDATES = [
    os.getenv("CLASSIFY_E2E_CSV"),
    "/app/dataset_soft.csv",
    str(Path(__file__).resolve().parents[3] / "dataset_soft.csv"),
]


def _resolve_csv_path() -> str:
    for cand in DEFAULT_CSV_CANDIDATES:
        if cand and Path(cand).exists():
            return cand
    return ""


CSV_PATH = _resolve_csv_path()


@pytest.mark.skipif(
    not E2E_URL or not E2E_KEY,
    reason="CLASSIFY_E2E_URL and CLASSIFY_E2E_API_KEY env vars must be set",
)
def test_credentials_check_against_live_service() -> None:
    creds = {"CLASSIFY_URL": E2E_URL, "CLASSIFY_API_KEY": E2E_KEY}
    result = mcp_tools._credentials_check(_credentials=creds)
    assert result["credential_test"] == "ok", (
        f"Live CLASSify probe did not return 'ok': {result}"
    )


@pytest.mark.skipif(
    not E2E_URL or not E2E_KEY,
    reason="CLASSIFY_E2E_URL and CLASSIFY_E2E_API_KEY env vars must be set",
)
def test_get_ml_options_returns_payload() -> None:
    creds = {"CLASSIFY_URL": E2E_URL, "CLASSIFY_API_KEY": E2E_KEY}
    result = mcp_tools.get_ml_options(_credentials=creds)
    assert "_data" in result
    assert result["_ui_components"][0].get("variant") != "error"


@pytest.mark.skipif(
    not E2E_URL or not E2E_KEY or not CSV_PATH,
    reason=(
        "CLASSIFY_E2E_URL, CLASSIFY_E2E_API_KEY, and a CSV at "
        "CLASSIFY_E2E_CSV (or /app/dataset_soft.csv) must be set."
    ),
)
def test_full_pipeline_against_live_service() -> None:
    """submit → set-columns → start-training → poll → get-results → delete."""
    creds = {"CLASSIFY_URL": E2E_URL, "CLASSIFY_API_KEY": E2E_KEY}
    report_uuid = None
    try:
        # 1. Submit the CSV.
        submit = mcp_tools.submit_dataset(
            file_handle=CSV_PATH, _credentials=creds, user_id="e2e-smoke",
        )
        assert submit["_ui_components"][0].get("variant") != "error", (
            f"submit_dataset failed: {submit}"
        )
        report_uuid = submit["_data"]["report_uuid"]
        column_types = submit["_data"]["column_types"] or {}
        assert report_uuid, "submit_dataset returned no report_uuid"
        assert column_types, "submit_dataset returned no column_types"
        print(
            f"[E2E] submit_dataset → report_uuid={report_uuid} "
            f"columns={len(column_types)}"
        )

        # 2. Pick the class column. dataset_soft.csv has a literal `class`
        # column with TRUE/FALSE values; fall back to the last column for
        # other CSVs.
        class_column = "class" if "class" in column_types else list(column_types)[-1]
        set_cols = mcp_tools.set_column_types(
            report_uuid=report_uuid,
            class_column=class_column,
            column_types=column_types,
            _credentials=creds,
            user_id="e2e-smoke",
        )
        assert set_cols["_ui_components"][0].get("variant") != "error", (
            f"set_column_types failed: {set_cols}"
        )
        print(f"[E2E] set_column_types → class_column={class_column}")

        # 3. Start training with one fast model.
        start = mcp_tools.start_training_job(
            report_uuid=report_uuid,
            class_column=class_column,
            models_to_train=["randomforest"],
            parameter_tune=False,
            supervised=True,
            _credentials=creds,
        )
        assert start["_ui_components"][0].get("variant") != "error", (
            f"start_training_job failed: {start}"
        )
        print(f"[E2E] start_training_job → started")

        # 4. Poll until Completed.
        client = mcp_tools.ClassifyHttpClient(creds)
        poll = mcp_tools._make_status_poll(client, report_uuid)
        deadline = time.time() + 600  # 10 min hard cap
        terminal = None
        while time.time() < deadline:
            res = poll()
            print(f"[E2E] poll → status={res['status']} message={res.get('message')!r}")
            if res["status"] in ("succeeded", "failed"):
                terminal = res
                break
            time.sleep(5)
        assert terminal is not None, "Training did not terminate within 10 minutes"
        assert terminal["status"] == "succeeded", (
            f"Training reported terminal status {terminal}"
        )

        # 5. Fetch results.
        results = mcp_tools.get_results(report_uuid=report_uuid, _credentials=creds)
        assert results["_ui_components"][0].get("variant") != "error", (
            f"get_results failed: {results}"
        )
        payload = results["_data"]["results"]
        print(
            f"[E2E] get_results → results type={type(payload).__name__} "
            f"keys={list(payload) if isinstance(payload, dict) else 'n/a'}"
        )
        assert payload, "get_results returned no payload"
    finally:
        if report_uuid:
            try:
                deleted = mcp_tools.delete_dataset(
                    report_uuid=report_uuid, _credentials=creds,
                )
                print(f"[E2E] delete_dataset → {deleted['_data'].get('response')}")
            except Exception as cleanup_err:
                print(f"[E2E] delete_dataset cleanup failed: {cleanup_err}")
