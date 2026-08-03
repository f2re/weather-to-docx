from __future__ import annotations

import importlib.util
import shutil
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from weather_to_docx import __version__
from weather_to_docx.domain.models import BatchRequest, JobRecord, JobStatus
from weather_to_docx.settings import Settings, get_settings
from weather_to_docx.sources.registry import SourceRegistry
from weather_to_docx.storage.jobs import JobRepository
from weather_to_docx.utils.files import ensure_within


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_directories()
    repository = JobRepository(settings.database_path)
    repository.initialise()
    registry = SourceRegistry(settings)

    app = FastAPI(
        title="Weather to DOCX API",
        version=__version__,
        description="Очередь пакетного формирования метеорологических документов по координатам.",
    )
    app.state.settings = settings
    app.state.repository = repository
    app.state.registry = registry

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/diagnostics", tags=["system"])
    def diagnostics() -> dict:
        return {
            "version": __version__,
            "data_dir": str(settings.data_dir),
            "database": str(settings.database_path),
            "database_exists": settings.database_path.exists(),
            "documents_dir": str(settings.documents_dir),
            "documents_writable": _is_writable(settings.documents_dir),
            "zstd": shutil.which("zstd"),
            "eccodes_python": importlib.util.find_spec("eccodes") is not None,
            "require_bundle_signature": settings.require_bundle_signature,
            "bundle_public_key": str(settings.bundle_public_key) if settings.bundle_public_key else None,
        }

    @app.get("/api/v1/sources", tags=["sources"])
    def sources() -> list[dict]:
        return [asdict(descriptor) for descriptor in registry.descriptors()]

    @app.post("/api/v1/jobs", response_model=JobRecord, status_code=201, tags=["jobs"])
    def create_job(request: BatchRequest) -> JobRecord:
        return repository.create(request)

    @app.get("/api/v1/jobs", response_model=list[JobRecord], tags=["jobs"])
    def list_jobs(
        limit: int = Query(default=100, ge=1, le=1000),
        status: JobStatus | None = None,
    ) -> list[JobRecord]:
        return repository.list(limit=limit, status=status)

    @app.get("/api/v1/jobs/{job_id}", response_model=JobRecord, tags=["jobs"])
    def get_job(job_id: str) -> JobRecord:
        return _job_or_404(repository, job_id)

    @app.post("/api/v1/jobs/{job_id}/cancel", response_model=JobRecord, tags=["jobs"])
    def cancel_job(job_id: str) -> JobRecord:
        try:
            return repository.cancel(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/jobs/{job_id}/retry", response_model=JobRecord, status_code=201, tags=["jobs"])
    def retry_job(job_id: str) -> JobRecord:
        try:
            return repository.retry(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/jobs/{job_id}/artifacts/{artifact_index}", tags=["artifacts"])
    def download_artifact(job_id: str, artifact_index: int) -> FileResponse:
        job = _job_or_404(repository, job_id)
        if job.result is None:
            raise HTTPException(status_code=409, detail="Задание ещё не содержит результатов")
        try:
            artifact = job.result.artifacts[artifact_index]
        except IndexError as exc:
            raise HTTPException(status_code=404, detail="Артефакт не найден") from exc
        try:
            path = ensure_within(Path(artifact.path), settings.documents_dir)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Недопустимый путь артефакта") from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Файл артефакта отсутствует")
        return FileResponse(path, filename=path.name)

    return app


def _job_or_404(repository: JobRepository, job_id: str) -> JobRecord:
    try:
        return repository.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


app = create_app()
