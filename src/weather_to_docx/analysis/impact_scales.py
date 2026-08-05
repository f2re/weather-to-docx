from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from weather_to_docx.analysis.consensus import daily_precipitation_total
from weather_to_docx.domain.models import ForecastPoint, ForecastSeries

# Это не климатическая норма конкретной станции, а единый оперативный ориентир,
# позволяющий сравнивать суточные суммы на всех метеограммах одной шкалой.
DAILY_PRECIPITATION_REFERENCE_MM = 10.0
PRECIPITATION_RATE_CAP_MM_H = 12.0
PRECIPITATION_RATE_TICKS = (0.0, 0.5, 2.0, 5.0, 10.0)

DRIZZLE_CODES = frozenset({51, 53, 55, 56, 57})
RAIN_CODES = frozenset({61, 63, 65, 66, 67})
SHOWER_CODES = frozenset({80, 81, 82, 85, 86})
THUNDER_CODES = frozenset({95, 96, 99})
FOG_CODES = frozenset({45, 48})


@dataclass(frozen=True, slots=True)
class PrecipitationScaleClass:
    code: str
    label: str
    color: str
    lower_rate_mm_h: float
    upper_rate_mm_h: float | None


@dataclass(frozen=True, slots=True)
class DailyPrecipitationSummary:
    total_mm: float
    maximum_rate_mm_h: float
    wet_hours: float
    label: str
    reference_ratio: float
    thunder: bool
    persistent_drizzle: bool

    @property
    def short_text(self) -> str:
        total = f"{self.total_mm:.1f}".replace(".", ",")
        return f"{total} мм/сут · {self.label}"


PRECIPITATION_CLASSES = (
    PrecipitationScaleClass("trace", "следы", "#c8dce8", 0.0, 0.1),
    PrecipitationScaleClass("drizzle", "морось", "#a8d5e5", 0.1, 0.5),
    PrecipitationScaleClass("light", "слабые", "#72b8d6", 0.5, 2.0),
    PrecipitationScaleClass("moderate", "умеренные", "#2f91c3", 2.0, 5.0),
    PrecipitationScaleClass("heavy", "сильные", "#176b9a", 5.0, 10.0),
    PrecipitationScaleClass("shower", "ливень", "#0a3f6b", 10.0, None),
)


def precipitation_scale_class(
    rate_mm_h: float,
    *,
    weather_code: int | None = None,
) -> PrecipitationScaleClass:
    rate = max(0.0, float(rate_mm_h))
    if weather_code in THUNDER_CODES:
        return PRECIPITATION_CLASSES[-1]
    if weather_code in DRIZZLE_CODES and rate < 2.0:
        return PRECIPITATION_CLASSES[1]
    if weather_code in SHOWER_CODES and rate >= 5.0:
        return PRECIPITATION_CLASSES[-1]
    for item in PRECIPITATION_CLASSES:
        if item.upper_rate_mm_h is None or rate < item.upper_rate_mm_h:
            return item
    return PRECIPITATION_CLASSES[-1]


def precipitation_interval_hours(
    points: list[ForecastPoint],
    index: int,
) -> float:
    point = points[index]
    measurement = point.measurement("precipitation")
    if measurement is not None:
        if measurement.accumulation_hours is not None:
            return max(0.01, float(measurement.accumulation_hours))
        if (
            measurement.source_start_step is not None
            and measurement.source_end_step is not None
            and measurement.source_end_step > measurement.source_start_step
        ):
            return float(
                measurement.source_end_step - measurement.source_start_step
            )
    if index > 0:
        hours = (
            point.valid_time_utc - points[index - 1].valid_time_utc
        ).total_seconds() / 3600
        if hours > 0:
            return hours
    if index + 1 < len(points):
        hours = (
            points[index + 1].valid_time_utc - point.valid_time_utc
        ).total_seconds() / 3600
        if hours > 0:
            return hours
    return 1.0


def normalise_precipitation_rates(
    points: list[ForecastPoint],
    values: Iterable[float | int | None],
) -> list[float]:
    rates: list[float] = []
    for index, raw in enumerate(values):
        value = _as_float(raw)
        if value is None or index >= len(points):
            rates.append(math.nan)
            continue
        rates.append(max(0.0, value) / precipitation_interval_hours(points, index))
    return rates


