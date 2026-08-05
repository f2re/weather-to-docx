from __future__ import annotations

import asyncio
import math
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

import httpx

from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    LeadTimeReference,
    Location,
    QualityFlag,
    SourceKind,
    SourceMetadata,
)
from weather_to_docx.ensemble.science import (
    ANGULAR_PARAMETERS,
    CATEGORICAL_PARAMETERS,
    circular_statistics,
    ensemble_statistics,
    primary_centre,
    probability_resolution,
    raw_probability,
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


class OpenMeteoEnsembleSource(ForecastSource):
    """Члены ансамбля, обработанные равными весами без скрытой калибровки."""

    descriptor: ClassVar[SourceDescriptor]
    default_endpoint: ClassVar[str] = (
        "https://ensemble-api.open-meteo.com/v1/ensemble"
    )
    model_id: ClassVar[str]
    spatial_resolution: ClassVar[str | None] = None
    licence: ClassVar[str] = (
        "Условия Open-Meteo и лицензия исходного поставщика"
    )
    attribution: ClassVar[str]
    expected_member_count: ClassVar[int | None] = None
    hourly_parameters: ClassVar[tuple[str, ...]] = ENSEMBLE_HOURLY_PARAMETERS

    def __init__(
        self,
        *,
        timeout_seconds: float = 90,
        max_retries: int = 3,
        user_agent: str = "weather-to-docx/0.3.1",
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
        thresholds = _thresholds(options)
        params: dict[str, Any] = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": ",".join(parameters),
            "models": model_id,
            "timezone": "UTC",
            "forecast_days": min(
                forecast_days,
                self.descriptor.horizon_days,
            ),
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
                            f"{self.descriptor.name} недоступен после "
                            f"{attempt} попыток: {exc}"
                        ) from exc
                    await asyncio.sleep(min(2 ** (attempt - 1), 5))
            if response is None:
                raise RuntimeError(
                    f"{self.descriptor.name} не вернул ответ: {last_error}"
                )
            payload = response.json()
            if isinstance(payload, list):
                if len(payload) != 1:
                    raise ValueError(
                        "Адаптер одной точки получил несколько наборов координат"
                    )
                payload = payload[0]
            return self.parse_payload(
                payload,
                location=location,
                retrieved_at_utc=datetime.now(UTC),
                endpoint=endpoint,
                model_id=model_id,
                precipitation_thresholds_mm=thresholds,
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
        precipitation_threshold_mm: float | None = None,
        precipitation_thresholds_mm: tuple[float, ...] | list[float] | None = None,
    ) -> ForecastSeries:
        thresholds = _normalise_thresholds(
            precipitation_thresholds_mm
            if precipitation_thresholds_mm is not None
            else (
                [precipitation_threshold_mm]
                if precipitation_threshold_mm is not None
                else [0.1, 1.0, 5.0]
            )
        )
        hourly = payload.get("hourly") or {}
        units = payload.get("hourly_units") or {}
        times = hourly.get("time") or []
        if not times:
            reason = (
                payload.get("reason")
                or payload.get("error")
                or "отсутствует hourly.time"
            )
            raise ValueError(
                f"Некорректный ответ ансамблевого API: {reason}"
            )

        member_series = _collect_member_series(hourly)
        if not member_series:
            raise ValueError(
                "Ансамблевый ответ не содержит массивов отдельных членов"
            )
        parsed_times = [_parse_time(value) for value in times]
        timezone = ZoneInfo(location.timezone)
        first_time = parsed_times[0]
        all_member_ids = {
            member
            for groups in member_series.values()
            for member in groups
        }
        observed_total = len(all_member_ids)
        expected_total = cls.expected_member_count or observed_total
        points: list[ForecastPoint] = []

        for index, valid_utc in enumerate(parsed_times):
            values: dict[str, ForecastValue] = {}
            point_warnings: list[str] = []
            weather_codes: list[int] = []
            counts: list[int] = []
            lead_hours = round(
                (valid_utc - first_time).total_seconds() / 3600
            )
            accumulation_hours = _interval_hours(parsed_times, index)
            source_start_step = (
                max(0, round(lead_hours - accumulation_hours))
                if accumulation_hours is not None
                else None
            )

            for parameter, parameter_members in sorted(member_series.items()):
                sample = _values_at_index(parameter_members, index)
                if parameter in CATEGORICAL_PARAMETERS:
                    weather_codes = [int(round(value)) for value in sample]
                    continue
                if not sample:
                    continue
                counts.append(len(sample))
                unit = _unit_for_parameter(
                    units,
                    parameter,
                    parameter_members,
                )
                if parameter in ANGULAR_PARAMETERS:
                    circular = circular_statistics(sample)
                    direction_quality = (
                        QualityFlag.CALCULATED
                        if circular.mean_degrees is not None
                        else QualityFlag.SUSPECT
                    )
                    direction_note = (
                        "Круговое среднее; "
                        f"R={circular.resultant_length:.3f}; "
                        f"равные веса; N={circular.count}"
                    )
                    if circular.mean_degrees is None:
                        direction_note = (
                            "Среднее направление не определено: "
                            f"направления взаимно компенсируются; "
                            f"R={circular.resultant_length:.3f}; "
                            f"N={circular.count}"
                        )
                        point_warnings.append(
                            "Направление ветра ансамбля не согласовано "
                            f"(R={circular.resultant_length:.3f})"
                        )
                    values[parameter] = ForecastValue(
                        value=circular.mean_degrees,
                        unit=unit,
                        quality=direction_quality,
                        source_parameter=f"{parameter}_member*",
                        note=direction_note,
                        sample_count=circular.count,
                    )
                    values[f"{parameter}_resultant_length"] = ForecastValue(
                        value=circular.resultant_length,
                        unit="",
                        quality=QualityFlag.CALCULATED,
                        source_parameter=f"{parameter}_member*",
                        note=(
                            "Длина среднего результирующего вектора R; "
                            "0 — направления не согласованы, "
                            "1 — полностью согласованы"
                        ),
                        sample_count=circular.count,
                    )
                    continue

                stats = ensemble_statistics(sample)
                primary, policy = primary_centre(parameter, stats)
                values[parameter] = ForecastValue(
                    value=primary,
                    unit=unit,
                    quality=QualityFlag.CALCULATED,
                    source_parameter=f"{parameter}_member*",
                    note=(
                        f"Центр={policy}; равные веса; N={stats.count}; "
                        "квантили Hyndman–Fan type 8"
                    ),
                    sample_count=stats.count,
                )
                _store_statistics(values, parameter, unit, stats)

            precipitation_members = _values_at_index(
                member_series.get("precipitation", {}),
                index,
            )
            for threshold_index, threshold in enumerate(thresholds):
                if not precipitation_members:
                    break
                probability, exceedances, member_count = raw_probability(
                    precipitation_members,
                    threshold,
                )
                interval_text = (
                    f" за {accumulation_hours:g} ч"
                    if accumulation_hours is not None
                    else " за интервал источника"
                )
                probability_value = ForecastValue(
                    value=probability,
                    unit="%",
                    quality=QualityFlag.CALCULATED,
                    source_parameter="precipitation_member*",
                    note=(
                        "Сырая некалиброванная вероятность: "
                        f"{exceedances}/{member_count} членов с осадками "
                        f"≥ {threshold:g} мм{interval_text}; "
                        "дискретность "
                        f"{probability_resolution(member_count):.2f} п.п."
                    ),
                    source_start_step=source_start_step,
                    source_end_step=lead_hours,
                    sample_count=member_count,
                    event_count=exceedances,
                    accumulation_hours=accumulation_hours,
                )
                values[_probability_code(threshold)] = probability_value
                if threshold_index == 0:
                    values["precipitation_probability"] = (
                        probability_value.model_copy()
                    )

            available = min(counts) if counts else 0
            if available:
                coverage = (
                    100.0 * available / expected_total
                    if expected_total
                    else 100.0
                )
                quality = (
                    QualityFlag.CALCULATED
                    if coverage >= 99.9
                    else QualityFlag.SUSPECT
                )
                values["ensemble_member_count"] = ForecastValue(
                    value=available,
                    unit="",
                    quality=quality,
                    source_parameter="member count",
                    note=(
                        f"Минимальное доступное число членов по полям: "
                        f"{available} из ожидаемых {expected_total}"
                    ),
                    sample_count=available,
                )
                values["ensemble_member_coverage"] = ForecastValue(
                    value=min(coverage, 100.0),
                    unit="%",
                    quality=quality,
                    source_parameter="member coverage",
                    note="Общая минимальная полнота членов для данного срока",
                    sample_count=available,
                )
                values["ensemble_probability_resolution"] = ForecastValue(
                    value=probability_resolution(available),
                    unit="п.п.",
                    quality=QualityFlag.CALCULATED,
                    source_parameter="member count",
                    note=(
                        "Минимальный шаг общей справочной вероятности 100/N; "
                        "для конкретного события используйте N из его ячейки"
                    ),
                    sample_count=available,
                )
            if available and available < expected_total:
                point_warnings.append(
                    f"Неполный ансамбль: {available}/{expected_total} членов"
                )

            weather_code = (
                Counter(weather_codes).most_common(1)[0][0]
                if weather_codes
                else None
            )
            is_day_raw = _indexed(hourly.get("is_day"), index)
            points.append(
                ForecastPoint(
                    valid_time_utc=valid_utc,
                    valid_time_local=valid_utc.astimezone(timezone),
                    lead_hours=lead_hours,
                    weather_code=weather_code,
                    is_day=(
                        bool(is_day_raw)
                        if is_day_raw is not None
                        else None
                    ),
                    values=values,
                    warnings=point_warnings,
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
        coverage = (
            100.0 * observed_total / expected_total
            if expected_total
            else None
        )
        warnings = [
            (
                "Члены ансамбля считаются равновероятными; "
                "межмодельное объединение не выполняется."
            ),
            (
                "Для температуры и давления центр — среднее, spread — "
                "стандартное отклонение относительно среднего."
            ),
            (
                "Для осадков, скорости ветра и других асимметричных "
                "величин центр — медиана; диапазон q10–q90 содержит "
                "центральные 80 % членов."
            ),
            (
                "Вероятности являются сырыми долями членов; для каждой "
                "вероятности сохраняются собственные M, N и интервал накопления."
            ),
            (
                "Нормированный spread, Brier Skill Score и CRPSS не "
                "рассчитываются без проверочного архива."
            ),
            (
                "Заблаговременность отсчитывается от начала выдачи Open-Meteo, "
                "поскольку точный цикл исходной модели в ответе не указан."
            ),
        ]
        if observed_total < expected_total:
            warnings.append(
                f"Ответ неполный: обнаружено {observed_total} из "
                f"ожидаемых {expected_total} членов."
            )
        return ForecastSeries(
            location=location,
            source=SourceMetadata(
                source_id=cls.descriptor.source_id,
                provider=cls.descriptor.provider,
                model=cls.descriptor.model,
                product=(
                    "ensemble distribution: centre, spread, q10/q90 "
                    "and raw threshold probabilities"
                ),
                source_kind=SourceKind.ENSEMBLE,
                cycle_time_utc=None,
                retrieved_at_utc=retrieved_at_utc,
                horizon_hours=round(
                    (parsed_times[-1] - parsed_times[0]).total_seconds() / 3600
                ),
                native_time_step_hours=_median_step_hours(parsed_times),
                lead_time_reference=LeadTimeReference.RESPONSE_START,
                grid_type=(
                    "regular latitude-longitude; "
                    "point selection by Open-Meteo"
                ),
                spatial_resolution=cls.spatial_resolution,
                grid_latitude=grid_latitude,
                grid_longitude=grid_longitude,
                grid_distance_km=grid_distance,
                model_elevation_m=_optional_float(payload.get("elevation")),
                licence=cls.licence,
                source_reference=endpoint or cls.default_endpoint,
                attribution=cls.attribution,
                adapter_version="0.3.1",
                exact_cycle_known=False,
                ensemble_member_count=observed_total or None,
                ensemble_expected_member_count=expected_total or None,
                ensemble_member_coverage_percent=(
                    min(coverage, 100.0)
                    if coverage is not None
                    else None
                ),
                member_weighting="equal",
                primary_statistic_policy=(
                    "mean for symmetric thermodynamic fields; "
                    "median for skewed/non-negative/bounded fields"
                ),
                quantile_method="Hyndman-Fan type 8; q10/q50/q90",
                probability_calibration=(
                    "raw_uncalibrated_member_fraction"
                ),
                upstream_model_id=model_id or cls.model_id,
                delivery_service="Open-Meteo ensemble API",
                precipitation_thresholds_mm=thresholds,
            ),
            points=points,
            warnings=warnings,
        )


class OpenMeteoGefS025Source(OpenMeteoEnsembleSource):
    descriptor = SourceDescriptor(
        "open_meteo_gefs_0p25",
        "NOAA GEFS 0.25° через Open-Meteo",
        "Open-Meteo / NOAA",
        "NOAA GEFS 0.25°",
        10,
        False,
        SourceKind.ENSEMBLE,
        notes="31-членный ансамбль; сырые вероятности и распределение.",
    )
    model_id = "ncep_gefs025"
    expected_member_count = 31
    spatial_resolution = "0.25°; выдача точки подготовлена Open-Meteo"
    licence = "Условия Open-Meteo; исходные данные NOAA/NCEP"
    attribution = "NOAA GEFS, delivered by Open-Meteo"


class OpenMeteoGefS05Source(OpenMeteoEnsembleSource):
    descriptor = SourceDescriptor(
        "open_meteo_gefs_0p5",
        "NOAA GEFS 0.5° через Open-Meteo",
        "Open-Meteo / NOAA",
        "NOAA GEFS 0.5°",
        35,
        False,
        SourceKind.ENSEMBLE,
        notes="Дальняя тенденция; не детальный почасовой сценарий.",
    )
    model_id = "ncep_gefs05"
    expected_member_count = 31
    spatial_resolution = "0.5°; выдача точки подготовлена Open-Meteo"
    licence = "Условия Open-Meteo; исходные данные NOAA/NCEP"
    attribution = "NOAA GEFS, delivered by Open-Meteo"


class OpenMeteoEcmwfIfsEnsembleSource(OpenMeteoEnsembleSource):
    descriptor = SourceDescriptor(
        "open_meteo_ecmwf_ifs_ensemble",
        "ECMWF IFS ENS 0.25° через Open-Meteo",
        "Open-Meteo / ECMWF",
        "ECMWF IFS Ensemble 0.25°",
        15,
        False,
        SourceKind.ENSEMBLE,
        notes="Вероятностный ансамбль ECMWF IFS.",
    )
    model_id = "ecmwf_ifs025_ensemble"
    spatial_resolution = "0.25°; выдача точки подготовлена Open-Meteo"
    licence = "ECMWF Open Data CC BY 4.0; условия Open-Meteo"
    attribution = "ECMWF IFS Ensemble Open Data, delivered by Open-Meteo"


class OpenMeteoEcmwfAifsEnsembleSource(OpenMeteoEnsembleSource):
    descriptor = SourceDescriptor(
        "open_meteo_ecmwf_aifs_ensemble",
        "ECMWF AIFS ENS 0.25° через Open-Meteo",
        "Open-Meteo / ECMWF",
        "ECMWF AIFS Ensemble 0.25°",
        15,
        False,
        SourceKind.ENSEMBLE,
        notes="Ансамбль машинно-обученной модели ECMWF AIFS.",
    )
    model_id = "ecmwf_aifs025_ensemble"
    spatial_resolution = "0.25°; выдача точки подготовлена Open-Meteo"
    licence = "ECMWF Open Data CC BY 4.0; условия Open-Meteo"
    attribution = "ECMWF AIFS Ensemble Open Data, delivered by Open-Meteo"


class OpenMeteoDwdIconEpsSource(OpenMeteoEnsembleSource):
    descriptor = SourceDescriptor(
        "open_meteo_dwd_icon_eps",
        "DWD ICON Global EPS через Open-Meteo",
        "Open-Meteo / DWD",
        "DWD ICON Global EPS",
        8,
        False,
        SourceKind.ENSEMBLE,
        notes="Глобальный 40-членный вероятностный ансамбль ICON.",
    )
    model_id = "icon_global_eps"
    expected_member_count = 40
    spatial_resolution = (
        "глобальная сетка ICON EPS; выдача точки подготовлена Open-Meteo"
    )
    licence = "DWD Open Data; условия Open-Meteo"
    attribution = "DWD ICON EPS Open Data, delivered by Open-Meteo"


class OpenMeteoGemGepsSource(OpenMeteoEnsembleSource):
    descriptor = SourceDescriptor(
        "open_meteo_gem_geps",
        "ECCC GEPS через Open-Meteo",
        "Open-Meteo / ECCC",
        "ECCC Global Ensemble Prediction System",
        16,
        False,
        SourceKind.ENSEMBLE,
        notes="Канадский глобальный вероятностный ансамбль.",
    )
    model_id = "gem_global_ensemble"
    spatial_resolution = (
        "глобальная сетка GEPS; выдача точки подготовлена Open-Meteo"
    )
    licence = "ECCC Open Data; условия Open-Meteo"
    attribution = (
        "Environment and Climate Change Canada GEPS, delivered by Open-Meteo"
    )


def _store_statistics(values, parameter, unit, stats) -> None:
    source = f"{parameter}_member*"
    fields = {
        "mean": (stats.mean, "Среднее по равновесным членам"),
        "median": (stats.median, "Медиана q50, Hyndman–Fan type 8"),
        "spread": (
            stats.standard_deviation,
            "Стандартное отклонение относительно среднего",
        ),
        "p10": (stats.p10, "10-й процентиль, Hyndman–Fan type 8"),
        "p90": (stats.p90, "90-й процентиль, Hyndman–Fan type 8"),
        "min": (stats.minimum, "Минимум членов ансамбля"),
        "max": (stats.maximum, "Максимум членов ансамбля"),
    }
    for suffix, (value, note) in fields.items():
        values[f"{parameter}_{suffix}"] = ForecastValue(
            value=value,
            unit=unit,
            quality=QualityFlag.CALCULATED,
            source_parameter=source,
            note=f"{note}; N={stats.count}",
            sample_count=stats.count,
        )


def _thresholds(options: dict[str, Any]) -> tuple[float, ...]:
    configured = options.get("precipitation_thresholds_mm")
    if configured is None:
        configured = [
            options.get("precipitation_threshold_mm", 0.1),
            1.0,
            5.0,
        ]
    return _normalise_thresholds(configured)


def _normalise_thresholds(values) -> tuple[float, ...]:
    if isinstance(values, (int, float, str)):
        values = [values]
    thresholds = sorted({float(value) for value in values})
    if not thresholds or thresholds[0] < 0:
        raise ValueError("Пороги осадков должны быть неотрицательными")
    return tuple(thresholds)


def _probability_code(threshold: float) -> str:
    token = f"{threshold:g}".replace(".", "p")
    return f"precipitation_probability_ge_{token}mm"


def _collect_member_series(
    hourly: dict[str, Any],
) -> dict[str, dict[int, list[Any]]]:
    grouped: dict[str, dict[int, list[Any]]] = {}
    plain_series: dict[str, list[Any]] = {}
    for key, value in hourly.items():
        if key in {"time", "is_day"} or not isinstance(value, list):
            continue
        match = _MEMBER_PATTERN.fullmatch(key)
        if match:
            grouped.setdefault(
                match.group("parameter"),
                {},
            )[int(match.group("member"))] = value
        else:
            plain_series[key] = value
    for parameter, values in plain_series.items():
        if parameter not in grouped:
            grouped[parameter] = {0: values}
    return grouped


def _values_at_index(
    member_series: dict[int, list[Any]],
    index: int,
) -> list[float]:
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


def _unit_for_parameter(units, parameter, members) -> str | None:
    direct = units.get(parameter)
    if direct is not None:
        return _normalise_unit(str(direct))
    for member in members:
        for key in (
            f"{parameter}_member{member:02d}",
            f"{parameter}_member{member}",
        ):
            value = units.get(key)
            if value is not None:
                return _normalise_unit(str(value))
    return None


def _parse_time(value: str | int | float) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _interval_hours(values: list[datetime], index: int) -> float | None:
    if len(values) < 2:
        return None
    if index > 0:
        interval = (values[index] - values[index - 1]).total_seconds() / 3600
    else:
        interval = (values[1] - values[0]).total_seconds() / 3600
    return float(interval) if interval > 0 else None


def _median_step_hours(values: list[datetime]) -> float | None:
    if len(values) < 2:
        return None
    differences = sorted(
        (right - left).total_seconds() / 3600
        for left, right in zip(values, values[1:], strict=False)
    )
    return differences[len(differences) // 2]


def _indexed(value: Any, index: int) -> Any:
    return value[index] if isinstance(value, list) and index < len(value) else None


def _normalise_unit(value: str | None) -> str | None:
    return {
        "hPa": "гПа",
        "W/m²": "Вт/м²",
        "J/kg": "Дж/кг",
    }.get(value, value)


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
