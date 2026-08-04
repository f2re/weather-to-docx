from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from weather_to_docx.api.app import create_app
from weather_to_docx.settings import Settings


def _location(location_id: str = "point-1", *, name: str = "Точка 1") -> dict:
    return {
        "id": location_id,
        "name": name,
        "latitude": 59.9386,
        "longitude": 30.3141,
        "elevation_m": 12,
        "timezone": "Europe/Moscow",
        "group": "Основные",
        "output_name": None,
    }


def test_operator_interface_and_static_assets(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))

    response = client.get("/")
    assert response.status_code == 200
    assert "Weather to DOCX" in response.text
    assert "Сводный прогноз и профессиональные метеограммы" in response.text
    assert "Модели прогноза" in response.text
    assert "для каждой пригодной модели" in response.text
    assert "includeMeteograms" in response.text

    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "createJob" in response.text

    response = client.get("/static/compact_report.js")
    assert response.status_code == 200
    assert "createCompactJob" in response.text
    assert 'page_size: "A4"' in response.text
    assert "include_all_parameters: false" in response.text
    assert "include_meteograms: includeMeteograms" in response.text
    assert 'meteogram_smoothing: "pchip"' in response.text

    response = client.get("/static/styles.css")
    assert response.status_code == 200
    assert "--accent" in response.text


def test_location_crud_import_export_and_diagnostics(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))

    response = client.post("/api/v1/locations", json=_location())
    assert response.status_code == 201
    assert response.json()["id"] == "point-1"

    duplicate = client.post("/api/v1/locations", json=_location())
    assert duplicate.status_code == 409

    response = client.get("/api/v1/locations")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["point-1"]

    updated = _location(name="Точка после изменения")
    response = client.put("/api/v1/locations/point-1", json=updated)
    assert response.status_code == 200
    assert response.json()["name"] == "Точка после изменения"

    response = client.post(
        "/api/v1/locations/import",
        json={
            "replace_existing": False,
            "locations": [_location("point-2", name="Точка 2")],
        },
    )
    assert response.status_code == 201
    assert response.json()[0]["id"] == "point-2"

    response = client.get("/api/v1/location-catalog/export")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {"point-1", "point-2"}

    response = client.get("/api/v1/diagnostics")
    assert response.status_code == 200
    assert response.json()["location_count"] == 2
    assert response.json()["source_count"] >= 13

    response = client.delete("/api/v1/locations/point-2")
    assert response.status_code == 204
    assert client.get("/api/v1/locations/point-2").status_code == 404


def test_sources_endpoint_exposes_independent_models(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))
    response = client.get("/api/v1/sources")
    assert response.status_code == 200
    sources = {item["source_id"]: item for item in response.json()}

    expected = {
        "open_meteo_gfs",
        "open_meteo_ecmwf_ifs",
        "open_meteo_ecmwf_aifs",
        "open_meteo_dwd_icon_global",
        "open_meteo_gem_gdps",
        "open_meteo_gefs_0p25",
        "open_meteo_gefs_0p5",
        "open_meteo_ecmwf_ifs_ensemble",
        "open_meteo_ecmwf_aifs_ensemble",
        "open_meteo_dwd_icon_eps",
        "open_meteo_gem_geps",
        "noaa_gfs_0p25",
    }
    assert expected <= set(sources)
    assert (
        sources["open_meteo_ecmwf_ifs"]["model"]
        != sources["open_meteo_ecmwf_aifs"]["model"]
    )
    assert sources["open_meteo_gefs_0p5"]["horizon_days"] == 35
