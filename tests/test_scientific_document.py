from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from docx import Document

from weather_to_docx.document.scientific_generator import ScientificDocumentGenerator
from weather_to_docx.domain.models import (
    DocumentOptions,
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    LeadTimeReference,
    Location,
    QualityFlag,
    SourceKind,
    SourceMetadata,
    TimezoneSource,
)


def _location() -> Location:
    return Location(
        id="spb",
        name="Санкт-Петербург",
        latitude=59.9386,
        longitude=30.3141,
        timezone="Europe/Moscow",
        timezone_source=TimezoneSource.COORDINATES,
    )


def _deterministic(location: Location) -> ForecastSeries:
    valid = datetime(2026, 8, 4, 0, tzinfo=UTC)
    return ForecastSeries(
        location=location,
        source=SourceMetadata(
            source_id="gfs-test",
            provider="NOAA",
            model="GFS test",
            product="deterministic point forecast",
            source_kind=SourceKind.DETERMINISTIC,
            cycle_time_utc=valid,
            retrieved_at_utc=valid,
            horizon_hours=0,
            native_time_step_hours=1,
            lead_time_reference=LeadTimeReference.CYCLE,
        ),
        points=[
            ForecastPoint(
                valid_time_utc=valid,
                valid_time_local=valid,
                lead_hours=0,
                weather_code=1,
                is_day=False,
                values={
                    "temperature_2m": ForecastValue(value=18.0, unit="°C"),
                    "apparent_temperature": ForecastValue(
                        value=17.0,
                        unit="°C",
                    ),
                    "dew_point_2m": ForecastValue(value=10.0, unit="°C"),
                    "relative_humidity_2m": ForecastValue(value=60, unit="%"),
                    "precipitation": ForecastValue(
                        value=0.0,
                        unit="мм",
                        accumulation_hours=1,
                    ),
                    "wind_speed_10m": ForecastValue(value=4.0, unit="м/с"),
                    "wind_direction_10m": ForecastValue(value=270, unit="°"),
                    "pressure_msl": ForecastValue(value=1012.0, unit="гПа"),
                    "cloud_cover": ForecastValue(value=20, unit="%"),
                },
            )
        ],
    )


def _ensemble(location: Location, model: str, offset: float = 0) -> ForecastSeries:
    valid = datetime(2026, 8, 4, 0, tzinfo=UTC)
    calculated = QualityFlag.CALCULATED
    values = {
        "temperature_2m_mean": ForecastValue(
            value=18.0 + offset,
            unit="°C",
            quality=calculated,
            sample_count=31,
        ),
        "temperature_2m_spread": ForecastValue(
            value=1.5,
            unit="°C",
            quality=calculated,
            sample_count=31,
        ),
        "temperature_2m_p10": ForecastValue(
            value=16.0 + offset,
            unit="°C",
            quality=calculated,
            sample_count=31,
        ),
        "temperature_2m_p90": ForecastValue(
            value=20.0 + offset,
            unit="°C",
            quality=calculated,
            sample_count=31,
        ),
        "precipitation_median": ForecastValue(
            value=0.4,
            unit="мм",
            quality=calculated,
            sample_count=31,
        ),
        "precipitation_p10": ForecastValue(
            value=0.0,
            unit="мм",
            quality=calculated,
            sample_count=31,
        ),
        "precipitation_p90": ForecastValue(
            value=3.2,
            unit="мм",
            quality=calculated,
            sample_count=31,
        ),
        "wind_speed_10m_median": ForecastValue(
            value=5.0,
            unit="м/с",
            quality=calculated,
            sample_count=31,
        ),
        "wind_speed_10m_p10": ForecastValue(
            value=3.0,
            unit="м/с",
            quality=calculated,
            sample_count=31,
        ),
        "wind_speed_10m_p90": ForecastValue(
            value=8.0,
            unit="м/с",
            quality=calculated,
            sample_count=31,
        ),
        "wind_gusts_10m_median": ForecastValue(
            value=8.0,
            unit="м/с",
            quality=calculated,
            sample_count=31,
        ),
        "wind_gusts_10m_p90": ForecastValue(
            value=13.0,
            unit="м/с",
            quality=calculated,
            sample_count=31,
        ),
        "pressure_msl_mean": ForecastValue(
            value=1011.0,
            unit="гПа",
            quality=calculated,
            sample_count=31,
        ),
        "pressure_msl_spread": ForecastValue(
            value=2.0,
            unit="гПа",
            quality=calculated,
            sample_count=31,
        ),
        "pressure_msl_p10": ForecastValue(
            value=1008.0,
            unit="гПа",
            quality=calculated,
            sample_count=31,
        ),
        "pressure_msl_p90": ForecastValue(
            value=1014.0,
            unit="гПа",
            quality=calculated,
            sample_count=31,
        ),
        "cape_median": ForecastValue(
            value=200.0,
            unit="Дж/кг",
            quality=calculated,
            sample_count=31,
        ),
        "cape_p10": ForecastValue(
            value=0.0,
            unit="Дж/кг",
            quality=calculated,
            sample_count=31,
        ),
        "cape_p90": ForecastValue(
            value=700.0,
            unit="Дж/кг",
            quality=calculated,
            sample_count=31,
        ),
        "precipitation_probability_ge_0p1mm": ForecastValue(
            value=70,
            unit="%",
            quality=calculated,
            event_count=22,
            sample_count=31,
            accumulation_hours=3,
        ),
        "precipitation_probability_ge_1mm": ForecastValue(
            value=35,
            unit="%",
            quality=calculated,
            event_count=11,
            sample_count=31,
            accumulation_hours=3,
        ),
        "ensemble_member_count": ForecastValue(
            value=31,
            quality=calculated,
            sample_count=31,
        ),
        "ensemble_member_coverage": ForecastValue(
            value=100,
            unit="%",
            quality=calculated,
            sample_count=31,
        ),
        "ensemble_probability_resolution": ForecastValue(
            value=100 / 31,
            unit="п.п.",
            quality=calculated,
            sample_count=31,
        ),
    }
    return ForecastSeries(
        location=location,
        source=SourceMetadata(
            source_id=f"ensemble-{model.lower().replace(' ', '-')}",
            provider="Test",
            model=model,
            product="ensemble distribution",
            source_kind=SourceKind.ENSEMBLE,
            retrieved_at_utc=valid,
            exact_cycle_known=False,
            lead_time_reference=LeadTimeReference.RESPONSE_START,
            ensemble_member_count=31,
            ensemble_expected_member_count=31,
            ensemble_member_coverage_percent=100,
            member_weighting="equal",
            probability_calibration="raw_uncalibrated_member_fraction",
        ),
        points=[
            ForecastPoint(
                valid_time_utc=valid,
                valid_time_local=valid,
                lead_hours=0,
                values=values,
            )
        ],
    )


