from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

import matplotlib
import numpy as np

matplotlib.use("Agg", force=True)

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from weather_to_docx.domain.models import ForecastPoint, ForecastSeries
from weather_to_docx.plotting.smoothing import smooth_segments

FONT_FAMILY: Final = ["Liberation Sans", "DejaVu Sans"]


@dataclass(frozen=True, slots=True)
class MeteogramPalette:
    temperature: str = "#e55d2d"
    temperature_band: str = "#f39a76"
    humidity: str = "#168aad"
    humidity_band: str = "#8ecae6"
    precipitation: str = "#2878b5"
    precipitation_light: str = "#90caf9"
    wind: str = "#318b5b"
    gust: str = "#145a32"
    pressure: str = "#7656a6"
    cloud_low: str = "#5f6b73"
    cloud_mid: str = "#89949b"
    cloud_high: str = "#c0c8cd"
    grid: str = "#d7dee3"
    night: str = "#243447"
    text: str = "#1f2d36"


class MeteogramRenderer:
    """Рендер автономных PNG-метеограмм для DOCX.

    Визуальная композиция основана на общих приёмах профессиональных
    метеограмм: единая временная шкала, полупрозрачные облачные слои,
    непрерывные поля с shape-preserving сглаживанием и несглаженные осадки.
    """

    def __init__(
        self,
        *,
        dpi: int = 180,
        smoothing: str = "pchip",
        palette: MeteogramPalette | None = None,
    ) -> None:
        if not 96 <= dpi <= 360:
            raise ValueError("Разрешение метеограммы должно быть от 96 до 360 dpi")
        if smoothing not in {"pchip", "linear"}:
            raise ValueError("Поддерживаются режимы сглаживания pchip и linear")
        self.dpi = dpi
        self.smoothing = smoothing
        self.palette = palette or MeteogramPalette()

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
        figure, axes = self._new_figure(title or forecast.source.model)
        cloud_ax, thermo_ax, precip_ax, wind_ax = axes
        self._shade_night(axes, forecast.points, x)
        self._plot_clouds_deterministic(cloud_ax, x, forecast)
        self._plot_thermodynamics_deterministic(thermo_ax, x, forecast)
        self._plot_precipitation_deterministic(precip_ax, x, forecast)
        self._plot_wind_pressure_deterministic(wind_ax, x, forecast)
        self._finish_figure(figure, axes, times, forecast)
        return self._save(figure, output_path)

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
        figure, axes = self._new_figure(title or forecast.source.model)
        cloud_ax, thermo_ax, precip_ax, wind_ax = axes
        self._shade_night(axes, forecast.points, x)
        self._plot_clouds_ensemble(cloud_ax, x, forecast)
        self._plot_thermodynamics_ensemble(thermo_ax, x, forecast)
        self._plot_precipitation_ensemble(precip_ax, x, forecast)
        self._plot_wind_pressure_ensemble(wind_ax, x, forecast)
        self._finish_figure(figure, axes, times, forecast, ensemble=True)
        return self._save(figure, output_path)

    def _new_figure(self, title: str) -> tuple[Figure, tuple[Axes, Axes, Axes, Axes]]:
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
            4,
            1,
            figsize=(11.4, 4.8),
            dpi=self.dpi,
            sharex=True,
            gridspec_kw={"height_ratios": (0.65, 2.0, 0.85, 1.25), "hspace": 0.08},
        )
        figure.patch.set_facecolor("white")
        figure.suptitle(title, x=0.055, y=0.99, ha="left", fontsize=12, fontweight="bold")
        for axis in axes:
            axis.set_axisbelow(True)
            axis.grid(axis="x", color=self.palette.grid, linewidth=0.55, alpha=0.8)
            axis.spines[["top", "right"]].set_visible(False)
            axis.tick_params(labelsize=7, length=2)
        return figure, tuple(axes)

    def _plot_clouds_deterministic(self, axis: Axes, x: np.ndarray, forecast: ForecastSeries) -> None:
        axis.set_facecolor("#edf8ff")
        low = _values(forecast, "cloud_cover_low")
        middle = _values(forecast, "cloud_cover_mid")
        high = _values(forecast, "cloud_cover_high")
        total = _values(forecast, "cloud_cover")
        available_layers = np.isfinite(low).any() or np.isfinite(middle).any() or np.isfinite(high).any()
        if available_layers:
            self._fill_smoothed(axis, x, high, 0, self.palette.cloud_high, 0.32, lower=0, upper=100)
            self._fill_smoothed(axis, x, middle, 0, self.palette.cloud_mid, 0.34, lower=0, upper=100)
            self._fill_smoothed(axis, x, low, 0, self.palette.cloud_low, 0.38, lower=0, upper=100)
            axis.text(0.005, 0.83, "облака: низкие / средние / высокие", transform=axis.transAxes, fontsize=6.8)
        else:
            self._fill_smoothed(axis, x, total, 0, self.palette.cloud_mid, 0.4, lower=0, upper=100)
            axis.text(0.005, 0.83, "общая облачность", transform=axis.transAxes, fontsize=6.8)
        axis.set_ylim(0, 100)
        axis.set_yticks((0, 50, 100), labels=("0", "50", "100 %"))
        axis.tick_params(axis="y", labelsize=6)

    def _plot_thermodynamics_deterministic(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
    ) -> None:
        temperature = _values(forecast, "temperature_2m")
        humidity = _values(forecast, "relative_humidity_2m")
        dewpoint = _values(forecast, "dew_point_2m")
        self._line_smoothed(axis, x, temperature, self.palette.temperature, 1.8, "температура")
        if np.isfinite(dewpoint).any():
            self._line_smoothed(axis, x, dewpoint, self.palette.humidity, 1.0, "точка росы", "--")
        axis.axhline(0, color="#7b8790", linewidth=0.7, alpha=0.6)
        axis.set_ylabel("°C", fontsize=7, rotation=0, labelpad=12)
        humidity_axis = axis.twinx()
        humidity_axis.spines["top"].set_visible(False)
        humidity_axis.spines["right"].set_color(self.palette.humidity)
        self._fill_smoothed(
            humidity_axis,
            x,
            humidity,
            0,
            self.palette.humidity_band,
            0.13,
            lower=0,
            upper=100,
        )
        self._line_smoothed(
            humidity_axis,
            x,
            humidity,
            self.palette.humidity,
            1.0,
            "влажность",
        )
        humidity_axis.set_ylim(0, 100)
        humidity_axis.set_ylabel("%", fontsize=7, rotation=0, labelpad=10)
        humidity_axis.tick_params(axis="y", labelsize=6, colors=self.palette.humidity)
        _combined_legend(axis, humidity_axis, loc="upper left")

    def _plot_precipitation_deterministic(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
    ) -> None:
        precipitation = np.nan_to_num(_values(forecast, "precipitation"), nan=0.0)
        width = _bar_width(x)
        axis.bar(
            x,
            precipitation,
            width=width,
            align="center",
            color=self.palette.precipitation,
            alpha=0.68,
            linewidth=0,
            label="осадки за интервал",
        )
        axis.set_ylabel("мм", fontsize=7, rotation=0, labelpad=12)
        axis.set_ylim(bottom=0)
        axis.legend(loc="upper left", fontsize=6.5, frameon=False)

    def _plot_wind_pressure_deterministic(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
    ) -> None:
        wind = _values(forecast, "wind_speed_10m")
        gust = _values(forecast, "wind_gusts_10m")
        pressure = _values(forecast, "pressure_msl")
        self._line_smoothed(axis, x, wind, self.palette.wind, 1.6, "ветер")
        self._line_smoothed(axis, x, gust, self.palette.gust, 1.1, "порывы", "--")
        axis.set_ylabel("м/с", fontsize=7, rotation=0, labelpad=12)
        axis.set_ylim(bottom=0)
        pressure_axis = axis.twinx()
        pressure_axis.spines["top"].set_visible(False)
        pressure_axis.spines["right"].set_color(self.palette.pressure)
        self._line_smoothed(
            pressure_axis,
            x,
            pressure,
            self.palette.pressure,
            1.15,
            "давление",
        )
        pressure_axis.set_ylabel("гПа", fontsize=7, rotation=0, labelpad=13)
        pressure_axis.tick_params(axis="y", labelsize=6, colors=self.palette.pressure)
        _combined_legend(axis, pressure_axis, loc="upper left")

    def _plot_clouds_ensemble(self, axis: Axes, x: np.ndarray, forecast: ForecastSeries) -> None:
        axis.set_facecolor("#edf8ff")
        centre = _stat_values(forecast, "cloud_cover", "median")
        if not np.isfinite(centre).any():
            centre = _values(forecast, "cloud_cover")
        lower = _stat_values(forecast, "cloud_cover", "p10")
        upper = _stat_values(forecast, "cloud_cover", "p90")
        self._band(axis, x, lower, upper, self.palette.cloud_mid, 0.2, lower_bound=0, upper_bound=100)
        self._fill_smoothed(axis, x, centre, 0, self.palette.cloud_low, 0.32, lower=0, upper=100)
        self._line_smoothed(axis, x, centre, self.palette.cloud_low, 1.0, "медиана облачности")
        axis.set_ylim(0, 100)
        axis.set_yticks((0, 50, 100), labels=("0", "50", "100 %"))
        axis.tick_params(axis="y", labelsize=6)
        axis.legend(loc="upper left", fontsize=6.4, frameon=False)

    def _plot_thermodynamics_ensemble(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
    ) -> None:
        temperature = _ensemble_centre(forecast, "temperature_2m")
        temperature_low = _stat_values(forecast, "temperature_2m", "p10")
        temperature_high = _stat_values(forecast, "temperature_2m", "p90")
        temperature_mean = _stat_values(forecast, "temperature_2m", "mean")
        temperature_spread = _stat_values(forecast, "temperature_2m", "spread")
        self._band(
            axis,
            x,
            temperature_low,
            temperature_high,
            self.palette.temperature_band,
            0.24,
        )
        inner_low = temperature_mean - temperature_spread
        inner_high = temperature_mean + temperature_spread
        inner_low = np.maximum(inner_low, temperature_low)
        inner_high = np.minimum(inner_high, temperature_high)
        self._band(axis, x, inner_low, inner_high, self.palette.temperature, 0.16)
        self._line_smoothed(axis, x, temperature, self.palette.temperature, 1.8, "медиана температуры")
        axis.axhline(0, color="#7b8790", linewidth=0.7, alpha=0.6)
        axis.set_ylabel("°C", fontsize=7, rotation=0, labelpad=12)

        humidity_axis = axis.twinx()
        humidity_axis.spines["top"].set_visible(False)
        humidity_axis.spines["right"].set_color(self.palette.humidity)
        humidity = _ensemble_centre(forecast, "relative_humidity_2m")
        humidity_low = _stat_values(forecast, "relative_humidity_2m", "p10")
        humidity_high = _stat_values(forecast, "relative_humidity_2m", "p90")
        self._band(
            humidity_axis,
            x,
            humidity_low,
            humidity_high,
            self.palette.humidity_band,
            0.13,
            lower_bound=0,
            upper_bound=100,
        )
        self._line_smoothed(
            humidity_axis,
            x,
            humidity,
            self.palette.humidity,
            1.0,
            "медиана влажности",
        )
        humidity_axis.set_ylim(0, 100)
        humidity_axis.set_ylabel("%", fontsize=7, rotation=0, labelpad=10)
        humidity_axis.tick_params(axis="y", labelsize=6, colors=self.palette.humidity)
        _combined_legend(axis, humidity_axis, loc="upper left")

    def _plot_precipitation_ensemble(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
    ) -> None:
        precipitation = _ensemble_centre(forecast, "precipitation")
        width = _bar_width(x)
        axis.bar(
            x,
            np.nan_to_num(precipitation, nan=0.0),
            width=width,
            color=self.palette.precipitation,
            alpha=0.5,
            linewidth=0,
            label="медиана осадков",
        )
        axis.set_ylabel("мм", fontsize=7, rotation=0, labelpad=12)
        axis.set_ylim(bottom=0)
        probability_axis = axis.twinx()
        probability_axis.spines["top"].set_visible(False)
        probability_axis.set_ylim(0, 100)
        probability_axis.set_ylabel("%", fontsize=7, rotation=0, labelpad=10)
        probability_axis.tick_params(axis="y", labelsize=6, colors=self.palette.precipitation)
        probability_codes = _probability_codes(forecast)
        line_styles = ("-", "--", ":")
        alphas = (0.18, 0.12, 0.08)
        for index, (code, threshold) in enumerate(probability_codes[:3]):
            probability = _values(forecast, code)
            color = self.palette.precipitation
            probability_axis.fill_between(
                x,
                0,
                np.nan_to_num(probability, nan=0.0),
                step="mid",
                color=color,
                alpha=alphas[index],
            )
            probability_axis.step(
                x,
                probability,
                where="mid",
                color=color,
                linewidth=1.0,
                linestyle=line_styles[index],
                label=f"P(≥{threshold} мм)",
            )
        _combined_legend(axis, probability_axis, loc="upper left")

    def _plot_wind_pressure_ensemble(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
    ) -> None:
        wind = _ensemble_centre(forecast, "wind_speed_10m")
        wind_low = _stat_values(forecast, "wind_speed_10m", "p10")
        wind_high = _stat_values(forecast, "wind_speed_10m", "p90")
        gust_high = _stat_values(forecast, "wind_gusts_10m", "p90")
        self._band(axis, x, wind_low, wind_high, self.palette.wind, 0.16, lower_bound=0)
        self._line_smoothed(axis, x, wind, self.palette.wind, 1.6, "медиана ветра")
        self._line_smoothed(axis, x, gust_high, self.palette.gust, 1.1, "q90 порывов", "--")
        axis.set_ylabel("м/с", fontsize=7, rotation=0, labelpad=12)
        axis.set_ylim(bottom=0)

        pressure_axis = axis.twinx()
        pressure_axis.spines["top"].set_visible(False)
        pressure_axis.spines["right"].set_color(self.palette.pressure)
        pressure = _ensemble_centre(forecast, "pressure_msl")
        pressure_low = _stat_values(forecast, "pressure_msl", "p10")
        pressure_high = _stat_values(forecast, "pressure_msl", "p90")
        self._band(
            pressure_axis,
            x,
            pressure_low,
            pressure_high,
            self.palette.pressure,
            0.12,
        )
        self._line_smoothed(
            pressure_axis,
            x,
            pressure,
            self.palette.pressure,
            1.1,
            "давление",
        )
        pressure_axis.set_ylabel("гПа", fontsize=7, rotation=0, labelpad=13)
        pressure_axis.tick_params(axis="y", labelsize=6, colors=self.palette.pressure)
        _combined_legend(axis, pressure_axis, loc="upper left")

    def _line_smoothed(
        self,
        axis: Axes,
        x: np.ndarray,
        values: np.ndarray,
        color: str,
        linewidth: float,
        label: str,
        linestyle: str = "-",
    ) -> None:
        segments = self._segments(x, values)
        for index, (smooth_x, smooth_y) in enumerate(segments):
            axis.plot(
                smooth_x,
                smooth_y,
                color=color,
                linewidth=linewidth,
                linestyle=linestyle,
                label=label if index == 0 else None,
                solid_capstyle="round",
                solid_joinstyle="round",
            )

    def _fill_smoothed(
        self,
        axis: Axes,
        x: np.ndarray,
        values: np.ndarray,
        baseline: float,
        color: str,
        alpha: float,
        *,
        lower: float | None = None,
        upper: float | None = None,
    ) -> None:
        for smooth_x, smooth_y in self._segments(x, values, lower=lower, upper=upper):
            axis.fill_between(smooth_x, baseline, smooth_y, color=color, alpha=alpha, linewidth=0)

    def _band(
        self,
        axis: Axes,
        x: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
        color: str,
        alpha: float,
        *,
        lower_bound: float | None = None,
        upper_bound: float | None = None,
    ) -> None:
        lower_segments = self._segments(x, lower, lower=lower_bound, upper=upper_bound)
        upper_segments = self._segments(x, upper, lower=lower_bound, upper=upper_bound)
        for (lower_x, lower_y), (upper_x, upper_y) in zip(
            lower_segments,
            upper_segments,
            strict=False,
        ):
            if lower_x.size != upper_x.size or not np.allclose(lower_x, upper_x):
                common = np.linspace(max(lower_x[0], upper_x[0]), min(lower_x[-1], upper_x[-1]), 200)
                if common[0] >= common[-1]:
                    continue
                lower_y = np.interp(common, lower_x, lower_y)
                upper_y = np.interp(common, upper_x, upper_y)
                lower_x = common
            low = np.minimum(lower_y, upper_y)
            high = np.maximum(lower_y, upper_y)
            axis.fill_between(lower_x, low, high, color=color, alpha=alpha, linewidth=0)

    def _segments(
        self,
        x: np.ndarray,
        values: np.ndarray,
        *,
        lower: float | None = None,
        upper: float | None = None,
    ) -> list[tuple[np.ndarray, np.ndarray]]:
        if self.smoothing == "linear":
            finite = np.isfinite(x) & np.isfinite(values)
            return [(x[finite], np.clip(values[finite], lower, upper))] if finite.any() else []
        return smooth_segments(
            x,
            values,
            samples_per_interval=5,
            lower=lower,
            upper=upper,
        )

    def _shade_night(
        self,
        axes: tuple[Axes, Axes, Axes, Axes],
        points: list[ForecastPoint],
        x: np.ndarray,
    ) -> None:
        if len(points) < 2:
            return
        edges = np.empty(len(x) + 1)
        edges[1:-1] = (x[:-1] + x[1:]) / 2
        edges[0] = x[0] - (x[1] - x[0]) / 2
        edges[-1] = x[-1] + (x[-1] - x[-2]) / 2
        for index, point in enumerate(points):
            if point.is_day is False:
                for axis in axes:
                    axis.axvspan(
                        edges[index],
                        edges[index + 1],
                        color=self.palette.night,
                        alpha=0.045,
                        linewidth=0,
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
        axes[-1].xaxis.set_major_locator(mdates.DayLocator(interval=1, tz=timezone))
        axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d.%m\n%a", tz=timezone))
        axes[-1].xaxis.set_minor_locator(mdates.HourLocator(byhour=(6, 12, 18), tz=timezone))
        axes[-1].xaxis.set_minor_formatter(mdates.DateFormatter("%H", tz=timezone))
        axes[-1].tick_params(axis="x", which="major", labelsize=7, pad=5)
        axes[-1].tick_params(axis="x", which="minor", labelsize=5.8, pad=2)
        axes[-1].set_xlim(times[0], times[-1])
        for axis in axes[:-1]:
            axis.tick_params(axis="x", labelbottom=False)
        explanation = (
            "линия — медиана; тёмная полоса — ±σ; светлая полоса — q10–q90"
            if ensemble
            else "непрерывные поля сглажены PCHIP; осадки показаны без сглаживания"
        )
        figure.text(
            0.055,
            0.01,
            f"{forecast.location.timezone} · {explanation}",
            fontsize=6.4,
            color="#53636d",
        )
        figure.subplots_adjust(left=0.055, right=0.945, top=0.93, bottom=0.12)

    def _save(self, figure: Figure, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(
            output_path,
            format="png",
            dpi=self.dpi,
            facecolor="white",
            bbox_inches="tight",
            pad_inches=0.06,
        )
        plt.close(figure)
        return output_path


def _times(forecast: ForecastSeries) -> list[datetime]:
    return [point.valid_time_local for point in forecast.points]


def _values(forecast: ForecastSeries, code: str) -> np.ndarray:
    values = []
    for point in forecast.points:
        raw = point.raw(code)
        try:
            value = float(raw) if raw is not None else math.nan
        except (TypeError, ValueError):
            value = math.nan
        values.append(value if math.isfinite(value) else math.nan)
    return np.asarray(values, dtype=float)


def _stat_values(forecast: ForecastSeries, code: str, statistic: str) -> np.ndarray:
    return _values(forecast, f"{code}_{statistic}")


def _ensemble_centre(forecast: ForecastSeries, code: str) -> np.ndarray:
    median = _stat_values(forecast, code, "median")
    if np.isfinite(median).any():
        return median
    mean = _stat_values(forecast, code, "mean")
    if np.isfinite(mean).any():
        return mean
    return _values(forecast, code)


def _bar_width(x: np.ndarray) -> float:
    if x.size < 2:
        return 0.03
    positive = np.diff(x)
    positive = positive[positive > 0]
    return float(np.median(positive) * 0.78) if positive.size else 0.03


def _probability_codes(forecast: ForecastSeries) -> list[tuple[str, str]]:
    codes: set[str] = set()
    for point in forecast.points:
        codes.update(
            code
            for code in point.values
            if code.startswith("precipitation_probability_ge_")
        )
    result = []
    for code in codes:
        threshold = (
            code.removeprefix("precipitation_probability_ge_")
            .removesuffix("mm")
            .replace("p", ",")
        )
        try:
            numeric = float(threshold.replace(",", "."))
        except ValueError:
            numeric = math.inf
        result.append((code, threshold, numeric))
    result.sort(key=lambda item: item[2])
    return [(code, threshold) for code, threshold, _ in result]


def _combined_legend(left_axis: Axes, right_axis: Axes, *, loc: str) -> None:
    handles_left, labels_left = left_axis.get_legend_handles_labels()
    handles_right, labels_right = right_axis.get_legend_handles_labels()
    if handles_left or handles_right:
        left_axis.legend(
            handles_left + handles_right,
            labels_left + labels_right,
            loc=loc,
            fontsize=6.4,
            frameon=False,
            ncol=min(4, max(1, len(handles_left) + len(handles_right))),
        )
