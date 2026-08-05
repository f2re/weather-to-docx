from __future__ import annotations

from weather_to_docx.domain.models import ForecastValue, QualityFlag


def install_ensemble_statistics_enhancements() -> None:
    """Добавить q25/q75 к нормализованным ансамблевым рядам.

    Функция устанавливается при создании реестра источников, сохраняя
    совместимость со старыми пакетами прогнозов и API адаптера.
    """

    from weather_to_docx.sources import open_meteo_ensemble

    open_meteo_ensemble._store_statistics = _store_statistics  # noqa: SLF001


def _store_statistics(values, parameter, unit, stats) -> None:
    source = f"{parameter}_member*"
    fields = {
        "mean": (stats.mean, "Среднее по равновесным членам"),
        "median": (stats.median, "Медиана, 50-й процентиль"),
        "spread": (
            stats.standard_deviation,
            "Стандартное отклонение относительно среднего",
        ),
        "p10": (stats.p10, "10-й процентиль, Hyndman–Fan type 8"),
        "p25": (stats.p25, "25-й процентиль, Hyndman–Fan type 8"),
        "p75": (stats.p75, "75-й процентиль, Hyndman–Fan type 8"),
        "p90": (stats.p90, "90-й процентиль, Hyndman–Fan type 8"),
        "min": (stats.minimum, "Минимум членов ансамбля"),
        "max": (stats.maximum, "Максимум членов ансамбля"),
    }
    for suffix, (value, note) in fields.items():
        values[f"{parameter}_{suffix}"] = ForecastValue(
            value=value,
            unit=unit,
            quality=QualityFlag.CALCULATED,
            source_parameter=source,
            note=f"{note}; N={stats.count}",
            sample_count=stats.count,
        )
