from __future__ import annotations

import math
import statistics
from collections import Counter
from datetime import UTC, date

from weather_to_docx.analysis.consensus import RiskSignal
from weather_to_docx.analysis.impact_scales import (
    DailyPrecipitationSummary,
    daily_precipitation_summary,
    temperature_impact_label,
)
from weather_to_docx.analysis.semantic_policy import (
    strict_majority,
    support_assessment,
)
from weather_to_docx.document.compact_generator import (
    AGREEMENT_HIGH,
    AGREEMENT_LOW,
    AGREEMENT_MEDIUM,
    DailyModelMetrics,
)
from weather_to_docx.document.weather_rules import (
    SUMMARY_HEAVY_PRECIPITATION,
    SUMMARY_LIGHT_PRECIPITATION,
    SUMMARY_POSSIBLE_PRECIPITATION,
    SUMMARY_RAIN,
    SUMMARY_THUNDERSTORM,
    weather_presentation,
)
from weather_to_docx.domain.models import ForecastPoint, ForecastSeries

THUNDER_CODES = frozenset({95, 96, 99})
DRIZZLE_CODES = frozenset({51, 53, 55, 56, 57})
HEAVY_PRECIPITATION_CODES = frozenset({65, 67, 75, 82, 86, 96, 99})


def consistent_daily_model_metrics(
    forecast: ForecastSeries,
    day: date,
) -> DailyModelMetrics | None:
    """Сформировать суточные метрики одной модели из данных метеограммы."""

    points = _points_for_day(forecast, day)
    if not points:
        return None

    temperatures = _values(points, "temperature_2m")
    winds = _values(points, "wind_speed_10m")
    gusts = _values(points, "wind_gusts_10m")
    pressure = _values(points, "pressure_msl")
    precipitation = daily_precipitation_summary(forecast, day)

    return DailyModelMetrics(
        source=forecast,
        weather_code=_daily_model_weather_code(points, precipitation),
        temperature_min=min(temperatures) if temperatures else None,
        temperature_max=max(temperatures) if temperatures else None,
        precipitation_total=precipitation.total_mm if precipitation else None,
        wind_max=max(winds) if winds else None,
        gust_max=max(gusts) if gusts else None,
        pressure_min=min(pressure) if pressure else None,
        pressure_max=max(pressure) if pressure else None,
    )


def consistent_daily_presentation_point(
    metrics: list[DailyModelMetrics],
    day: date,
) -> ForecastPoint:
    """Выбрать сводное явление без повышения опасности из-за одной модели."""

    if not metrics:
        raise ValueError("Нет модельных метрик для суточной характеристики")

    local_time = min(
        (
            point.valid_time_local
            for metric in metrics
            for point in metric.source.points
            if point.valid_time_local.date() == day
        ),
        key=lambda value: abs(value.hour - 12),
    )
    return ForecastPoint(
        valid_time_utc=local_time.astimezone(UTC),
        valid_time_local=local_time,
        weather_code=_consensus_weather_code(metrics),
        is_day=True,
        values={},
    )


def daily_temperature_text(metrics: list[DailyModelMetrics]) -> str:
    lows = [
        item.temperature_min
        for item in metrics
        if item.temperature_min is not None
    ]
    highs = [
        item.temperature_max
        for item in metrics
        if item.temperature_max is not None
    ]
    if not lows or not highs:
        return "нет данных"

    low = statistics.median(lows)
    high = statistics.median(highs)
    text = f"{low:.1f}…{high:.1f} °C".replace(".", ",")
    label = temperature_impact_label(low, high)
    return f"{text}\n{label}" if label else text


def daily_wind_text(metrics: list[DailyModelMetrics]) -> str:
    winds = [item.wind_max for item in metrics if item.wind_max is not None]
    gusts = [item.gust_max for item in metrics if item.gust_max is not None]
    if not winds:
        return "нет данных"

    wind_available = len(winds)
    wind_required = strict_majority(wind_available)
    median_wind = statistics.median(winds)
    lines = [f"до {median_wind:.1f} м/с".replace(".", ",")]

    if gusts:
        median_gust = statistics.median(gusts)
        lines.append(
            f"порывы: медиана {median_gust:.1f} м/с".replace(".", ",")
        )
        if max(gusts) - min(gusts) >= 3.0:
            spread = f"{min(gusts):.1f}–{max(gusts):.1f}".replace(".", ",")
            lines.append(f"по моделям {spread} м/с")

    dangerous_gusts = sum(value >= 20.0 for value in gusts)
    strong_gusts = sum(value >= 14.0 for value in gusts)
    strong_wind = sum(value >= 10.0 for value in winds)
    breezy = sum(value >= 5.0 for value in winds)
    gust_required = strict_majority(len(gusts)) if gusts else 1

    if gusts and dangerous_gusts >= gust_required:
        lines.append("опасные порывы")
    elif gusts and strong_gusts >= gust_required:
        lines.append("сильные порывы")
    elif strong_wind >= wind_required:
        lines.append("сильный ветер")
    elif breezy >= wind_required:
        lines.append("ветрено")
    elif strong_gusts:
        lines.append(
            f"порывы ≥14 м/с: {strong_gusts}/{len(gusts)} моделей с данными"
        )

    missing = len(metrics) - max(len(winds), len(gusts))
    if missing > 0:
        lines.append(f"нет данных: {missing}/{len(metrics)} моделей")
    return "\n".join(lines)


