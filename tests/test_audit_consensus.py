from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from weather_to_docx.analysis.consensus import (
    build_risk_signals,
    daily_agreement,
    daily_precipitation_total,
)
from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    Location,
    SourceMetadata,
)


LOCATION = Location(
    id="audit-point",
    name="Точка аудита",
    latitude=59.9,
    longitude=30.3,
    timezone="UTC",
)
START = datetime(2026, 8, 5, tzinfo=UTC)


def _series(source_id: str, *, thunder: bool, temperature: float = 20) -> ForecastSeries:
    points = []
    for hour in (0, 3, 6, 9):
        points.append(
            ForecastPoint(
                valid_time_utc=START + timedelta(hours=hour),
                valid_time_local=START + timedelta(hours=hour),
                lead_hours=hour,
                weather_code=95 if thunder and hour in {3, 6} else 2,
                values={
                    "temperature_2m": ForecastValue(value=temperature + hour / 10),
                    "precipitation": ForecastValue(
                        value=2.0 if thunder else 0.0,
                        source_start_step=max(0, hour - 3),
                        source_end_step=hour,
                        accumulation_hours=3,
                    ),
                    "wind_speed_10m": ForecastValue(value=4.0),
                    "wind_gusts_10m": ForecastValue(value=8.0),
                    "pressure_msl": ForecastValue(value=1015.0),
                },
            )
        )
    return ForecastSeries(
        location=LOCATION,
        source=SourceMetadata(
            source_id=source_id,
            provider="Test",
            model=source_id,
            product="test",
            retrieved_at_utc=START,
            exact_cycle_known=False,
        ),
        points=points,
    )


def test_overlapping_accumulation_intervals_are_not_double_counted() -> None:
    points = [
        ForecastPoint(
            valid_time_utc=START + timedelta(hours=index),
            valid_time_local=START + timedelta(hours=index),
            values={
                "precipitation": ForecastValue(
                    value=value,
                    source_start_step=start,
                    source_end_step=end,
                    accumulation_hours=end - start,
                )
            },
        )
        for index, (start, end, value) in enumerate(
            ((0, 3, 2.0), (0, 3, 1.0), (2, 5, 4.0), (5, 6, 1.0))
        )
    ]
    assert daily_precipitation_total(points) == 3.0


def test_single_model_has_no_false_agreement_grade() -> None:
    forecast = _series("one", thunder=False)
    assert daily_agreement([forecast], date(2026, 8, 5)) is None


def test_single_thunder_model_is_labelled_as_separate_scenario() -> None:
    signals = build_risk_signals(
        [_series("thunder", thunder=True), _series("dry", thunder=False)],
        [],
        [date(2026, 8, 5)],
    )
    thunder = next(signal for signal in signals if signal.phenomenon == "ГРОЗА")
    assert thunder.scenario == "Отдельный сценарий"
    assert thunder.support_count == 1
    assert thunder.model_count == 2
    assert thunder.confidence == "низкая"


def test_majority_thunder_signal_is_stable() -> None:
    signals = build_risk_signals(
        [_series("one", thunder=True), _series("two", thunder=True)],
        [],
        [date(2026, 8, 5)],
    )
    thunder = next(signal for signal in signals if signal.phenomenon == "ГРОЗА")
    assert thunder.scenario == "Устойчивый сигнал"
    assert thunder.support_text == "2 из 2 моделей"
    assert thunder.confidence == "высокая"


def test_agreement_detects_temperature_disagreement() -> None:
    agreement = daily_agreement(
        [
            _series("cold", thunder=False, temperature=12),
            _series("warm", thunder=False, temperature=24),
        ],
        date(2026, 8, 5),
    )
    assert agreement is not None
    assert agreement.temperature == "низкая"
    assert "температура — низкая" in agreement.note
