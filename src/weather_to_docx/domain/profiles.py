from __future__ import annotations

# Поля обычного операторского отчёта и профессиональной метеограммы. Слои
# облачности не выводятся отдельными табличными колонками, но используются в
# полупрозрачной облачной панели графика. Явный options["hourly"] сохраняет
# возможность отдельного исследовательского запроса.
OPERATIONAL_HOURLY_PARAMETERS = (
    "temperature_2m",
    "dew_point_2m",
    "relative_humidity_2m",
    "precipitation",
    "snowfall",
    "weather_code",
    "pressure_msl",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "visibility",
    "cape",
    "is_day",
)

# Ансамблевый запрос содержит только поля таблицы и вероятностной метеограммы.
# Для каждого поля адаптер сохраняет центр, spread и q10/q90, когда поставщик
# отдаёт отдельные члены ансамбля.
COMPACT_ENSEMBLE_HOURLY_PARAMETERS = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "pressure_msl",
    "cloud_cover",
    "wind_speed_10m",
    "wind_gusts_10m",
    "weather_code",
)
