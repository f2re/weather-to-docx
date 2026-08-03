from __future__ import annotations

import asyncio
import math
import re
import statistics
from collections import Counter
from datetime import UTC, datetime
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

import httpx

from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    Location,
    QualityFlag,
    SourceMetadata,
)
from weather_to_docx.sources.base import ForecastSource, SourceDescriptor
from weather_to_docx.utils.meteorology import haversine_km

ENSEMBLE_HOURLY_PARAMETERS = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation",
    "rain",
    "snowfall",
    "pressure_msl",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "cape",
    "weather_code",
)

_MEMBER_PATTERN = re.compile(r"^(?P<parameter>.+)_member(?P<member>\d+)$")
_ANGULAR_PARAMETERS = {"wind_direction_10m"}
_CATEGORICAL_PARAMETERS = {"weather_code"}


class OpenMeteoEnsembleSource(ForecastSource):
    """Получение членов ансамбля и расчёт воспроизводимых статистик."""

    descriptor: ClassVar[SourceDescriptor]
    default_endpoint: ClassVar[str] = "https://ensemble-api.open-meteo.com/v1/ensemble"
    model_id: ClassVar[str]
    spatial_resolution: ClassVar[str | None] = None
    licence: ClassVar[str] = "Условия Open-Meteo и лицензия исходного поставщика"
    attribution: ClassVar[str]
    hourly_parameters: ClassVar[tuple[str, ...]] = ENSEMBLE_HOURLY_PARAMETERS

    def __init__(
        self,
        *,
        timeout_seconds: float = 90,
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
        parameters = tuple(options.get("hourly", self.hourly_parameters))
        model_id = str(options.get("model", self.model_id))
        threshold = float(options.get("precipitation_threshold_mm", 0.1))
        if threshold < 0:
            raise ValueError("Порог вероятности осадков не может быть отрицательным")

        params: dict[str, Any] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": ",".join(parameters),
            "models": model_id,
            "timezone": "UTC",
            "forecast_days": min(forecast_days, self.descriptor.horizon_days),
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
                precipitation_threshold_mm=threshold,
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
        precipitation_threshold_mm: float = 0.1,
    ) -> ForecastSeries:
        hourly = payload.get("hourly") or {}
        units = payload.get("hourly_units") or {}
        times = hourly.get("time") or []
        if not times:
            reason = payload.get("reason") or payload.get("error") or "отсутствует массив hourly.time"
            raise ValueError(f"Некорректный ответ ансамблевого API: {reason}")

        member_series = _collect_member_series(hourly)
        if not member_series:
            raise ValueError("Ансамблевый ответ не содержит массивов отдельных членов")

        parsed_times = [_parse_time(value) for value in times]
        timezone = ZoneInfo(location.timezone)
        first_time = parsed_times[0]
        points: list[ForecastPoint] = []
        all_member_ids = {
            member
            for parameter_members in member_series.values()
            for member in parameter_members
        }

        for index, valid_utc in enumerate(parsed_times):
            values: dict[str, ForecastValue] = {}
            point_member_count = 0
            weather_codes: list[int] = []

            for parameter, parameter_members in sorted(member_series.items()):
                raw_values = _values_at_index(parameter_members, index)
                if parameter in _CATEGORICAL_PARAMETERS:
                    weather_codes = [
                        int(round(value))
                        for value in raw_values
                        if math.isfinite(value)
                    ]
                    continue
                if not raw_values:
                    continue

                point_member_count = max(point_member_count, len(raw_values))
                unit = _unit_for_parameter(units, parameter, parameter_members)
                if parameter in _ANGULAR_PARAMETERS:
                    mean = _circular_mean_degrees(raw_values)
                    values[parameter] = ForecastValue(
                        value=mean,
                        unit=unit,
                        quality=QualityFlag.CALCULATED,
                        source_parameter=f"{parameter}_member*",
                        note=f"Круговое среднее по {len(raw_values)} членам ансамбля",
                    )
                    continue

                mean = statistics.fmean(raw_values)
                note = f"Среднее по {len(raw_values)} членам ансамбля"
                values[parameter] = ForecastValue(
                    value=mean,
                    unit=unit,
                    quality=QualityFlag.CALCULATED,
                    source_parameter=f"{parameter}_member*",
                    note=note,
                )
                if len(raw_values) >= 2:
                    values[f"{parameter}_spread"] = ForecastValue(
                        value=statistics.pstdev(raw_values),
                        unit=unit,
                        quality=QualityFlag.CALCULATED,
                        source_parameter=f"{parameter}_member*",
                        note=f"Стандартное отклонение по {len(raw_values)} членам",
                    )
                    values[f"{parameter}_p10"] = ForecastValue(
                        value=_quantile(raw_values, 0.10),
                        unit=unit,
                        quality=QualityFlag.CALCULATED,
                        source_parameter=f"{parameter}_member*",
                        note="10-й процентиль ансамбля",
                    )
                    values[f"{parameter}_p90"] = ForecastValue(
                        value=_quantile(raw_values, 0.90),
                        unit=unit,
                        quality=QualityFlag.CALCULATED,
                        source_parameter=f"{parameter}_member*",
                        note="90-й процентиль ансамбля",
                    )

            precipitation_members = _values_at_index(
                member_series.get("precipitation", {}),
                index,
            )
            if precipitation_members:
                exceedances = sum(
                    value >= precipitation_threshold_mm
                    for value in precipitation_members
                )
                values["precipitation_probability"] = ForecastValue(
                    value=100 * exceedances / len(precipitation_members),
                    unit="%",
                    quality=QualityFlag.CALCULATED,
                    source_parameter="precipitation_member*",
                    note=(
                        f"Доля членов с осадками ≥ {precipitation_threshold_mm:g} мм; "
                        f"N={len(precipitation_members)}"
                    ),
                )

            if point_member_count:
                values["ensemble_member_count"] = ForecastValue(
                    value=point_member_count,
                    unit="",
                    quality=QualityFlag.CALCULATED,
                    source_parameter="member count",
                    note="Число доступных членов для данного срока",
                )

            weather_code = Counter(weather_codes).most_common(1)[0][0] if weather_codes else None
            is_day_raw = _indexed(hourly.get("is_day"), index)
            points.append(
                ForecastPoint(
                    valid_time_utc=valid_utc,
                    valid_time_local=valid_utc.astimezone(timezone),
                    lead_hours=round((valid_utc - first_time).total_seconds() / 3600),
                    weather_code=weather_code,
                    is_day=bool(is_day_raw) if is_day_raw is not None else None,
                    values=values,
                )
            )

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

        actual_model_id = model_id or cls.model_id
        member_count = len(all_member_ids)
        warnings = [
            "Таблица содержит статистики ансамбля, а не отдельный детерминированный сценарий.",
            (
                "Вероятность осадков рассчитана как доля доступных членов с суммой "
                f"за интервал ≥ {precipitation_threshold_mm:g} мм."
            ),
            (
                "Стандартный ответ Open-Meteo не содержит надёжного времени исходного "
                "цикла ансамбля; фиксируется время получения."
            ),
            "Нативные сроки модели могут быть приведены Open-Meteo к более частой временной сетке.",
        ]
        if member_count:
            warnings.append(f"В ответе обнаружено {member_count} уникальных членов ансамбля.")

        return ForecastSeries(
            location=location,
            source=SourceMetadata(
                source_id=cls.descriptor.source_id,
                provider=cls.descriptor.provider,
                model=cls.descriptor.model,
                product="ensemble mean, spread, percentiles and threshold probability",
                cycle_time_utc=None,
                retrieved_at_utc=retrieved_at_utc,
                horizon_hours=round((parsed_times[-1] - parsed_times[0]).total_seconds() / 3600),
                native_time_step_hours=_median_step_hours(parsed_times),
                grid_type="regular latitude-longitude; point selection by Open-Meteo",
                spatial_resolution=cls.spatial_resolution,
                grid_latitude=grid_latitude,
                grid_longitude=grid_longitude,
                grid_distance_km=grid_distance,
                model_elevation_m=_optional_float(payload.get("elevation")),
                licence=cls.licence,
                source_reference=endpoint or cls.default_endpoint,
                attribution=cls.attribution,
                adapter_version="0.2.0",
                exact_cycle_known=False,
                upstream_model_id=actual_model_id,
                delivery_service="Open-Meteo ensemble API",
                ensemble_member_count=member_count or None,
                precipitation_threshold_mm=precipitation_threshold_mm,
            ),
            points=points,
            warnings=warnings,
        )