def daily_pressure_text(metrics: list[DailyModelMetrics]) -> str:
    lows = [item.pressure_min for item in metrics if item.pressure_min is not None]
    highs = [
        item.pressure_max
        for item in metrics
        if item.pressure_max is not None
    ]
    if not lows or not highs:
        return "нет данных"

    central_low = statistics.median(lows)
    central_high = statistics.median(highs)
    lines = [f"{central_low:.0f}–{central_high:.0f} гПа"]

    envelope_low = min(lows)
    envelope_high = max(highs)
    if (
        abs(envelope_low - central_low) >= 2.0
        or abs(envelope_high - central_high) >= 2.0
    ):
        lines.append(
            f"по моделям {envelope_low:.0f}–{envelope_high:.0f} гПа"
        )

    required = strict_majority(min(len(lows), len(highs)))
    if sum(value < 990 for value in lows) >= required:
        lines.append("низкое")
    elif sum(value > 1030 for value in highs) >= required:
        lines.append("высокое")

    missing = len(metrics) - min(len(lows), len(highs))
    if missing > 0:
        lines.append(f"нет данных: {missing}/{len(metrics)} моделей")
    return "\n".join(lines)


def daily_precipitation_metrics_text(
    metrics: list[DailyModelMetrics],
) -> str:
    """Compatibility text for the compact generator from prepared metrics."""

    totals = [
        item.precipitation_total
        for item in metrics
        if item.precipitation_total is not None
    ]
    if not totals:
        return "нет данных"

    wet_count = sum(total >= 0.1 for total in totals)
    if wet_count == 0:
        text = "без осадков"
    else:
        median_total = statistics.median(totals)
        text = "\n".join(
            (
                _precipitation_amount_text(
                    median_total,
                    min(totals),
                    max(totals),
                ),
                f"осадки: {wet_count}/{len(totals)} моделей с данными",
            )
        )
    missing = len(metrics) - len(totals)
    return (
        f"{text}\nнет данных: {missing}/{len(metrics)} моделей"
        if missing > 0
        else text
    )


def daily_precipitation_text(
    forecasts: list[ForecastSeries],
    day: date,
) -> str:
    summaries = [
        summary
        for forecast in forecasts
        if (summary := daily_precipitation_summary(forecast, day)) is not None
    ]
    if not summaries:
        return "нет данных"

    selected_count = len(forecasts)
    available_count = len(summaries)
    required = strict_majority(available_count)
    totals = [summary.total_mm for summary in summaries]
    wet_count = sum(total >= 0.1 for total in totals)
    if wet_count == 0:
        lines = ["без осадков"]
    else:
        median_total = statistics.median(totals)
        lines = [
            _precipitation_amount_text(
                median_total,
                min(totals),
                max(totals),
            ),
            _consensus_precipitation_label(
                summaries,
                wet_count=wet_count,
                required=required,
                median_total=median_total,
            ),
            f"осадки: {wet_count}/{available_count} моделей с данными",
        ]

        thunder_count = sum(summary.thunder for summary in summaries)
        drizzle_count = sum(summary.persistent_drizzle for summary in summaries)
        if 0 < thunder_count < required:
            lines.append(
                f"гроза: {thunder_count}/{available_count} моделей"
            )
        if 0 < drizzle_count < required:
            lines.append(
                "длительная морось: "
                f"{drizzle_count}/{available_count} моделей"
            )

    missing = selected_count - available_count
    if missing > 0:
        lines.append(f"нет данных об осадках: {missing}/{selected_count} моделей")
    return "\n".join(lines)


