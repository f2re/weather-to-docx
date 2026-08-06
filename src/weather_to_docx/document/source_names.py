from __future__ import annotations

from weather_to_docx.domain.models import ForecastSeries

MODEL_SHORT_NAMES = {
    "NOAA GFS 0.25°": "NOAA GFS",
    "Global Forecast System (GFS)": "NOAA GFS",
    "ECMWF IFS 0.25° Open Data": "ECMWF IFS",
    "ECMWF AIFS 0.25° Single": "ECMWF AIFS",
    "DWD ICON Global": "ICON",
    "ECCC GEM Global (GDPS)": "GDPS",
    "NOAA GEFS 0.25°": "GEFS",
    "NOAA GEFS 0.5°": "GEFS",
    "ECMWF IFS Ensemble 0.25°": "ECMWF ENS",
    "ECMWF AIFS Ensemble 0.25°": "AIFS ENS",
    "DWD ICON Global EPS": "ICON-EPS",
    "ECCC Global Ensemble Prediction System": "GEPS",
}


def source_display_name(forecast: ForecastSeries) -> str:
    """Вернуть однозначное имя модели вместе с каналом доставки при необходимости."""

    source = forecast.source
    source_id = source.source_id.casefold()
    provider = source.provider.casefold()
    model = MODEL_SHORT_NAMES.get(source.model, source.model)

    if source_id == "noaa_gfs_0p25" or "nomads" in provider:
        return "NOAA GFS (NOMADS)"
    if (
        source_id == "open_meteo_gfs"
        or "open-meteo" in provider
    ) and ("gfs" in source_id or "gfs" in source.model.casefold()):
        return "NOAA GFS (Open-Meteo)"

    return model


__all__ = ["source_display_name"]