class OpenMeteoGefS025Source(OpenMeteoEnsembleSource):
    descriptor = SourceDescriptor(
        source_id="open_meteo_gefs_0p25",
        name="NOAA GEFS 0.25° через Open-Meteo",
        provider="Open-Meteo / NOAA",
        model="NOAA GEFS 0.25°",
        horizon_days=10,
        exact_cycle=False,
        notes="Ансамбль повышенного разрешения для вероятностного прогноза до 10 суток.",
    )
    model_id = "ncep_gefs025"
    spatial_resolution = "0.25°; выдача точки подготовлена Open-Meteo"
    licence = "Условия Open-Meteo; исходные данные NOAA/NCEP"
    attribution = "NOAA GEFS, delivered by Open-Meteo"


class OpenMeteoGefS05Source(OpenMeteoEnsembleSource):
    descriptor = SourceDescriptor(
        source_id="open_meteo_gefs_0p5",
        name="NOAA GEFS 0.5° через Open-Meteo",
        provider="Open-Meteo / NOAA",
        model="NOAA GEFS 0.5°",
        horizon_days=35,
        exact_cycle=False,
        notes="Дальняя ансамблевая тенденция; не предназначена для детального почасового сценария.",
    )
    model_id = "ncep_gefs05"
    spatial_resolution = "0.5°; выдача точки подготовлена Open-Meteo"
    licence = "Условия Open-Meteo; исходные данные NOAA/NCEP"
    attribution = "NOAA GEFS, delivered by Open-Meteo"


