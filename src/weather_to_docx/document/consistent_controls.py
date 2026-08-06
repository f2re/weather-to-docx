from __future__ import annotations

import math
import statistics
from collections import Counter

from weather_to_docx.analysis.semantic_policy import strict_majority
from weather_to_docx.document.compact_generator import DailyModelMetrics
from weather_to_docx.document.styles import (
    DANGER,
    WARNING,
    set_cell_shading,
)
from weather_to_docx.document.weather_rules import (
    SUMMARY_HEAVY_PRECIPITATION,
    SUMMARY_LIGHT_PRECIPITATION,
    SUMMARY_POSSIBLE_PRECIPITATION,
    SUMMARY_RAIN,
    SUMMARY_THUNDERSTORM,
    weather_presentation,
)
from weather_to_docx.domain.models import ForecastPoint, ForecastValue
from weather_to_docx.utils.meteorology import wind_rumb

THUNDER_CODES = frozenset({95, 96, 99})
DRIZZLE_CODES = frozenset({51, 53, 55, 56, 57})
FREEZING_CODES = frozenset({56, 57, 66, 67})
SNOW_CODES = frozenset({71, 73, 75, 77, 85, 86})


def consistent_control_point(
    points: list[ForecastPoint],
    reference: ForecastPoint,
) -> ForecastPoint:
    """Собрать срок по медианам и поддержке, а не по худшей модели."""

    values: dict[str, ForecastValue] = {}
    for code in (
        "temperature_2m",
        "relative_humidity_2m",
        "pressure_msl",
        "precipitation",
        "snowfall",
        "cloud_cover",
        "visibility",
        "cape",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
    ):
        sample = _values(points, code)
        if sample:
            values[code] = ForecastValue(value=statistics.median(sample))

    day_votes = sum(point.is_day is not False for point in points)
    return ForecastPoint(
        valid_time_utc=reference.valid_time_utc,
        valid_time_local=reference.valid_time_local,
        lead_hours=reference.lead_hours,
        weather_code=_control_weather_code(points),
        is_day=day_votes >= len(points) / 2,
        values=values,
    )


def detail_precipitation_text(points: list[ForecastPoint]) -> str:
    values = _values(points, "precipitation")
    if not values:
        return "нет данных"

    wet_count = sum(value >= 0.1 for value in values)
    if wet_count == 0:
        return "нет"

    model_count = len(values)
    required = strict_majority(model_count)
    median = statistics.median(values)
    low = min(values)
    high = max(values)
    if wet_count < required:
        return (
            f"осадки возможны\n{wet_count}/{model_count} моделей с данными; "
            f"до {_fmt(high)} мм"
        )

    lines = [f"медиана {_fmt(median)} мм"]
    if high - low >= max(0.2, median * 0.5):
        lines.append(f"диапазон {_fmt(low)}–{_fmt(high)} мм")
    lines.append(f"осадки: {wet_count}/{model_count} моделей с данными")
    return "\n".join(lines)


def detail_wind_text(points: list[ForecastPoint]) -> str:
    speeds = _values(points, "wind_speed_10m")
    gusts = _values(points, "wind_gusts_10m")
    directions = _values(points, "wind_direction_10m")
    if not speeds:
        return "нет данных"

    speed = statistics.median(speeds)
    direction, resultant = _circular_mean(directions)
    if direction is None or resultant < 0.2:
        direction_text = "направление различается"
    else:
        direction_text = wind_rumb(direction, speed)
    lines = [f"{direction_text}, {_fmt(speed)} м/с"]

    if gusts:
        median_gust = statistics.median(gusts)
        lines.append(f"порывы: медиана {_fmt(median_gust)} м/с")
        if max(gusts) - min(gusts) >= 3.0:
            lines.append(
                f"по моделям {_fmt(min(gusts))}–{_fmt(max(gusts))} м/с"
            )
    return "\n".join(lines)


def shade_daily_hazard(
    cells,
    metrics: list[DailyModelMetrics],
) -> None:
    """Окрашивать сутки только при строгом большинстве моделей с данными."""

    if not metrics:
        return
    totals = [
        item.precipitation_total
        for item in metrics
        if item.precipitation_total is not None
    ]
    gusts = [item.gust_max for item in metrics if item.gust_max is not None]
    highs = [
        item.temperature_max
        for item in metrics
        if item.temperature_max is not None
    ]
    lows = [
        item.temperature_min
        for item in metrics
        if item.temperature_min is not None
    ]

    dangerous = (
        _supported(totals, lambda value: value >= 30.0)
        or _supported(gusts, lambda value: value >= 20.0)
    )
    warning = (
        _supported(totals, lambda value: value >= 15.0)
        or _supported(gusts, lambda value: value >= 14.0)
        or _supported(highs, lambda value: value >= 35.0)
        or _supported(lows, lambda value: value <= -25.0)
    )
    if dangerous:
        for cell in cells:
            set_cell_shading(cell, DANGER)
    elif warning:
        for cell in cells:
            set_cell_shading(cell, WARNING)


