"""SQLite storage layer for the test audit trail."""

import json
import os
import sqlite3
from datetime import datetime
from typing import List, Optional

from qual_audit.models import (
    AuditAction,
    AuditEntry,
    LatexArtifact,
    Outcome,
    RunStatus,
    TestCaseResult,
    TestEvidence,
    TestRun,
    VerificationStatus,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS test_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    system_state TEXT NOT NULL,
    categories TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS test_case_results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES test_runs(id),
    suite TEXT NOT NULL,
    test_name TEXT NOT NULL,
    outcome TEXT NOT NULL,
    duration_ms REAL DEFAULT 0.0,
    metrics TEXT,
    qualitative TEXT DEFAULT '',
    evidence_hash TEXT DEFAULT '',
    verification_status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS test_evidence (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES test_case_results(id),
    evidence_type TEXT NOT NULL,
    data TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_entries (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES test_case_results(id),
    action TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    rationale TEXT DEFAULT '',
    timestamp TEXT NOT NULL,
    previous_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS latex_artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES test_runs(id),
    filename TEXT NOT NULL,
    generated_from TEXT NOT NULL,
    verification_complete INTEGER NOT NULL DEFAULT 0,
    generated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_run ON test_case_results(run_id);
CREATE INDEX IF NOT EXISTS idx_cases_suite ON test_case_results(suite);
CREATE INDEX IF NOT EXISTS idx_evidence_case ON test_evidence(case_id);
CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_entries(case_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON latex_artifacts(run_id);
"""


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


class AuditDatabase:
    """CRUD layer for the test audit trail backed by SQLite."""

    def __init__(self, db_path: str = "data/test_audit.db"):
        self.db_path = db_path
        dirname = os.path.dirname(db_path)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init(self):
        conn = self._conn()
        conn.executescript(_SCHEMA)
        conn.commit()
        conn.close()

    # -- TestRun ---------------------------------------------------------------

    def insert_run(self, run: TestRun) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO test_runs (id, started_at, finished_at, system_state, categories, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run.id,
                _iso(run.started_at),
                _iso(run.finished_at) if run.finished_at else None,
                json.dumps(run.system_state),
                json.dumps(run.categories),
                run.status.value,
            ),
        )
        conn.commit()
        conn.close()

    def finish_run(self, run_id: str, status: RunStatus) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE test_runs SET finished_at = ?, status = ? WHERE id = ?",
            (_iso(datetime.now()), status.value, run_id),
        )
        conn.commit()
        conn.close()

    def get_run(self, run_id: str) -> Optional[TestRun]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM test_runs WHERE id = ?", (run_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return TestRun(
            id=row["id"],
            started_at=_parse_iso(row["started_at"]),
            finished_at=_parse_iso(row["finished_at"]) if row["finished_at"] else None,
            system_state=json.loads(row["system_state"]),
            categories=json.loads(row["categories"]),
            status=RunStatus(row["status"]),
        )

    def get_latest_run(self) -> Optional[TestRun]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM test_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            return None
        return TestRun(
            id=row["id"],
            started_at=_parse_iso(row["started_at"]),
            finished_at=_parse_iso(row["finished_at"]) if row["finished_at"] else None,
            system_state=json.loads(row["system_state"]),
            categories=json.loads(row["categories"]),
            status=RunStatus(row["status"]),
        )

    # -- TestCaseResult --------------------------------------------------------

    def insert_case(self, case: TestCaseResult) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO test_case_results "
            "(id, run_id, suite, test_name, outcome, duration_ms, metrics, qualitative, evidence_hash, verification_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                case.id,
                case.run_id,
                case.suite,
                case.test_name,
                case.outcome.value,
                case.duration_ms,
                json.dumps(case.metrics),
                case.qualitative,
                case.evidence_hash,
                case.verification_status.value,
            ),
        )
        conn.commit()
        conn.close()

    def get_cases_for_run(
        self, run_id: str, suite: Optional[str] = None
    ) -> List[TestCaseResult]:
        conn = self._conn()
        if suite:
            rows = conn.execute(
                "SELECT * FROM test_case_results WHERE run_id = ? AND suite = ? ORDER BY test_name",
                (run_id, suite),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM test_case_results WHERE run_id = ? ORDER BY suite, test_name",
                (run_id,),
            ).fetchall()
        conn.close()
        return [self._row_to_case(r) for r in rows]

    def get_case(self, case_id: str) -> Optional[TestCaseResult]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM test_case_results WHERE id = ?", (case_id,)
        ).fetchone()
        conn.close()
        return self._row_to_case(row) if row else None

    def update_verification_status(
        self, case_id: str, status: VerificationStatus
    ) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE test_case_results SET verification_status = ? WHERE id = ?",
            (status.value, case_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _row_to_case(row) -> TestCaseResult:
        return TestCaseResult(
            id=row["id"],
            run_id=row["run_id"],
            suite=row["suite"],
            test_name=row["test_name"],
            outcome=Outcome(row["outcome"]),
            duration_ms=row["duration_ms"] or 0.0,
            metrics=json.loads(row["metrics"]) if row["metrics"] else {},
            qualitative=row["qualitative"] or "",
            evidence_hash=row["evidence_hash"] or "",
            verification_status=VerificationStatus(row["verification_status"]),
        )

    # -- TestEvidence ----------------------------------------------------------

    def insert_evidence(self, ev: TestEvidence) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO test_evidence (id, case_id, evidence_type, data, sha256, captured_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ev.id, ev.case_id, ev.evidence_type, json.dumps(ev.data), ev.sha256, _iso(ev.captured_at)),
        )
        conn.commit()
        conn.close()

    def get_evidence_for_case(self, case_id: str) -> List[TestEvidence]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM test_evidence WHERE case_id = ? ORDER BY captured_at",
            (case_id,),
        ).fetchall()
        conn.close()
        return [
            TestEvidence(
                id=r["id"],
                case_id=r["case_id"],
                evidence_type=r["evidence_type"],
                data=json.loads(r["data"]),
                sha256=r["sha256"],
                captured_at=_parse_iso(r["captured_at"]),
            )
            for r in rows
        ]

    # -- AuditEntry ------------------------------------------------------------

    def insert_audit(self, entry: AuditEntry) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO audit_entries (id, case_id, action, reviewer, rationale, timestamp, previous_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                entry.id,
                entry.case_id,
                entry.action.value,
                entry.reviewer,
                entry.rationale,
                _iso(entry.timestamp),
                entry.previous_hash,
            ),
        )
        conn.commit()
        conn.close()

    def get_audits_for_case(self, case_id: str) -> List[AuditEntry]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM audit_entries WHERE case_id = ? ORDER BY timestamp",
            (case_id,),
        ).fetchall()
        conn.close()
        return [self._row_to_audit(r) for r in rows]

    def get_latest_audit(self) -> Optional[AuditEntry]:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM audit_entries ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return self._row_to_audit(row) if row else None

    def get_all_audits_for_run(self, run_id: str) -> List[AuditEntry]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT a.* FROM audit_entries a "
            "JOIN test_case_results c ON a.case_id = c.id "
            "WHERE c.run_id = ? ORDER BY a.timestamp, a.rowid",
            (run_id,),
        ).fetchall()
        conn.close()
        return [self._row_to_audit(r) for r in rows]

    @staticmethod
    def _row_to_audit(row) -> AuditEntry:
        return AuditEntry(
            id=row["id"],
            case_id=row["case_id"],
            action=AuditAction(row["action"]),
            reviewer=row["reviewer"],
            rationale=row["rationale"] or "",
            timestamp=_parse_iso(row["timestamp"]),
            previous_hash=row["previous_hash"],
        )

    # -- LatexArtifact ---------------------------------------------------------

    def insert_artifact(self, art: LatexArtifact) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO latex_artifacts (id, run_id, filename, generated_from, verification_complete, generated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                art.id,
                art.run_id,
                art.filename,
                json.dumps(art.generated_from),
                1 if art.verification_complete else 0,
                _iso(art.generated_at),
            ),
        )
        conn.commit()
        conn.close()

    def get_artifacts_for_run(self, run_id: str) -> List[LatexArtifact]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM latex_artifacts WHERE run_id = ? ORDER BY filename",
            (run_id,),
        ).fetchall()
        conn.close()
        return [
            LatexArtifact(
                id=r["id"],
                run_id=r["run_id"],
                filename=r["filename"],
                generated_from=json.loads(r["generated_from"]),
                verification_complete=bool(r["verification_complete"]),
                generated_at=_parse_iso(r["generated_at"]),
            )
            for r in rows
        ]
