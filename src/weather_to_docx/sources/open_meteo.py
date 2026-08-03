from __future__ import annotations

import asyncio
import statistics
from datetime import UTC, datetime
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

import httpx

from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    Location,
    SourceMetadata,
)
from weather_to_docx.sources.base import ForecastSource, SourceDescriptor
from weather_to_docx.utils.meteorology import haversine_km

OPEN_METEO_CORE_PARAMETERS = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "snowfall",
    "weather_code",
    "pressure_msl",
    "surface_pressure",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "sunshine_duration",
    "cape",
    "is_day",
)

OPEN_METEO_HOURLY_PARAMETERS = OPEN_METEO_CORE_PARAMETERS + (
    "precipitation_probability",
    "showers",
    "snow_depth",
    "visibility",
    "evapotranspiration",
    "et0_fao_evapotranspiration",
    "vapour_pressure_deficit",
    "soil_temperature_0cm",
    "soil_temperature_6cm",
    "soil_temperature_18cm",
    "soil_temperature_54cm",
    "soil_moisture_0_to_1cm",
    "soil_moisture_1_to_3cm",
    "soil_moisture_3_to_9cm",
    "soil_moisture_9_to_27cm",
    "soil_moisture_27_to_81cm",
)


class OpenMeteoDeterministicSource(ForecastSource):
    """Общий адаптер конкретной детерминированной модели Open-Meteo.

    Модель всегда передаётся явно через ``models``. Это исключает незаметное
    смешивание региональных и глобальных моделей в режимах ``best_match`` и
    ``seamless``.
    """

    descriptor: ClassVar[SourceDescriptor]
    default_endpoint: ClassVar[str] = "https://api.open-meteo.com/v1/forecast"
    model_id: ClassVar[str]
    hourly_parameters: ClassVar[tuple[str, ...]] = OPEN_METEO_CORE_PARAMETERS
    product: ClassVar[str] = "hourly point forecast"
    grid_type: ClassVar[str] = "regular latitude-longitude; point selection by Open-Meteo"
    spatial_resolution: ClassVar[str | None] = None
    licence: ClassVar[str] = "Условия Open-Meteo и лицензия исходного поставщика"
    attribution: ClassVar[str]
    interpolation_warning: ClassVar[str | None] = (
        "Open-Meteo может приводить нативные сроки модели к почасовой сетке; "
        "такие значения являются обработанной выдачей сервиса."
    )
    strict_source_hint: ClassVar[str | None] = None

    def __init__(
        self,
        *,
        timeout_seconds: float = 60,
        max_retries: int = 3,
        user_agent: str = "weather-to-docx/0.2.0",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.user_agent = user_agent
        self._client = client

    async def fetch(
        self,
        location: Location,
        forecast_days: int,
        options: dict[str, Any] | None = None,
    ) -> ForecastSeries:
        options = options or {}
        endpoint = str(options.get("endpoint", self.default_endpoint))
        requested_parameters = tuple(options.get("hourly", self.hourly_parameters))
        forecast_days = min(forecast_days, self.descriptor.horizon_days)
        model_id = str(options.get("model", self.model_id))
        params: dict[str, Any] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": ",".join(requested_parameters),
            "models": model_id,
            "timezone": "UTC",
            "forecast_days": forecast_days,
            "temperature_unit": "celsius",
            "wind_speed_unit": "ms",
            "precipitation_unit": "mm",
            "cell_selection": options.get("cell_selection", "nearest"),
        }
        if location.elevation_m is not None:
            params["elevation"] = location.elevation_m

        own_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        )
        try:
            response: httpx.Response | None = None
            last_error: Exception | None = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await client.get(endpoint, params=params)
                    response.raise_for_status()
                    break
                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    last_error = exc
                    if attempt == self.max_retries:
                        raise RuntimeError(
                            f"{self.descriptor.name} недоступен после {attempt} попыток: {exc}"
                        ) from exc
                    await asyncio.sleep(min(2 ** (attempt - 1), 5))
            if response is None:
                raise RuntimeError(f"{self.descriptor.name} не вернул ответ: {last_error}")
            payload = response.json()
            if isinstance(payload, list):
                if len(payload) != 1:
                    raise ValueError("Адаптер одной точки получил несколько наборов координат")
                payload = payload[0]
            return self.parse_payload(
                payload,
                location=location,
                retrieved_at_utc=datetime.now(UTC),
                endpoint=endpoint,
                model_id=model_id,
            )
        finally:
            if own_client:
                await client.aclose()

    @classmethod
    def parse_payload(
        cls,
        payload: dict[str, Any],
        *,
        location: Location,
        retrieved_at_utc: datetime,
        endpoint: str | None = None,
        model_id: str | None = None,
    ) -> ForecastSeries:
        hourly = payload.get("hourly") or {}
        hourly_units = payload.get("hourly_units") or {}
        times = hourly.get("time") or []
        if not times:
            reason = payload.get("reason") or payload.get("error") or "отсутствует массив hourly.time"
            raise ValueError(f"Некорректный ответ Open-Meteo: {reason}")

        timezone = ZoneInfo(location.timezone)
        parsed_times = [_parse_open_meteo_time(value) for value in times]
        first_time = parsed_times[0]
        points: list[ForecastPoint] = []
        ignored = {"time", "weather_code", "is_day"}

        for index, valid_utc in enumerate(parsed_times):
            values: dict[str, ForecastValue] = {}
            for parameter, series in hourly.items():
                if parameter in ignored or not isinstance(series, list):
                    continue
                raw = series[index] if index < len(series) else None
                if raw is None:
                    continue
                values[parameter] = ForecastValue(
                    value=raw,
                    unit=_normalise_unit(hourly_units.get(parameter)),
                    source_parameter=parameter,
                )

            weather_code = _indexed(hourly.get("weather_code"), index)
            is_day_raw = _indexed(hourly.get("is_day"), index)
            points.append(
                ForecastPoint(
                    valid_time_utc=valid_utc,
                    valid_time_local=valid_utc.astimezone(timezone),
                    lead_hours=round((valid_utc - first_time).total_seconds() / 3600),
                    weather_code=int(weather_code) if weather_code is not None else None,
                    is_day=bool(is_day_raw) if is_day_raw is not None else None,
                    values=values,
                )
            )

        step_hours = _median_step_hours(parsed_times)
        grid_latitude = _optional_float(payload.get("latitude"))
        grid_longitude = _optional_float(payload.get("longitude"))
        grid_distance = None
        if grid_latitude is not None and grid_longitude is not None:
            grid_distance = haversine_km(
                location.latitude,
                location.longitude,
                grid_latitude,
                grid_longitude,
            )

        actual_endpoint = endpoint or cls.default_endpoint
        actual_model_id = model_id or cls.model_id
        warnings = [
            "Стандартный ответ Open-Meteo не содержит надёжного времени исходного "
            f"цикла {cls.descriptor.model}; в документе фиксируется время получения."
        ]
        if cls.interpolation_warning:
            warnings.append(cls.interpolation_warning)
        if cls.strict_source_hint:
            warnings.append(cls.strict_source_hint)

        return ForecastSeries(
            location=location,
            source=SourceMetadata(
                source_id=cls.descriptor.source_id,
                provider=cls.descriptor.provider,
                model=cls.descriptor.model,
                product=cls.product,
                cycle_time_utc=None,
                retrieved_at_utc=retrieved_at_utc,
                horizon_hours=round((parsed_times[-1] - parsed_times[0]).total_seconds() / 3600),
                native_time_step_hours=step_hours,
                grid_type=cls.grid_type,
                spatial_resolution=cls.spatial_resolution,
                grid_latitude=grid_latitude,
                grid_longitude=grid_longitude,
                grid_distance_km=grid_distance,
                model_elevation_m=_optional_float(payload.get("elevation")),
                licence=cls.licence,
                source_reference=actual_endpoint,
                attribution=cls.attribution,
                adapter_version="0.2.0",
                exact_cycle_known=False,
                upstream_model_id=actual_model_id,
                delivery_service="Open-Meteo",
            ),
            points=points,
            warnings=warnings,
        )


