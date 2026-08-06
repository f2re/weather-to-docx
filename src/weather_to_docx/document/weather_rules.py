from __future__ import annotations

from dataclasses import dataclass

from weather_to_docx.domain.models import ForecastPoint


@dataclass(frozen=True, slots=True)
class WeatherPresentation:
    code: int
    description: str
    icon_key: str


# Служебные коды суточной межмодельной сводки. Они не являются кодами WMO:
# WMO-код относится к конкретному сроку, а эти значения описывают согласованный
# сценарий суток по количественным данным и поддержке моделей.
SUMMARY_POSSIBLE_PRECIPITATION = 1001
SUMMARY_LIGHT_PRECIPITATION = 1002
SUMMARY_RAIN = 1003
SUMMARY_HEAVY_PRECIPITATION = 1004
SUMMARY_THUNDERSTORM = 1005


WMO_DESCRIPTIONS: dict[int, str] = {
    0: "Ясно",
    1: "Преимущественно ясно",
    2: "Переменная облачность",
    3: "Пасмурно",
    45: "Туман",
    48: "Изморозевый туман",
    51: "Слабая морось",
    53: "Морось",
    55: "Сильная морось",
    56: "Слабая ледяная морось",
    57: "Сильная ледяная морось",
    61: "Слабый дождь",
    63: "Дождь",
    65: "Сильный дождь",
    66: "Слабый ледяной дождь",
    67: "Сильный ледяной дождь",
    71: "Слабый снег",
    73: "Снег",
    75: "Сильный снег",
    77: "Снежные зёрна",
    80: "Слабый ливень",
    81: "Ливень",
    82: "Сильный ливень",
    85: "Слабый снегопад",
    86: "Сильный снегопад",
    95: "Гроза",
    96: "Гроза с небольшим градом",
    99: "Гроза с сильным градом",
    SUMMARY_POSSIBLE_PRECIPITATION: "Осадки возможны",
    SUMMARY_LIGHT_PRECIPITATION: "Слабые осадки",
    SUMMARY_RAIN: "Дождь",
    SUMMARY_HEAVY_PRECIPITATION: "Сильные осадки",
    SUMMARY_THUNDERSTORM: "Гроза",
}


def precipitation_interval_hours(point: ForecastPoint) -> float:
    """Return the source accumulation interval used by a point."""

    measurement = point.measurement("precipitation")
    if measurement is not None:
        if measurement.accumulation_hours is not None:
            return max(0.01, float(measurement.accumulation_hours))
        if (
            measurement.source_start_step is not None
            and measurement.source_end_step is not None
            and measurement.source_end_step > measurement.source_start_step
        ):
            return float(
                measurement.source_end_step - measurement.source_start_step
            )
    return 1.0


def precipitation_rate_mm_h(point: ForecastPoint) -> float:
    amount = _number(point.raw("precipitation")) or 0.0
    return max(0.0, amount) / precipitation_interval_hours(point)


def derive_weather_code(point: ForecastPoint) -> int:
    """Derive a point code from interval-normalised physical quantities."""

    if point.weather_code is not None:
        return int(point.weather_code)

    precipitation_rate = precipitation_rate_mm_h(point)
    interval_hours = precipitation_interval_hours(point)
    snowfall_rate = max(0.0, _number(point.raw("snowfall")) or 0.0) / interval_hours
    shower_rate = max(
        _number(point.raw("showers")) or 0.0,
        _number(point.raw("convective_precipitation")) or 0.0,
    ) / interval_hours
    temperature = _number(point.raw("temperature_2m"))
    visibility = _number(point.raw("visibility"))
    cloud = _number(point.raw("cloud_cover")) or 0.0
    cape = _number(point.raw("cape")) or 0.0

    if cape >= 800 and precipitation_rate >= 0.2:
        return 95
    if snowfall_rate > 0:
        if snowfall_rate >= 1.5:
            return 75
        if snowfall_rate >= 0.5:
            return 73
        return 71
    if shower_rate > 0:
        if shower_rate >= 10:
            return 82
        if shower_rate >= 5:
            return 81
        return 80
    if precipitation_rate > 0 and temperature is not None and temperature <= 0:
        return 67 if precipitation_rate >= 5 else 66
    if precipitation_rate >= 5:
        return 65
    if precipitation_rate >= 2:
        return 63
    if precipitation_rate >= 0.5:
        return 61
    if precipitation_rate > 0:
        return 51
    if visibility is not None and visibility < 1000:
        return 45
    if cloud >= 85:
        return 3
    if cloud >= 35:
        return 2
    if cloud >= 15:
        return 1
    return 0


def weather_presentation(point: ForecastPoint) -> WeatherPresentation:
    code = derive_weather_code(point)
    description = WMO_DESCRIPTIONS.get(code, f"Код погоды {code}")
    is_day = point.is_day is not False

    if code == 0:
        icon = "clear_day" if is_day else "clear_night"
    elif code in {1, 2}:
        icon = "partly_cloudy_day" if is_day else "partly_cloudy_night"
    elif code == 3:
        icon = "cloudy"
    elif code in {45, 48}:
        icon = "fog"
    elif code in {
        51,
        53,
        55,
        61,
        63,
        65,
        80,
        81,
        82,
        SUMMARY_POSSIBLE_PRECIPITATION,
        SUMMARY_LIGHT_PRECIPITATION,
        SUMMARY_RAIN,
        SUMMARY_HEAVY_PRECIPITATION,
    }:
        icon = "rain"
    elif code in {56, 57, 66, 67}:
        icon = "freezing_rain"
    elif code in {71, 73, 75, 77, 85, 86}:
        icon = "snow"
    elif code in {95, 96, 99, SUMMARY_THUNDERSTORM}:
        icon = "thunderstorm"
    else:
        icon = "cloudy"
    return WeatherPresentation(code=code, description=description, icon_key=icon)


def _number(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