def daily_agreement_from_metrics(
    metrics: list[DailyModelMetrics],
) -> tuple[str, str]:
    if len(metrics) <= 1:
        return "не оценивается", AGREEMENT_MEDIUM

    highs = [
        item.temperature_max
        for item in metrics
        if item.temperature_max is not None
    ]
    totals = [
        item.precipitation_total
        for item in metrics
        if item.precipitation_total is not None
    ]
    codes = [item.weather_code for item in metrics]
    weather_ratio = max(Counter(codes).values()) / len(codes)
    temperature_spread = max(highs) - min(highs) if len(highs) >= 2 else 0.0
    wet = [value >= 0.1 for value in totals]
    precipitation_agrees = len(wet) >= 2 and (all(wet) or not any(wet))

    if (
        weather_ratio >= 0.67
        and temperature_spread <= 2.5
        and precipitation_agrees
    ):
        return "высокая", AGREEMENT_HIGH
    if weather_ratio >= 0.5 and temperature_spread <= 4.5:
        return "средняя", AGREEMENT_MEDIUM
    return "низкая", AGREEMENT_LOW


def build_highlights(
    forecasts: list[ForecastSeries],
    report_dates: list[date],
    maximum: int,
) -> list[str]:
    signals = build_consistent_risk_signals(
        forecasts,
        [],
        report_dates,
        maximum=maximum,
    )
    return [
        f"{signal.phenomenon.lower()} {signal.day:%d.%m}: {signal.value_text}"
        for signal in signals
    ]


def build_consistent_risk_signals(
    forecasts: list[ForecastSeries],
    ensembles: list[ForecastSeries],
    report_dates: list[date],
    *,
    maximum: int = 3,
) -> list[RiskSignal]:
    """Строить риски по количественным данным и строгому большинству."""

    del ensembles
    signals: list[RiskSignal] = []
    if not forecasts:
        return signals

    for day in report_dates:
        model_data = []
        for forecast in forecasts:
            points = _points_for_day(forecast, day)
            if points:
                summary = daily_precipitation_summary(forecast, day)
                model_data.append((forecast, points, summary))
        if not model_data:
            continue

        available_models = len(model_data)
        required = strict_majority(available_models)

        thunder = [
            item for item in model_data if item[2] and item[2].thunder
        ]
        if len(thunder) >= required:
            points = [
                point
                for _, values, _ in thunder
                for point in values
                if point.weather_code in THUNDER_CODES
            ]
            signals.append(
                _risk_signal(
                    phenomenon="ГРОЗА",
                    day=day,
                    points=points,
                    value_text=(
                        f"подтверждают {len(thunder)} из "
                        f"{available_models} моделей с данными"
                    ),
                    support_count=len(thunder),
                    model_count=available_models,
                    severity=90,
                )
            )

        precipitation = [
            item for item in model_data if item[2] is not None
        ]
        summaries = [
            item[2] for item in precipitation if item[2] is not None
        ]
        if summaries:
            precipitation_required = strict_majority(len(summaries))
            totals = [summary.total_mm for summary in summaries]
            median_total = statistics.median(totals)
            strong = [
                item
                for item in precipitation
                if item[2] is not None
                and (
                    item[2].total_mm >= 15.0
                    or item[2].maximum_rate_mm_h >= 5.0
                )
            ]
            if (
                len(strong) >= precipitation_required
                and median_total >= 15.0
            ):
                representative = min(
                    strong,
                    key=lambda item: abs(
                        item[2].total_mm - median_total
                    ),
                )
                signals.append(
                    _risk_signal(
                        phenomenon="СИЛЬНЫЕ ОСАДКИ",
                        day=day,
                        points=representative[1],
                        value_text=_risk_precipitation_value(
                            median_total,
                            min(totals),
                            max(totals),
                        ),
                        support_count=len(strong),
                        model_count=len(summaries),
                        severity=85 if median_total < 30 else 95,
                        peak_code="precipitation",
                    )
                )

        gust_data = []
        for forecast, points, _ in model_data:
            gust = _maximum(points, "wind_gusts_10m")
            if gust is not None and gust >= 14.0:
                gust_data.append((forecast, points, gust))
        gust_available = sum(
            _maximum(points, "wind_gusts_10m") is not None
            for _, points, _ in model_data
        )
        if (
            gust_available > 0
            and len(gust_data) >= strict_majority(gust_available)
        ):
            median_gust = statistics.median(item[2] for item in gust_data)
            representative = min(
                gust_data,
                key=lambda item: abs(item[2] - median_gust),
            )
            signals.append(
                _risk_signal(
                    phenomenon="СИЛЬНЫЕ ПОРЫВЫ",
                    day=day,
                    points=representative[1],
                    value_text=(
                        f"медиана {median_gust:.1f} м/с".replace(".", ",")
                    ),
                    support_count=len(gust_data),
                    model_count=gust_available,
                    severity=90 if median_gust >= 20 else 72,
                    peak_code="wind_gusts_10m",
                )
            )

        heat = []
        cold = []
        temperature_available = 0
        for forecast, points, _ in model_data:
            maximum_temperature = _maximum(points, "temperature_2m")
            minimum_temperature = _minimum(points, "temperature_2m")
            if maximum_temperature is not None or minimum_temperature is not None:
                temperature_available += 1
            if (
                maximum_temperature is not None
                and maximum_temperature >= 30.0
            ):
                heat.append((forecast, points, maximum_temperature))
            if (
                minimum_temperature is not None
                and minimum_temperature <= -15.0
            ):
                cold.append((forecast, points, minimum_temperature))

        if (
            temperature_available > 0
            and len(heat) >= strict_majority(temperature_available)
        ):
            median_heat = statistics.median(item[2] for item in heat)
            representative = min(
                heat,
                key=lambda item: abs(item[2] - median_heat),
            )
            signals.append(
                _risk_signal(
                    phenomenon="ЖАРА",
                    day=day,
                    points=representative[1],
                    value_text=(
                        f"медиана {median_heat:.1f} °C".replace(".", ",")
                    ),
                    support_count=len(heat),
                    model_count=temperature_available,
                    severity=68,
                    peak_code="temperature_2m",
                )
            )
        if (
            temperature_available > 0
            and len(cold) >= strict_majority(temperature_available)
        ):
            median_cold = statistics.median(item[2] for item in cold)
            representative = min(
                cold,
                key=lambda item: abs(item[2] - median_cold),
            )
            signals.append(
                _risk_signal(
                    phenomenon="СИЛЬНЫЙ МОРОЗ",
                    day=day,
                    points=representative[1],
                    value_text=(
                        f"медиана {median_cold:.1f} °C".replace(".", ",")
                    ),
                    support_count=len(cold),
                    model_count=temperature_available,
                    severity=68,
                    peak_code="temperature_2m",
                    minimum_peak=True,
                )
            )

    signals.sort(
        key=lambda signal: (
            signal.severity,
            signal.support_count / max(1, signal.model_count),
        ),
        reverse=True,
    )
    return signals[:maximum]


