from __future__ import annotations

import asyncio
from pathlib import Path

from weather_to_docx.domain.models import (
    BatchRequest,
    DocumentOptions,
    JobStatus,
    Location,
    SourceRequest,
)
from weather_to_docx.services.batch import ForecastBatchService
from weather_to_docx.settings import Settings
from weather_to_docx.storage.jobs import JobRepository


def request() -> BatchRequest:
    return BatchRequest(
        locations=[
            Location(id="one", name="Точка 1", latitude=55.75, longitude=37.62, timezone="Europe/Moscow"),
            Location(id="two", name="Точка 2", latitude=59.94, longitude=30.31, timezone="Europe/Moscow"),
        ],
        sources=[SourceRequest(source_id="demo", forecast_days=1, options={"hours": 6})],
        document=DocumentOptions(),
        batch_name="test-batch",
    )


def test_batch_generates_one_document_per_location(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    settings.ensure_directories()
    result = asyncio.run(ForecastBatchService(settings).generate(request(), output_root=tmp_path / "out"))
    assert result.status == JobStatus.COMPLETED
    assert len([item for item in result.artifacts if item.kind == "docx"]) == 2
    assert len([item for item in result.artifacts if item.kind == "zip"]) == 1


def test_sqlite_job_queue(tmp_path: Path) -> None:
    repository = JobRepository(tmp_path / "jobs.sqlite3")
    created = repository.create(request())
    assert created.status == JobStatus.QUEUED
    claimed = repository.claim_next()
    assert claimed is not None
    assert claimed.status == JobStatus.RUNNING
    failed = repository.fail(claimed.id, "test")
    assert failed.status == JobStatus.FAILED
    retry = repository.retry(failed.id)
    assert retry.status == JobStatus.QUEUED
