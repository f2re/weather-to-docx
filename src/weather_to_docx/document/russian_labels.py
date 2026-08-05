from __future__ import annotations

from datetime import datetime

from weather_to_docx.document import compact_generator


RUSSIAN_MODEL_NAMES = {
    "Global Forecast System (GFS)": "NOAA GFS",
    "Global Forecast System": "NOAA GFS",
    "NOAA Global Forecast System": "NOAA GFS",
    "NOAA GFS 0.25°": "NOAA GFS",
    "ECMWF Integrated Forecasting System (IFS)": "ECMWF IFS",
    "ECMWF IFS 0.25° Open Data": "ECMWF IFS",
    "ECMWF AIFS 0.25° Single": "ECMWF AIFS",
    "DWD ICON Global": "ICON",
    "ECCC GEM Global (GDPS)": "GDPS",
    "ECCC Global Ensemble Prediction System": "GEPS",
}


def apply_russian_display_names() -> None:
    compact_generator.MODEL_SHORT_NAMES.update(RUSSIAN_MODEL_NAMES)


def visible_timezone_label(current: datetime) -> str:
    offset = current.utcoffset()
    if offset is None:
        return "местное время"
    total_minutes = round(offset.total_seconds() / 60)
    sign = "+" if total_minutes >= 0 else "−"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"
