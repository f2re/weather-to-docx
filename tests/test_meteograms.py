from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image, ImageStat

from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    LeadTimeReference,
    Location,
    QualityFlag,
    SourceKind,
    SourceMetadata,
)
from weather_to_docx.plotting.meteogram import MeteogramRenderer
from weather_to_docx.plotting.smoothing import pchip_interpolate, smooth_segments

MOSCOW = ZoneInfo("Europe/Moscow")


def _location() -> Location:
    return Location(
        id="meteogram",
        name="Тестовая точка",
        latitude=59.9,
        longitude=30.3,
        timezone="Europe/Moscow",
    )


def _deterministic() -> ForecastSeries:
    location = _location()
    start = datetime(2026, 8, 4, tzinfo=UTC)
    points = []
    for hour in range(0, 96, 3):
        valid_utc = start + timedelta(hours=hour)
        local = valid_utc.astimezone(MOSCOW)
        wave = math.sin((local.hour - 6) / 24 * 2 * math.pi)
        rain = 1.2 if hour in {30, 33, 72} else 0.0
        values = {
            "temperature_2m": ForecastValue(value=17 + 6 * wave, unit="°C"),
            "dew_point_2m": ForecastValue(value=11 + 2 * wave, unit="°C"),
            "relative_humidity_2m": ForecastValue(value=68 - 20 * wave, unit="%"),
            "precipitation": ForecastValue(value=rain, unit="мм", accumulation_hours=3),
            "pressure_msl": ForecastValue(value=1018 - hour * 0.05, unit="гПа"),
            "cloud_cover": ForecastValue(value=80 if rain else 35, unit="%"),
            "cloud_cover_low": ForecastValue(value=70 if rain else 20, unit="%"),
            "cloud_cover_mid": ForecastValue(value=45 if rain else 25, unit="%"),
            "cloud_cover_high": ForecastValue(value=30, unit="%"),
            "wind_speed_10m": ForecastValue(value=3 + hour / 60, unit="м/с"),
            "wind_gusts_10m": ForecastValue(value=7 + hour / 45, unit="м/с"),
        }
        points.append(
            ForecastPoint(
                valid_time_utc=valid_utc,
                valid_time_local=local,
                lead_hours=hour,
                weather_code=61 if rain else 2,
                is_day=6 <= local.hour < 21,
                values=values,
            )
        )
    return ForecastSeries(
        location=location,
        source=SourceMetadata(
            source_id="test-model",
            provider="Test",
            model="Тестовая модель",
            product="forecast",
            retrieved_at_utc=start,
            exact_cycle_known=False,
            lead_time_reference=LeadTimeReference.RESPONSE_START,
        ),
        points=points,
    )


def _ensemble() -> ForecastSeries:
    deterministic = _deterministic()
    points = []
    calculated = QualityFlag.CALCULATED
    for point in deterministic.points:
        values = {}
        for code in (
            "temperature_2m",
            "relative_humidity_2m",
            "cloud_cover",
            "wind_speed_10m",
            "wind_gusts_10m",
            "pressure_msl",
            "precipitation",
        ):
            centre = float(point.raw(code) or 0.0)
            spread = {
                "temperature_2m": 1.6,
                "relative_humidity_2m": 8.0,
                "cloud_cover": 18.0,
                "wind_speed_10m": 1.2,
                "wind_gusts_10m": 2.5,
                "pressure_msl": 2.0,
                "precipitation": 0.5,
            }[code]
            values[code] = ForecastValue(value=centre, quality=calculated, sample_count=31)
            values[f"{code}_median"] = ForecastValue(
                value=centre,
                quality=calculated,
                sample_count=31,
            )
            values[f"{code}_mean"] = ForecastValue(
                value=centre,
                quality=calculated,
                sample_count=31,
            )
            values[f"{code}_spread"] = ForecastValue(
                value=spread,
                quality=calculated,
                sample_count=31,
            )
            values[f"{code}_p10"] = ForecastValue(
                value=centre - spread * 1.4,
                quality=calculated,
                sample_count=31,
            )
            values[f"{code}_p90"] = ForecastValue(
                value=centre + spread * 1.4,
                quality=calculated,
                sample_count=31,
            )
        probability = 70 if float(point.raw("precipitation") or 0) > 0 else 10
        values["precipitation_probability_ge_0p1mm"] = ForecastValue(
            value=probability,
            unit="%",
            quality=calculated,
            event_count=22 if probability == 70 else 3,
            sample_count=31,
            accumulation_hours=3,
        )
        values["precipitation_probability_ge_1mm"] = ForecastValue(
            value=35 if probability == 70 else 0,
            unit="%",
            quality=calculated,
            event_count=11 if probability == 70 else 0,
            sample_count=31,
            accumulation_hours=3,
        )
        points.append(point.model_copy(update={"values": values}))
    return ForecastSeries(
        location=deterministic.location,
        source=SourceMetadata(
            source_id="test-ensemble",
            provider="Test",
            model="Тестовый ансамбль",
            product="ensemble",
            source_kind=SourceKind.ENSEMBLE,
            retrieved_at_utc=deterministic.source.retrieved_at_utc,
            exact_cycle_known=False,
            lead_time_reference=LeadTimeReference.RESPONSE_START,
            ensemble_member_count=31,
            ensemble_expected_member_count=31,
            ensemble_member_coverage_percent=100,
        ),
        points=points,
    )


def test_pchip_is_shape_preserving() -> None:
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([0.0, 1.0, 1.5, 2.0])
    target = np.linspace(0, 3, 121)
    result = pchip_interpolate(x, y, target)
    assert result.min() >= y.min()
    assert result.max() <= y.max()
    assert np.all(np.diff(result) >= -1e-12)


def test_smoothing_does_not_bridge_missing_periods() -> None:
    segments = smooth_segments(
        [0, 1, 2, 8, 9],
        [1, 2, 3, 4, 5],
        max_gap_factor=2.5,
    )
    assert len(segments) == 2
    assert segments[0][0][-1] == 2
    assert segments[1][0][0] == 8


def test_deterministic_and_ensemble_meteograms_are_rendered(tmp_path: Path) -> None:
    renderer = MeteogramRenderer(dpi=120)
    deterministic_path = renderer.render_deterministic(
        _deterministic(),
        tmp_path / "deterministic.png",
    )
    ensemble_path = renderer.render_ensemble(
        _ensemble(),
        tmp_path / "ensemble.png",
    )

    for path in (deterministic_path, ensemble_path):
        assert path.exists()
        with Image.open(path) as image:
            assert image.width >= 1100
            assert image.height >= 450
            assert image.format == "PNG"
            grayscale = image.convert("L")
            assert ImageStat.Stat(grayscale).var[0] > 150
