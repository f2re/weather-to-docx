from __future__ import annotations

from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastValue,
    QualityFlag,
)
from weather_to_docx.sources.gfs_nomads import (
    GfsNomadsSource as _BaseGfsNomadsSource,
)


class GfsNomadsSource(_BaseGfsNomadsSource):
    """GFS source with correct interval metadata for cumulative APCP."""

    @staticmethod
    def _derive_interval_precipitation(
        points: list[ForecastPoint],
    ) -> None:
        previous_accumulated: float | None = None
        previous_end_step: int | None = None

        for point in points:
            measurement = point.measurement("precipitation_accumulated")
            if measurement is None or measurement.value is None:
                continue

            accumulated = max(0.0, float(measurement.value))
            source_start = measurement.source_start_step
            source_end = measurement.source_end_step
            interval = accumulated
            interval_start = source_start
            interval_end = source_end
            note = "Интервальная сумма принята из поля APCP"

            is_cumulative = source_start == 0 and source_end is not None
            can_difference = (
                is_cumulative
                and previous_accumulated is not None
                and previous_end_step is not None
                and source_end > previous_end_step
            )
            if can_difference and accumulated >= previous_accumulated:
                interval = accumulated - previous_accumulated
                interval_start = previous_end_step
                interval_end = source_end
                note = (
                    "Интервальная сумма рассчитана разностью "
                    "последовательных накопленных полей APCP"
                )
            elif can_difference and accumulated < previous_accumulated:
                interval = accumulated
                interval_start = previous_end_step
                interval_end = source_end
                note = (
                    "Обнаружен сброс накопления APCP; текущее значение "
                    "принято как сумма после сброса"
                )
            elif is_cumulative and previous_end_step is not None and source_end > 0:
                interval_start = previous_end_step
                interval_end = source_end

            accumulation_hours = None
            if (
                interval_start is not None
                and interval_end is not None
                and interval_end > interval_start
            ):
                accumulation_hours = float(interval_end - interval_start)

            point.values["precipitation"] = ForecastValue(
                value=max(0.0, interval),
                unit="мм",
                quality=QualityFlag.CALCULATED,
                source_parameter="precipitation_accumulated",
                note=note,
                source_start_step=interval_start,
                source_end_step=interval_end,
                accumulation_hours=accumulation_hours,
            )
            previous_accumulated = accumulated
            previous_end_step = source_end


__all__ = ["GfsNomadsSource"]
