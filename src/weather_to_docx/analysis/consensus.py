from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from weather_to_docx.domain.models import ForecastPoint, ForecastSeries

THUNDER_CODES = frozenset({95, 96, 99})
SIGNIFICANT_WEATHER_CODES = frozenset(
    {45, 48, 55, 57, 63, 65, 66, 67, 73, 75, 77, 81, 82, 85, 86, 95, 96, 99}
)


@dataclass(frozen=True, slots=True)
class DailyAgreement:
    overall: str
    score: float
    temperature: str
    precipitation: str
    wind: str
    phenomenon: str
    note: str


@dataclass(frozen=True, slots=True)
class RiskSignal:
    phenomenon: str
    scenario: str
    confidence: str
    day: date
    start_local: datetime | None
    end_local: datetime | None
    peak_local: datetime | None
    value_text: str
    support_count: int
    model_count: int
    ensemble_probability: float | None
    severity: int

    @property
    def support_text(self) -> str:
        return f"{self.support_count} из {self.model_count} моделей"

    @property
    def time_text(self) -> str:
        if self.start_local is None:
            return self.day.strftime("%d.%m")
        if self.end_local is None or self.end_local == self.start_local:
            return self.start_local.strftime("%d.%m, %H:%M")
        return (
            f"{self.start_local:%d.%m, %H:%M}–"
            f"{self.end_local:%H:%M}"
        )


def daily_precipitation_total(points: Iterable[ForecastPoint]) -> float | None:
    """Суммировать только неперекрывающиеся интервалы накопления.

    Если поставщик передал start/end step, интервалы дедуплицируются и
    перекрывающиеся значения не складываются повторно. При отсутствии явной
    семантики используется один результат на срок валидности.
    """

    intervals: list[tuple[float, float, float]] = []
    fallback: dict[datetime, float] = {}
    for point in points:
        measurement = point.measurement("precipitation")
        if measurement is None:
            continue
        value = _as_float(measurement.value)
        if value is None:
            continue
        if (
            measurement.source_start_step is not None
            and measurement.source_end_step is not None
            and measurement.source_end_step >= measurement.source_start_step
        ):
            intervals.append(
                (
                    float(measurement.source_start_step),
                    float(measurement.source_end_step),
                    max(0.0, value),
                )
            )
        else:
            fallback[point.valid_time_utc] = max(0.0, value)

    if intervals:
        unique: dict[tuple[float, float], float] = {}
        for start, end, value in intervals:
            unique[(start, end)] = max(unique.get((start, end), 0.0), value)
        selected: list[tuple[float, float, float]] = []
        for start, end in sorted(unique, key=lambda item: (item[1], item[0])):
            value = unique[(start, end)]
            overlaps = any(start < chosen_end and end > chosen_start for chosen_start, chosen_end, _ in selected)
            if overlaps:
                continue
            selected.append((start, end, value))
        return sum(value for _, _, value in selected)
    if fallback:
        return sum(fallback.values())
    return None


def daily_agreement(
    forecasts: list[ForecastSeries],
    day: date,
) -> DailyAgreement | None:
    daily = [(forecast, _points_for_day(forecast, day)) for forecast in forecasts]
    daily = [(forecast, points) for forecast, points in daily if points]
    if len(daily) <= 1:
        return None

    temperature_maxima = [
        value
        for _, points in daily
        if (value := _max_value(points, "temperature_2m")) is not None
    ]
    temperature_score = _spread_score(temperature_maxima, good=2.5, acceptable=5.0)

    precipitation_totals = [
        value
        for _, points in daily
        if (value := daily_precipitation_total(points)) is not None
    ]
    wet_flags = [value >= 0.1 for value in precipitation_totals]
    if len(precipitation_totals) < 2:
        precipitation_score = 0.5
    elif all(wet_flags) or not any(wet_flags):
        precipitation_score = _relative_spread_score(
            precipitation_totals,
            absolute_floor=1.0,
            good=0.35,
            acceptable=0.9,
        )
    else:
        precipitation_score = 0.15

    gust_maxima = [
        value
        for _, points in daily
        if (value := _max_value(points, "wind_gusts_10m")) is not None
    ]
    if not gust_maxima:
        gust_maxima = [
            value
            for _, points in daily
            if (value := _max_value(points, "wind_speed_10m")) is not None
        ]
    wind_score = _spread_score(gust_maxima, good=3.0, acceptable=6.0)

    phenomena = [_dominant_phenomenon(points) for _, points in daily]
    phenomenon_ratio = max(Counter(phenomena).values()) / len(phenomena)
    phenomenon_score = (
        1.0 if phenomenon_ratio >= 0.75 else 0.65 if phenomenon_ratio >= 0.5 else 0.25
    )

    score = (
        0.30 * temperature_score
        + 0.30 * precipitation_score
        + 0.22 * wind_score
        + 0.18 * phenomenon_score
    )
    overall = _level(score)
    note = (
        f"температура — {_level(temperature_score)}, "
        f"осадки — {_level(precipitation_score)}, "
        f"ветер — {_level(wind_score)}, "
        f"явление — {_level(phenomenon_score)}"
    )
    return DailyAgreement(
        overall=overall,
        score=score,
        temperature=_level(temperature_score),
        precipitation=_level(precipitation_score),
        wind=_level(wind_score),
        phenomenon=_level(phenomenon_score),
        note=note,
    )


