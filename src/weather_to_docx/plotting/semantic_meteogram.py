from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from pathlib import Path

import matplotlib.dates as mdates
import numpy as np
from matplotlib.axes import Axes
from matplotlib.patches import Patch

from weather_to_docx.analysis.impact_scales import (
    DAILY_PRECIPITATION_REFERENCE_MM,
    PRECIPITATION_CLASSES,
    PRECIPITATION_RATE_CAP_MM_H,
    PRECIPITATION_RATE_TICKS,
    daily_precipitation_summary,
    fog_risk,
    normalise_precipitation_rates,
    precipitation_scale_class,
    temperature_impact_label,
)
from weather_to_docx.domain.models import ForecastSeries
from weather_to_docx.plotting.meteogram import (
    _bar_width,
    _combined_legend,
    _ensemble_centre,
    _probability_codes,
    _stat_values,
    _values,
)
from weather_to_docx.plotting.professional_meteogram import (
    ProfessionalMeteogramRenderer,
)


class SemanticMeteogramRenderer(ProfessionalMeteogramRenderer):
    """Профессиональная метеограмма с одинаковыми смысловыми шкалами."""

    def _plot_temperature(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
        *,
        ensemble: bool,
    ) -> None:
        centre = (
            _ensemble_centre(forecast, "temperature_2m")
            if ensemble
            else _values(forecast, "temperature_2m")
        )
        outer = [centre]
        if ensemble:
            outer.extend(
                [
                    _stat_values(forecast, "temperature_2m", "p10"),
                    _stat_values(forecast, "temperature_2m", "p90"),
                ]
            )
        finite = np.concatenate(
            [values[np.isfinite(values)] for values in outer if np.isfinite(values).any()]
        ) if any(np.isfinite(values).any() for values in outer) else np.asarray([])
        lower = min(-20.0, math.floor((float(finite.min()) - 3) / 5) * 5) if finite.size else -20.0
        upper = max(40.0, math.ceil((float(finite.max()) + 3) / 5) * 5) if finite.size else 40.0

        self._temperature_background(axis, lower, upper)
        super()._plot_temperature(axis, x, forecast, ensemble=ensemble)
        axis.set_ylim(lower, upper)
        axis.set_yticks(np.arange(math.ceil(lower / 10) * 10, upper + 0.1, 10))
        self._mark_zero_crossings(axis, x, centre)

        if finite.size:
            label = temperature_impact_label(float(finite.min()), float(finite.max()))
            if label:
                index = int(np.nanargmax(centre)) if float(finite.max()) >= 30 else int(np.nanargmin(centre))
                if "переход" in label:
                    index = int(np.flatnonzero(np.isfinite(centre))[0])
                axis.annotate(
                    label,
                    (x[index], centre[index]),
                    xytext=(5, -15 if centre[index] > 20 else 12),
                    textcoords="offset points",
                    fontsize=7.1,
                    fontweight="bold",
                    color="#9b2c2c" if centre[index] >= 30 else "#225b8f",
                    bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.82},
                    zorder=8,
                )

    def _temperature_background(self, axis: Axes, lower: float, upper: float) -> None:
        zones = (
            (lower, -20, "#bfdcf5", "очень холодно"),
            (-20, -10, "#d6eafb", "сильный мороз"),
            (-10, 0, "#eaf5fd", "мороз"),
            (0, 25, "#ffffff", ""),
            (25, 30, "#fff7d6", "тепло"),
            (30, 35, "#ffe6bd", "жара"),
            (35, upper, "#ffd0ca", "очень жарко"),
        )
        for start, end, color, label in zones:
            visible_start = max(lower, start)
            visible_end = min(upper, end)
            if visible_end <= visible_start:
                continue
            axis.axhspan(visible_start, visible_end, color=color, alpha=0.52, zorder=-10)
            if label:
                axis.text(
                    0.997,
                    (visible_start + visible_end) / 2,
                    label,
                    transform=axis.get_yaxis_transform(),
                    ha="right",
                    va="center",
                    fontsize=6.2,
                    color="#5c6670",
                    alpha=0.82,
                    zorder=0,
                )
        for threshold in (-20, -10, 0, 30, 35):
            if lower < threshold < upper:
                axis.axhline(
                    threshold,
                    color="#82909a" if threshold == 0 else "#b8c1c7",
                    linewidth=1.0 if threshold == 0 else 0.55,
                    linestyle="-" if threshold == 0 else ":",
                    alpha=0.85,
                    zorder=0,
                )

    def _mark_zero_crossings(self, axis: Axes, x: np.ndarray, values: np.ndarray) -> None:
        for index in range(1, len(values)):
            left = values[index - 1]
            right = values[index]
            if not (np.isfinite(left) and np.isfinite(right)) or left == right:
                continue
            if (left < 0 <= right) or (left > 0 >= right):
                fraction = -left / (right - left)
                crossing_x = x[index - 1] + fraction * (x[index] - x[index - 1])
                axis.scatter(
                    [crossing_x],
                    [0],
                    s=22,
                    facecolor="white",
                    edgecolor="#315b7d",
                    linewidth=1.1,
                    zorder=9,
                )
                axis.annotate(
                    "через 0 °C",
                    (crossing_x, 0),
                    xytext=(4, 8),
                    textcoords="offset points",
                    fontsize=6.6,
                    color="#315b7d",
                    zorder=9,
                )

    def _plot_humidity(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
        *,
        ensemble: bool,
    ) -> None:
        axis.axhspan(0, 40, color="#fff4d6", alpha=0.45, zorder=-10)
        axis.axhspan(40, 70, color="#f8fbfd", alpha=0.45, zorder=-10)
        axis.axhspan(70, 90, color="#e9f4fa", alpha=0.58, zorder=-10)
        axis.axhspan(90, 100, color="#cfe7f4", alpha=0.64, zorder=-10)
        for threshold in (40, 70, 90, 95):
            axis.axhline(threshold, color="#aebdc7", linewidth=0.55, linestyle=":", zorder=0)
        super()._plot_humidity(axis, x, forecast, ensemble=ensemble)
        for y, label in ((20, "сухо"), (80, "влажно"), (96, "очень влажно")):
            axis.text(
                0.997,
                y,
                label,
                transform=axis.get_yaxis_transform(),
                ha="right",
                va="center",
                fontsize=6.2,
                color="#53636d",
                alpha=0.82,
            )
        if not ensemble:
            self._mark_fog_risk(axis, x, forecast)

    def _mark_fog_risk(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
    ) -> None:
        for index, point in enumerate(forecast.points):
            if fog_risk(
                relative_humidity_percent=_float(point.raw("relative_humidity_2m")),
                temperature_c=_float(point.raw("temperature_2m")),
                dew_point_c=_float(point.raw("dew_point_2m")),
                wind_speed_ms=_float(point.raw("wind_speed_10m")),
                weather_code=point.weather_code,
            ):
                axis.annotate(
                    "туман / дымка возможны",
                    (x[index], 96),
                    xytext=(4, -15),
                    textcoords="offset points",
                    fontsize=6.8,
                    fontweight="bold",
                    color="#315b7d",
                    bbox={"boxstyle": "round,pad=0.18", "fc": "white", "ec": "none", "alpha": 0.8},
                )
                break

    def _plot_precipitation(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
        *,
        ensemble: bool,
    ) -> None:
        precipitation = (
            _ensemble_centre(forecast, "precipitation")
            if ensemble
            else _values(forecast, "precipitation")
        )
        rates = np.asarray(
            normalise_precipitation_rates(forecast.points, precipitation),
            dtype=float,
        )
        display_rates = np.minimum(
            np.nan_to_num(rates, nan=0.0),
            PRECIPITATION_RATE_CAP_MM_H,
        )
        colors = [
            precipitation_scale_class(
                rate if math.isfinite(rate) else 0.0,
                weather_code=forecast.points[index].weather_code,
            ).color
            for index, rate in enumerate(rates)
        ]

        self._precipitation_background(axis)
        bars = axis.bar(
            x,
            display_rates,
            width=_bar_width(x) * 0.88,
            color=colors,
            alpha=0.86,
            edgecolor=[
                "#6a1b9a"
                if forecast.points[index].weather_code in {95, 96, 99}
                else "none"
                for index in range(len(forecast.points))
            ],
            linewidth=0.9,
            label="интенсивность осадков",
            zorder=3,
        )
        axis.set_ylabel("мм/ч", fontsize=8, rotation=0, labelpad=15)
        axis.set_ylim(0, PRECIPITATION_RATE_CAP_MM_H)
        axis.set_yticks(PRECIPITATION_RATE_TICKS)
        axis.text(
            0.004,
            0.97,
            f"суточный ориентир: {DAILY_PRECIPITATION_REFERENCE_MM:g} мм",
            transform=axis.transAxes,
            va="top",
            fontsize=6.3,
            color="#53636d",
        )

        for index, rate in enumerate(rates):
            if math.isfinite(rate) and rate > PRECIPITATION_RATE_CAP_MM_H:
                axis.annotate(
                    f"↑ {rate:.1f}".replace(".", ","),
                    (x[index], PRECIPITATION_RATE_CAP_MM_H),
                    xytext=(0, -11),
                    textcoords="offset points",
                    ha="center",
                    fontsize=6.7,
                    fontweight="bold",
                    color="#0a3f6b",
                )
            if forecast.points[index].weather_code in {95, 96, 99} and display_rates[index] > 0:
                axis.text(
                    x[index],
                    min(PRECIPITATION_RATE_CAP_MM_H - 0.5, display_rates[index] + 0.35),
                    "гроза",
                    ha="center",
                    va="bottom",
                    fontsize=6.2,
                    color="#6a1b9a",
                    fontweight="bold",
                )

        self._annotate_daily_precipitation(axis, x, forecast, precipitation)

        if ensemble:
            probability_axis = axis.twinx()
            probability_axis.spines["top"].set_visible(False)
            probability_colors = ("#1d70a2", "#6a4c93", "#b23a48", "#ef8354")
            for index, (code, threshold) in enumerate(_probability_codes(forecast)[:4]):
                probability = _values(forecast, code)
                probability_axis.step(
                    x,
                    probability,
                    where="mid",
                    color=probability_colors[index % len(probability_colors)],
                    linewidth=1.15,
                    label=f"вероятность ≥{threshold} мм",
                    zorder=5,
                )
            probability_axis.set_ylim(0, 100)
            probability_axis.set_ylabel("%", fontsize=8, rotation=0, labelpad=12)
            probability_axis.tick_params(axis="y", labelsize=7)
            _combined_legend(axis, probability_axis, loc="upper left")
        else:
            axis.legend(
                handles=[
                    Patch(facecolor=item.color, label=item.label)
                    for item in PRECIPITATION_CLASSES[1:]
                ],
                loc="upper left",
                fontsize=6.4,
                frameon=False,
                ncol=5,
                handlelength=1.0,
                columnspacing=0.7,
            )
        # Сохраняем ссылку для тестов соотношения высот столбиков.
        axis._weather_precipitation_bars = bars  # type: ignore[attr-defined]

    def _precipitation_background(self, axis: Axes) -> None:
        for item in PRECIPITATION_CLASSES:
            lower = item.lower_rate_mm_h
            upper = item.upper_rate_mm_h or PRECIPITATION_RATE_CAP_MM_H
            upper = min(upper, PRECIPITATION_RATE_CAP_MM_H)
            if upper <= lower:
                continue
            axis.axhspan(lower, upper, color=item.color, alpha=0.075, zorder=-10)
            if lower > 0:
                axis.axhline(lower, color=item.color, linewidth=0.55, linestyle=":", alpha=0.75)
            if item.code not in {"trace"}:
                axis.text(
                    0.997,
                    (lower + upper) / 2,
                    item.label,
                    transform=axis.get_yaxis_transform(),
                    ha="right",
                    va="center",
                    fontsize=5.9,
                    color="#45535e",
                    alpha=0.78,
                )

    def _annotate_daily_precipitation(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
        precipitation: np.ndarray,
    ) -> None:
        by_day: dict[date, list[int]] = defaultdict(list)
        for index, point in enumerate(forecast.points):
            by_day[point.valid_time_local.date()].append(index)
        for day, indices in sorted(by_day.items()):
            summary = daily_precipitation_summary(
                forecast,
                day,
                values=precipitation,
            )
            if summary is None:
                continue
            centre_x = float(np.mean(x[indices]))
            ratio = summary.reference_ratio
            ratio_text = (
                f"{ratio:.1f}× ориентира".replace(".", ",")
                if ratio >= 0.1
                else "меньше 0,1× ориентира"
            )
            axis.text(
                centre_x,
                PRECIPITATION_RATE_CAP_MM_H * 0.965,
                f"{summary.short_text}\n{ratio_text}",
                ha="center",
                va="top",
                fontsize=5.8,
                color="#253846",
                fontweight="bold" if summary.total_mm >= 15 or summary.thunder else "normal",
                bbox={"boxstyle": "round,pad=0.14", "fc": "white", "ec": "none", "alpha": 0.72},
                zorder=8,
            )

    def _plot_wind_pressure(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
        *,
        ensemble: bool,
    ) -> None:
        wind = (
            _ensemble_centre(forecast, "wind_speed_10m")
            if ensemble
            else _values(forecast, "wind_speed_10m")
        )
        gust = (
            _stat_values(forecast, "wind_gusts_10m", "p90")
            if ensemble
            else _values(forecast, "wind_gusts_10m")
        )
        finite_wind = np.concatenate(
            [values[np.isfinite(values)] for values in (wind, gust) if np.isfinite(values).any()]
        ) if any(np.isfinite(values).any() for values in (wind, gust)) else np.asarray([])
        upper = max(25.0, math.ceil((float(finite_wind.max()) + 2) / 5) * 5) if finite_wind.size else 25.0
        self._wind_background(axis, upper)
        axes_before = len(axis.figure.axes)
        super()._plot_wind_pressure(axis, x, forecast, ensemble=ensemble)
        axis.set_ylim(0, upper)
        axis.set_yticks([value for value in (0, 5, 10, 14, 20, 25, 30, 35) if value <= upper])

        pressure_axis = axis.figure.axes[-1] if len(axis.figure.axes) > axes_before else None
        if pressure_axis is not None and pressure_axis is not axis:
            pressure = (
                _ensemble_centre(forecast, "pressure_msl")
                if ensemble
                else _values(forecast, "pressure_msl")
            )
            finite_pressure = pressure[np.isfinite(pressure)]
            lower_pressure = min(970.0, math.floor(float(finite_pressure.min()) / 10) * 10) if finite_pressure.size else 970.0
            upper_pressure = max(1040.0, math.ceil(float(finite_pressure.max()) / 10) * 10) if finite_pressure.size else 1040.0
            pressure_axis.axhspan(lower_pressure, 990, color="#fde8e7", alpha=0.32, zorder=-10)
            pressure_axis.axhspan(1030, upper_pressure, color="#e7f1fb", alpha=0.34, zorder=-10)
            pressure_axis.axhline(1013, color="#7f6f52", linewidth=0.6, linestyle=":", alpha=0.75)
            pressure_axis.set_ylim(lower_pressure, upper_pressure)
            pressure_axis.set_yticks(
                np.arange(math.ceil(lower_pressure / 20) * 20, upper_pressure + 0.1, 20)
            )

    def _wind_background(self, axis: Axes, upper: float) -> None:
        zones = (
            (0, 5, "#eef7ef", "слабый"),
            (5, 10, "#f4f7e8", "ветрено"),
            (10, 14, "#fff4d6", "сильный"),
            (14, 20, "#ffe4cc", "очень сильный"),
            (20, upper, "#ffd1d1", "опасный"),
        )
        for lower, end, color, label in zones:
            visible_end = min(end, upper)
            if visible_end <= lower:
                continue
            axis.axhspan(lower, visible_end, color=color, alpha=0.5, zorder=-10)
            axis.text(
                0.997,
                (lower + visible_end) / 2,
                label,
                transform=axis.get_yaxis_transform(),
                ha="right",
                va="center",
                fontsize=6.0,
                color="#53636d",
                alpha=0.8,
            )
        for threshold in (5, 10, 14, 20):
            if threshold < upper:
                axis.axhline(
                    threshold,
                    color="#b2b8bd" if threshold < 14 else "#b23a48",
                    linewidth=0.6 if threshold < 14 else 0.9,
                    linestyle=":" if threshold < 14 else "--",
                    alpha=0.82,
                    zorder=0,
                )


def _float(value) -> float | None:
    try:
        number = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return number if number is not None and math.isfinite(number) else None