class OpenMeteoGfsSource(OpenMeteoDeterministicSource):
    descriptor = SourceDescriptor(
        source_id="open_meteo_gfs",
        name="NOAA GFS 0.25° через Open-Meteo",
        provider="Open-Meteo / NOAA",
        model="NOAA GFS 0.25°",
        horizon_days=16,
        exact_cycle=False,
        notes="Быстрый резервный источник; модель задана явно как gfs025.",
    )
    default_endpoint = "https://api.open-meteo.com/v1/gfs"
    model_id = "gfs025"
    hourly_parameters = OPEN_METEO_HOURLY_PARAMETERS
    spatial_resolution = "0.25°; выдача точки подготовлена Open-Meteo"
    licence = "Условия Open-Meteo; исходные данные NOAA/NCEP"
    attribution = "Weather data by Open-Meteo; underlying model NOAA GFS"
    strict_source_hint = (
        "Для строгой фиксации цикла и исходных GRIB2 используйте прямой источник noaa_gfs_0p25."
    )


class OpenMeteoEcmwfIfsSource(OpenMeteoDeterministicSource):
    descriptor = SourceDescriptor(
        source_id="open_meteo_ecmwf_ifs",
        name="ECMWF IFS 0.25° Open Data через Open-Meteo",
        provider="Open-Meteo / ECMWF",
        model="ECMWF IFS 0.25° Open Data",
        horizon_days=15,
        exact_cycle=False,
        notes="Независимый глобальный детерминированный прогноз ECMWF.",
    )
    default_endpoint = "https://api.open-meteo.com/v1/ecmwf"
    model_id = "ecmwf_ifs025"
    spatial_resolution = "0.25°; выдача точки подготовлена Open-Meteo"
    licence = "ECMWF Open Data CC BY 4.0; условия Open-Meteo"
    attribution = "ECMWF Open Data, delivered by Open-Meteo"


