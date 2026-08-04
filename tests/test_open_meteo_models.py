from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from weather_to_docx.domain.models import (
    LeadTimeReference,
    Location,
    QualityFlag,
    SourceKind,
)
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
    assert point.raw("temperature_2m_mean") == pytest.approx(12.0)
    assert point.raw("temperature_2m_median") == pytest.approx(12.0)
    assert point.raw("temperature_2m_spread") == pytest.approx(
        1.632993,
        rel=1e-5,
    )
    assert point.raw("temperature_2m_p10") == pytest.approx(10.0)
    assert point.raw("temperature_2m_p90") == pytest.approx(14.0)
    assert point.measurement("temperature_2m_mean").sample_count == 3

    # Для асимметричных неотрицательных осадков основной центр — медиана.
    assert point.raw("precipitation") == pytest.approx(0.6)
    assert point.raw("precipitation_median") == pytest.approx(0.6)
    assert point.raw("precipitation_mean") == pytest.approx(0.6)

    assert point.raw("precipitation_probability") == pytest.approx(200 / 3)
    assert point.raw("precipitation_probability_ge_0p5mm") == pytest.approx(
        200 / 3
    )
    probability = point.measurement("precipitation_probability")
    assert probability.quality is QualityFlag.CALCULATED
    assert probability.event_count == 2
    assert probability.sample_count == 3
    assert probability.accumulation_hours == pytest.approx(3.0)
    assert probability.source_start_step == 0
    assert probability.source_end_step == 0
    assert "2/3" in (probability.note or "")
    assert "за 3 ч" in (probability.note or "")
    assert "некалиброванная" in (probability.note or "")

    assert point.raw("ensemble_member_count") == 3
    assert point.raw("ensemble_member_coverage") == pytest.approx(300 / 31)
    assert (
        point.measurement("ensemble_member_count").quality
        is QualityFlag.SUSPECT
    )
    assert point.raw("ensemble_probability_resolution") == pytest.approx(100 / 3)
    assert point.weather_code == 61

    direction = point.raw("wind_direction_10m")
    assert direction is not None
    assert min(abs(direction), abs(direction - 360)) < 1e-6
    assert point.raw("wind_direction_10m_resultant_length") > 0.98
    assert series.source.native_time_step_hours == 3
    assert series.source.model == "NOAA GEFS 0.5°"
    assert series.source.source_kind is SourceKind.ENSEMBLE
    assert series.source.lead_time_reference is LeadTimeReference.RESPONSE_START
    assert series.source.ensemble_member_count == 3
    assert series.source.ensemble_expected_member_count == 31
    assert (
        series.source.probability_calibration
        == "raw_uncalibrated_member_fraction"
    )


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

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        source = OpenMeteoEcmwfIfsSource(client=client)
        series = await source.fetch(LOCATION, 3)

    assert series.points[0].raw("temperature_2m") == 18.5
    assert series.source.model_dump()["upstream_model_id"] == "ecmwf_ifs025"
    assert series.source.source_kind is SourceKind.DETERMINISTIC
    assert series.source.lead_time_reference is LeadTimeReference.RESPONSE_START


def test_registered_models_are_separate_sources(tmp_path) -> None:
    registry = SourceRegistry(Settings(data_dir=tmp_path))
    descriptors = {item.source_id: item for item in registry.descriptors()}
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
    } <= set(descriptors)
    assert (
        descriptors["open_meteo_gefs_0p25"].source_kind
        is SourceKind.ENSEMBLE
    )
    assert (
        descriptors["open_meteo_gfs"].source_kind
        is SourceKind.DETERMINISTIC
    )


def test_model_descriptors_keep_provenance() -> None:
    descriptors = (
        OpenMeteoEcmwfIfsSource.descriptor,
        OpenMeteoEcmwfAifsSource.descriptor,
        OpenMeteoDwdIconGlobalSource.descriptor,
        OpenMeteoGemGdpsSource.descriptor,
    )
    assert len({descriptor.model for descriptor in descriptors}) == len(descriptors)
    assert all(descriptor.exact_cycle is False for descriptor in descriptors)
    assert all(
        descriptor.source_kind is SourceKind.DETERMINISTIC
        for descriptor in descriptors
    )
