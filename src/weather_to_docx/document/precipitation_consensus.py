from __future__ import annotations

import statistics
from datetime import date

from weather_to_docx.analysis.impact_scales import daily_precipitation_summary
from weather_to_docx.domain.models import ForecastSeries


def daily_precipitation_text(
    forecasts: list[ForecastSeries],
    day: date,
) -> str:
    """Описать осадки по медиане и поддержке моделей.

    Продолжительность или код мороси не могут понизить количественный класс
    суток: при медиане 5–15 мм основная характеристика остаётся «заметные
    осадки». Миноритарные грозовые и моросящие сценарии указываются отдельно.
    """

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
    lines = [
        _amount_text(median_total, low, high),
        _class_label(
            summaries,
            wet_count=wet_count,
            required=required,
            median_total=median_total,
        ),
        f"осадки: {wet_count}/{model_count} моделей",
    ]

    thunder_count = sum(summary.thunder for summary in summaries)
    drizzle_count = sum(summary.persistent_drizzle for summary in summaries)
    if 0 < thunder_count < required:
        lines.append(f"гроза: {thunder_count}/{model_count} моделей")
    if 0 < drizzle_count < required:
        lines.append(
            f"длительная морось: {drizzle_count}/{model_count} моделей"
        )
    return "\n".join(lines)


def _class_label(
    summaries,
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
    if sum(summary.persistent_drizzle for summary in summaries) >= required:
        return "длительная морось"
    if median_total >= 1.0:
        return "небольшие осадки"
    return "слабые осадки"


def _amount_text(median: float, low: float, high: float) -> str:
    median_text = _fmt(median)
    if high - low < max(0.5, median * 0.35):
        return f"{median_text} мм"
    return (
        f"медиана {median_text} мм\n"
        f"диапазон {_fmt(low)}–{_fmt(high)} мм"
    )


def _fmt(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _majority(model_count: int) -> int:
    if model_count <= 1:
        return 1
    return max(2, (model_count + 1) // 2)
