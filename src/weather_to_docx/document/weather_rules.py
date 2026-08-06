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


def derive_weather_code(point: ForecastPoint) -> int:
    if point.weather_code is not None:
        return int(point.weather_code)

    precipitation = float(point.raw("precipitation", 0) or 0)
    snowfall = float(point.raw("snowfall", 0) or 0)
    temperature = float(point.raw("temperature_2m", 5) or 5)
    visibility = float(point.raw("visibility", 100_000) or 100_000)
    cloud = float(point.raw("cloud_cover", 0) or 0)
    cape = float(point.raw("cape", 0) or 0)

    if cape >= 800 and precipitation >= 0.2:
        return 95
    if snowfall >= 0.1 or (temperature <= 0 and precipitation >= 0.3):
        return 75 if snowfall >= 1.5 else 73 if snowfall >= 0.5 else 71
    if precipitation >= 7:
        return 82
    if precipitation >= 2:
        return 65
    if precipitation >= 0.2:
        return 61
    if visibility < 1000:
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
