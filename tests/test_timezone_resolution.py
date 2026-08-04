from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from weather_to_docx.api.app import create_app
from weather_to_docx.domain.models import TimezoneSource
from weather_to_docx.geocoding.parser import resolve_item
from weather_to_docx.geocoding.timezone import resolve_timezone
from weather_to_docx.settings import Settings


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
