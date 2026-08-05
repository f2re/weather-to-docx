from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from weather_to_docx.api.app import create_app
from weather_to_docx.document.verification import (
    inspect_meteogram_docx,
    require_meteogram_docx,
)
from weather_to_docx.runtime_check import (
    meteogram_runtime_status,
    verify_meteogram_generation,
)
from weather_to_docx.settings import Settings


def _fake_docx(path: Path, *, marker: bool, image_bytes: int) -> Path:
    with ZipFile(path, "w") as archive:
        text = "Метеограмма модели" if marker else "Обычный документ"
        archive.writestr("word/document.xml", f"<document>{text}</document>")
        archive.writestr("word/media/image1.png", b"x" * image_bytes)
    return path


def test_document_verification_accepts_large_marked_graph(tmp_path: Path) -> None:
    path = _fake_docx(
        tmp_path / "with-graph.docx",
        marker=True,
        image_bytes=20_000,
    )
    inspection = inspect_meteogram_docx(path)
    assert inspection.ready is True
    assert inspection.large_media_count == 1
    assert require_meteogram_docx(path).ready is True


def test_small_weather_icon_cannot_masquerade_as_meteogram(tmp_path: Path) -> None:
    path = _fake_docx(
        tmp_path / "icons-only.docx",
        marker=True,
        image_bytes=1_000,
    )
    inspection = inspect_meteogram_docx(path)
    assert inspection.ready is False
    assert inspection.media_count == 1
    assert inspection.large_media_count == 0
    with pytest.raises(RuntimeError, match="не содержит графика"):
        require_meteogram_docx(path)


def test_runtime_points_to_meteogram_generator() -> None:
    status = meteogram_runtime_status()
    assert status["version"] == "0.4.2"
    assert status["document_generator"].endswith(
        ".localized_meteogram_document"
    )
    assert status["meteogram_generator_active"] is True
    assert status["meteograms_enabled_by_default"] is True
    assert status["matplotlib_available"] is True
    assert status["numpy_available"] is True
    assert status["meteogram_ready"] is True


def test_deep_runtime_check_generates_embedded_graph(tmp_path: Path) -> None:
    result = verify_meteogram_generation(Settings(data_dir=tmp_path / "data"))
    assert result["deep_check"] is True
    assert result["meteogram_embedded"] is True
    assert result["large_media_count"] >= 1
    assert result["error"] is None


def test_api_exposes_loaded_runtime_and_rejects_missing_generator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    with TestClient(create_app(settings)) as client:
        diagnostics = client.get("/api/v1/diagnostics")
        assert diagnostics.status_code == 200
        payload = diagnostics.json()
        assert payload["version"] == "0.4.2"
        assert payload["meteogram_ready"] is True
        assert payload["document_generator"].endswith(
            ".localized_meteogram_document"
        )
        assert payload["package_file"].endswith("runtime_check.py")

    monkeypatch.setattr(
        "weather_to_docx.api.app.meteogram_runtime_status",
        lambda: {
            "version": "0.3.2",
            "document_generator": "weather_to_docx.document.compact_generator",
            "meteogram_ready": False,
        },
    )
    with TestClient(create_app(Settings(data_dir=tmp_path / "old-runtime"))) as client:
        response = client.post(
            "/api/v1/jobs",
            json={
                "locations": [
                    {
                        "id": "point",
                        "name": "Точка",
                        "latitude": 59.9,
                        "longitude": 30.3,
                        "timezone": "Europe/Moscow",
                    }
                ],
                "sources": [
                    {
                        "source_id": "demo",
                        "forecast_days": 1,
                        "options": {"hours": 12},
                    }
                ],
                "document": {"include_meteograms": True},
            },
        )
    assert response.status_code == 503
    assert "старого или неполного runtime" in response.json()["detail"]
