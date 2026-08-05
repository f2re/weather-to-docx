# ruff: noqa: I001
from __future__ import annotations

import math
from datetime import UTC, datetime


CIVIL_SUNSET_ELEVATION_DEGREES = -0.833


def solar_elevation_degrees(
    when: datetime,
    *,
    latitude: float,
    longitude: float,
) -> float:
    """Приближённая высота Солнца по алгоритму NOAA.

    Расчёт автономный и нужен как резерв, когда поставщик прогноза не передал
    поле ``is_day``. Точности достаточно для визуального выделения ночных
    интервалов на метеограмме.
    """

    if when.tzinfo is None:
        raise ValueError("Время должно содержать часовой пояс")
    if not -90 <= latitude <= 90:
        raise ValueError("Широта должна быть от -90 до 90 градусов")
    if not -180 <= longitude <= 180:
        raise ValueError("Долгота должна быть от -180 до 180 градусов")

    utc = when.astimezone(UTC)
    day_of_year = utc.timetuple().tm_yday
    hour = utc.hour + utc.minute / 60 + utc.second / 3600
    gamma = 2 * math.pi / 365 * (day_of_year - 1 + (hour - 12) / 24)

    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )

    minutes_utc = utc.hour * 60 + utc.minute + utc.second / 60
    true_solar_minutes = (minutes_utc + equation_of_time + 4 * longitude) % 1440
    hour_angle = true_solar_minutes / 4 - 180

    latitude_rad = math.radians(latitude)
    hour_angle_rad = math.radians(hour_angle)
    cosine_zenith = (
        math.sin(latitude_rad) * math.sin(declination)
        + math.cos(latitude_rad)
        * math.cos(declination)
        * math.cos(hour_angle_rad)
    )
    cosine_zenith = min(1.0, max(-1.0, cosine_zenith))
    zenith = math.degrees(math.acos(cosine_zenith))
    return 90 - zenith


def is_night(
    when: datetime,
    *,
    latitude: float,
    longitude: float,
    threshold_degrees: float = CIVIL_SUNSET_ELEVATION_DEGREES,
) -> bool:
    return (
        solar_elevation_degrees(
            when,
            latitude=latitude,
            longitude=longitude,
        )
        < threshold_degrees
    )
