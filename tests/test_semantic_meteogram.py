from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import numpy as np
import pytest
from PIL import Image

from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    Location,
    SourceMetadata,
)
from weather_to_docx.plotting.semantic_meteogram import SemanticMeteogramRenderer


LOCATION = Location(
    id="semantic-chart",
    name="Смысловая шкала",
    latitude=59.9,
    longitude=30.3,
    timezone="UTC",
)
START = datetime(2026, 8, 5, tzinfo=UTC)


def _forecast(
    *,
    precipitation: tuple[float, ...] = (0.0, 1.0, 4.0, 14.0),
    weather_codes: tuple[int, ...] = (2, 51, 63, 95),
) -> ForecastSeries:
    temperatures = (-3.0, -1.0, 2.0, 32.0)
    points = []
    for index in range(4):
        valid = START + timedelta(hours=index)
        points.append(
            ForecastPoint(
                valid_time_utc=valid,
                valid_time_local=valid,
                lead_hours=index,
                weather_code=weather_codes[index],
                is_day=index >= 2,
                values={
                    "temperature_2m": ForecastValue(value=temperatures[index]),
                    "dew_point_2m": ForecastValue(value=temperatures[index] - 1),
                    "relative_humidity_2m": ForecastValue(value=(60, 96, 92, 80)[index]),
                    "precipitation": ForecastValue(
                        value=precipitation[index],
                        accumulation_hours=1,
                    ),
                    "wind_speed_10m": ForecastValue(value=(2, 6, 11, 16)[index]),
                    "wind_gusts_10m": ForecastValue(value=(4, 9, 15, 23)[index]),
                    "wind_direction_10m": ForecastValue(value=(0, 90, 180, 270)[index]),
                    "pressure_msl": ForecastValue(value=(1015, 1008, 995, 985)[index]),
                    "cloud_cover_low": ForecastValue(value=30),
                    "cloud_cover_mid": ForecastValue(value=40),
                    "cloud_cover_high": ForecastValue(value=50),
                },
            )
        )
    return ForecastSeries(
        location=LOCATION,
        source=SourceMetadata(
            source_id="semantic-test",
            provider="Test",
            model="Semantic",
            product="test",
            retrieved_at_utc=START,
            exact_cycle_known=False,
        ),
        points=points,
    )


def _multi_day_forecast() -> ForecastSeries:
    points = []
    precipitation_pattern = (0.2, 0.0, 0.3, 0.0)
    for index in range(28):
        valid = START + timedelta(hours=6 * index)
        amount = precipitation_pattern[index % len(precipitation_pattern)]
        points.append(
            ForecastPoint(
                valid_time_utc=valid,
                valid_time_local=valid,
                lead_hours=6 * index,
                weather_code=51 if amount > 0 else 2,
                is_day=6 <= valid.hour < 18,
                values={
                    "temperature_2m": ForecastValue(value=15 + (index % 4)),
                    "dew_point_2m": ForecastValue(value=12 + (index % 4)),
                    "relative_humidity_2m": ForecastValue(value=75),
                    "precipitation": ForecastValue(value=amount, accumulation_hours=6),
                    "wind_speed_10m": ForecastValue(value=4),
                    "wind_gusts_10m": ForecastValue(value=8),
                    "wind_direction_10m": ForecastValue(value=240),
                    "pressure_msl": ForecastValue(value=1012),
                    "cloud_cover_low": ForecastValue(value=40),
                    "cloud_cover_mid": ForecastValue(value=30),
                    "cloud_cover_high": ForecastValue(value=20),
                },
            )
        )
    return ForecastSeries(
        location=LOCATION,
        source=SourceMetadata(
            source_id="semantic-layout-test",
            provider="Test",
            model="Semantic layout",
            product="test",
            retrieved_at_utc=START,
            exact_cycle_known=False,
        ),
        points=points,
    )


