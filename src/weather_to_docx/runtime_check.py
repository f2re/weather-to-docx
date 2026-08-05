from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from weather_to_docx import __version__
from weather_to_docx.document.scientific_generator import ScientificDocumentGenerator
from weather_to_docx.document.verification import inspect_meteogram_docx
from weather_to_docx.domain.models import (
    BatchRequest,
    DocumentOptions,
    Location,
    SourceRequest,
)
from weather_to_docx.services.batch import ForecastBatchService
from weather_to_docx.settings import Settings


ACTIVE_GENERATOR_MODULES = {
    "weather_to_docx.document.meteogram_document",
    "weather_to_docx.document.localized_meteogram_document",
}


def meteogram_runtime_status() -> dict[str, Any]:
    """Вернуть сведения именно о загруженном процессе, а не о git-каталоге."""

    package_file = Path(__file__).resolve()
    generator_module = ScientificDocumentGenerator.__module__
    matplotlib_available = importlib.util.find_spec("matplotlib") is not None
    numpy_available = importlib.util.find_spec("numpy") is not None
    generator_active = generator_module in ACTIVE_GENERATOR_MODULES
    default_enabled = DocumentOptions().include_meteograms
    return {
        "version": __version__,
        "python_executable": sys.executable,
        "package_file": str(package_file),
        "document_generator": generator_module,
        "meteogram_generator_active": generator_active,
        "meteograms_enabled_by_default": default_enabled,
        "matplotlib_available": matplotlib_available,
        "numpy_available": numpy_available,
        "meteogram_ready": (
            generator_active
            and default_enabled
            and matplotlib_available
            and numpy_available
        ),
    }


def verify_meteogram_generation(settings: Settings | None = None) -> dict[str, Any]:
    """Сформировать автономный DOCX и проверить встроенный крупный график."""

    status = meteogram_runtime_status()
    if not status["meteogram_ready"]:
        return {
            **status,
            "deep_check": False,
            "meteogram_embedded": False,
            "error": "Загруженный runtime не готов к построению метеограмм",
        }

    with tempfile.TemporaryDirectory(prefix="weather-to-docx-runtime-check-") as temporary:
        root = Path(temporary)
        local_settings = settings or Settings(data_dir=root / "data")
        local_settings.ensure_directories()
        request = BatchRequest(
            locations=[
                Location(
                    id="runtime-check",
                    name="Проверка метеограммы",
                    latitude=59.9386,
                    longitude=30.3141,
                    timezone="Europe/Moscow",
                )
            ],
            sources=[
                SourceRequest(
                    source_id="demo",
                    forecast_days=1,
                    options={"hours": 12},
                )
            ],
            document=DocumentOptions(
                title="Проверка генератора метеограмм",
                include_meteograms=True,
            ),
            batch_name="runtime-check",
        )
        result = asyncio.run(
            ForecastBatchService(local_settings).generate(
                request,
                output_root=root / "output",
            )
        )
        artifact = next(
            (item for item in result.artifacts if item.kind == "docx"),
            None,
        )
        if artifact is None:
            return {
                **status,
                "deep_check": True,
                "meteogram_embedded": False,
                "error": "; ".join(result.errors) or "DOCX не сформирован",
            }
        inspection = inspect_meteogram_docx(artifact.path)
        return {
            **status,
            "deep_check": True,
            "meteogram_embedded": inspection.ready,
            "media_count": inspection.media_count,
            "large_media_count": inspection.large_media_count,
            "large_media_names": list(inspection.large_media_names),
            "error": inspection.error,
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Проверить, какой runtime формирует документы и встраивает ли он графики."
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="сформировать автономный DOCX и проверить встроенную метеограмму",
    )
    arguments = parser.parse_args()
    result = (
        verify_meteogram_generation()
        if arguments.deep
        else meteogram_runtime_status()
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    success = bool(
        result.get("meteogram_embedded")
        if arguments.deep
        else result.get("meteogram_ready")
    )
    raise SystemExit(0 if success else 2)


if __name__ == "__main__":
    main()
