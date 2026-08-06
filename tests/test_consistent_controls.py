from __future__ import annotations

from datetime import UTC, datetime

from weather_to_docx.document.consistent_controls import (
    consistent_control_point,
    detail_precipitation_text,
    detail_wind_text,
)
from weather_to_docx.document.weather_rules import weather_presentation
from weather_to_docx.domain.models import ForecastPoint, ForecastValue

VALID = datetime(2026, 8, 10, 12, tzinfo=UTC)


def _point(
    *,
    precipitation: float,
    weather_code: int,
    wind: float = 4.0,
    gust: float = 9.0,
) -> ForecastPoint:
    return ForecastPoint(
        valid_time_utc=VALID,
        valid_time_local=VALID,
        lead_hours=12,
        weather_code=weather_code,
        is_day=True,
        values={
            "temperature_2m": ForecastValue(value=20.0),
            "relative_humidity_2m": ForecastValue(value=70.0),
            "precipitation": ForecastValue(
                value=precipitation,
                accumulation_hours=6,
            ),
            "wind_speed_10m": ForecastValue(value=wind),
            "wind_direction_10m": ForecastValue(value=270.0),
            "wind_gusts_10m": ForecastValue(value=gust),
            "pressure_msl": ForecastValue(value=1012.0),
            "cloud_cover": ForecastValue(value=55.0),
        },
    )


def test_control_time_one_rain_outlier_is_only_possible_precipitation() -> None:
    points = [
        _point(precipitation=0.8, weather_code=65),
        _point(precipitation=0.0, weather_code=2),
        _point(precipitation=0.0, weather_code=2),
        _point(precipitation=0.0, weather_code=2),
        _point(precipitation=0.0, weather_code=2),
    ]

    consensus = consistent_control_point(points, points[0])
    presentation = weather_presentation(consensus)
    precipitation = detail_precipitation_text(points)

    assert presentation.description == "Осадки возможны"
    assert presentation.description != "Сильный дождь"
    assert "осадки возможны" in precipitation
    assert "1/5 моделей" in precipitation
    assert "до 0,8 мм" in precipitation


def test_control_time_thunder_requires_model_support() -> None:
    points = [
        _point(precipitation=1.0, weather_code=95),
        _point(precipitation=0.4, weather_code=61),
        _point(precipitation=0.3, weather_code=61),
        _point(precipitation=0.0, weather_code=2),
        _point(precipitation=0.0, weather_code=2),
    ]

    consensus = consistent_control_point(points, points[0])

    assert weather_presentation(consensus).description != "Гроза"


def test_control_time_wind_uses_median_gust_not_maximum() -> None:
    points = [
        _point(precipitation=0.0, weather_code=2, wind=4.0, gust=8.0),
        _point(precipitation=0.0, weather_code=2, wind=4.4, gust=9.0),
        _point(precipitation=0.0, weather_code=2, wind=4.8, gust=10.0),
        _point(precipitation=0.0, weather_code=2, wind=5.0, gust=11.0),
        _point(precipitation=0.0, weather_code=2, wind=5.2, gust=18.0),
    ]

    text = detail_wind_text(points)

    assert "порывы: медиана 10,0 м/с" in text
    assert "порывы до 18,0 м/с" not in text
    assert "по моделям 8,0–18,0 м/с" in text
