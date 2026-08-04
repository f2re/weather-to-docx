from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from weather_to_docx.domain.models import BatchRequest, BatchResult, JobRecord, JobStatus


class JobRepository:
    """Устойчивая SQLite-очередь с арендой задания и heartbeat worker."""

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
                    updated_at_utc TEXT NOT NULL,
                    worker_id TEXT,
                    lease_expires_at_utc TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    progress_current INTEGER NOT NULL DEFAULT 0,
                    progress_total INTEGER NOT NULL DEFAULT 0,
                    progress_message TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_status_created
                    ON jobs(status, created_at_utc);
                CREATE TABLE IF NOT EXISTS workers (
                    worker_id TEXT PRIMARY KEY,
                    last_seen_utc TEXT NOT NULL,
                    details_json TEXT
                );
                """
            )
            self._ensure_column(connection, "jobs", "worker_id", "TEXT")
            self._ensure_column(connection, "jobs", "lease_expires_at_utc", "TEXT")
            self._ensure_column(
                connection,
                "jobs",
                "attempt_count",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "jobs",
                "progress_current",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "jobs",
                "progress_total",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(connection, "jobs", "progress_message", "TEXT")
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_lease
                ON jobs(status, lease_expires_at_utc)
                """
            )

    def create(self, request: BatchRequest, *, job_id: str | None = None) -> JobRecord:
        self.initialise()
        job_id = job_id or uuid.uuid4().hex
        now = datetime.now(UTC)
        total = len(request.locations) * len(request.sources)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs(
                    id, status, request_json, result_json, error,
                    created_at_utc, updated_at_utc,
                    worker_id, lease_expires_at_utc, attempt_count,
                    progress_current, progress_total, progress_message
                )
                VALUES (?, ?, ?, NULL, NULL, ?, ?, NULL, NULL, 0, 0, ?, ?)
                """,
                (
                    job_id,
                    JobStatus.QUEUED.value,
                    request.model_dump_json(),
                    now.isoformat(),
                    now.isoformat(),
                    total,
                    "Ожидает свободный worker",
                ),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> JobRecord:
        self.initialise()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Задание {job_id} не найдено")
        return self._row_to_record(row)

    def list(
        self,
        *,
        limit: int = 100,
        status: JobStatus | None = None,
    ) -> list[JobRecord]:
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

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_seconds: int = 30,
    ) -> JobRecord | None:
        self.initialise()
        lease_seconds = max(10, min(int(lease_seconds), 3600))
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._recover_stale_jobs(connection, datetime.now(UTC))
            row = connection.execute(
                "SELECT id FROM jobs WHERE status = ? ORDER BY created_at_utc LIMIT 1",
                (JobStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                connection.rollback()
                return None
            now = datetime.now(UTC)
            lease_until = now + timedelta(seconds=lease_seconds)
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, worker_id = ?, lease_expires_at_utc = ?,
                    attempt_count = attempt_count + 1,
                    progress_message = ?, updated_at_utc = ?, error = NULL
                WHERE id = ? AND status = ?
                """,
                (
                    JobStatus.RUNNING.value,
                    worker_id,
                    lease_until.isoformat(),
                    "Получение прогнозов и формирование документов",
                    now.isoformat(),
                    row["id"],
                    JobStatus.QUEUED.value,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return None
            connection.commit()
            return self.get(row["id"])
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def heartbeat(
        self,
        job_id: str,
        *,
        worker_id: str,
        lease_seconds: int = 30,
        progress_current: int | None = None,
        progress_total: int | None = None,
        progress_message: str | None = None,
    ) -> bool:
        now = datetime.now(UTC)
        lease_until = now + timedelta(seconds=max(10, min(lease_seconds, 3600)))
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET lease_expires_at_utc = ?, updated_at_utc = ?,
                    progress_current = COALESCE(?, progress_current),
                    progress_total = COALESCE(?, progress_total),
                    progress_message = COALESCE(?, progress_message)
                WHERE id = ? AND status = ? AND worker_id = ?
                """,
                (
                    lease_until.isoformat(),
                    now.isoformat(),
                    progress_current,
                    progress_total,
                    progress_message,
                    job_id,
                    JobStatus.RUNNING.value,
                    worker_id,
                ),
            )
        return cursor.rowcount == 1

    def complete(
        self,
        job_id: str,
        result: BatchResult,
        *,
        worker_id: str | None = None,
    ) -> JobRecord:
        current = self.get(job_id)
        if current.status == JobStatus.CANCELLED:
            return current
        if worker_id and current.worker_id != worker_id:
            raise RuntimeError("Задание принадлежит другому worker")
        return self._update(
            job_id,
            status=result.status,
            result_json=result.model_dump_json(),
            error=None,
            clear_lease=True,
            progress_current=current.progress_total,
            progress_message="Завершено",
        )

    def fail(
        self,
        job_id: str,
        error: str,
        *,
        worker_id: str | None = None,
    ) -> JobRecord:
        current = self.get(job_id)
        if current.status == JobStatus.CANCELLED:
            return current
        if worker_id and current.worker_id != worker_id:
            raise RuntimeError("Задание принадлежит другому worker")
        return self._update(
            job_id,
            status=JobStatus.FAILED,
            error=error,
            clear_lease=True,
            progress_message="Ошибка",
        )

    def cancel(self, job_id: str) -> JobRecord:
        current = self.get(job_id)
        if current.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
            return current
        return self._update(
            job_id,
            status=JobStatus.CANCELLED,
            clear_lease=True,
            progress_message="Отменено оператором",
        )

    def retry(self, job_id: str) -> JobRecord:
        current = self.get(job_id)
        if current.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
            raise ValueError("Нельзя повторно поставить активное задание")
        return self.create(current.request)

    def is_cancelled(self, job_id: str) -> bool:
        return self.get(job_id).status == JobStatus.CANCELLED

    def recover_stale_jobs(self) -> int:
        self.initialise()
        with self._connect() as connection:
            return self._recover_stale_jobs(connection, datetime.now(UTC))

    def touch_worker(
        self,
        worker_id: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.initialise()
        now = datetime.now(UTC).isoformat()
        payload = json.dumps(details or {}, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workers(worker_id, last_seen_utc, details_json)
                VALUES (?, ?, ?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    last_seen_utc = excluded.last_seen_utc,
                    details_json = excluded.details_json
                """,
                (worker_id, now, payload),
            )

    def worker_status(self, *, max_age_seconds: int = 20) -> dict[str, Any]:
        self.initialise()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT worker_id, last_seen_utc, details_json
                FROM workers
                ORDER BY last_seen_utc DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return {
                "online": False,
                "worker_id": None,
                "last_seen_utc": None,
                "age_seconds": None,
                "details": {},
            }
        last_seen = datetime.fromisoformat(row["last_seen_utc"])
        age = max(0.0, (datetime.now(UTC) - last_seen).total_seconds())
        return {
            "online": age <= max_age_seconds,
            "worker_id": row["worker_id"],
            "last_seen_utc": last_seen.isoformat(),
            "age_seconds": round(age, 1),
            "details": json.loads(row["details_json"] or "{}"),
        }

    def queue_metrics(self) -> dict[str, int]:
        self.initialise()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
            ).fetchall()
            stale = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM jobs
                WHERE status = ? AND lease_expires_at_utc IS NOT NULL
                  AND lease_expires_at_utc < ?
                """,
                (JobStatus.RUNNING.value, datetime.now(UTC).isoformat()),
            ).fetchone()["count"]
        values = {status.value: 0 for status in JobStatus}
        values.update({row["status"]: int(row["count"]) for row in rows})
        values["stale_running"] = int(stale)
        return values

    def _update(
        self,
        job_id: str,
        *,
        status: JobStatus,
        result_json: str | None = None,
        error: str | None = None,
        clear_lease: bool = False,
        progress_current: int | None = None,
        progress_message: str | None = None,
    ) -> JobRecord:
        current = self.get(job_id)
        now = datetime.now(UTC).isoformat()
        worker_id = None if clear_lease else current.worker_id
        lease_text = (
            None
            if clear_lease or current.lease_expires_at_utc is None
            else current.lease_expires_at_utc.isoformat()
        )
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, result_json = COALESCE(?, result_json), error = ?,
                    worker_id = ?, lease_expires_at_utc = ?,
                    progress_current = COALESCE(?, progress_current),
                    progress_message = COALESCE(?, progress_message),
                    updated_at_utc = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    result_json,
                    error,
                    worker_id,
                    lease_text,
                    progress_current,
                    progress_message,
                    now,
                    job_id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Задание {job_id} не найдено")
        return self.get(job_id)

    @staticmethod
    def _recover_stale_jobs(
        connection: sqlite3.Connection,
        now: datetime,
    ) -> int:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET status = ?, worker_id = NULL, lease_expires_at_utc = NULL,
                progress_message = ?, updated_at_utc = ?, error = ?
            WHERE status = ? AND lease_expires_at_utc IS NOT NULL
              AND lease_expires_at_utc < ?
            """,
            (
                JobStatus.QUEUED.value,
                "Возвращено в очередь после потери worker",
                now.isoformat(),
                "Предыдущий worker перестал подтверждать выполнение",
                JobStatus.RUNNING.value,
                now.isoformat(),
            ),
        )
        return cursor.rowcount

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        existing = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> JobRecord:
        keys = set(row.keys())
        lease = (
            datetime.fromisoformat(row["lease_expires_at_utc"])
            if "lease_expires_at_utc" in keys and row["lease_expires_at_utc"]
            else None
        )
        return JobRecord(
            id=row["id"],
            status=JobStatus(row["status"]),
            request=BatchRequest.model_validate_json(row["request_json"]),
            result=(
                BatchResult.model_validate_json(row["result_json"])
                if row["result_json"]
                else None
            ),
            error=row["error"],
            created_at_utc=datetime.fromisoformat(row["created_at_utc"]),
            updated_at_utc=datetime.fromisoformat(row["updated_at_utc"]),
            worker_id=row["worker_id"] if "worker_id" in keys else None,
            lease_expires_at_utc=lease,
            attempt_count=(
                int(row["attempt_count"] or 0)
                if "attempt_count" in keys
                else 0
            ),
            progress_current=(
                int(row["progress_current"] or 0)
                if "progress_current" in keys
                else 0
            ),
            progress_total=(
                int(row["progress_total"] or 0)
                if "progress_total" in keys
                else 0
            ),
            progress_message=(
                row["progress_message"]
                if "progress_message" in keys
                else None
            ),
        )
