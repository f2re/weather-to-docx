from __future__ import annotations

import asyncio
import json
import logging
import uuid
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from weather_to_docx.document.generator import DocumentGenerator
from weather_to_docx.domain.models import (
    BatchArtifact,
    BatchRequest,
    BatchResult,
    CollectedLocation,
    ForecastSeries,
    JobStatus,
    Location,
)
from weather_to_docx.settings import Settings
from weather_to_docx.sources.registry import SourceRegistry
from weather_to_docx.utils.files import safe_filename, sha256_file

LOGGER = logging.getLogger(__name__)


class ForecastBatchService:
    def __init__(self, settings: Settings, registry: SourceRegistry | None = None) -> None:
        self.settings = settings
        self.registry = registry or SourceRegistry(settings)
        self.generator = DocumentGenerator(settings.icon_cache_dir)

    async def collect(self, request: BatchRequest) -> list[CollectedLocation]:
        collected = {location.id: CollectedLocation(location=location) for location in request.locations}
        order: dict[tuple[str, str], int] = {
            (location.id, source.source_id): index
            for index, (location, source) in enumerate(
                pair for location in request.locations for pair in ((location, source) for source in request.sources)
            )
        }
        semaphore = asyncio.Semaphore(6)

        async def fetch_one(location: Location, source_request) -> tuple[str, str, ForecastSeries | None, str | None]:
            async with semaphore:
                try:
                    source = self.registry.get(source_request.source_id)
                    forecast = await source.fetch(
                        location=location,
                        forecast_days=source_request.forecast_days,
                        options=source_request.options,
                    )
                    return location.id, source_request.source_id, forecast, None
                except Exception as exc:
                    LOGGER.exception("Forecast source %s failed for %s", source_request.source_id, location.id)
                    return location.id, source_request.source_id, None, str(exc)

        tasks = [
            fetch_one(location, source_request)
            for location in request.locations
            for source_request in request.sources
        ]
        results = await asyncio.gather(*tasks)
        sorted_results = sorted(results, key=lambda item: order[(item[0], item[1])])
        for location_id, source_id, forecast, error in sorted_results:
            item = collected[location_id]
            if forecast is not None:
                item.series.append(forecast)
            else:
                item.errors.append(f"{source_id}: {error}")
        return [collected[location.id] for location in request.locations]

    async def generate(
        self,
        request: BatchRequest,
        *,
        output_root: Path | None = None,
        batch_id: str | None = None,
    ) -> BatchResult:
        batch_id = batch_id or uuid.uuid4().hex
        collected = await self.collect(request)
        return self.generate_from_collected(
            request=request,
            collected=collected,
            output_root=output_root,
            batch_id=batch_id,
        )

    def generate_from_series(
        self,
        *,
        locations: list[Location],
        series: list[ForecastSeries],
        document_options,
        output_root: Path | None = None,
        batch_name: str | None = None,
        batch_id: str | None = None,
    ) -> BatchResult:
        grouped: dict[str, list[ForecastSeries]] = defaultdict(list)
        for item in series:
            grouped[item.location.id].append(item)
        collected = [
            CollectedLocation(
                location=location,
                series=grouped.get(location.id, []),
                errors=[] if grouped.get(location.id) else ["В пакете нет прогнозов для координаты"],
            )
            for location in locations
        ]
        request = BatchRequest(
            locations=locations,
            sources=[
                {
                    "source_id": source_id,
                    "forecast_days": 1,
                    "options": {"origin": "forecast-bundle"},
                }
                for source_id in sorted({item.source.source_id for item in series})
            ],
            document=document_options,
            batch_name=batch_name,
        )
        return self.generate_from_collected(
            request=request,
            collected=collected,
            output_root=output_root,
            batch_id=batch_id or uuid.uuid4().hex,
        )

    def generate_from_collected(
        self,
        *,
        request: BatchRequest,
        collected: list[CollectedLocation],
        output_root: Path | None,
        batch_id: str,
    ) -> BatchResult:
        batch_dir = (output_root or self.settings.documents_dir) / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        result = BatchResult(batch_id=batch_id, status=JobStatus.RUNNING)
        generated_documents: list[Path] = []
        source_manifest: list[dict] = []

        for item in collected:
            if item.errors:
                result.errors.extend(f"{item.location.name}: {error}" for error in item.errors)
            if not item.series:
                continue
            document_name = self._document_name(item.location)
            path = batch_dir / document_name
            try:
                self.generator.generate(
                    location=item.location,
                    series=item.series,
                    options=request.document,
                    output_path=path,
                )
                generated_documents.append(path)
                result.artifacts.append(self._artifact(path, "docx", item.location.id))
                for forecast in item.series:
                    source_manifest.append(
                        {
                            "location_id": item.location.id,
                            "source": forecast.source.model_dump(mode="json"),
                            "warnings": forecast.warnings,
                            "point_count": len(forecast.points),
                        }
                    )
                    result.warnings.extend(
                        f"{item.location.name} / {forecast.source.source_id}: {warning}"
                        for warning in forecast.warnings
                    )
            except Exception as exc:
                LOGGER.exception("DOCX generation failed for %s", item.location.id)
                result.errors.append(f"{item.location.name}: документ не сформирован: {exc}")

        if not generated_documents:
            result.status = JobStatus.FAILED
        elif result.errors:
            result.status = JobStatus.PARTIAL
        else:
            result.status = JobStatus.COMPLETED

        manifest = {
            "schema_version": 1,
            "batch_id": batch_id,
            "batch_name": request.batch_name,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "status": result.status.value,
            "request": request.model_dump(mode="json"),
            "sources": source_manifest,
            "documents": [
                {
                    "name": path.name,
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
                for path in generated_documents
            ],
            "warnings": result.warnings,
            "errors": result.errors,
        }
        manifest_path = batch_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        result.artifacts.append(self._artifact(manifest_path, "manifest", None))

        archive_name = safe_filename(request.batch_name or f"forecast_batch_{batch_id}") + ".zip"
        archive_path = batch_dir / archive_name
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in generated_documents:
                archive.write(path, arcname=path.name)
            archive.write(manifest_path, arcname=manifest_path.name)
        result.artifacts.append(self._artifact(archive_path, "zip", None))
        return result

    @staticmethod
    def _document_name(location: Location) -> str:
        base = location.output_name or f"Прогноз_{location.name}"
        date_text = datetime.now().strftime("%Y-%m-%d")
        return f"{safe_filename(base)}_{date_text}.docx"

    @staticmethod
    def _artifact(path: Path, kind: str, location_id: str | None) -> BatchArtifact:
        return BatchArtifact(
            kind=kind,
            path=path.resolve(),
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
            location_id=location_id,
        )
