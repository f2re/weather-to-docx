from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from weather_to_docx.api.app import create_app
from weather_to_docx.domain.models import DocumentOptions
from weather_to_docx.services.worker import run_worker
from weather_to_docx.settings import Settings


def test_api_queue_and_artifact_download(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    application = create_app(settings)
    client = TestClient(application)
    payload = {
        "batch_name": "api-test",
        "locations": [
            {
                "id": "point",
                "name": "Тестовая точка",
                "latitude": 55.75,
                "longitude": 37.62,
                "timezone": "Europe/Moscow",
            }
        ],
        "sources": [
            {
                "source_id": "demo",
                "forecast_days": 1,
                "options": {"hours": 6},
            }
        ],
        "document": {"page_size": "A4"},
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 201
    job_id = response.json()["id"]

    assert run_worker(settings, once=True) == 1

    response = client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    docx_index = next(
        index
        for index, artifact in enumerate(body["result"]["artifacts"])
        if artifact["kind"] == "docx"
    )

    response = client.get(f"/api/v1/jobs/{job_id}/artifacts/{docx_index}")
    assert response.status_code == 200
    assert response.content.startswith(b"PK")


def test_a4_defaults_to_operational_profile_and_rejects_other_profiles() -> None:
    assert DocumentOptions(page_size="A4").parameter_profile == "operational"
    with pytest.raises(ValueError, match="A4 поддерживает"):
        DocumentOptions(page_size="A4", parameter_profile="extended")
