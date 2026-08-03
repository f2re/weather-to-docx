from __future__ import annotations

from datetime import UTC, datetime

from weather_to_docx.document.weather_rules import derive_weather_code, weather_presentation
from weather_to_docx.domain.models import ForecastPoint, ForecastValue


def point(**values: float) -> ForecastPoint:
    now = datetime.now(UTC)
    return ForecastPoint(
        valid_time_utc=now,
        valid_time_local=now,
        is_day=True,
        values={key: ForecastValue(value=value) for key, value in values.items()},
    )


def test_thunderstorm_has_priority() -> None:
    item = point(cape=1200, precipitation=1.0, cloud_cover=100)
    assert derive_weather_code(item) == 95
    assert weather_presentation(item).icon_key == "thunderstorm"


def test_fog_without_precipitation() -> None:
    item = point(visibility=600, cloud_cover=40, precipitation=0)
    assert derive_weather_code(item) == 45