def build_risk_signals(
    forecasts: list[ForecastSeries],
    ensembles: list[ForecastSeries],
    report_dates: list[date],
    *,
    maximum: int = 3,
) -> list[RiskSignal]:
    signals: list[RiskSignal] = []
    model_count = len(forecasts)
    if not model_count:
        return signals

    for day in report_dates:
        day_data = [(forecast, _points_for_day(forecast, day)) for forecast in forecasts]
        day_data = [(forecast, points) for forecast, points in day_data if points]
        if not day_data:
            continue

        thunder_support = [
            (forecast, [point for point in points if point.weather_code in THUNDER_CODES])
            for forecast, points in day_data
        ]
        thunder_support = [(forecast, points) for forecast, points in thunder_support if points]
        if thunder_support:
            all_points = [point for _, points in thunder_support for point in points]
            signals.append(
                _signal(
                    phenomenon="ГРОЗА",
                    day=day,
                    points=all_points,
                    value_text="грозовой сценарий",
                    support_count=len(thunder_support),
                    model_count=model_count,
                    ensemble_probability=_ensemble_precipitation_probability(ensembles, day, 1.0),
                    severity=100,
                )
            )

        precipitation = []
        for forecast, points in day_data:
            total = daily_precipitation_total(points)
            if total is not None:
                precipitation.append((forecast, points, total))
        significant_precipitation = [item for item in precipitation if item[2] >= 3.0]
        if significant_precipitation:
            max_item = max(significant_precipitation, key=lambda item: item[2])
            signals.append(
                _signal(
                    phenomenon="СИЛЬНЫЕ ОСАДКИ",
                    day=day,
                    points=max_item[1],
                    value_text=(
                        f"до {max(item[2] for item in significant_precipitation):.1f} мм за сутки"
                        .replace(".", ",")
                    ),
                    support_count=len(significant_precipitation),
                    model_count=model_count,
                    ensemble_probability=_ensemble_precipitation_probability(ensembles, day, 5.0),
                    severity=85 if max_item[2] >= 10 else 70,
                    peak_code="precipitation",
                )
            )

        gust_support = []
        for forecast, points in day_data:
            gust = _max_value(points, "wind_gusts_10m")
            if gust is not None and gust >= 14.0:
                gust_support.append((forecast, points, gust))
        if gust_support:
            strongest = max(gust_support, key=lambda item: item[2])
            signals.append(
                _signal(
                    phenomenon="СИЛЬНЫЕ ПОРЫВЫ",
                    day=day,
                    points=strongest[1],
                    value_text=f"до {strongest[2]:.1f} м/с".replace(".", ","),
                    support_count=len(gust_support),
                    model_count=model_count,
                    ensemble_probability=None,
                    severity=90 if strongest[2] >= 20 else 72,
                    peak_code="wind_gusts_10m",
                )
            )

        heat_support = []
        cold_support = []
        for forecast, points in day_data:
            maximum_temperature = _max_value(points, "temperature_2m")
            minimum_temperature = _min_value(points, "temperature_2m")
            if maximum_temperature is not None and maximum_temperature >= 30:
                heat_support.append((forecast, points, maximum_temperature))
            if minimum_temperature is not None and minimum_temperature <= -15:
                cold_support.append((forecast, points, minimum_temperature))
        if heat_support:
            hottest = max(heat_support, key=lambda item: item[2])
            signals.append(
                _signal(
                    phenomenon="ЖАРА",
                    day=day,
                    points=hottest[1],
                    value_text=f"до {hottest[2]:.1f} °C".replace(".", ","),
                    support_count=len(heat_support),
                    model_count=model_count,
                    ensemble_probability=None,
                    severity=68,
                    peak_code="temperature_2m",
                )
            )
        if cold_support:
            coldest = min(cold_support, key=lambda item: item[2])
            signals.append(
                _signal(
                    phenomenon="СИЛЬНЫЙ МОРОЗ",
                    day=day,
                    points=coldest[1],
                    value_text=f"до {coldest[2]:.1f} °C".replace(".", ","),
                    support_count=len(cold_support),
                    model_count=model_count,
                    ensemble_probability=None,
                    severity=68,
                    peak_code="temperature_2m",
                    minimum_peak=True,
                )
            )

    # Одиночные сценарии допускаются только для потенциально опасных событий.
    signals = [
        signal
        for signal in signals
        if signal.support_count >= 2
        or signal.ensemble_probability is not None
        or signal.severity >= 85
    ]
    signals.sort(
        key=lambda signal: (
            signal.severity,
            signal.support_count / max(1, signal.model_count),
            signal.ensemble_probability or 0.0,
        ),
        reverse=True,
    )
    return signals[:maximum]


