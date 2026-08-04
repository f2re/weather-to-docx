from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from weather_to_docx.domain.models import BatchRequest, Location, SourceRequest
from weather_to_docx.storage.jobs import JobRepository


def _request() -> BatchRequest:
    return BatchRequest(
        locations=[
            Location(
                id="lease-point",
                name="Точка аренды",
                latitude=59.93,
                longitude=30.31,
                timezone="Europe/Moscow",
            )
        ],
        sources=[SourceRequest(source_id="demo", forecast_days=1)],
    )


def test_existing_030_database_is_migrated(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                request_json TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
            """
        )

    repository = JobRepository(database)
    repository.initialise()

    with sqlite3.connect(database) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
    assert {
        "worker_id",
        "lease_expires_at_utc",
        "attempt_count",
        "progress_current",
        "progress_total",
        "progress_message",
    } <= columns


def test_stale_running_job_returns_to_queue(tmp_path: Path) -> None:
    database = tmp_path / "queue.sqlite3"
    repository = JobRepository(database)
    created = repository.create(_request())
    claimed = repository.claim_next(worker_id="worker-one", lease_seconds=10)
    assert claimed is not None
    assert claimed.id == created.id
    assert claimed.attempt_count == 1

    expired = datetime.now(UTC) - timedelta(seconds=1)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE jobs SET lease_expires_at_utc = ? WHERE id = ?",
            (expired.isoformat(), created.id),
        )

    assert repository.recover_stale_jobs() == 1
    recovered = repository.get(created.id)
    assert recovered.status.value == "queued"
    assert recovered.worker_id is None
    assert "потери worker" in (recovered.progress_message or "")

    second = repository.claim_next(worker_id="worker-two", lease_seconds=10)
    assert second is not None
    assert second.attempt_count == 2
    assert second.worker_id == "worker-two"


def test_cancelled_job_rejects_old_worker_heartbeat(tmp_path: Path) -> None:
    repository = JobRepository(tmp_path / "queue.sqlite3")
    job = repository.create(_request())
    claimed = repository.claim_next(worker_id="worker-one", lease_seconds=30)
    assert claimed is not None

    cancelled = repository.cancel(job.id)
    assert cancelled.status.value == "cancelled"
    assert repository.heartbeat(
        job.id,
        worker_id="worker-one",
        lease_seconds=30,
    ) is False


def test_worker_online_status_uses_heartbeat_age(tmp_path: Path) -> None:
    repository = JobRepository(tmp_path / "queue.sqlite3")
    assert repository.worker_status(max_age_seconds=10)["online"] is False

    repository.touch_worker("worker-one", details={"pid": 42})
    status = repository.worker_status(max_age_seconds=10)
    assert status["online"] is True
    assert status["worker_id"] == "worker-one"
    assert status["details"]["pid"] == 42
