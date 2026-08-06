from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from weather_to_docx.document.compact_generator import DailyModelMetrics
from weather_to_docx.document.consistent_summary import (
    build_consistent_risk_signals,
    consistent_daily_model_metrics,
    consistent_daily_presentation_point,
    daily_precipitation_text,
    daily_wind_text,
)
from weather_to_docx.document.weather_rules import weather_presentation
from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    Location,
    SourceMetadata,
)

LOCATION = Location(
    id="consistency-point",
    name="Точка проверки",
    latitude=59.9,
    longitude=30.3,
    timezone="UTC",
)
START = datetime(2026, 8, 10, tzinfo=UTC)
DAY = date(2026, 8, 10)


def _series(
    source_id: str,
    *,
    total_mm: float,
    weather_code: int = 2,
    intervals: int = 4,
) -> ForecastSeries:
    interval_hours = 24 / intervals
    value = total_mm / intervals
    points = []
    for index in range(intervals):
        end_hour = int((index + 1) * interval_hours)
        valid = START + timedelta(hours=end_hour)
        points.append(
            ForecastPoint(
                valid_time_utc=valid,
                valid_time_local=valid,
                lead_hours=end_hour,
                weather_code=weather_code,
                is_day=6 <= valid.hour <= 18,
                values={
                    "temperature_2m": ForecastValue(value=18.0 + index),
                    "relative_humidity_2m": ForecastValue(value=75.0),
                    "precipitation": ForecastValue(
                        value=value,
                        source_start_step=index * interval_hours,
                        source_end_step=(index + 1) * interval_hours,
                        accumulation_hours=interval_hours,
                    ),
                    "wind_speed_10m": ForecastValue(value=4.0),
                    "wind_gusts_10m": ForecastValue(value=9.0),
                    "pressure_msl": ForecastValue(value=1012.0),
                    "cloud_cover": ForecastValue(value=55.0),
                },
            )
        )
    return ForecastSeries(
        location=LOCATION,
        source=SourceMetadata(
            source_id=source_id,
            provider="Test",
            model=source_id,
            product="test",
            retrieved_at_utc=START,
            exact_cycle_known=False,
        ),
        points=points,
    )


def test_trace_amount_cannot_become_strong_rain_from_wmo_code() -> None:
    forecast = _series("outlier", total_mm=0.8, weather_code=65)
    metric = consistent_daily_model_metrics(forecast, DAY)

    assert metric is not None
    assert metric.weather_code != 65
    assert metric.precipitation_total == 0.8


def test_one_heavy_code_does_not_define_five_model_daily_weather() -> None:
    forecasts = [
        _series("outlier", total_mm=0.8, weather_code=65),
        _series("dry-1", total_mm=0.0),
        _series("dry-2", total_mm=0.0),
        _series("dry-3", total_mm=0.0),
        _series("dry-4", total_mm=0.0),
    ]
    metrics = [
        metric
        for forecast in forecasts
        if (metric := consistent_daily_model_metrics(forecast, DAY)) is not None
    ]
    point = consistent_daily_presentation_point(metrics, DAY)

    assert weather_presentation(point).description == "Осадки возможны"
    assert weather_presentation(point).description != "Сильный дождь"


def test_single_thunder_scenario_is_not_consensus_or_key_risk() -> None:
    forecasts = [
        _series("thunder", total_mm=4.4, weather_code=95),
        _series("rain", total_mm=1.4, weather_code=61),
        _series("drizzle", total_mm=0.6, weather_code=51),
        _series("dry-1", total_mm=0.0),
        _series("dry-2", total_mm=0.0),
    ]

    text = daily_precipitation_text(forecasts, DAY)
    risks = build_consistent_risk_signals(forecasts, [], [DAY])

    assert "гроза с осадками" not in text
    assert "гроза: 1/5 моделей" in text
    assert all(signal.phenomenon != "ГРОЗА" for signal in risks)


def test_outlier_total_does_not_define_precipitation_class_or_risk() -> None:
    forecasts = [
        _series("gfs", total_mm=2.5, weather_code=61),
        _series("icon", total_mm=3.9, weather_code=61),
        _series("aifs", total_mm=11.2, weather_code=61),
        _series("ifs", total_mm=15.0, weather_code=61),
        _series("gdps", total_mm=38.2, weather_code=63),
    ]

    text = daily_precipitation_text(forecasts, DAY)
    risks = build_consistent_risk_signals(forecasts, [], [DAY])

    assert "медиана 11,2 мм" in text
    assert "диапазон 2,5–38,2 мм" in text
    assert "заметные осадки" in text
    assert "очень много осадков" not in text
    assert all(signal.phenomenon != "СИЛЬНЫЕ ОСАДКИ" for signal in risks)


def test_one_persistent_drizzle_model_is_reported_as_minority() -> None:
    forecasts = [
        _series("persistent", total_mm=9.3, weather_code=51, intervals=8),
        _series("wet-1", total_mm=0.6, weather_code=51),
        _series("wet-2", total_mm=0.4, weather_code=51),
        _series("dry-1", total_mm=0.0),
        _series("dry-2", total_mm=0.0),
    ]

    text = daily_precipitation_text(forecasts, DAY)

    assert "длительная морось: 1/5 моделей" in text
    assert "\nдлительная морось\n" not in text


def test_wind_and_gust_terms_are_not_mixed() -> None:
    source = _series("wind", total_mm=0.0)
    metrics = [
        DailyModelMetrics(
            source=source,
            weather_code=2,
            temperature_min=15.0,
            temperature_max=20.0,
            precipitation_total=0.0,
            wind_max=wind,
            gust_max=gust,
            pressure_min=1008.0,
            pressure_max=1012.0,
        )
        for wind, gust in (
            (4.0, 8.0),
            (4.4, 9.0),
            (4.8, 10.0),
            (5.0, 11.1),
            (5.2, 12.0),
        )
    ]

    text = daily_wind_text(metrics)

    assert "сильный ветер" not in text
    assert "сильные порывы" not in text
    assert "порывы: медиана 10,0 м/с" in text