def daily_precipitation_summary(
    forecast: ForecastSeries,
    day: date,
    *,
    values: Iterable[float | int | None] | None = None,
) -> DailyPrecipitationSummary | None:
    indices = [
        index
        for index, point in enumerate(forecast.points)
        if point.valid_time_local.date() == day
    ]
    if not indices:
        return None
    points = [forecast.points[index] for index in indices]
    if values is None:
        raw_values = [point.raw("precipitation") for point in forecast.points]
    else:
        raw_values = list(values)
    selected_values = [raw_values[index] for index in indices]
    rates = normalise_precipitation_rates(points, selected_values)

    total = daily_precipitation_total(points)
    if total is None:
        finite_values = [_as_float(value) for value in selected_values]
        total = sum(max(0.0, value) for value in finite_values if value is not None)
    finite_rates = [rate for rate in rates if math.isfinite(rate)]
    maximum_rate = max(finite_rates, default=0.0)
    wet_hours = sum(
        precipitation_interval_hours(points, index)
        for index, rate in enumerate(rates)
        if math.isfinite(rate) and rate >= 0.05
    )
    weather_codes = {
        point.weather_code for point in points if point.weather_code is not None
    }
    thunder = bool(weather_codes & THUNDER_CODES)
    drizzle_hours = sum(
        precipitation_interval_hours(points, index)
        for index, (point, rate) in enumerate(zip(points, rates, strict=False))
        if point.weather_code in DRIZZLE_CODES
        or (math.isfinite(rate) and 0.05 <= rate < 0.5)
    )
    persistent_drizzle = drizzle_hours >= 6 and maximum_rate < 2.0

    if thunder:
        label = "гроза / ливень"
    elif maximum_rate >= 10.0:
        label = "ливень"
    elif persistent_drizzle:
        label = "длительная морось"
    elif total < 0.1:
        label = "сухо"
    elif total < 1.0:
        label = "следы осадков"
    elif total < 5.0:
        label = "небольшие осадки"
    elif total < 15.0:
        label = "заметный дождь"
    elif total < 30.0:
        label = "много осадков"
    else:
        label = "очень много осадков"

    return DailyPrecipitationSummary(
        total_mm=total,
        maximum_rate_mm_h=maximum_rate,
        wet_hours=wet_hours,
        label=label,
        reference_ratio=total / DAILY_PRECIPITATION_REFERENCE_MM,
        thunder=thunder,
        persistent_drizzle=persistent_drizzle,
    )


def temperature_impact_label(
    minimum_c: float | None,
    maximum_c: float | None,
) -> str | None:
    if minimum_c is None or maximum_c is None:
        return None
    if minimum_c < 0 < maximum_c:
        return "переход через 0 °C"
    if maximum_c >= 35:
        return "очень жарко"
    if maximum_c >= 30:
        return "жара"
    if minimum_c <= -20:
        return "очень холодно"
    if minimum_c <= -10:
        return "сильный мороз"
    if minimum_c < 0:
        return "заморозок"
    if maximum_c <= 5:
        return "холодно"
    return None


def wind_impact_label(
    maximum_wind_ms: float | None,
    maximum_gust_ms: float | None,
) -> str | None:
    effective = max(
        maximum_wind_ms or 0.0,
        maximum_gust_ms or 0.0,
    )
    if effective >= 20:
        return "опасные порывы"
    if effective >= 14:
        return "сильные порывы"
    if effective >= 10:
        return "сильный ветер"
    if effective >= 5:
        return "ветрено"
    return None


def humidity_impact_label(
    relative_humidity_percent: float | None,
) -> str | None:
    if relative_humidity_percent is None:
        return None
    if relative_humidity_percent >= 95:
        return "очень влажно"
    if relative_humidity_percent >= 90:
        return "влажно"
    if relative_humidity_percent < 40:
        return "сухо"
    return None


def fog_risk(
    *,
    relative_humidity_percent: float | None,
    temperature_c: float | None,
    dew_point_c: float | None,
    wind_speed_ms: float | None,
    weather_code: int | None,
) -> bool:
    if weather_code in FOG_CODES:
        return True
    if (
        relative_humidity_percent is None
        or temperature_c is None
        or dew_point_c is None
        or wind_speed_ms is None
    ):
        return False
    return (
        relative_humidity_percent >= 95
        and abs(temperature_c - dew_point_c) <= 1.5
        and wind_speed_ms <= 3.0
    )


def _as_float(value) -> float | None:
    try:
        number = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return number if number is not None and math.isfinite(number) else None
