from __future__ import annotations

# Поля обычного операторского отчёта. Остальные параметры не запрашиваются
# автоматически: они раздували ответ поставщика и создавали десятки пустых
# колонок в DOCX. Явный пользовательский список hourly по-прежнему имеет
# приоритет в адаптере источника.
OPERATIONAL_HOURLY_PARAMETERS = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation",
    "rain",
    "showers",
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

# Для ансамбля загружаются только поля, которые реально входят в компактную
# вероятностную таблицу. Сырые члены почвы, радиации и других технических
# параметров в обычном отчёте не используются.
COMPACT_ENSEMBLE_HOURLY_PARAMETERS = (
    "temperature_2m",
    "precipitation",
    "pressure_msl",
    "wind_speed_10m",
    "wind_gusts_10m",
    "weather_code",
)
