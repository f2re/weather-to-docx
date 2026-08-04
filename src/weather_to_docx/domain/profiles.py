from __future__ import annotations

# Поля обычного операторского отчёта. В набор входят только величины, которые
# отображаются в двухстраничном DOCX либо нужны для определения погодного
# явления. Явный options["hourly"] в адаптере по-прежнему позволяет выполнить
# отдельный исследовательский запрос с другим составом параметров.
OPERATIONAL_HOURLY_PARAMETERS = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "snowfall",
    "weather_code",
    "pressure_msl",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "visibility",
    "cape",
    "is_day",
)

# Для ансамбля загружаются только поля компактной вероятностной таблицы.
COMPACT_ENSEMBLE_HOURLY_PARAMETERS = (
    "temperature_2m",
    "precipitation",
    "pressure_msl",
    "wind_speed_10m",
    "wind_gusts_10m",
    "weather_code",
)
