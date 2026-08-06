from __future__ import annotations

import math
import statistics
from collections import Counter
from datetime import date, datetime

from weather_to_docx.analysis.consensus import RiskSignal
from weather_to_docx.analysis.impact_scales import (
    DailyPrecipitationSummary,
    daily_precipitation_summary,
    temperature_impact_label,
)
from weather_to_docx.document.compact_generator import DailyModelMetrics
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
PRECIPITATION_CODES = frozenset(
    {
        51,
        53,
        55,
        56,
        57,
        61,
        63,
        65,
        66,
        67,
        71,
        73,
        75,
        77,
        80,
        81,
        82,
        85,
        86,
        95,
        96,
        99,
    }
)
DRIZZLE_CODES = frozenset({51, 53, 55, 56, 57})
HEAVY_PRECIPITATION_CODES = frozenset({65, 67, 75, 82, 86, 96, 99})


def consistent_daily_model_metrics(
    forecast: ForecastSeries,
    day: date,
) -> DailyModelMetrics | None:
    """Сформировать суточные метрики одной модели из тех же данных, что и график."""

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
        precipitation_total=(precipitation.total_mm if precipitation else None),
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

    code = _consensus_weather_code(metrics)
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
        valid_time_utc=local_time.astimezone(),
        valid_time_local=local_time,
        weather_code=code,
        is_day=True,
        values={},
    )


def daily_temperature_text(metrics: list[DailyModelMetrics]) -> str:
    lows = [item.temperature_min for item in metrics if item.temperature_min is not None]
    highs = [item.temperature_max for item in metrics if item.temperature_max is not None]
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

    model_count = len(metrics)
    required = _majority(model_count)
    median_wind = statistics.median(winds)
    lines = [f"до {median_wind:.1f} м/с".replace(".", ",")]

    if gusts:
        median_gust = statistics.median(gusts)
        lines.append(f"порывы: медиана {median_gust:.1f} м/с".replace(".", ","))
        if max(gusts) - min(gusts) >= 3.0:
            spread = f"{min(gusts):.1f}–{max(gusts):.1f}".replace(".", ",")
            lines.append(f"по моделям {spread} м/с")

    dangerous_gusts = sum(value >= 20.0 for value in gusts)
    strong_gusts = sum(value >= 14.0 for value in gusts)
    strong_wind = sum(value >= 10.0 for value in winds)
    breezy = sum(value >= 5.0 for value in winds)

    if dangerous_gusts >= required:
        lines.append("опасные порывы")
    elif strong_gusts >= required:
        lines.append("сильные порывы")
    elif strong_wind >= required:
        lines.append("сильный ветер")
    elif breezy >= required:
        lines.append("ветрено")
    elif strong_gusts:
        lines.append(f"порывы ≥14 м/с: {strong_gusts}/{model_count} моделей")

    return "\n".join(lines)


def daily_pressure_text(metrics: list[DailyModelMetrics]) -> str:
    lows = [item.pressure_min for item in metrics if item.pressure_min is not None]
    highs = [item.pressure_max for item in metrics if item.pressure_max is not None]
    if not lows or not highs:
        return "нет данных"

    low = min(lows)
    high = max(highs)
    text = f"{low:.0f}–{high:.0f} гПа"
    required = _majority(len(metrics))
    low_support = sum(value < 990 for value in lows)
    high_support = sum(value > 1030 for value in highs)
    if low_support >= required:
        return f"{text}\nнизкое"
    if high_support >= required:
        return f"{text}\nвысокое"
    return text


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

    model_count = len(summaries)
    required = _majority(model_count)
    totals = [summary.total_mm for summary in summaries]
    wet_count = sum(total >= 0.1 for total in totals)
    if wet_count == 0:
        return "без осадков"

    median_total = statistics.median(totals)
    low = min(totals)
    high = max(totals)
    lines = [_precipitation_amount_text(median_total, low, high)]

    thunder_count = sum(summary.thunder for summary in summaries)
    drizzle_count = sum(summary.persistent_drizzle for summary in summaries)
    label = _consensus_precipitation_label(
        summaries,
        wet_count=wet_count,
        required=required,
        median_total=median_total,
    )
    lines.append(label)
    lines.append(f"осадки: {wet_count}/{model_count} моделей")

    if 0 < thunder_count < required:
        lines.append(f"гроза: {thunder_count}/{model_count} моделей")
    if 0 < drizzle_count < required:
        lines.append(f"длительная морось: {drizzle_count}/{model_count} моделей")
    return "\n".join(lines)


