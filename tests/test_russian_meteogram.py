from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import matplotlib.dates as mdates
import numpy as np

from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    Location,
    SourceMetadata,
)
from weather_to_docx.plotting.russian_meteogram import (
    RussianMeteogramRenderer,
    russian_day_label,
    russian_timezone_label,
)
from weather_to_docx.plotting.solar import is_night, solar_elevation_degrees

MOSCOW = ZoneInfo("Europe/Moscow")


def _forecast_without_is_day() -> ForecastSeries:
    start = datetime(2026, 8, 5, tzinfo=UTC)
    location = Location(
        id="spb-night",
        name="Санкт-Петербург",
        latitude=59.9607,
        longitude=30.1587,
        timezone="Europe/Moscow",
    )
    points = []
    for hour in range(0, 48, 3):
        valid_utc = start + timedelta(hours=hour)
        points.append(
            ForecastPoint(
                valid_time_utc=valid_utc,
                valid_time_local=valid_utc.astimezone(MOSCOW),
                lead_hours=hour,
                is_day=None,
                values={
                    "temperature_2m": ForecastValue(value=18.0),
                    "relative_humidity_2m": ForecastValue(value=70.0),
                    "precipitation": ForecastValue(value=0.0),
                    "wind_speed_10m": ForecastValue(value=3.0),
                    "wind_gusts_10m": ForecastValue(value=6.0),
                    "pressure_msl": ForecastValue(value=1015.0),
                    "cloud_cover": ForecastValue(value=50.0),
                },
            )
        )
    return ForecastSeries(
        location=location,
        source=SourceMetadata(
            source_id="night-test",
            provider="Test",
            model="Тестовая модель",
            product="forecast",
            retrieved_at_utc=start,
            exact_cycle_known=False,
        ),
        points=points,
    )


def test_weekday_labels_are_independent_from_system_locale() -> None:
    value = mdates.date2num(datetime(2026, 8, 6, tzinfo=MOSCOW))
    assert russian_day_label(value, timezone=MOSCOW) == "06.08\nчт"
    assert "Thu" not in russian_day_label(value, timezone=MOSCOW)


def test_visible_timezone_is_russian_and_uses_offset() -> None:
    current = datetime(2026, 8, 6, 12, tzinfo=MOSCOW)
    assert russian_timezone_label(current) == "местное время, UTC+03:00"
    assert "Europe/" not in russian_timezone_label(current)


def test_solar_fallback_distinguishes_day_and_night_in_saint_petersburg() -> None:
    local_noon = datetime(2026, 8, 6, 12, tzinfo=MOSCOW)
    local_midnight = datetime(2026, 8, 6, 0, tzinfo=MOSCOW)
    assert solar_elevation_degrees(
        local_noon,
        latitude=59.9607,
        longitude=30.1587,
    ) > 20
    assert is_night(
        local_midnight,
        latitude=59.9607,
        longitude=30.1587,
    )
    assert not is_night(
        local_noon,
        latitude=59.9607,
        longitude=30.1587,
    )


def test_night_is_shaded_even_when_source_does_not_provide_is_day() -> None:
    forecast = _forecast_without_is_day()
    renderer = RussianMeteogramRenderer(dpi=120)
    figure, axes = renderer._new_figure("Проверка ночи")
    renderer._forecast_context = forecast
    x = mdates.date2num(
        [point.valid_time_local for point in forecast.points]
    )
    renderer._shade_night(axes, forecast.points, np.asarray(x))

    assert all(axis.patches for axis in axes)
    labels = [text.get_text() for text in axes[0].texts]
    assert "ночь" in labels
    figure.clear()
