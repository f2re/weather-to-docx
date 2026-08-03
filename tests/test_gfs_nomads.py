from __future__ import annotations

from datetime import UTC, date, datetime

from weather_to_docx.domain.models import Location
from weather_to_docx.sources.gfs_nomads import GfsNomadsSource, GfsRun


def test_forecast_hours_use_hourly_then_three_hourly() -> None:
    values = GfsNomadsSource.forecast_hours(130, hourly_to_120=True)
    assert values[:3] == [0, 1, 2]
    assert 120 in values
    assert values[-3:] == [123, 126, 129]


def test_subset_url_parameters() -> None:
    run = GfsRun(date(2026, 8, 3), 12)
    location = Location(id="spb", name="СПб", latitude=59.94, longitude=30.31)
    params = GfsNomadsSource.subset_params(
        location=location,
        run=run,
        forecast_hour=6,
        box_degrees=0.5,
    )
    assert params["file"] == "gfs.t12z.pgrb2.0p25.f006"
    assert params["dir"] == "/gfs.20260803/12/atmos"
    assert params["var_TMP"] == "on"
    assert params["lev_2_m_above_ground"] == "on"


def test_candidate_runs_cross_midnight() -> None:
    values = GfsNomadsSource.candidate_runs(datetime(2026, 8, 3, 3, tzinfo=UTC), count=3)
    assert [(item.run_date.isoformat(), item.cycle) for item in values] == [
        ("2026-08-02", 18),
        ("2026-08-02", 12),
        ("2026-08-02", 6),
    ]
