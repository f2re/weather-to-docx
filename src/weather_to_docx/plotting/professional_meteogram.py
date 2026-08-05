from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from weather_to_docx.domain.models import ForecastPoint, ForecastSeries
from weather_to_docx.plotting.meteogram import (
    FONT_FAMILY,
    _bar_width,
    _combined_legend,
    _ensemble_centre,
    _probability_codes,
    _stat_values,
    _times,
    _values,
)
from weather_to_docx.plotting.russian_meteogram import (
    RussianMeteogramRenderer,
    russian_day_label,
    russian_timezone_label,
)

WIND_ARROWS = ("↓", "↙", "←", "↖", "↑", "↗", "→", "↘")
THUNDER_CODES = frozenset({95, 96, 99})


class ProfessionalMeteogramRenderer(RussianMeteogramRenderer):
    """Пятизонная метеограмма с отдельной влажностью и ветровыми стрелками."""

    def render_deterministic(
        self,
        forecast: ForecastSeries,
        output_path: Path,
        *,
        title: str | None = None,
    ) -> Path:
        times = _times(forecast)
        if len(times) < 2:
            raise ValueError("Для метеограммы требуется не менее двух сроков")
        x = mdates.date2num(times)
        self._forecast_context = forecast
        try:
            figure, axes = self._new_professional_figure(title or forecast.source.model)
            cloud_ax, temperature_ax, humidity_ax, precipitation_ax, wind_ax = axes
            self._shade_night(axes, forecast.points, x)
            self._plot_cloud_bands(cloud_ax, x, forecast, ensemble=False)
            self._plot_temperature(temperature_ax, x, forecast, ensemble=False)
            self._plot_humidity(humidity_ax, x, forecast, ensemble=False)
            self._plot_precipitation(precipitation_ax, x, forecast, ensemble=False)
            self._plot_wind_pressure(wind_ax, x, forecast, ensemble=False)
            self._annotate_events(axes, x, forecast)
            self._finish_professional(figure, axes, times, ensemble=False)
            return self._save(figure, output_path)
        finally:
            self._forecast_context = None

    def render_ensemble(
        self,
        forecast: ForecastSeries,
        output_path: Path,
        *,
        title: str | None = None,
    ) -> Path:
        times = _times(forecast)
        if len(times) < 2:
            raise ValueError("Для ансамблевой метеограммы требуется не менее двух сроков")
        x = mdates.date2num(times)
        self._forecast_context = forecast
        try:
            figure, axes = self._new_professional_figure(title or forecast.source.model)
            cloud_ax, temperature_ax, humidity_ax, precipitation_ax, wind_ax = axes
            self._shade_night(axes, forecast.points, x)
            self._plot_cloud_bands(cloud_ax, x, forecast, ensemble=True)
            self._plot_temperature(temperature_ax, x, forecast, ensemble=True)
            self._plot_humidity(humidity_ax, x, forecast, ensemble=True)
            self._plot_precipitation(precipitation_ax, x, forecast, ensemble=True)
            self._plot_wind_pressure(wind_ax, x, forecast, ensemble=True)
            self._finish_professional(figure, axes, times, ensemble=True)
            return self._save(figure, output_path)
        finally:
            self._forecast_context = None

    def _new_professional_figure(
        self,
        title: str,
    ) -> tuple[Figure, tuple[Axes, Axes, Axes, Axes, Axes]]:
        plt.rcParams.update(
            {
                "font.family": "sans-serif",
                "font.sans-serif": FONT_FAMILY,
                "axes.edgecolor": self.palette.grid,
                "axes.labelcolor": self.palette.text,
                "xtick.color": self.palette.text,
                "ytick.color": self.palette.text,
                "text.color": self.palette.text,
            }
        )
        figure, axes = plt.subplots(
            5,
            1,
            figsize=(11.4, 5.55),
            dpi=self.dpi,
            sharex=True,
            gridspec_kw={
                "height_ratios": (0.85, 1.55, 0.72, 0.9, 1.35),
                "hspace": 0.08,
            },
        )
        figure.patch.set_facecolor("white")
        figure.suptitle(
            title,
            x=0.065,
            y=0.988,
            ha="left",
            fontsize=12.5,
            fontweight="bold",
        )
        for axis in axes:
            axis.set_axisbelow(True)
            axis.grid(axis="x", color=self.palette.grid, linewidth=0.55, alpha=0.75)
            axis.spines[["top", "right"]].set_visible(False)
            axis.tick_params(labelsize=8, length=2.5)
        return figure, tuple(axes)

    def _plot_cloud_bands(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
        *,
        ensemble: bool,
    ) -> None:
        axis.set_facecolor("#f4f9fc")
        layers = (
            ("cloud_cover_low", "низкие", self.palette.cloud_low, 0.0),
            ("cloud_cover_mid", "средние", self.palette.cloud_mid, 1.0),
            ("cloud_cover_high", "высокие", self.palette.cloud_high, 2.0),
        )
        has_layers = any(np.isfinite(_values(forecast, code)).any() for code, _, _, _ in layers)
        if not has_layers:
            layers = (("cloud_cover", "общая", self.palette.cloud_mid, 1.0),)

        for code, _label, color, baseline in layers:
            centre = _ensemble_centre(forecast, code) if ensemble else _values(forecast, code)
            for smooth_x, smooth_y in self._segments(x, centre, lower=0, upper=100):
                axis.fill_between(
                    smooth_x,
                    baseline,
                    baseline + smooth_y / 100,
                    color=color,
                    alpha=0.62,
                    linewidth=0,
                )
            if ensemble:
                lower = _stat_values(forecast, code, "p10")
                upper = _stat_values(forecast, code, "p90")
                self._band(
                    axis,
                    x,
                    baseline + lower / 100,
                    baseline + upper / 100,
                    color,
                    0.13,
                    lower_bound=baseline,
                    upper_bound=baseline + 1,
                )

        axis.axhline(1, color=self.palette.grid, linewidth=0.6)
        axis.axhline(2, color=self.palette.grid, linewidth=0.6)
        axis.set_ylim(0, 3)
        axis.set_yticks((0.5, 1.5, 2.5), labels=("низкие", "средние", "высокие"))
        axis.tick_params(axis="y", labelsize=7.3)
        axis.text(
            0.004,
            0.95,
            "облачность, %",
            transform=axis.transAxes,
            va="top",
            fontsize=7.5,
            fontweight="bold",
        )

    def _plot_temperature(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
        *,
        ensemble: bool,
    ) -> None:
        if ensemble:
            centre = _ensemble_centre(forecast, "temperature_2m")
            p10 = _stat_values(forecast, "temperature_2m", "p10")
            p90 = _stat_values(forecast, "temperature_2m", "p90")
            p25 = _stat_values(forecast, "temperature_2m", "p25")
            p75 = _stat_values(forecast, "temperature_2m", "p75")
            self._band(axis, x, p10, p90, self.palette.temperature_band, 0.22)
            self._band(axis, x, p25, p75, self.palette.temperature, 0.22)
            self._line_smoothed(axis, x, centre, self.palette.temperature, 2.0, "медиана")
        else:
            temperature = _values(forecast, "temperature_2m")
            dewpoint = _values(forecast, "dew_point_2m")
            self._line_smoothed(
                axis,
                x,
                temperature,
                self.palette.temperature,
                2.0,
                "температура",
            )
            if np.isfinite(dewpoint).any():
                self._line_smoothed(
                    axis,
                    x,
                    dewpoint,
                    self.palette.humidity,
                    1.15,
                    "точка росы",
                    "--",
                )
        axis.axhline(0, color="#7b8790", linewidth=0.75, alpha=0.7)
        axis.set_ylabel("°C", fontsize=8, rotation=0, labelpad=13)
        axis.legend(loc="upper left", fontsize=7.5, frameon=False, ncol=3)
        self._mark_extrema(axis, x, _ensemble_centre(forecast, "temperature_2m") if ensemble else _values(forecast, "temperature_2m"), "°C")

    def _plot_humidity(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
        *,
        ensemble: bool,
    ) -> None:
        humidity = _ensemble_centre(forecast, "relative_humidity_2m") if ensemble else _values(forecast, "relative_humidity_2m")
        if ensemble:
            p10 = _stat_values(forecast, "relative_humidity_2m", "p10")
            p90 = _stat_values(forecast, "relative_humidity_2m", "p90")
            p25 = _stat_values(forecast, "relative_humidity_2m", "p25")
            p75 = _stat_values(forecast, "relative_humidity_2m", "p75")
            self._band(axis, x, p10, p90, self.palette.humidity_band, 0.18, lower_bound=0, upper_bound=100)
            self._band(axis, x, p25, p75, self.palette.humidity, 0.15, lower_bound=0, upper_bound=100)
        self._fill_smoothed(axis, x, humidity, 0, self.palette.humidity_band, 0.14, lower=0, upper=100)
        self._line_smoothed(axis, x, humidity, self.palette.humidity, 1.35, "влажность")
        axis.set_ylim(0, 100)
        axis.set_yticks((0, 50, 100), labels=("0", "50", "100"))
        axis.set_ylabel("%", fontsize=8, rotation=0, labelpad=13)
        axis.legend(loc="upper left", fontsize=7.5, frameon=False)

    def _plot_precipitation(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
        *,
        ensemble: bool,
    ) -> None:
        precipitation = _ensemble_centre(forecast, "precipitation") if ensemble else _values(forecast, "precipitation")
        axis.bar(
            x,
            np.nan_to_num(precipitation, nan=0.0),
            width=_bar_width(x),
            color=self.palette.precipitation,
            alpha=0.66,
            linewidth=0,
            label="осадки за интервал" if not ensemble else "медиана осадков",
        )
        axis.set_ylabel("мм", fontsize=8, rotation=0, labelpad=13)
        axis.set_ylim(bottom=0)
        if ensemble:
            probability_axis = axis.twinx()
            probability_axis.spines["top"].set_visible(False)
            colors = ("#1d70a2", "#6a4c93", "#b23a48", "#ef8354")
            for index, (code, threshold) in enumerate(_probability_codes(forecast)[:4]):
                probability = _values(forecast, code)
                probability_axis.step(
                    x,
                    probability,
                    where="mid",
                    color=colors[index % len(colors)],
                    linewidth=1.15,
                    label=f"вероятность ≥{threshold} мм",
                )
            probability_axis.set_ylim(0, 100)
            probability_axis.set_ylabel("%", fontsize=8, rotation=0, labelpad=12)
            probability_axis.tick_params(axis="y", labelsize=7)
            _combined_legend(axis, probability_axis, loc="upper left")
        else:
            axis.legend(loc="upper left", fontsize=7.5, frameon=False)
        values = np.nan_to_num(precipitation, nan=0.0)
        if values.size and values.max() >= 0.1:
            index = int(np.argmax(values))
            axis.annotate(
                f"{values[index]:.1f} мм".replace(".", ","),
                (x[index], values[index]),
                xytext=(0, 8),
                textcoords="offset points",
                ha="center",
                fontsize=7.2,
                fontweight="bold",
                color=self.palette.precipitation,
            )

    def _plot_wind_pressure(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
        *,
        ensemble: bool,
    ) -> None:
        wind = _ensemble_centre(forecast, "wind_speed_10m") if ensemble else _values(forecast, "wind_speed_10m")
        gust = (
            _stat_values(forecast, "wind_gusts_10m", "p90")
            if ensemble
            else _values(forecast, "wind_gusts_10m")
        )
        if ensemble:
            p10 = _stat_values(forecast, "wind_speed_10m", "p10")
            p90 = _stat_values(forecast, "wind_speed_10m", "p90")
            p25 = _stat_values(forecast, "wind_speed_10m", "p25")
            p75 = _stat_values(forecast, "wind_speed_10m", "p75")
            self._band(axis, x, p10, p90, self.palette.wind, 0.14, lower_bound=0)
            self._band(axis, x, p25, p75, self.palette.wind, 0.21, lower_bound=0)
        self._line_smoothed(axis, x, wind, self.palette.wind, 1.8, "ветер")
        self._line_smoothed(
            axis,
            x,
            gust,
            self.palette.gust,
            1.2,
            "90-й процентиль порывов" if ensemble else "порывы",
            "--",
        )
        axis.axhline(14, color="#b23a48", linewidth=0.7, linestyle=":", alpha=0.8)
        axis.text(
            0.995,
            14,
            "порог 14 м/с",
            transform=axis.get_yaxis_transform(),
            ha="right",
            va="bottom",
            fontsize=6.8,
            color="#9f2d3a",
        )
        axis.set_ylabel("м/с", fontsize=8, rotation=0, labelpad=13)
        axis.set_ylim(bottom=0)

        pressure_axis = axis.twinx()
        pressure_axis.spines["top"].set_visible(False)
        pressure_axis.spines["right"].set_color(self.palette.pressure)
        pressure = _ensemble_centre(forecast, "pressure_msl") if ensemble else _values(forecast, "pressure_msl")
        if ensemble:
            self._band(
                pressure_axis,
                x,
                _stat_values(forecast, "pressure_msl", "p10"),
                _stat_values(forecast, "pressure_msl", "p90"),
                self.palette.pressure,
                0.1,
            )
        self._line_smoothed(pressure_axis, x, pressure, self.palette.pressure, 1.15, "давление")
        pressure_axis.set_ylabel("гПа", fontsize=8, rotation=0, labelpad=15)
        pressure_axis.tick_params(axis="y", labelsize=7, colors=self.palette.pressure)
        _combined_legend(axis, pressure_axis, loc="upper left")
        self._add_wind_direction_arrows(axis, x, forecast)

    def _add_wind_direction_arrows(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
    ) -> None:
        direction = _values(forecast, "wind_direction_10m")
        finite = np.flatnonzero(np.isfinite(direction))
        if finite.size == 0:
            return
        step = max(1, math.ceil(finite.size / 28))
        for index in finite[::step]:
            arrow_index = int(((direction[index] % 360) + 22.5) // 45) % 8
            axis.text(
                x[index],
                0.04,
                WIND_ARROWS[arrow_index],
                transform=axis.get_xaxis_transform(),
                ha="center",
                va="bottom",
                fontsize=8.5,
                color="#2f5d46",
                fontweight="bold",
            )

    def _annotate_events(
        self,
        axes: tuple[Axes, ...],
        x: np.ndarray,
        forecast: ForecastSeries,
    ) -> None:
        thunder = np.asarray(
            [point.weather_code in THUNDER_CODES for point in forecast.points],
            dtype=bool,
        )
        if thunder.any():
            indices = np.flatnonzero(thunder)
            left = x[indices[0]]
            right = x[indices[-1]]
            for axis in axes:
                axis.axvspan(left, right, color="#7b2cbf", alpha=0.065, linewidth=0, zorder=0.2)
            axes[0].text(
                (left + right) / 2,
                0.12,
                "гроза",
                transform=axes[0].get_xaxis_transform(),
                ha="center",
                fontsize=7.2,
                color="#6a1b9a",
                fontweight="bold",
            )

    def _mark_extrema(
        self,
        axis: Axes,
        x: np.ndarray,
        values: np.ndarray,
        unit: str,
    ) -> None:
        finite = np.flatnonzero(np.isfinite(values))
        if finite.size == 0:
            return
        for index in {int(finite[np.argmin(values[finite])]), int(finite[np.argmax(values[finite])])}:
            axis.scatter([x[index]], [values[index]], s=12, color=self.palette.temperature, zorder=6)
            axis.annotate(
                f"{values[index]:.1f} {unit}".replace(".", ","),
                (x[index], values[index]),
                xytext=(0, 7),
                textcoords="offset points",
                ha="center",
                fontsize=7,
                color=self.palette.temperature,
            )

    def _finish_professional(
        self,
        figure: Figure,
        axes: tuple[Axes, ...],
        times: list[datetime],
        *,
        ensemble: bool,
    ) -> None:
        timezone = times[0].tzinfo
        axes[-1].xaxis.set_major_locator(mdates.DayLocator(interval=1, tz=timezone))
        axes[-1].xaxis.set_major_formatter(
            FuncFormatter(lambda value, _position: russian_day_label(value, timezone=timezone))
        )
        axes[-1].xaxis.set_minor_locator(mdates.HourLocator(byhour=(6, 12, 18), tz=timezone))
        axes[-1].xaxis.set_minor_formatter(mdates.DateFormatter("%H", tz=timezone))
        axes[-1].tick_params(axis="x", which="major", labelsize=8, pad=5)
        axes[-1].tick_params(axis="x", which="minor", labelsize=7, pad=2)
        axes[-1].set_xlim(times[0], times[-1])
        for axis in axes[:-1]:
            axis.tick_params(axis="x", labelbottom=False)
        band_text = (
            "тёмная полоса — 25–75-й процентили; светлая — 10–90-й"
            if ensemble
            else "линии проходят через исходные расчётные сроки"
        )
        figure.text(
            0.065,
            0.012,
            f"{russian_timezone_label(times[0])} · серые полосы — ночь · {band_text}",
            fontsize=7.2,
            color="#53636d",
        )
        figure.subplots_adjust(left=0.065, right=0.935, top=0.94, bottom=0.12)
