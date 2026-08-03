from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    code: str
    name_ru: str
    default_unit: str
    precision: int = 1
    group: str = "Прочее"


PARAMETERS: dict[str, ParameterDefinition] = {
    "temperature_2m": ParameterDefinition("temperature_2m", "Температура 2 м", "°C", 1, "Температура"),
    "apparent_temperature": ParameterDefinition("apparent_temperature", "Ощущаемая температура", "°C", 1, "Температура"),
    "dew_point_2m": ParameterDefinition("dew_point_2m", "Точка росы 2 м", "°C", 1, "Температура"),
    "wet_bulb_temperature_2m": ParameterDefinition("wet_bulb_temperature_2m", "Температура смоченного термометра 2 м", "°C", 1, "Температура"),
    "relative_humidity_2m": ParameterDefinition("relative_humidity_2m", "Относительная влажность 2 м", "%", 0, "Температура"),
    "pressure_msl": ParameterDefinition("pressure_msl", "Давление на уровне моря", "гПа", 1, "Давление"),
    "surface_pressure": ParameterDefinition("surface_pressure", "Давление у поверхности", "гПа", 1, "Давление"),
    "wind_speed_10m": ParameterDefinition("wind_speed_10m", "Скорость ветра 10 м", "м/с", 1, "Ветер"),
    "wind_direction_10m": ParameterDefinition("wind_direction_10m", "Направление ветра 10 м", "°", 0, "Ветер"),
    "wind_gusts_10m": ParameterDefinition("wind_gusts_10m", "Порывы ветра 10 м", "м/с", 1, "Ветер"),
    "wind_speed_100m": ParameterDefinition("wind_speed_100m", "Скорость ветра 100 м", "м/с", 1, "Ветер"),
    "wind_direction_100m": ParameterDefinition("wind_direction_100m", "Направление ветра 100 м", "°", 0, "Ветер"),
    "u_wind_10m": ParameterDefinition("u_wind_10m", "U-компонента ветра 10 м", "м/с", 1, "Ветер"),
    "v_wind_10m": ParameterDefinition("v_wind_10m", "V-компонента ветра 10 м", "м/с", 1, "Ветер"),
    "precipitation": ParameterDefinition("precipitation", "Осадки за интервал", "мм", 1, "Осадки"),
    "precipitation_accumulated": ParameterDefinition("precipitation_accumulated", "Накопленные осадки", "мм", 1, "Осадки"),
    "precipitation_probability": ParameterDefinition("precipitation_probability", "Вероятность осадков", "%", 0, "Осадки"),
    "rain": ParameterDefinition("rain", "Дождь", "мм", 1, "Осадки"),
    "showers": ParameterDefinition("showers", "Ливневые осадки", "мм", 1, "Осадки"),
    "convective_precipitation": ParameterDefinition("convective_precipitation", "Конвективные осадки", "мм", 1, "Осадки"),
    "snowfall": ParameterDefinition("snowfall", "Снег", "см", 1, "Осадки"),
    "snow_depth": ParameterDefinition("snow_depth", "Высота снежного покрова", "м", 2, "Осадки"),
    "cloud_cover": ParameterDefinition("cloud_cover", "Общая облачность", "%", 0, "Облачность"),
    "cloud_cover_low": ParameterDefinition("cloud_cover_low", "Нижняя облачность", "%", 0, "Облачность"),
    "cloud_cover_mid": ParameterDefinition("cloud_cover_mid", "Средняя облачность", "%", 0, "Облачность"),
    "cloud_cover_high": ParameterDefinition("cloud_cover_high", "Верхняя облачность", "%", 0, "Облачность"),
    "cloud_base": ParameterDefinition("cloud_base", "Высота нижней границы облаков", "м", 0, "Облачность"),
    "visibility": ParameterDefinition("visibility", "Видимость", "м", 0, "Облачность"),
    "cape": ParameterDefinition("cape", "CAPE", "Дж/кг", 0, "Конвекция"),
    "cin": ParameterDefinition("cin", "CIN", "Дж/кг", 0, "Конвекция"),
    "lifted_index": ParameterDefinition("lifted_index", "Lifted Index", "K", 1, "Конвекция"),
    "freezing_level_height": ParameterDefinition("freezing_level_height", "Высота нулевой изотермы", "м", 0, "Конвекция"),
    "precipitable_water": ParameterDefinition("precipitable_water", "Осаждённая вода", "кг/м²", 1, "Конвекция"),
    "shortwave_radiation": ParameterDefinition("shortwave_radiation", "Коротковолновая радиация", "Вт/м²", 0, "Радиация"),
    "direct_radiation": ParameterDefinition("direct_radiation", "Прямая радиация", "Вт/м²", 0, "Радиация"),
    "diffuse_radiation": ParameterDefinition("diffuse_radiation", "Рассеянная радиация", "Вт/м²", 0, "Радиация"),
    "sunshine_duration": ParameterDefinition("sunshine_duration", "Солнечное сияние", "с", 0, "Радиация"),
    "evapotranspiration": ParameterDefinition("evapotranspiration", "Эвапотранспирация", "мм", 2, "Почва"),
    "et0_fao_evapotranspiration": ParameterDefinition("et0_fao_evapotranspiration", "Эталонная эвапотранспирация ET₀", "мм", 2, "Почва"),
    "vapour_pressure_deficit": ParameterDefinition("vapour_pressure_deficit", "Дефицит давления водяного пара", "кПа", 2, "Почва"),
    "soil_temperature_0cm": ParameterDefinition("soil_temperature_0cm", "Температура почвы 0 см", "°C", 1, "Почва"),
    "soil_temperature_6cm": ParameterDefinition("soil_temperature_6cm", "Температура почвы 6 см", "°C", 1, "Почва"),
    "soil_temperature_18cm": ParameterDefinition("soil_temperature_18cm", "Температура почвы 18 см", "°C", 1, "Почва"),
    "soil_temperature_54cm": ParameterDefinition("soil_temperature_54cm", "Температура почвы 54 см", "°C", 1, "Почва"),
    "soil_moisture_0_to_1cm": ParameterDefinition("soil_moisture_0_to_1cm", "Влажность почвы 0–1 см", "м³/м³", 3, "Почва"),
    "soil_moisture_1_to_3cm": ParameterDefinition("soil_moisture_1_to_3cm", "Влажность почвы 1–3 см", "м³/м³", 3, "Почва"),
    "soil_moisture_3_to_9cm": ParameterDefinition("soil_moisture_3_to_9cm", "Влажность почвы 3–9 см", "м³/м³", 3, "Почва"),
    "soil_moisture_9_to_27cm": ParameterDefinition("soil_moisture_9_to_27cm", "Влажность почвы 9–27 см", "м³/м³", 3, "Почва"),
    "soil_moisture_27_to_81cm": ParameterDefinition("soil_moisture_27_to_81cm", "Влажность почвы 27–81 см", "м³/м³", 3, "Почва"),
    "boundary_layer_height": ParameterDefinition("boundary_layer_height", "Высота пограничного слоя", "м", 0, "Почва"),
    "ensemble_member_count": ParameterDefinition("ensemble_member_count", "Число членов ансамбля", "", 0, "Ансамбль"),
}