class OpenMeteoEcmwfAifsSource(OpenMeteoDeterministicSource):
    descriptor = SourceDescriptor(
        source_id="open_meteo_ecmwf_aifs",
        name="ECMWF AIFS 0.25° Single через Open-Meteo",
        provider="Open-Meteo / ECMWF",
        model="ECMWF AIFS 0.25° Single",
        horizon_days=15,
        exact_cycle=False,
        notes="Глобальная модель машинного обучения ECMWF; не смешивается с IFS.",
    )
    default_endpoint = "https://api.open-meteo.com/v1/ecmwf"
    model_id = "ecmwf_aifs025_single"
    spatial_resolution = "0.25°; нативный шаг AIFS обработан Open-Meteo"
    licence = "ECMWF Open Data CC BY 4.0; условия Open-Meteo"
    attribution = "ECMWF AIFS Open Data, delivered by Open-Meteo"
    interpolation_warning = (
        "AIFS имеет более редкие нативные сроки; почасовые строки Open-Meteo являются "
        "временной интерполяцией и не должны трактоваться как отдельные расчётные сроки модели."
    )


class OpenMeteoDwdIconGlobalSource(OpenMeteoDeterministicSource):
    descriptor = SourceDescriptor(
        source_id="open_meteo_dwd_icon_global",
        name="DWD ICON Global через Open-Meteo",
        provider="Open-Meteo / DWD",
        model="DWD ICON Global",
        horizon_days=8,
        exact_cycle=False,
        notes="Глобальная ICON задана явно; региональные ICON-EU/ICON-D2 не подмешиваются.",
    )
    default_endpoint = "https://api.open-meteo.com/v1/dwd-icon"
    model_id = "dwd_icon_global"
    spatial_resolution = "около 0.1° / 11 км; выдача точки подготовлена Open-Meteo"
    licence = "DWD Open Data; условия Open-Meteo"
    attribution = "DWD ICON Open Data, delivered by Open-Meteo"


class OpenMeteoGemGdpsSource(OpenMeteoDeterministicSource):
    descriptor = SourceDescriptor(
        source_id="open_meteo_gem_gdps",
        name="ECCC GEM Global (GDPS) через Open-Meteo",
        provider="Open-Meteo / ECCC",
        model="ECCC GEM Global (GDPS)",
        horizon_days=10,
        exact_cycle=False,
        notes="Канадская глобальная детерминированная модель GDPS.",
    )
    default_endpoint = "https://api.open-meteo.com/v1/gem"
    model_id = "cmc_gem_gdps"
    spatial_resolution = "0.15° / около 15 км; выдача точки подготовлена Open-Meteo"
    licence = "ECCC Open Data; условия Open-Meteo"
    attribution = "Environment and Climate Change Canada GEM/GDPS, delivered by Open-Meteo"


def _parse_open_meteo_time(value: str | int | float) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _indexed(value: Any, index: int) -> Any:
    return value[index] if isinstance(value, list) and index < len(value) else None


def _median_step_hours(values: list[datetime]) -> float | None:
    if len(values) < 2:
        return None
    differences = [
        (right - left).total_seconds() / 3600
        for left, right in zip(values, values[1:], strict=False)
    ]
    return float(statistics.median(differences))


def _normalise_unit(value: str | None) -> str | None:
    replacements = {
        "°": "°",
        "hPa": "гПа",
        "wmo code": "код WMO",
        "m³/m³": "м³/м³",
        "W/m²": "Вт/м²",
        "J/kg": "Дж/кг",
    }
    return replacements.get(value, value)


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