def _daily_model_weather_code(
    points: list[ForecastPoint],
    precipitation: DailyPrecipitationSummary | None,
) -> int:
    if precipitation is None or precipitation.total_mm < 0.1:
        return _dry_weather_code(points)
    if precipitation.thunder:
        return 95
    if precipitation.persistent_drizzle:
        return 53
    rate = precipitation.maximum_rate_mm_h
    if rate >= 10.0:
        return 82
    if rate >= 5.0:
        return 65
    if rate >= 2.0:
        return 63
    if rate >= 0.5:
        return 61
    return 51


def _consensus_weather_code(metrics: list[DailyModelMetrics]) -> int:
    if len(metrics) == 1:
        return metrics[0].weather_code

    wet = [
        item
        for item in metrics
        if item.precipitation_total is not None
        and item.precipitation_total >= 0.1
    ]
    available = [
        item
        for item in metrics
        if item.precipitation_total is not None
    ]
    if not available:
        return _stable_mode([item.weather_code for item in metrics])
    required = strict_majority(len(available))
    if not wet:
        return _stable_mode([item.weather_code for item in metrics])
    if len(wet) < required:
        return SUMMARY_POSSIBLE_PRECIPITATION

    if sum(item.weather_code in THUNDER_CODES for item in wet) >= required:
        return SUMMARY_THUNDERSTORM

    totals = [item.precipitation_total or 0.0 for item in available]
    median_total = statistics.median(totals)
    heavy_count = sum(
        item.weather_code in HEAVY_PRECIPITATION_CODES
        or (item.precipitation_total or 0.0) >= 15.0
        for item in wet
    )
    drizzle_count = sum(item.weather_code in DRIZZLE_CODES for item in wet)
    if median_total >= 15.0 and heavy_count >= required:
        return SUMMARY_HEAVY_PRECIPITATION
    if median_total >= 1.0:
        return SUMMARY_RAIN
    if drizzle_count >= required:
        return 53
    return SUMMARY_LIGHT_PRECIPITATION