def _table_texts(document: Document) -> list[str]:
    return [
        "\n".join(cell.text for row in table.rows for cell in row.cells)
        for table in document.tables
    ]


def test_deterministic_tables_precede_one_ensemble_table(tmp_path: Path) -> None:
    location = _location()
    output = tmp_path / "scientific.docx"
    ScientificDocumentGenerator(tmp_path / "icons").generate(
        location=location,
        series=[
            _ensemble(location, "GEFS"),
            _deterministic(location),
            _ensemble(location, "IFS ENS", offset=1),
        ],
        options=DocumentOptions(
            page_size="A3",
            include_detailed_table=True,
            include_ensemble_section=True,
            parameter_profile="extended",
        ),
        output_path=output,
    )

    document = Document(output)
    assert len(document.tables) == 5
    texts = _table_texts(document)
    assert "Детерминированных моделей\n1" in texts[0]
    assert "Ансамблевых систем\n2" in texts[0]
    assert "определён по координатам" in texts[0]
    assert "детерминированный прогноз" in texts[1]
    assert "GEFS" not in texts[2]
    assert "Подробный" not in texts[-1]
    assert "Ансамбль" in texts[-1]
    assert "GEFS" in texts[-1]
    assert "IFS ENS" in texts[-1]
    assert "≥0.1 мм за 3 ч: 70 % (22/31)" in texts[-1]
    assert "q10–q90" in texts[-1]
    assert "от начала выдачи" in texts[-1]

    paragraph_text = "\n".join(
        paragraph.text for paragraph in document.paragraphs
    )
    assert paragraph_text.index("GFS test") < paragraph_text.index(
        "Ансамблевая оценка неопределённости"
    )
    assert "не является ещё одним детерминированным сценарием" in paragraph_text
    assert "некалиброванная" in paragraph_text
    assert "собственные M, N и интервал" in paragraph_text


def test_a4_operational_uses_compact_tables(tmp_path: Path) -> None:
    location = _location()
    output = tmp_path / "compact-a4.docx"
    ScientificDocumentGenerator(tmp_path / "icons").generate(
        location=location,
        series=[_deterministic(location), _ensemble(location, "GEFS")],
        options=DocumentOptions(
            page_size="A4",
            parameter_profile="operational",
            include_detailed_table=True,
        ),
        output_path=output,
    )
    document = Document(output)
    texts = _table_texts(document)
    compact_details = next(text for text in texts if "Погода и T/Td/RH" in text)
    compact_ensemble = next(
        text for text in texts if "Осадки и вероятность" in text
    )
    assert "Давление и конвекция" in compact_details
    assert "22/31" in compact_ensemble


def test_a4_extended_profile_is_rejected(tmp_path: Path) -> None:
    location = _location()
    with pytest.raises(ValueError, match="A4 поддерживает только оперативный"):
        ScientificDocumentGenerator(tmp_path / "icons").generate(
            location=location,
            series=[_deterministic(location)],
            options=DocumentOptions(
                page_size="A4",
                parameter_profile="extended",
            ),
            output_path=tmp_path / "bad.docx",
        )