class OpenMeteoEcmwfIfsEnsembleSource(OpenMeteoEnsembleSource):
    descriptor = SourceDescriptor(
        source_id="open_meteo_ecmwf_ifs_ensemble",
        name="ECMWF IFS ENS 0.25° через Open-Meteo",
        provider="Open-Meteo / ECMWF",
        model="ECMWF IFS Ensemble 0.25°",
        horizon_days=15,
        exact_cycle=False,
        notes="Вероятностный ансамбль ECMWF IFS.",
    )
    model_id = "ecmwf_ifs025_ensemble"
    spatial_resolution = "0.25°; выдача точки подготовлена Open-Meteo"
    licence = "ECMWF Open Data CC BY 4.0; условия Open-Meteo"
    attribution = "ECMWF IFS Ensemble Open Data, delivered by Open-Meteo"


class OpenMeteoEcmwfAifsEnsembleSource(OpenMeteoEnsembleSource):
    descriptor = SourceDescriptor(
        source_id="open_meteo_ecmwf_aifs_ensemble",
        name="ECMWF AIFS ENS 0.25° через Open-Meteo",
        provider="Open-Meteo / ECMWF",
        model="ECMWF AIFS Ensemble 0.25°",
        horizon_days=15,
        exact_cycle=False,
        notes="Вероятностный ансамбль машинно-обученной модели ECMWF AIFS.",
    )
    model_id = "ecmwf_aifs025_ensemble"
    spatial_resolution = "0.25°; выдача точки подготовлена Open-Meteo"
    licence = "ECMWF Open Data CC BY 4.0; условия Open-Meteo"
    attribution = "ECMWF AIFS Ensemble Open Data, delivered by Open-Meteo"