def build_consistent_risk_signals(
    forecasts: list[ForecastSeries],
    ensembles: list[ForecastSeries],
    report_dates: list[date],
    *,
    maximum: int = 3,
) -> list[RiskSignal]:
    """Строить ключевые риски только по подтверждённым сценариям."""

    signals: list[RiskSignal] = []
    model_count = len(forecasts)
    if not model_count:
        return signals
    required = _majority(model_count)

    for day in report_dates:
        model_data = []
        for forecast in forecasts:
            points = _points_for_day(forecast, day)
            summary = daily_precipitation_summary(forecast, day)
            if points:
                model_data.append((forecast, points, summary))
        if not model_data:
            continue

        thunder = [item for item in model_data if item[2] and item[2].thunder]
        if len(thunder) >= required:
            points = [point for _, values, _ in thunder for point in values]
            signals.append(
                _risk_signal(
                    phenomenon="ГРОЗА",
                    day=day,
                    points=points,
                    value_text=f"подтверждают {len(thunder)} из {model_count} моделей",
                    support_count=len(thunder),
                    model_count=model_count,
                    ensemble_probability=None,
                    severity=90,
                )
            )

        precipitation = [item for item in model_data if item[2] is not None]
        summaries = [item[2] for item in precipitation if item[2] is not None]
        if summaries:
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
            ensemble_probability = _ensemble_probability(ensembles, day, 5.0)
            if (
                len(strong) >= required
                and median_total >= 15.0
                and (ensemble_probability is None or ensemble_probability >= 30.0)
            ):
                representative = min(
                    strong,
                    key=lambda item: abs(item[2].total_mm - median_total),
                )
                value = _risk_precipitation_value(median_total, min(totals), max(totals))
                signals.append(
                    _risk_signal(
                        phenomenon="СИЛЬНЫЕ ОСАДКИ",
                        day=day,
                        points=representative[1],
                        value_text=value,
                        support_count=len(strong),
                        model_count=model_count,
                        ensemble_probability=ensemble_probability,
                        severity=85 if median_total < 30 else 95,
                        peak_code="precipitation",
                    )
                )

        gust_data = []
        for forecast, points, _ in model_data:
            gust = _maximum(points, "wind_gusts_10m")
            if gust is not None and gust >= 14.0:
                gust_data.append((forecast, points, gust))
        if len(gust_data) >= required:
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
                    value_text=f"медиана {median_gust:.1f} м/с".replace(".", ","),
                    support_count=len(gust_data),
                    model_count=model_count,
                    ensemble_probability=None,
                    severity=90 if median_gust >= 20 else 72,
                    peak_code="wind_gusts_10m",
                )
            )

        heat = []
        cold = []
        for forecast, points, _ in model_data:
            maximum = _maximum(points, "temperature_2m")
            minimum = _minimum(points, "temperature_2m")
            if maximum is not None and maximum >= 30.0:
                heat.append((forecast, points, maximum))
            if minimum is not None and minimum <= -15.0:
                cold.append((forecast, points, minimum))
        if len(heat) >= required:
            median_heat = statistics.median(item[2] for item in heat)
            representative = min(heat, key=lambda item: abs(item[2] - median_heat))
            signals.append(
                _risk_signal(
                    phenomenon="ЖАРА",
                    day=day,
                    points=representative[1],
                    value_text=f"медиана {median_heat:.1f} °C".replace(".", ","),
                    support_count=len(heat),
                    model_count=model_count,
                    ensemble_probability=None,
                    severity=68,
                    peak_code="temperature_2m",
                )
            )
        if len(cold) >= required:
            median_cold = statistics.median(item[2] for item in cold)
            representative = min(cold, key=lambda item: abs(item[2] - median_cold))
            signals.append(
                _risk_signal(
                    phenomenon="СИЛЬНЫЙ МОРОЗ",
                    day=day,
                    points=representative[1],
                    value_text=f"медиана {median_cold:.1f} °C".replace(".", ","),
                    support_count=len(cold),
                    model_count=model_count,
                    ensemble_probability=None,
                    severity=68,
                    peak_code="temperature_2m",
                    minimum_peak=True,
                )
            )

    signals.sort(
        key=lambda signal: (
            signal.severity,
            signal.support_count / max(1, signal.model_count),
            signal.ensemble_probability or 0.0,
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

    model_count = len(metrics)
    required = _majority(model_count)
    wet = [
        item
        for item in metrics
        if item.precipitation_total is not None and item.precipitation_total >= 0.1
    ]
    if not wet:
        return _stable_mode([item.weather_code for item in metrics])
    if len(wet) < required:
        return SUMMARY_POSSIBLE_PRECIPITATION

    thunder_count = sum(item.weather_code in THUNDER_CODES for item in wet)
    if thunder_count >= required:
        return SUMMARY_THUNDERSTORM

    totals = [item.precipitation_total or 0.0 for item in metrics]
    median_total = statistics.median(totals)
    heavy_count = sum(item.weather_code in HEAVY_PRECIPITATION_CODES for item in wet)
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

    thunder_count = sum(summary.thunder for summary in summaries)
    drizzle_count = sum(summary.persistent_drizzle for summary in summaries)
    if thunder_count >= required:
        return "гроза с осадками"
    if drizzle_count >= required:
        return "длительная морось"
    if median_total >= 30.0:
        return "очень много осадков"
    if median_total >= 15.0:
        return "много осадков"
    if median_total >= 5.0:
        return "заметные осадки"
    if median_total >= 1.0:
        return "небольшие осадки"
    return "слабые осадки"


def _precipitation_amount_text(median: float, low: float, high: float) -> str:
    median_text = f"{median:.1f}".replace(".", ",")
    if high - low < max(0.5, median * 0.35):
        return f"{median_text} мм"
    low_text = f"{low:.1f}".replace(".", ",")
    high_text = f"{high:.1f}".replace(".", ",")
    return f"медиана {median_text} мм\nдиапазон {low_text}–{high_text} мм"


def _risk_precipitation_value(median: float, low: float, high: float) -> str:
    median_text = f"{median:.1f}".replace(".", ",")
    low_text = f"{low:.1f}".replace(".", ",")
    high_text = f"{high:.1f}".replace(".", ",")
    return f"медиана {median_text} мм/сут; диапазон {low_text}–{high_text} мм"


def _risk_signal(
    *,
    phenomenon: str,
    day: date,
    points: list[ForecastPoint],
    value_text: str,
    support_count: int,
    model_count: int,
    ensemble_probability: float | None,
    severity: int,
    peak_code: str | None = None,
    minimum_peak: bool = False,
) -> RiskSignal:
    support_ratio = support_count / max(1, model_count)
    if support_ratio >= 0.67 and (
        ensemble_probability is None or ensemble_probability >= 40.0
    ):
        scenario = "Устойчивый сигнал"
        confidence = "высокая"
    else:
        scenario = "Вероятный сигнал"
        confidence = "средняя"

    ordered = sorted(points, key=lambda point: point.valid_time_local)
    peak = None
    if peak_code:
        candidates = [
            (point, _number(point.raw(peak_code)))
            for point in ordered
            if _number(point.raw(peak_code)) is not None
        ]
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
        scenario=scenario,
        confidence=confidence,
        day=day,
        start_local=ordered[0].valid_time_local if ordered else None,
        end_local=ordered[-1].valid_time_local if ordered else None,
        peak_local=peak.valid_time_local if peak else None,
        value_text=value_text,
        support_count=support_count,
        model_count=model_count,
        ensemble_probability=ensemble_probability,
        severity=severity,
    )


def _ensemble_probability(
    ensembles: list[ForecastSeries],
    day: date,
    threshold_mm: float,
) -> float | None:
    token = f"{threshold_mm:g}".replace(".", "p")
    code = f"precipitation_probability_ge_{token}mm"
    values = []
    coverages = []
    for forecast in ensembles:
        for point in _points_for_day(forecast, day):
            value = _number(point.raw(code))
            if value is not None:
                values.append(value)
                coverage = _number(point.raw("ensemble_member_coverage"))
                if coverage is not None:
                    coverages.append(coverage)
    if not values:
        return None
    probability = max(values)
    if coverages and min(coverages) < 80.0:
        probability *= min(coverages) / 100.0
    return probability


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
    candidates = [code for code, count in counts.items() if count == best_count]
    if len(candidates) == 1:
        return candidates[0]
    ordered = sorted(candidates)
    return ordered[(len(ordered) - 1) // 2]


def _points_for_day(forecast: ForecastSeries, day: date) -> list[ForecastPoint]:
    return [point for point in forecast.points if point.valid_time_local.date() == day]


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
    return number if number is not None and math.isfinite(number) else None


def _majority(model_count: int) -> int:
    return 1 if model_count <= 1 else max(2, math.ceil(model_count / 2))
