from __future__ import annotations

import statistics
from datetime import date

from weather_to_docx.analysis.impact_scales import (
    daily_precipitation_summary,
    temperature_impact_label,
    wind_impact_label,
)
from weather_to_docx.domain.models import ForecastSeries


def daily_temperature_text(metrics) -> str:
    lows = [item.temperature_min for item in metrics if item.temperature_min is not None]
    highs = [item.temperature_max for item in metrics if item.temperature_max is not None]
    if not lows or not highs:
        return "нет данных"
    low = statistics.median(lows)
    high = statistics.median(highs)
    text = f"{low:.1f}…{high:.1f} °C".replace(".", ",")
    label = temperature_impact_label(min(lows), max(highs))
    return f"{text}\n{label}" if label else text


def daily_wind_text(metrics) -> str:
    winds = [item.wind_max for item in metrics if item.wind_max is not None]
    gusts = [item.gust_max for item in metrics if item.gust_max is not None]
    if not winds:
        return "нет данных"
    wind = statistics.median(winds)
    gust = max(gusts) if gusts else None
    text = f"до {wind:.1f} м/с".replace(".", ",")
    if gust is not None:
        text += f"\nпорывы до {gust:.1f} м/с".replace(".", ",")
    label = wind_impact_label(max(winds), gust)
    return f"{text}\n{label}" if label else text


def daily_pressure_text(metrics) -> str:
    lows = [item.pressure_min for item in metrics if item.pressure_min is not None]
    highs = [item.pressure_max for item in metrics if item.pressure_max is not None]
    if not lows or not highs:
        return "нет данных"
    low = min(lows)
    high = max(highs)
    text = f"{low:.0f}–{high:.0f} гПа"
    if high < 990:
        return f"{text}\nочень низкое"
    if low < 990:
        return f"{text}\nнизкое"
    if low > 1030:
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
    totals = [summary.total_mm for summary in summaries]
    wet_count = sum(total >= 0.1 for total in totals)
    if max(totals) < 0.1:
        return "без осадков"

    low = min(totals)
    high = max(totals)
    amount = (
        f"{statistics.median(totals):.1f} мм"
        if high - low < 0.05
        else f"{low:.1f}–{high:.1f} мм"
    ).replace(".", ",")
    most_significant = max(
        summaries,
        key=lambda item: (
            item.thunder,
            item.maximum_rate_mm_h,
            item.total_mm,
        ),
    )
    duration = (
        f" · около {most_significant.wet_hours:.0f} ч"
        if most_significant.persistent_drizzle
        else ""
    )
    return (
        f"{amount}\n{most_significant.label}{duration}\n"
        f"осадки: {wet_count}/{len(totals)} моделей"
    )
