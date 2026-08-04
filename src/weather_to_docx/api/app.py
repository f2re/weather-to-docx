from __future__ import annotations

import importlib.util
import shutil
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from weather_to_docx import __version__
from weather_to_docx.api.geocoding import create_geocoding_router
from weather_to_docx.domain.models import BatchRequest, JobRecord, JobStatus, Location
from weather_to_docx.settings import Settings, get_settings
from weather_to_docx.sources.registry import SourceRegistry
from weather_to_docx.storage.jobs import JobRepository
from weather_to_docx.storage.locations import LocationRepository
from weather_to_docx.utils.files import ensure_within


class LocationImportRequest(BaseModel):
    locations: list[Location] = Field(min_length=1, max_length=10000)
    replace_existing: bool = False


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_directories()
    repository = JobRepository(settings.database_path)
    repository.initialise()
    locations = LocationRepository(settings.database_path)
    locations.initialise()
    registry = SourceRegistry(settings)

    app = FastAPI(
        title="Weather to DOCX API",
        version=__version__,
        description=(
            "Геокодирование, справочник координат, источники прогноза и очередь "
            "пакетного формирования метеорологических документов."
        ),
    )
    app.state.settings = settings
    app.state.repository = repository
    app.state.locations = locations
    app.state.registry = registry
    app.include_router(create_geocoding_router(settings))

    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False, response_model=None)
    def operator_interface() -> Response:
        index = static_dir / "index.html"
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse(
            "<h1>Weather to DOCX</h1><p>Интерфейс не включён в пакет.</p>",
            status_code=503,
        )

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/diagnostics", tags=["system"])
    def diagnostics() -> dict:
        descriptors = registry.descriptors()
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
            "bundle_public_key": (
                str(settings.bundle_public_key)
                if settings.bundle_public_key
                else None
            ),
            "location_count": len(locations.list(limit=10000)),
            "source_count": len(descriptors),
            "deterministic_source_count": sum(
                item.source_kind.value == "deterministic" for item in descriptors
            ),
            "ensemble_source_count": sum(
                item.source_kind.value == "ensemble" for item in descriptors
            ),
            "dadata_configured": settings.dadata_configured,
            "dadata_cleaner_configured": bool(settings.dadata_secret),
            "telegram_enabled": settings.telegram_enabled,
            "telegram_token_configured": bool(settings.telegram_bot_token),
            "default_sources": list(settings.default_sources),
            "default_forecast_days": settings.default_forecast_days,
        }

    @app.get("/api/v1/sources", tags=["sources"])
    def sources() -> list[dict]:
        return [asdict(descriptor) for descriptor in registry.descriptors()]

    @app.get(
        "/api/v1/locations",
        response_model=list[Location],
        tags=["locations"],
    )
    def list_locations(
        group: str | None = None,
        limit: int = Query(default=1000, ge=1, le=10000),
    ) -> list[Location]:
        return locations.list(group=group, limit=limit)

    @app.get(
        "/api/v1/location-catalog/export",
        response_model=list[Location],
        tags=["locations"],
    )
    @app.get(
        "/api/v1/locations/export",
        response_model=list[Location],
        tags=["locations"],
    )
    def export_locations() -> list[Location]:
        return locations.list(limit=10000)

    @app.post(
        "/api/v1/locations",
        response_model=Location,
        status_code=201,
        tags=["locations"],
    )
    def create_location(location: Location) -> Location:
        try:
            return locations.create(location)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get(
        "/api/v1/locations/{location_id}",
        response_model=Location,
        tags=["locations"],
    )
    def get_location(location_id: str) -> Location:
        try:
            return locations.get(location_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put(
        "/api/v1/locations/{location_id}",
        response_model=Location,
        tags=["locations"],
    )
    def replace_location(location_id: str, location: Location) -> Location:
        try:
            return locations.replace(location_id, location)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.delete(
        "/api/v1/locations/{location_id}",
        status_code=204,
        tags=["locations"],
    )
    def delete_location(location_id: str) -> Response:
        if not locations.delete(location_id):
            raise HTTPException(
                status_code=404,
                detail=f"Координата {location_id!r} не найдена",
            )
        return Response(status_code=204)

    @app.post(
        "/api/v1/locations/import",
        response_model=list[Location],
        status_code=201,
        tags=["locations"],
    )
    def import_locations(request: LocationImportRequest) -> list[Location]:
        try:
            return locations.import_many(
                request.locations,
                replace_existing=request.replace_existing,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/api/v1/jobs",
        response_model=JobRecord,
        status_code=201,
        tags=["jobs"],
    )
    def create_job(request: BatchRequest) -> JobRecord:
        return repository.create(request)

    @app.get(
        "/api/v1/jobs",
        response_model=list[JobRecord],
        tags=["jobs"],
    )
    def list_jobs(
        limit: int = Query(default=100, ge=1, le=1000),
        status: JobStatus | None = None,
    ) -> list[JobRecord]:
        return repository.list(limit=limit, status=status)

    @app.get(
        "/api/v1/jobs/{job_id}",
        response_model=JobRecord,
        tags=["jobs"],
    )
    def get_job(job_id: str) -> JobRecord:
        return _job_or_404(repository, job_id)

    @app.post(
        "/api/v1/jobs/{job_id}/cancel",
        response_model=JobRecord,
        tags=["jobs"],
    )
    def cancel_job(job_id: str) -> JobRecord:
        try:
            return repository.cancel(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post(
        "/api/v1/jobs/{job_id}/retry",
        response_model=JobRecord,
        status_code=201,
        tags=["jobs"],
    )
    def retry_job(job_id: str) -> JobRecord:
        try:
            return repository.retry(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get(
        "/api/v1/jobs/{job_id}/artifacts/{artifact_index}",
        tags=["artifacts"],
    )
    def download_artifact(job_id: str, artifact_index: int) -> FileResponse:
        job = _job_or_404(repository, job_id)
        if job.result is None:
            raise HTTPException(
                status_code=409,
                detail="Задание ещё не содержит результатов",
            )
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