def _signal(
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
    if support_ratio >= 0.67 and (ensemble_probability is None or ensemble_probability >= 40):
        scenario = "Устойчивый сигнал"
        confidence = "высокая"
    elif support_count >= 2 or (ensemble_probability or 0) >= 30:
        scenario = "Вероятный сигнал"
        confidence = "средняя"
    else:
        scenario = "Отдельный сценарий"
        confidence = "низкая"

    ordered = sorted(points, key=lambda point: point.valid_time_local)
    peak = None
    if peak_code:
        candidates = [
            (point, _as_float(point.raw(peak_code)))
            for point in ordered
            if _as_float(point.raw(peak_code)) is not None
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


def _ensemble_precipitation_probability(
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
            value = _as_float(point.raw(code))
            if value is not None:
                values.append(value)
                coverage = _as_float(point.raw("ensemble_member_coverage"))
                if coverage is not None:
                    coverages.append(coverage)
    if not values:
        return None
    probability = max(values)
    if coverages and min(coverages) < 80:
        probability *= min(coverages) / 100
    return probability


def _points_for_day(forecast: ForecastSeries, day: date) -> list[ForecastPoint]:
    return [point for point in forecast.points if point.valid_time_local.date() == day]


def _dominant_phenomenon(points: list[ForecastPoint]) -> str:
    codes = [point.weather_code for point in points if point.weather_code is not None]
    if not codes:
        return "нет кода"
    if any(code in THUNDER_CODES for code in codes):
        return "гроза"
    if any(code in SIGNIFICANT_WEATHER_CODES for code in codes):
        return "опасное явление"
    return str(Counter(codes).most_common(1)[0][0])


def _spread_score(values: list[float], *, good: float, acceptable: float) -> float:
    if len(values) < 2:
        return 0.5
    spread = max(values) - min(values)
    if spread <= good:
        return 1.0
    if spread <= acceptable:
        return 0.65
    return 0.2


def _relative_spread_score(
    values: list[float],
    *,
    absolute_floor: float,
    good: float,
    acceptable: float,
) -> float:
    if len(values) < 2:
        return 0.5
    median = statistics.median(values)
    denominator = max(absolute_floor, abs(median))
    relative = (max(values) - min(values)) / denominator
    if relative <= good:
        return 1.0
    if relative <= acceptable:
        return 0.65
    return 0.2


def _level(score: float) -> str:
    if score >= 0.78:
        return "высокая"
    if score >= 0.48:
        return "средняя"
    return "низкая"


def _max_value(points: list[ForecastPoint], code: str) -> float | None:
    values = [_as_float(point.raw(code)) for point in points]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _min_value(points: list[ForecastPoint], code: str) -> float | None:
    values = [_as_float(point.raw(code)) for point in points]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def _as_float(value) -> float | None:
    try:
        number = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return number if number is not None and math.isfinite(number) else None
