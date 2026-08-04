from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from docx import Document

from weather_to_docx.document.scientific_generator import ScientificDocumentGenerator
from weather_to_docx.domain.models import (
    DocumentOptions,
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    Location,
    QualityFlag,
    SourceKind,
    SourceMetadata,
)


def _location() -> Location:
    return Location(
        id="spb",
        name="Санкт-Петербург",
        latitude=59.9386,
        longitude=30.3141,
        timezone="Europe/Moscow",
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
                    "apparent_temperature": ForecastValue(value=17.0, unit="°C"),
                    "dew_point_2m": ForecastValue(value=10.0, unit="°C"),
                    "relative_humidity_2m": ForecastValue(value=60, unit="%"),
                    "precipitation": ForecastValue(value=0.0, unit="мм"),
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
        "temperature_2m_mean": ForecastValue(value=18.0 + offset, unit="°C", quality=calculated),
        "temperature_2m_spread": ForecastValue(value=1.5, unit="°C", quality=calculated),
        "temperature_2m_p10": ForecastValue(value=16.0 + offset, unit="°C", quality=calculated),
        "temperature_2m_p90": ForecastValue(value=20.0 + offset, unit="°C", quality=calculated),
        "precipitation_median": ForecastValue(value=0.4, unit="мм", quality=calculated),
        "precipitation_p10": ForecastValue(value=0.0, unit="мм", quality=calculated),
        "precipitation_p90": ForecastValue(value=3.2, unit="мм", quality=calculated),
        "wind_speed_10m_median": ForecastValue(value=5.0, unit="м/с", quality=calculated),
        "wind_speed_10m_p10": ForecastValue(value=3.0, unit="м/с", quality=calculated),
        "wind_speed_10m_p90": ForecastValue(value=8.0, unit="м/с", quality=calculated),
        "wind_gusts_10m_median": ForecastValue(value=8.0, unit="м/с", quality=calculated),
        "wind_gusts_10m_p90": ForecastValue(value=13.0, unit="м/с", quality=calculated),
        "pressure_msl_mean": ForecastValue(value=1011.0, unit="гПа", quality=calculated),
        "pressure_msl_spread": ForecastValue(value=2.0, unit="гПа", quality=calculated),
        "pressure_msl_p10": ForecastValue(value=1008.0, unit="гПа", quality=calculated),
        "pressure_msl_p90": ForecastValue(value=1014.0, unit="гПа", quality=calculated),
        "cape_median": ForecastValue(value=200.0, unit="Дж/кг", quality=calculated),
        "cape_p10": ForecastValue(value=0.0, unit="Дж/кг", quality=calculated),
        "cape_p90": ForecastValue(value=700.0, unit="Дж/кг", quality=calculated),
        "precipitation_probability_ge_0p1mm": ForecastValue(value=70, unit="%", quality=calculated),
        "precipitation_probability_ge_1mm": ForecastValue(value=35, unit="%", quality=calculated),
        "ensemble_member_count": ForecastValue(value=31, quality=calculated),
        "ensemble_member_coverage": ForecastValue(value=100, unit="%", quality=calculated),
        "ensemble_probability_resolution": ForecastValue(value=100 / 31, unit="п.п.", quality=calculated),
    }
    return ForecastSeries(
        location=location,
        source=SourceMetadata(
            source_id=f"ensemble-{model.lower()}",
            provider="Test",
            model=model,
            product="ensemble distribution",
            source_kind=SourceKind.ENSEMBLE,
            retrieved_at_utc=valid,
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
    # Заголовочная таблица + 3 детерминированные таблицы + 1 ансамблевая.
    assert len(document.tables) == 5
    texts = [
        "\n".join(cell.text for row in table.rows for cell in row.cells)
        for table in document.tables
    ]
    assert "детерминированный прогноз" in texts[1]
    assert "Вероятность" not in texts[2]
    assert "GEFS" not in texts[2]
    assert "Подробный" not in texts[-1]
    assert "Ансамбль" in texts[-1]
    assert "GEFS" in texts[-1]
    assert "IFS ENS" in texts[-1]
    assert "≥0.1 мм" in texts[-1]
    assert "q10–q90" in texts[-1]

    paragraph_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert paragraph_text.index("GFS test") < paragraph_text.index(
        "Ансамблевая оценка неопределённости"
    )
    assert "не является ещё одним детерминированным сценарием" in paragraph_text
    assert "некалиброванная" in paragraph_text
