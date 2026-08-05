from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from weather_to_docx.domain.models import Location, QualityFlag
from weather_to_docx.settings import Settings
from weather_to_docx.sources.ensemble_catalog import (
    OpenMeteoEcmwfAifsEnsembleSource,
    OpenMeteoEcmwfIfsEnsembleSource,
    OpenMeteoGemGepsSource,
)
from weather_to_docx.sources.registry import SourceRegistry

LOCATION = Location(
    id="coverage",
    name="Проверка полноты",
    latitude=55.75,
    longitude=37.62,
    timezone="Europe/Moscow",
)


def _payload() -> dict:
    return {
        "latitude": 55.75,
        "longitude": 37.62,
        "hourly_units": {
            "temperature_2m_member01": "°C",
            "temperature_2m_member02": "°C",
            "temperature_2m_member03": "°C",
        },
        "hourly": {
            "time": ["2026-08-04T00:00"],
            "temperature_2m_member01": [18.0],
            "temperature_2m_member02": [19.0],
            "temperature_2m_member03": [20.0],
        },
    }


def test_catalog_declares_operational_member_counts() -> None:
    assert OpenMeteoEcmwfIfsEnsembleSource.expected_member_count == 51
    assert OpenMeteoEcmwfAifsEnsembleSource.expected_member_count == 51
    assert OpenMeteoGemGepsSource.expected_member_count == 21


def test_registry_uses_scientific_catalog(tmp_path: Path) -> None:
    registry = SourceRegistry(Settings(data_dir=tmp_path))
    assert registry.get("open_meteo_ecmwf_ifs_ensemble").expected_member_count == 51
    assert registry.get("open_meteo_ecmwf_aifs_ensemble").expected_member_count == 51
    assert registry.get("open_meteo_gem_geps").expected_member_count == 21


def test_registry_uses_current_open_meteo_model_ids(tmp_path: Path) -> None:
    registry = SourceRegistry(Settings(data_dir=tmp_path))
    assert registry.get("open_meteo_dwd_icon_eps").model_id == "icon_global_eps"
    assert registry.get("open_meteo_gem_geps").model_id == "gem_global_ensemble"


@pytest.mark.parametrize(
    ("source_type", "expected"),
    [
        (OpenMeteoEcmwfIfsEnsembleSource, 51),
        (OpenMeteoEcmwfAifsEnsembleSource, 51),
        (OpenMeteoGemGepsSource, 21),
    ],
)
def test_incomplete_response_is_marked_suspect(source_type, expected: int) -> None:
    series = source_type.parse_payload(
        _payload(),
        location=LOCATION,
        retrieved_at_utc=datetime(2026, 8, 4, 1, tzinfo=UTC),
    )
    point = series.points[0]
    assert series.source.ensemble_expected_member_count == expected
    assert series.source.ensemble_member_count == 3
    assert point.raw("ensemble_member_coverage") == pytest.approx(300 / expected)
    assert point.measurement("ensemble_member_count").quality is QualityFlag.SUSPECT
    assert any("неполный ансамбль" in warning.lower() for warning in point.warnings)
