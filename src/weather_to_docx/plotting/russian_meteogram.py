from __future__ import annotations

from datetime import datetime

import matplotlib.dates as mdates
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from weather_to_docx.domain.models import ForecastPoint, ForecastSeries
from weather_to_docx.plotting.meteogram import MeteogramRenderer
from weather_to_docx.plotting.solar import is_night

RUSSIAN_WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


class RussianMeteogramRenderer(MeteogramRenderer):
    """Метеограмма с русскими подписями и надёжным выделением ночи."""

    def render_deterministic(
        self,
        forecast: ForecastSeries,
        output_path,
        *,
        title: str | None = None,
    ):
        self._forecast_context = forecast
        try:
            return super().render_deterministic(
                forecast,
                output_path,
                title=title,
            )
        finally:
            self._forecast_context = None

    def render_ensemble(
        self,
        forecast: ForecastSeries,
        output_path,
        *,
        title: str | None = None,
    ):
        self._forecast_context = forecast
        try:
            return super().render_ensemble(
                forecast,
                output_path,
                title=title,
            )
        finally:
            self._forecast_context = None

    def _shade_night(
        self,
        axes: tuple[Axes, Axes, Axes, Axes],
        points: list[ForecastPoint],
        x: np.ndarray,
    ) -> None:
        if len(points) < 2:
            return
        forecast = getattr(self, "_forecast_context", None)
        if forecast is None:
            return

        edges = np.empty(len(x) + 1)
        edges[1:-1] = (x[:-1] + x[1:]) / 2
        edges[0] = x[0] - (x[1] - x[0]) / 2
        edges[-1] = x[-1] + (x[-1] - x[-2]) / 2

        night_mask: list[bool] = []
        for point in points:
            if point.is_day is not None:
                night_mask.append(point.is_day is False)
            else:
                night_mask.append(
                    is_night(
                        point.valid_time_utc,
                        latitude=forecast.location.latitude,
                        longitude=forecast.location.longitude,
                    )
                )

        for start, end in _contiguous_true_ranges(night_mask):
            left = edges[start]
            right = edges[end]
            for axis in axes:
                axis.axvspan(
                    left,
                    right,
                    color=self.palette.night,
                    alpha=0.11,
                    linewidth=0,
                    zorder=0.15,
                )
            if right - left >= 2 / 24:
                axes[0].text(
                    (left + right) / 2,
                    0.88,
                    "ночь",
                    transform=axes[0].get_xaxis_transform(),
                    ha="center",
                    va="center",
                    fontsize=6.2,
                    color="#45535e",
                    fontweight="bold",
                    alpha=0.9,
                    zorder=5,
                )

    def _finish_figure(
        self,
        figure: Figure,
        axes: tuple[Axes, Axes, Axes, Axes],
        times: list[datetime],
        forecast: ForecastSeries,
        *,
        ensemble: bool = False,
    ) -> None:
        timezone = times[0].tzinfo
        axes[-1].xaxis.set_major_locator(
            mdates.DayLocator(interval=1, tz=timezone)
        )
        axes[-1].xaxis.set_major_formatter(
            FuncFormatter(
                lambda value, _position: russian_day_label(
                    value,
                    timezone=timezone,
                )
            )
        )
        axes[-1].xaxis.set_minor_locator(
            mdates.HourLocator(byhour=(6, 12, 18), tz=timezone)
        )
        axes[-1].xaxis.set_minor_formatter(
            mdates.DateFormatter("%H", tz=timezone)
        )
        axes[-1].tick_params(axis="x", which="major", labelsize=7.2, pad=5)
        axes[-1].tick_params(axis="x", which="minor", labelsize=6.0, pad=2)
        axes[-1].set_xlim(times[0], times[-1])
        for axis in axes[:-1]:
            axis.tick_params(axis="x", labelbottom=False)

        explanation = (
            "линия — медиана; тёмная полоса — ±σ; светлая полоса — "
            "10–90-й процентили"
            if ensemble
            else "непрерывные поля сглажены методом PCHIP; "
            "осадки показаны без сглаживания"
        )
        figure.text(
            0.055,
            0.01,
            f"{russian_timezone_label(times[0])} · серые полосы — ночь · "
            f"{explanation}",
            fontsize=6.6,
            color="#53636d",
        )
        figure.subplots_adjust(
            left=0.055,
            right=0.945,
            top=0.93,
            bottom=0.12,
        )

    def _plot_precipitation_ensemble(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
    ) -> None:
        super()._plot_precipitation_ensemble(axis, x, forecast)
        _replace_legend_text(axis, "P(≥", "вероятность ≥")
        _replace_legend_text(axis, " мм)", " мм")

    def _plot_wind_pressure_ensemble(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
    ) -> None:
        super()._plot_wind_pressure_ensemble(axis, x, forecast)
        _replace_legend_text(
            axis,
            "q90 порывов",
            "90-й процентиль порывов",
        )


def russian_day_label(value: float, *, timezone) -> str:
    current = mdates.num2date(value, tz=timezone)
    return f"{current:%d.%m}\n{RUSSIAN_WEEKDAYS[current.weekday()]}"


def russian_timezone_label(current: datetime) -> str:
    offset = current.utcoffset()
    if offset is None:
        return "местное время"
    total_minutes = round(offset.total_seconds() / 60)
    sign = "+" if total_minutes >= 0 else "−"
    absolute = abs(total_minutes)
    hours, minutes = divmod(absolute, 60)
    return f"местное время, UTC{sign}{hours:02d}:{minutes:02d}"


def _contiguous_true_ranges(mask: list[bool]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(mask):
        if value and start is None:
            start = index
        if start is not None and (not value or index == len(mask) - 1):
            end = index if not value else index + 1
            ranges.append((start, end))
            start = None
    return ranges


def _replace_legend_text(axis: Axes, old: str, new: str) -> None:
    legend = axis.get_legend()
    if legend is None:
        return
    for text in legend.get_texts():
        text.set_text(text.get_text().replace(old, new))
