from __future__ import annotations

from datetime import UTC, datetime

from weather_to_docx.document.source_names import source_display_name
from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    Location,
    SourceMetadata,
)

LOCATION = Location(
    id="source-name",
    name="Точка",
    latitude=59.9,
    longitude=30.3,
    timezone="UTC",
)
NOW = datetime(2026, 8, 6, tzinfo=UTC)


def _forecast(
    *,
    source_id: str,
    provider: str,
    model: str,
) -> ForecastSeries:
    point = ForecastPoint(
        valid_time_utc=NOW,
        valid_time_local=NOW,
        lead_hours=0,
        weather_code=2,
        is_day=True,
        values={
            "temperature_2m": ForecastValue(value=20.0),
            "wind_speed_10m": ForecastValue(value=3.0),
            "pressure_msl": ForecastValue(value=1012.0),
        },
    )
    return ForecastSeries(
        location=LOCATION,
        source=SourceMetadata(
            source_id=source_id,
            provider=provider,
            model=model,
            product="test",
            retrieved_at_utc=NOW,
            exact_cycle_known=False,
        ),
        points=[point],
    )


def test_direct_and_open_meteo_gfs_names_are_distinct() -> None:
    direct = _forecast(
        source_id="noaa_gfs_0p25",
        provider="NOAA/NCEP NOMADS",
        model="Global Forecast System (GFS)",
    )
    delivered = _forecast(
        source_id="open_meteo_gfs",
        provider="Open-Meteo / NOAA",
        model="NOAA GFS 0.25°",
    )

    assert source_display_name(direct) == "NOAA GFS (NOMADS)"
    assert source_display_name(delivered) == "NOAA GFS (Open-Meteo)"
    assert source_display_name(direct) != source_display_name(delivered)
