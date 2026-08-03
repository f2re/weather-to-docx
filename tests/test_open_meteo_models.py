from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from weather_to_docx.domain.models import Location, QualityFlag
from weather_to_docx.settings import Settings
from weather_to_docx.sources.open_meteo import (
    OpenMeteoDwdIconGlobalSource,
    OpenMeteoEcmwfAifsSource,
    OpenMeteoEcmwfIfsSource,
    OpenMeteoGemGdpsSource,
)
from weather_to_docx.sources.open_meteo_ensemble import OpenMeteoGefS05Source
from weather_to_docx.sources.registry import SourceRegistry

LOCATION = Location(
    id="test-point",
    name="Тестовая точка",
    latitude=59.9386,
    longitude=30.3141,
    elevation_m=12,
    timezone="Europe/Moscow",
)


def _payload() -> dict:
    return {
        "latitude": 59.94,
        "longitude": 30.31,
        "elevation": 14,
        "hourly_units": {
            "temperature_2m_member01": "°C",
            "temperature_2m_member02": "°C",
            "temperature_2m_member03": "°C",
            "precipitation_member01": "mm",
            "precipitation_member02": "mm",
            "precipitation_member03": "mm",
            "wind_direction_10m_member01": "°",
            "wind_direction_10m_member02": "°",
            "wind_direction_10m_member03": "°",
        },
        "hourly": {
            "time": ["2026-08-03T00:00", "2026-08-03T03:00"],
            "is_day": [0, 1],
            "temperature_2m_member01": [10.0, 11.0],
            "temperature_2m_member02": [12.0, 13.0],
            "temperature_2m_member03": [14.0, 15.0],
            "precipitation_member01": [0.0, 0.0],
            "precipitation_member02": [0.6, 0.2],
            "precipitation_member03": [1.2, 1.0],
            "wind_direction_10m_member01": [350.0, 90.0],
            "wind_direction_10m_member02": [10.0, 100.0],
            "wind_direction_10m_member03": [0.0, 110.0],
            "weather_code_member01": [1, 2],
            "weather_code_member02": [61, 3],
            "weather_code_member03": [61, 3],
        },
    }


def test_ensemble_statistics_and_probability() -> None:
    series = OpenMeteoGefS05Source.parse_payload(
        _payload(),
        location=LOCATION,
        retrieved_at_utc=datetime(2026, 8, 3, 1, tzinfo=UTC),
        precipitation_threshold_mm=0.5,
    )

    point = series.points[0]
    assert point.raw("temperature_2m") == pytest.approx(12.0)
    assert point.raw("temperature_2m_spread") == pytest.approx(1.632993, rel=1e-5)
    assert point.raw("temperature_2m_p10") == pytest.approx(10.4)
    assert point.raw("temperature_2m_p90") == pytest.approx(13.6)
    assert point.raw("precipitation_probability") == pytest.approx(200 / 3)
    assert point.measurement("precipitation_probability").quality is QualityFlag.CALCULATED
    assert point.raw("ensemble_member_count") == 3
    assert point.weather_code == 61
    direction = point.raw("wind_direction_10m")
    assert min(abs(direction), abs(direction - 360)) < 1e-6
    assert series.source.native_time_step_hours == 3
    assert series.source.model == "NOAA GEFS 0.5°"
    assert series.source.model_dump()["ensemble_member_count"] == 3


@pytest.mark.asyncio
async def test_deterministic_model_is_sent_explicitly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["models"] == "ecmwf_ifs025"
        return httpx.Response(
            200,
            json={
                "latitude": LOCATION.latitude,
                "longitude": LOCATION.longitude,
                "hourly_units": {"temperature_2m": "°C"},
                "hourly": {
                    "time": ["2026-08-03T00:00"],
                    "temperature_2m": [18.5],
                    "weather_code": [1],
                    "is_day": [0],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = OpenMeteoEcmwfIfsSource(client=client)
        series = await source.fetch(LOCATION, 3)

    assert series.points[0].raw("temperature_2m") == 18.5
    assert series.source.model_dump()["upstream_model_id"] == "ecmwf_ifs025"


def test_registered_models_are_separate_sources(tmp_path) -> None:
    registry = SourceRegistry(Settings(data_dir=tmp_path))
    source_ids = {descriptor.source_id for descriptor in registry.descriptors()}
    assert {
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
    } <= source_ids


def test_model_descriptors_keep_provenance() -> None:
    descriptors = (
        OpenMeteoEcmwfIfsSource.descriptor,
        OpenMeteoEcmwfAifsSource.descriptor,
        OpenMeteoDwdIconGlobalSource.descriptor,
        OpenMeteoGemGdpsSource.descriptor,
    )
    assert len({descriptor.model for descriptor in descriptors}) == len(descriptors)
    assert all(descriptor.exact_cycle is False for descriptor in descriptors)