class OpenMeteoDwdIconEpsSource(OpenMeteoEnsembleSource):
    descriptor = SourceDescriptor(
        source_id="open_meteo_dwd_icon_eps",
        name="DWD ICON Global EPS через Open-Meteo",
        provider="Open-Meteo / DWD",
        model="DWD ICON Global EPS",
        horizon_days=8,
        exact_cycle=False,
        notes="Глобальный вероятностный ансамбль ICON.",
    )
    model_id = "dwd_icon_global_eps"
    spatial_resolution = "глобальная сетка ICON EPS; выдача точки подготовлена Open-Meteo"
    licence = "DWD Open Data; условия Open-Meteo"
    attribution = "DWD ICON EPS Open Data, delivered by Open-Meteo"


class OpenMeteoGemGepsSource(OpenMeteoEnsembleSource):
    descriptor = SourceDescriptor(
        source_id="open_meteo_gem_geps",
        name="ECCC GEPS через Open-Meteo",
        provider="Open-Meteo / ECCC",
        model="ECCC Global Ensemble Prediction System",
        horizon_days=16,
        exact_cycle=False,
        notes="Канадский глобальный вероятностный ансамбль.",
    )
    model_id = "cmc_gem_geps"
    spatial_resolution = "глобальная сетка GEPS; выдача точки подготовлена Open-Meteo"
    licence = "ECCC Open Data; условия Open-Meteo"
    attribution = "Environment and Climate Change Canada GEPS, delivered by Open-Meteo"


def _collect_member_series(hourly: dict[str, Any]) -> dict[str, dict[int, list[Any]]]:
    grouped: dict[str, dict[int, list[Any]]] = {}
    plain_series: dict[str, list[Any]] = {}
    for key, value in hourly.items():
        if key in {"time", "is_day"} or not isinstance(value, list):
            continue
        match = _MEMBER_PATTERN.fullmatch(key)
        if match:
            parameter = match.group("parameter")
            member = int(match.group("member"))
            grouped.setdefault(parameter, {})[member] = value
        else:
            plain_series[key] = value

    for parameter, values in plain_series.items():
        if parameter not in grouped:
            grouped[parameter] = {0: values}
    return grouped


def _values_at_index(member_series: dict[int, list[Any]], index: int) -> list[float]:
    values: list[float] = []
    for series in member_series.values():
        raw = series[index] if index < len(series) else None
        try:
            value = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            value = None
        if value is not None and math.isfinite(value):
            values.append(value)
    return values


def _unit_for_parameter(
    units: dict[str, Any],
    parameter: str,
    members: dict[int, list[Any]],
) -> str | None:
    direct = units.get(parameter)
    if direct is not None:
        return _normalise_unit(str(direct))
    for member in members:
        value = units.get(f"{parameter}_member{member:02d}")
        if value is not None:
            return _normalise_unit(str(value))
    return None


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _circular_mean_degrees(values: list[float]) -> float:
    radians = [math.radians(value % 360) for value in values]
    sine = statistics.fmean(math.sin(value) for value in radians)
    cosine = statistics.fmean(math.cos(value) for value in radians)
    if abs(sine) < 1e-12 and abs(cosine) < 1e-12:
        return values[0] % 360
    return math.degrees(math.atan2(sine, cosine)) % 360


def _parse_time(value: str | int | float) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _median_step_hours(values: list[datetime]) -> float | None:
    if len(values) < 2:
        return None
    differences = [
        (right - left).total_seconds() / 3600
        for left, right in zip(values, values[1:], strict=False)
    ]
    return float(statistics.median(differences))


def _indexed(value: Any, index: int) -> Any:
    return value[index] if isinstance(value, list) and index < len(value) else None


def _normalise_unit(value: str | None) -> str | None:
    replacements = {
        "hPa": "гПа",
        "W/m²": "Вт/м²",
        "J/kg": "Дж/кг",
    }
    return replacements.get(value, value)


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
