from __future__ import annotations

import asyncio
from pathlib import Path

import matplotlib.dates as mdates
from PIL import Image, ImageStat

from weather_to_docx.domain.models import Location
from weather_to_docx.plotting.professional_meteogram import ProfessionalMeteogramRenderer
from weather_to_docx.sources.demo import DemoSource


LOCATION = Location(
    id="professional-chart",
    name="Санкт-Петербург",
    latitude=59.9386,
    longitude=30.3141,
    timezone="Europe/Moscow",
)


def _forecast():
    return asyncio.run(
        DemoSource().fetch(
            LOCATION,
            forecast_days=3,
            options={"hours": 72},
        )
    )


def test_professional_chart_has_five_readable_panels(tmp_path: Path) -> None:
    forecast = _forecast()
    output = tmp_path / "professional.png"
    renderer = ProfessionalMeteogramRenderer(dpi=120)
    renderer.render_deterministic(forecast, output)

    with Image.open(output).convert("L") as image:
        assert image.width > 1200
        assert image.height > 550
        thirds = (
            image.crop((0, 0, image.width, image.height // 3)),
            image.crop((0, image.height // 3, image.width, image.height * 2 // 3)),
            image.crop((0, image.height * 2 // 3, image.width, image.height)),
        )
        # Заголовок/облачность, центральные поля и временная шкала реально видимы.
        assert all(ImageStat.Stat(part).mean[0] < 253 for part in thirds)


def test_wind_direction_arrows_are_added() -> None:
    forecast = _forecast()
    renderer = ProfessionalMeteogramRenderer(dpi=120)
    figure, axes = renderer._new_professional_figure("Ветер")
    x = mdates.date2num([point.valid_time_local for point in forecast.points])
    renderer._add_wind_direction_arrows(axes[-1], x, forecast)
    assert len(axes[-1].texts) >= 10
    assert all(text.get_text() in "↓↙←↖↑↗→↘" for text in axes[-1].texts)
    figure.clear()


def test_cloud_panel_uses_separate_low_mid_high_bands() -> None:
    forecast = _forecast()
    renderer = ProfessionalMeteogramRenderer(dpi=120)
    figure, axes = renderer._new_professional_figure("Облачность")
    x = mdates.date2num([point.valid_time_local for point in forecast.points])
    renderer._plot_cloud_bands(axes[0], x, forecast, ensemble=False)
    labels = [tick.get_text() for tick in axes[0].get_yticklabels()]
    assert labels == ["низкие", "средние", "высокие"]
    assert len(axes[0].collections) >= 3
    figure.clear()