def _control_weather_code(points: list[ForecastPoint]) -> int:
    precipitation = [
        _number(point.raw("precipitation"))
        for point in points
    ]
    available_indices = [
        index for index, value in enumerate(precipitation) if value is not None
    ]
    if not available_indices:
        return _dry_control_code(points)

    wet_indices = [
        index
        for index in available_indices
        if (precipitation[index] or 0.0) >= 0.1
    ]
    required = strict_majority(len(available_indices))
    if not wet_indices:
        return _dry_control_code(points)
    if len(wet_indices) < required:
        return SUMMARY_POSSIBLE_PRECIPITATION

    wet_points = [points[index] for index in wet_indices]
    codes = [weather_presentation(point).code for point in wet_points]
    if sum(code in THUNDER_CODES for code in codes) >= required:
        return SUMMARY_THUNDERSTORM
    if sum(code in SNOW_CODES for code in codes) >= required:
        median_rate = statistics.median(
            _precipitation_rate(point) for point in wet_points
        )
        return 75 if median_rate >= 5.0 else 73 if median_rate >= 0.5 else 71
    if sum(code in FREEZING_CODES for code in codes) >= required:
        median_rate = statistics.median(
            _precipitation_rate(point) for point in wet_points
        )
        return 67 if median_rate >= 5.0 else 66

    rates = [_precipitation_rate(point) for point in wet_points]
    median_rate = statistics.median(rates)
    if (
        sum(code in DRIZZLE_CODES for code in codes) >= required
        and median_rate < 0.5
    ):
        return 53
    if median_rate >= 5.0:
        return SUMMARY_HEAVY_PRECIPITATION
    if median_rate >= 0.5:
        return SUMMARY_RAIN
    return SUMMARY_LIGHT_PRECIPITATION


def _dry_control_code(points: list[ForecastPoint]) -> int:
    visibility = _values(points, "visibility")
    if (
        visibility
        and sum(value < 1000 for value in visibility)
        >= strict_majority(len(visibility))
    ):
        return 45
    cloud = _values(points, "cloud_cover")
    if not cloud:
        dry_codes = [
            weather_presentation(point).code
            for point in points
            if weather_presentation(point).code in {0, 1, 2, 3}
        ]
        return _stable_mode(dry_codes) if dry_codes else 2
    median_cloud = statistics.median(cloud)
    if median_cloud >= 85:
        return 3
    if median_cloud >= 35:
        return 2
    if median_cloud >= 15:
        return 1
    return 0


def _precipitation_rate(point: ForecastPoint) -> float:
    measurement = point.measurement("precipitation")
    if measurement is None:
        return 0.0
    value = _number(measurement.value) or 0.0
    interval = measurement.accumulation_hours
    if interval is None and (
        measurement.source_start_step is not None
        and measurement.source_end_step is not None
        and measurement.source_end_step > measurement.source_start_step
    ):
        interval = measurement.source_end_step - measurement.source_start_step
    return max(0.0, value) / max(0.01, float(interval or 1.0))


def _circular_mean(values: list[float]) -> tuple[float | None, float]:
    if not values:
        return None, 0.0
    radians = [math.radians(value % 360) for value in values]
    x = statistics.fmean(math.cos(value) for value in radians)
    y = statistics.fmean(math.sin(value) for value in radians)
    resultant = math.hypot(x, y)
    if resultant < 1e-9:
        return None, resultant
    return math.degrees(math.atan2(y, x)) % 360, resultant


def _stable_mode(codes: list[int]) -> int:
    counts = Counter(codes)
    best = max(counts.values())
    candidates = sorted(
        code for code, count in counts.items() if count == best
    )
    return candidates[(len(candidates) - 1) // 2]


def _values(points: list[ForecastPoint], code: str) -> list[float]:
    values = []
    for point in points:
        value = _number(point.raw(code))
        if value is not None:
            values.append(value)
    return values


def _supported(values: list[float], predicate) -> bool:
    if not values:
        return False
    return (
        sum(predicate(value) for value in values)
        >= strict_majority(len(values))
    )


def _number(value) -> float | None:
    try:
        number = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return (
        number
        if number is not None and math.isfinite(number)
        else None
    )


def _fmt(value: float, precision: int = 1) -> str:
    return f"{value:.{precision}f}".replace(".", ",")


def _majority(model_count: int) -> int:
    """Backward-compatible name for the strict-majority policy."""

    return strict_majority(model_count)