_STATISTIC_SUFFIXES = {
    "_spread": ("разброс σ", 2),
    "_p10": ("10-й процентиль", 2),
    "_p90": ("90-й процентиль", 2),
}
_PRESSURE_LEVEL_PATTERN = re.compile(
    r"^(temperature|relative_humidity|wind_speed|wind_direction|"
    r"geopotential_height|vertical_velocity)_(\d+)hPa$"
)
_PRESSURE_LEVEL_NAMES = {
    "temperature": ("Температура", "°C", 1),
    "relative_humidity": ("Относительная влажность", "%", 0),
    "wind_speed": ("Скорость ветра", "м/с", 1),
    "wind_direction": ("Направление ветра", "°", 0),
    "geopotential_height": ("Геопотенциальная высота", "м", 0),
    "vertical_velocity": ("Вертикальная скорость", "Па/с", 3),
}


def definition(code: str) -> ParameterDefinition:
    direct = PARAMETERS.get(code)
    if direct:
        return direct

    for suffix, (statistic_name, precision) in _STATISTIC_SUFFIXES.items():
        if code.endswith(suffix):
            base_code = code[: -len(suffix)]
            base = definition(base_code)
            return ParameterDefinition(
                code,
                f"{base.name_ru}: {statistic_name}",
                base.default_unit,
                max(base.precision, precision),
                "Ансамбль",
            )

    pressure_level = _PRESSURE_LEVEL_PATTERN.fullmatch(code)
    if pressure_level:
        parameter, level = pressure_level.groups()
        name, unit, precision = _PRESSURE_LEVEL_NAMES[parameter]
        return ParameterDefinition(
            code,
            f"{name} на {level} гПа",
            unit,
            precision,
            "Вертикальный профиль",
        )

    return ParameterDefinition(code, code, "", 2, "Прочее")