def test_precipitation_axis_is_fixed_and_bar_heights_are_comparable() -> None:
    forecast = _forecast()
    renderer = SemanticMeteogramRenderer(dpi=100)
    figure, axes = renderer._new_professional_figure("Осадки")
    x = mdates.date2num([point.valid_time_local for point in forecast.points])
    renderer._plot_precipitation(axes[3], np.asarray(x), forecast, ensemble=False)

    bars = axes[3]._weather_precipitation_bars
    heights = [patch.get_height() for patch in bars.patches]
    assert axes[3].get_ylim() == pytest.approx((0.0, 12.0))
    assert heights[1] == pytest.approx(1.0)
    assert heights[2] == pytest.approx(4.0)
    assert heights[2] / heights[1] == pytest.approx(4.0)
    assert heights[3] == pytest.approx(12.0)

    assert bars.patches[1].get_linewidth() == pytest.approx(0.0)
    assert bars.patches[1].get_edgecolor()[3] == pytest.approx(0.0)
    assert bars.patches[3].get_linewidth() == pytest.approx(0.9)
    assert bars.patches[3].get_edgecolor()[:3] == pytest.approx((0.4157, 0.1059, 0.6039), abs=1e-3)
    assert bars.patches[3].get_edgecolor()[3] == pytest.approx(1.0)
    figure.clear()


def test_trace_precipitation_uses_marker_without_false_bar_height() -> None:
    forecast = _forecast(
        precipitation=(0.05, 0.0, 0.0, 0.0),
        weather_codes=(51, 2, 2, 2),
    )
    renderer = SemanticMeteogramRenderer(dpi=100)
    figure, axes = renderer._new_professional_figure("Следы осадков")
    x = mdates.date2num([point.valid_time_local for point in forecast.points])
    renderer._plot_precipitation(axes[3], np.asarray(x), forecast, ensemble=False)

    bars = axes[3]._weather_precipitation_bars
    assert bars.patches[0].get_height() == pytest.approx(0.0)
    assert axes[3]._weather_precipitation_trace_markers is not None
    figure.clear()


def test_precipitation_labels_and_legend_use_separate_layout_rows() -> None:
    forecast = _multi_day_forecast()
    renderer = SemanticMeteogramRenderer(dpi=100)
    figure, axes = renderer._new_professional_figure("Компоновка осадков")
    x = mdates.date2num([point.valid_time_local for point in forecast.points])
    renderer._plot_precipitation(axes[3], np.asarray(x), forecast, ensemble=False)
    figure.canvas.draw()

    legend = axes[3].get_legend()
    assert legend is not None
    assert legend.get_frame().get_alpha() >= 0.9
    axis_box = axes[3].get_window_extent()
    legend_box = legend.get_window_extent()
    assert legend_box.y0 >= axis_box.y1

    labels = axes[3]._weather_precipitation_daily_labels
    assert labels
    assert all("\n" not in label.get_text() for label in labels)
    label_boxes = sorted((label.get_window_extent() for label in labels), key=lambda box: box.x0)
    assert all(left.x1 <= right.x0 for left, right in zip(label_boxes, label_boxes[1:], strict=False))
    assert max(box.y1 for box in label_boxes) < legend_box.y0
    figure.clear()


def test_temperature_axis_has_common_range_and_marks_zero_crossing() -> None:
    forecast = _forecast()
    renderer = SemanticMeteogramRenderer(dpi=100)
    figure, axes = renderer._new_professional_figure("Температура")
    x = mdates.date2num([point.valid_time_local for point in forecast.points])
    renderer._plot_temperature(axes[1], np.asarray(x), forecast, ensemble=False)

    lower, upper = axes[1].get_ylim()
    assert lower <= -20
    assert upper >= 40
    texts = [text.get_text() for text in axes[1].texts]
    assert "через 0 °C" in texts
    assert "жара" in texts
    assert axes[1].get_legend() is not None
    assert axes[1].get_legend().get_frame().get_alpha() >= 0.9
    figure.clear()


def test_wind_and_pressure_do_not_autoscale_small_variations() -> None:
    forecast = _forecast()
    renderer = SemanticMeteogramRenderer(dpi=100)
    figure, axes = renderer._new_professional_figure("Ветер")
    x = mdates.date2num([point.valid_time_local for point in forecast.points])
    renderer._plot_wind_pressure(axes[4], np.asarray(x), forecast, ensemble=False)

    assert axes[4].get_ylim()[0] == 0
    assert axes[4].get_ylim()[1] >= 25
    pressure_axis = figure.axes[-1]
    assert pressure_axis.get_ylim()[0] <= 970
    assert pressure_axis.get_ylim()[1] >= 1040
    assert axes[4].get_legend() is not None
    figure.clear()


def test_full_semantic_meteogram_renders(tmp_path: Path) -> None:
    output = tmp_path / "semantic.png"
    SemanticMeteogramRenderer(dpi=100).render_deterministic(
        _forecast(),
        output,
        title="Проверка смысловых шкал",
    )
    with Image.open(output) as image:
        assert image.width > 1000
        assert image.height > 650
