from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from weather_to_docx.domain.models import Location
from weather_to_docx.sources.open_meteo import OpenMeteoGfsSource

FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_gfs.json"


def test_parse_open_meteo_payload() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    location = Location(
        id="spb",
        name="Санкт-Петербург",
        latitude=59.9386,
        longitude=30.3141,
        elevation_m=12,
        timezone="Europe/Moscow",
    )
    series = OpenMeteoGfsSource.parse_payload(
        payload,
        location=location,
        retrieved_at_utc=datetime(2026, 8, 3, 6, tzinfo=UTC),
    )

    assert len(series.points) == 6
    assert series.points[0].valid_time_utc.tzinfo is not None
    assert series.points[0].valid_time_local.hour == 3
    assert series.points[4].weather_code == 63
    assert series.points[4].raw("precipitation") == 2.3
    assert series.source.exact_cycle_known is False
    assert series.source.native_time_step_hours == 1
    assert series.source.grid_distance_km is not None
