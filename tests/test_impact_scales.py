from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from weather_to_docx.analysis.impact_scales import (
    DAILY_PRECIPITATION_REFERENCE_MM,
    daily_precipitation_summary,
    normalise_precipitation_rates,
    precipitation_scale_class,
    temperature_impact_label,
    wind_impact_label,
)
from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    Location,
    SourceMetadata,
)


LOCATION = Location(
    id="impact",
    name="Шкалы",
    latitude=59.9,
    longitude=30.3,
    timezone="UTC",
)
START = datetime(2026, 8, 5, tzinfo=UTC)


def _forecast(
    amounts: list[float],
    *,
    intervals: list[float],
    weather_codes: list[int],
) -> ForecastSeries:
    points = []
    elapsed = 0.0
    for amount, interval, code in zip(
        amounts,
        intervals,
        weather_codes,
        strict=True,
    ):
        elapsed += interval
        valid = START + timedelta(hours=elapsed)
        points.append(
            ForecastPoint(
                valid_time_utc=valid,
                valid_time_local=valid,
                lead_hours=round(elapsed),
                weather_code=code,
                values={
                    "precipitation": ForecastValue(
                        value=amount,
                        accumulation_hours=interval,
                    )
                },
            )
        )
    return ForecastSeries(
        location=LOCATION,
        source=SourceMetadata(
            source_id="impact-test",
            provider="Test",
            model="Test",
            product="test",
            retrieved_at_utc=START,
            exact_cycle_known=False,
        ),
        points=points,
    )


def test_precipitation_is_normalised_to_rate() -> None:
    forecast = _forecast(
        [1.0, 4.0],
        intervals=[3.0, 1.0],
        weather_codes=[61, 63],
    )
    rates = normalise_precipitation_rates(
        forecast.points,
        [1.0, 4.0],
    )
    assert rates[0] == pytest.approx(1 / 3)
    assert rates[1] == pytest.approx(4.0)
    assert rates[1] / rates[0] == pytest.approx(12.0)


def test_precipitation_classes_keep_small_rain_small() -> None:
    assert precipitation_scale_class(0.2, weather_code=51).label == "морось"
    assert precipitation_scale_class(1.0, weather_code=61).label == "слабые"
    assert precipitation_scale_class(4.0, weather_code=63).label == "умеренные"
    assert precipitation_scale_class(11.0, weather_code=82).label == "ливень"
    assert precipitation_scale_class(1.0, weather_code=95).label == "ливень"


def test_persistent_drizzle_is_distinguished_from_shower() -> None:
    forecast = _forecast(
        [0.2, 0.2, 0.2, 0.2],
        intervals=[3.0, 3.0, 3.0, 3.0],
        weather_codes=[51, 51, 51, 51],
    )
    summary = daily_precipitation_summary(forecast, date(2026, 8, 5))
    assert summary is not None
    assert summary.persistent_drizzle is True
    assert summary.label == "длительная морось"
    assert summary.maximum_rate_mm_h < 0.1
    assert summary.reference_ratio == pytest.approx(
        summary.total_mm / DAILY_PRECIPITATION_REFERENCE_MM
    )


def test_thunderstorm_is_visually_classified_as_shower() -> None:
    forecast = _forecast(
        [6.0],
        intervals=[1.0],
        weather_codes=[95],
    )
    summary = daily_precipitation_summary(forecast, date(2026, 8, 5))
    assert summary is not None
    assert summary.thunder is True
    assert summary.label == "гроза / ливень"


def test_temperature_and_wind_labels_are_semantic() -> None:
    assert temperature_impact_label(-2, 4) == "переход через 0 °C"
    assert temperature_impact_label(12, 32) == "жара"
    assert temperature_impact_label(-24, -12) == "очень холодно"
    assert wind_impact_label(7, 15) == "сильные порывы"
    assert wind_impact_label(4, 8) == "ветрено"
    assert wind_impact_label(3, 4) is None
