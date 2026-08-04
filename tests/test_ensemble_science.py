from __future__ import annotations

from datetime import UTC, datetime

import pytest

from weather_to_docx.domain.models import SourceKind, SourceMetadata
from weather_to_docx.ensemble.science import (
    circular_mean_degrees,
    ensemble_statistics,
    primary_centre,
    probability_resolution,
    quantile_type8,
    raw_probability,
)


def test_hyndman_fan_type8_quantiles() -> None:
    sample = [10.0, 12.0, 14.0]
    assert quantile_type8(sample, 0.0) == 10.0
    assert quantile_type8(sample, 0.1) == 10.0
    assert quantile_type8(sample, 0.5) == 12.0
    assert quantile_type8(sample, 0.9) == 14.0
    assert quantile_type8(sample, 1.0) == 14.0

    # Для достаточно длинной равномерной выборки type 8 даёт интерполяцию,
    # а не выбор ближайшего порядкового элемента.
    assert quantile_type8(range(1, 11), 0.5) == pytest.approx(5.5)
    assert quantile_type8(range(1, 11), 0.1) == pytest.approx(1.3666666667)
    assert quantile_type8(range(1, 11), 0.9) == pytest.approx(9.6333333333)


def test_primary_centre_depends_on_distribution_type() -> None:
    temperature = ensemble_statistics([10.0, 11.0, 12.0, 13.0, 14.0])
    centre, policy = primary_centre("temperature_2m", temperature)
    assert centre == pytest.approx(12.0)
    assert policy == "mean"

    precipitation = ensemble_statistics([0.0, 0.0, 0.0, 0.5, 20.0])
    centre, policy = primary_centre("precipitation", precipitation)
    assert centre == pytest.approx(0.0)
    assert centre != pytest.approx(precipitation.mean)
    assert policy == "median"


def test_raw_probability_and_resolution() -> None:
    probability, exceedances, count = raw_probability(
        [0.0, 0.2, 1.0, 2.0],
        threshold=1.0,
    )
    assert probability == pytest.approx(50.0)
    assert exceedances == 2
    assert count == 4
    assert probability_resolution(count) == pytest.approx(25.0)


def test_circular_mean_does_not_average_north_to_south() -> None:
    direction = circular_mean_degrees([350.0, 0.0, 10.0])
    assert min(abs(direction), abs(direction - 360.0)) < 1e-8


def test_legacy_ensemble_metadata_is_upgraded() -> None:
    metadata = SourceMetadata(
        source_id="open_meteo_gefs_0p25",
        provider="Open-Meteo / NOAA",
        model="NOAA GEFS",
        product="ensemble statistics",
        retrieved_at_utc=datetime(2026, 8, 4, tzinfo=UTC),
        ensemble_member_count=31,
    )
    assert metadata.source_kind is SourceKind.ENSEMBLE


def test_unrelated_source_cannot_smuggle_ensemble_fields() -> None:
    with pytest.raises(ValueError, match="ансамблевого источника"):
        SourceMetadata(
            source_id="deterministic-test",
            provider="Test",
            model="Test deterministic",
            product="point forecast",
            retrieved_at_utc=datetime(2026, 8, 4, tzinfo=UTC),
            source_kind=SourceKind.DETERMINISTIC,
            ensemble_member_count=5,
        )
