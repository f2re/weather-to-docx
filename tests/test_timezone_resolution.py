from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from weather_to_docx.api.app import create_app
from weather_to_docx.domain.models import TimezoneSource
from weather_to_docx.geocoding.parser import resolve_item
from weather_to_docx.geocoding.timezone import resolve_timezone
from weather_to_docx.settings import Settings
from weather_to_docx.storage.locations import LocationRepository


def test_timezone_is_resolved_offline_for_coordinates() -> None:
    timezone, source = resolve_timezone(
        60.1699,
        24.9384,
        fallback="UTC",
    )
    assert timezone == "Europe/Helsinki"
    assert source == "coordinates"


async def test_coordinate_parser_does_not_silently_use_moscow() -> None:
    location = await resolve_item(
        "43.1155, 131.8855",
        geocoder=None,
        default_timezone="Europe/Moscow",
        automatic=False,
    )
    assert location.timezone == "Asia/Vladivostok"
    assert location.timezone_source is TimezoneSource.COORDINATES


def test_timezone_api_and_worker_diagnostics(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/timezone/resolve",
            json={"latitude": 59.9386, "longitude": 30.3141},
        )
        assert response.status_code == 200
        assert response.json()["timezone"] == "Europe/Moscow"
        assert response.json()["source"] == "coordinates"

        diagnostics = client.get("/api/v1/diagnostics")
        assert diagnostics.status_code == 200
        payload = diagnostics.json()
        assert payload["timezonefinder"] is True
        assert payload["worker"]["online"] is False
        assert "queue" in payload


def test_file_preview_uses_shared_parser_and_timezones(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    csv_text = (
        "name;latitude;longitude\n"
        "Хельсинки;60.1699;24.9384\n"
        "Владивосток;43.1155;131.8855\n"
        "Повтор;60.1699;24.9384\n"
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/geocoding/parse-file",
            json={
                "filename": "locations.csv",
                "content": csv_text,
                "max_locations": 100,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert [item["timezone"] for item in payload["locations"]] == [
        "Europe/Helsinki",
        "Asia/Vladivostok",
    ]
    assert all(
        item["timezone_source"] == "coordinates"
        for item in payload["locations"]
    )
    assert any("повтор координат" in warning for warning in payload["warnings"])


def test_legacy_catalog_timezone_is_rechecked_before_job(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    repository = LocationRepository(settings.database_path)
    repository.initialise()
    now = datetime.now(UTC).isoformat()
    legacy = {
        "id": "legacy-helsinki",
        "name": "Хельсинки из версии 0.3.0",
        "latitude": 60.1699,
        "longitude": 24.9384,
        "elevation_m": None,
        "timezone": "Europe/Moscow",
        "group": "Старый каталог",
        "output_name": None,
    }
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute(
            """
            INSERT INTO locations(
                id, location_json, group_name, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                legacy["id"],
                json.dumps(legacy, ensure_ascii=False),
                legacy["group"],
                now,
                now,
            ),
        )

    decoded = repository.get(legacy["id"])
    assert decoded.timezone_source is TimezoneSource.SYSTEM_DEFAULT

    with TestClient(create_app(settings)) as client:
        stored = client.get(f"/api/v1/locations/{legacy['id']}").json()
        response = client.post(
            "/api/v1/jobs",
            json={
                "batch_name": "legacy-timezone",
                "locations": [stored],
                "sources": [
                    {"source_id": "demo", "forecast_days": 1, "options": {}}
                ],
            },
        )
    assert response.status_code == 201
    job_location = response.json()["request"]["locations"][0]
    assert job_location["timezone"] == "Europe/Helsinki"
    assert job_location["timezone_source"] == "coordinates"