def _consensus_precipitation_label(
    summaries: list[DailyPrecipitationSummary],
    *,
    wet_count: int,
    required: int,
    median_total: float,
) -> str:
    if wet_count < required:
        return "осадки возможны"
    if sum(summary.thunder for summary in summaries) >= required:
        return "гроза с осадками"
    if median_total >= 30.0:
        return "очень много осадков"
    if median_total >= 15.0:
        return "много осадков"
    if median_total >= 5.0:
        return "заметные осадки"
    if (
        sum(summary.persistent_drizzle for summary in summaries) >= required
        and median_total < 5.0
    ):
        return "длительная морось"
    if median_total >= 1.0:
        return "небольшие осадки"
    return "слабые осадки"


def _precipitation_amount_text(median: float, low: float, high: float) -> str:
    median_text = f"{median:.1f}".replace(".", ",")
    if high - low < max(0.5, median * 0.35):
        return f"{median_text} мм"
    low_text = f"{low:.1f}".replace(".", ",")
    high_text = f"{high:.1f}".replace(".", ",")
    return (
        f"медиана {median_text} мм\n"
        f"диапазон {low_text}–{high_text} мм"
    )


def _risk_precipitation_value(
    median: float,
    low: float,
    high: float,
) -> str:
    median_text = f"{median:.1f}".replace(".", ",")
    low_text = f"{low:.1f}".replace(".", ",")
    high_text = f"{high:.1f}".replace(".", ",")
    return (
        f"медиана {median_text} мм/сут; "
        f"диапазон {low_text}–{high_text} мм"
    )


def _risk_signal(
    *,
    phenomenon: str,
    day: date,
    points: list[ForecastPoint],
    value_text: str,
    support_count: int,
    model_count: int,
    severity: int,
    peak_code: str | None = None,
    minimum_peak: bool = False,
) -> RiskSignal:
    assessment = support_assessment(support_count, model_count)
    ordered = sorted(points, key=lambda point: point.valid_time_local)
    peak = None
    if peak_code:
        candidates = []
        for point in ordered:
            value = _number(point.raw(peak_code))
            if value is not None:
                candidates.append((point, value))
        if candidates:
            peak = (
                min(candidates, key=lambda item: item[1])[0]
                if minimum_peak
                else max(candidates, key=lambda item: item[1])[0]
            )
    if peak is None and ordered:
        peak = ordered[len(ordered) // 2]

    return RiskSignal(
        phenomenon=phenomenon,
        scenario=assessment.scenario,
        confidence=assessment.confidence,
        day=day,
        start_local=ordered[0].valid_time_local if ordered else None,
        end_local=ordered[-1].valid_time_local if ordered else None,
        peak_local=peak.valid_time_local if peak else None,
        value_text=value_text,
        support_count=support_count,
        model_count=model_count,
        ensemble_probability=None,
        severity=severity,
    )


def _dry_weather_code(points: list[ForecastPoint]) -> int:
    noon = min(points, key=lambda point: abs(point.valid_time_local.hour - 12))
    code = weather_presentation(noon).code
    if code in {45, 48}:
        return code
    cloud = _number(noon.raw("cloud_cover"))
    if cloud is None:
        cloud = _median(_values(points, "cloud_cover"))
    if cloud is None:
        return code if code in {0, 1, 2, 3} else 2
    if cloud >= 85.0:
        return 3
    if cloud >= 35.0:
        return 2
    if cloud >= 15.0:
        return 1
    return 0


def _stable_mode(codes: list[int]) -> int:
    counts = Counter(codes)
    best_count = max(counts.values())
    candidates = sorted(
        code for code, count in counts.items() if count == best_count
    )
    return candidates[(len(candidates) - 1) // 2]


def _points_for_day(
    forecast: ForecastSeries,
    day: date,
) -> list[ForecastPoint]:
    return [
        point
        for point in forecast.points
        if point.valid_time_local.date() == day
    ]


def _values(points: list[ForecastPoint], code: str) -> list[float]:
    values = []
    for point in points:
        value = _number(point.raw(code))
        if value is not None:
            values.append(value)
    return values


def _maximum(points: list[ForecastPoint], code: str) -> float | None:
    values = _values(points, code)
    return max(values) if values else None


def _minimum(points: list[ForecastPoint], code: str) -> float | None:
    values = _values(points, code)
    return min(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


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


def _majority(model_count: int) -> int:
    """Backward-compatible name for the strict-majority policy."""

    return strict_majority(model_count)


__all__ = [
    "build_consistent_risk_signals",
    "build_highlights",
    "consistent_daily_model_metrics",
    "consistent_daily_presentation_point",
    "daily_agreement_from_metrics",
    "daily_precipitation_metrics_text",
    "daily_precipitation_text",
    "daily_pressure_text",
    "daily_temperature_text",
    "daily_wind_text",
]
