from __future__ import annotations

import asyncio
import statistics
from datetime import UTC, datetime
from typing import Any
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


OPEN_METEO_HOURLY_PARAMETERS = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "apparent_temperature",
    "precipitation_probability",
    "precipitation",
    "rain",
    "showers",
    "snowfall",
    "snow_depth",
    "weather_code",
    "pressure_msl",
    "surface_pressure",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "visibility",
    "evapotranspiration",
    "et0_fao_evapotranspiration",
    "vapour_pressure_deficit",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "sunshine_duration",
    "soil_temperature_0cm",
    "soil_temperature_6cm",
    "soil_temperature_18cm",
    "soil_temperature_54cm",
    "soil_moisture_0_to_1cm",
    "soil_moisture_1_to_3cm",
    "soil_moisture_3_to_9cm",
    "soil_moisture_9_to_27cm",
    "soil_moisture_27_to_81cm",
    "cape",
    "is_day",
)


class OpenMeteoGfsSource(ForecastSource):
    descriptor = SourceDescriptor(
        source_id="open_meteo_gfs",
        name="NOAA GFS через Open-Meteo",
        provider="Open-Meteo / NOAA",
        model="NOAA GFS",
        horizon_days=16,
        exact_cycle=False,
        notes="Быстрый рабочий источник. Точный цикл GFS в стандартном ответе API не публикуется.",
    )

    default_endpoint = "https://api.open-meteo.com/v1/gfs"

    def __init__(
        self,
        *,
        timeout_seconds: float = 60,
        max_retries: int = 3,
        user_agent: str = "weather-to-docx/0.1.0",
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
        requested_parameters = tuple(options.get("hourly", OPEN_METEO_HOURLY_PARAMETERS))
        forecast_days = min(forecast_days, self.descriptor.horizon_days)
        params: dict[str, Any] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": ",".join(requested_parameters),
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
                        raise RuntimeError(f"Open-Meteo недоступен после {attempt} попыток: {exc}") from exc
                    await asyncio.sleep(min(2 ** (attempt - 1), 5))
            if response is None:
                raise RuntimeError(f"Open-Meteo не вернул ответ: {last_error}")
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
        endpoint: str = default_endpoint,
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

        step_hours = None
        if len(parsed_times) > 1:
            differences = [
                (right - left).total_seconds() / 3600
                for left, right in zip(parsed_times, parsed_times[1:], strict=False)
            ]
            step_hours = float(statistics.median(differences))

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

        warnings = [
            "Стандартный ответ Open-Meteo не содержит точного времени цикла GFS; "
            "для строгой воспроизводимости используйте источник noaa_gfs_0p25."
        ]
        return ForecastSeries(
            location=location,
            source=SourceMetadata(
                source_id=cls.descriptor.source_id,
                provider=cls.descriptor.provider,
                model=cls.descriptor.model,
                product="hourly point forecast",
                cycle_time_utc=None,
                retrieved_at_utc=retrieved_at_utc,
                horizon_hours=round((parsed_times[-1] - parsed_times[0]).total_seconds() / 3600),
                native_time_step_hours=step_hours,
                grid_type="regular latitude-longitude; interpolated by Open-Meteo",
                spatial_resolution="GFS 0.25°; выдача интерполирована сервисом",
                grid_latitude=grid_latitude,
                grid_longitude=grid_longitude,
                grid_distance_km=grid_distance,
                model_elevation_m=_optional_float(payload.get("elevation")),
                licence="Условия Open-Meteo; исходные данные NOAA",
                source_reference=endpoint,
                attribution="Weather data by Open-Meteo; underlying model NOAA GFS",
                exact_cycle_known=False,
            ),
            points=points,
            warnings=warnings,
        )


def _parse_open_meteo_time(value: str | int | float) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _indexed(value: Any, index: int) -> Any:
    return value[index] if isinstance(value, list) and index < len(value) else None


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
