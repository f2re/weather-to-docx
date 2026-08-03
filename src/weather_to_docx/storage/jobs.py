from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from weather_to_docx.domain.models import BatchRequest, BatchResult, JobRecord, JobStatus


class JobRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_status_created
                    ON jobs(status, created_at_utc);
                """
            )

    def create(self, request: BatchRequest, *, job_id: str | None = None) -> JobRecord:
        self.initialise()
        job_id = job_id or uuid.uuid4().hex
        now = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs(id, status, request_json, result_json, error, created_at_utc, updated_at_utc)
                VALUES (?, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    job_id,
                    JobStatus.QUEUED.value,
                    request.model_dump_json(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> JobRecord:
        self.initialise()
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"Задание {job_id} не найдено")
        return self._row_to_record(row)

    def list(self, *, limit: int = 100, status: JobStatus | None = None) -> list[JobRecord]:
        self.initialise()
        limit = max(1, min(limit, 1000))
        with self._connect() as connection:
            if status:
                rows = connection.execute(
                    "SELECT * FROM jobs WHERE status = ? ORDER BY created_at_utc DESC LIMIT ?",
                    (status.value, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM jobs ORDER BY created_at_utc DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def claim_next(self) -> JobRecord | None:
        self.initialise()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM jobs WHERE status = ? ORDER BY created_at_utc LIMIT 1",
                (JobStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                connection.rollback()
                return None
            now = datetime.now(UTC).isoformat()
            connection.execute(
                "UPDATE jobs SET status = ?, updated_at_utc = ? WHERE id = ? AND status = ?",
                (JobStatus.RUNNING.value, now, row["id"], JobStatus.QUEUED.value),
            )
            connection.commit()
            return self.get(row["id"])
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def complete(self, job_id: str, result: BatchResult) -> JobRecord:
        return self._update(
            job_id,
            status=result.status,
            result_json=result.model_dump_json(),
            error=None,
        )

    def fail(self, job_id: str, error: str) -> JobRecord:
        return self._update(job_id, status=JobStatus.FAILED, error=error)

    def cancel(self, job_id: str) -> JobRecord:
        current = self.get(job_id)
        if current.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
            return current
        return self._update(job_id, status=JobStatus.CANCELLED)

    def retry(self, job_id: str) -> JobRecord:
        current = self.get(job_id)
        if current.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
            raise ValueError("Нельзя повторно поставить активное задание")
        return self.create(current.request)

    def is_cancelled(self, job_id: str) -> bool:
        return self.get(job_id).status == JobStatus.CANCELLED

    def _update(
        self,
        job_id: str,
        *,
        status: JobStatus,
        result_json: str | None = None,
        error: str | None = None,
    ) -> JobRecord:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, result_json = COALESCE(?, result_json), error = ?, updated_at_utc = ?
                WHERE id = ?
                """,
                (status.value, result_json, error, now, job_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Задание {job_id} не найдено")
        return self.get(job_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=row["id"],
            status=JobStatus(row["status"]),
            request=BatchRequest.model_validate_json(row["request_json"]),
            result=BatchResult.model_validate_json(row["result_json"]) if row["result_json"] else None,
            error=row["error"],
            created_at_utc=datetime.fromisoformat(row["created_at_utc"]),
            updated_at_utc=datetime.fromisoformat(row["updated_at_utc"]),
        )
