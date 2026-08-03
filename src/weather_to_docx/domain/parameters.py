from __future__ import annotations

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
    "relative_humidity_2m": ParameterDefinition("relative_humidity_2m", "Относительная влажность 2 м", "%", 0, "Температура"),
    "pressure_msl": ParameterDefinition("pressure_msl", "Давление на уровне моря", "гПа", 1, "Давление"),
    "surface_pressure": ParameterDefinition("surface_pressure", "Давление у поверхности", "гПа", 1, "Давление"),
    "wind_speed_10m": ParameterDefinition("wind_speed_10m", "Скорость ветра 10 м", "м/с", 1, "Ветер"),
    "wind_direction_10m": ParameterDefinition("wind_direction_10m", "Направление ветра 10 м", "°", 0, "Ветер"),
    "wind_gusts_10m": ParameterDefinition("wind_gusts_10m", "Порывы ветра 10 м", "м/с", 1, "Ветер"),
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
    "visibility": ParameterDefinition("visibility", "Видимость", "м", 0, "Облачность"),
    "cape": ParameterDefinition("cape", "CAPE", "Дж/кг", 0, "Конвекция"),
    "cin": ParameterDefinition("cin", "CIN", "Дж/кг", 0, "Конвекция"),
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
}


def definition(code: str) -> ParameterDefinition:
    return PARAMETERS.get(code, ParameterDefinition(code, code, "", 2, "Прочее"))
