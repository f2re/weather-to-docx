from __future__ import annotations

import asyncio
import logging
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from weather_to_docx.document.weather_rules import derive_weather_code
from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    Location,
    QualityFlag,
    SourceMetadata,
)
from weather_to_docx.sources.base import ForecastSource, SourceDescriptor
from weather_to_docx.utils.meteorology import haversine_km, wind_speed_direction_from_uv

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GfsRun:
    run_date: date
    cycle: int

    @property
    def cycle_time_utc(self) -> datetime:
        return datetime(
            self.run_date.year,
            self.run_date.month,
            self.run_date.day,
            self.cycle,
            tzinfo=UTC,
        )

    @property
    def stamp(self) -> str:
        return f"{self.run_date:%Y%m%d}{self.cycle:02d}"


class GfsNomadsSource(ForecastSource):
    descriptor = SourceDescriptor(
        source_id="noaa_gfs_0p25",
        name="NOAA GFS 0.25° напрямую",
        provider="NOAA/NCEP NOMADS",
        model="Global Forecast System (GFS)",
        horizon_days=16,
        exact_cycle=True,
        notes="Прямые подмножества GRIB2. Для декодирования требуется ecCodes.",
    )

    filter_endpoint = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    data_root = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod"

    def __init__(
        self,
        *,
        cache_dir: Path,
        timeout_seconds: float = 120,
        max_retries: int = 3,
        user_agent: str = "weather-to-docx/0.1.0",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.cache_dir = cache_dir
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
        run = self._run_from_options(options) or await self.detect_latest_run()
        max_hours = min(forecast_days * 24, 384)
        hourly_to_120 = bool(options.get("hourly_to_120", True))
        hours = self.forecast_hours(max_hours=max_hours, hourly_to_120=hourly_to_120)
        max_concurrency = max(1, min(int(options.get("max_concurrency", 4)), 12))
        box_degrees = max(0.25, min(float(options.get("box_degrees", 0.5)), 5.0))

        files, warnings = await self._download_all(
            location=location,
            run=run,
            hours=hours,
            max_concurrency=max_concurrency,
            box_degrees=box_degrees,
        )
        if not files:
            raise RuntimeError("NOAA NOMADS не вернул ни одного пригодного файла GRIB2")

        points = [self._parse_grib_file(path, location, run, forecast_hour) for forecast_hour, path in files]
        points = sorted((point for point in points if point is not None), key=lambda point: point.valid_time_utc)
        if not points:
            raise RuntimeError(
                "Файлы GFS загружены, но ecCodes не извлёк прогностические параметры. "
                "Проверьте установку пакета ecCodes."
            )
        self._derive_interval_precipitation(points)
        for point in points:
            self._derive_wind(point)
            point.weather_code = derive_weather_code(point)

        sample = self._first_grid_metadata(files[0][1], location)
        if hourly_to_120:
            native_step = 1 if max_hours <= 120 else None
        else:
            native_step = 3
        return ForecastSeries(
            location=location,
            source=SourceMetadata(
                source_id=self.descriptor.source_id,
                provider=self.descriptor.provider,
                model=self.descriptor.model,
                product="gfs.tCCz.pgrb2.0p25.fFFF",
                cycle_time_utc=run.cycle_time_utc,
                retrieved_at_utc=datetime.now(UTC),
                horizon_hours=max(point.lead_hours or 0 for point in points),
                native_time_step_hours=native_step,
                grid_type="regular latitude-longitude",
                spatial_resolution="0.25°",
                grid_latitude=sample.get("lat"),
                grid_longitude=sample.get("lon"),
                grid_distance_km=sample.get("distance"),
                model_elevation_m=None,
                licence="NOAA/NWS data; U.S. Government work",
                source_reference=self.filter_endpoint,
                attribution="NOAA/NCEP Global Forecast System via NOMADS",
                exact_cycle_known=True,
            ),
            points=points,
            warnings=warnings,
        )

    @staticmethod
    def forecast_hours(max_hours: int, *, hourly_to_120: bool = True) -> list[int]:
        max_hours = max(0, min(max_hours, 384))
        if not hourly_to_120:
            return list(range(0, max_hours + 1, 3))
        first_limit = min(max_hours, 120)
        values = list(range(0, first_limit + 1))
        if max_hours > 120:
            values.extend(range(123, max_hours + 1, 3))
        return values

    @classmethod
    def subset_params(
        cls,
        *,
        location: Location,
        run: GfsRun,
        forecast_hour: int,
        box_degrees: float,
    ) -> dict[str, str]:
        half = box_degrees / 2
        left = max(-180.0, location.longitude - half)
        right = min(180.0, location.longitude + half)
        top = min(90.0, location.latitude + half)
        bottom = max(-90.0, location.latitude - half)
        params: dict[str, str] = {
            "file": f"gfs.t{run.cycle:02d}z.pgrb2.0p25.f{forecast_hour:03d}",
            "subregion": "",
            "leftlon": f"{left:.4f}",
            "rightlon": f"{right:.4f}",
            "toplat": f"{top:.4f}",
            "bottomlat": f"{bottom:.4f}",
            "dir": f"/gfs.{run.run_date:%Y%m%d}/{run.cycle:02d}/atmos",
            "lev_2_m_above_ground": "on",
            "lev_10_m_above_ground": "on",
            "lev_surface": "on",
            "lev_mean_sea_level": "on",
            "lev_entire_atmosphere": "on",
            "lev_entire_atmosphere_(considered_as_a_single_layer)": "on",
            "var_TMP": "on",
            "var_RH": "on",
            "var_DPT": "on",
            "var_PRMSL": "on",
            "var_PRES": "on",
            "var_UGRD": "on",
            "var_VGRD": "on",
            "var_GUST": "on",
            "var_APCP": "on",
            "var_ACPCP": "on",
            "var_TCDC": "on",
            "var_LCDC": "on",
            "var_MCDC": "on",
            "var_HCDC": "on",
            "var_VIS": "on",
            "var_CAPE": "on",
            "var_CIN": "on",
            "var_DSWRF": "on",
            "var_PWAT": "on",
            "var_HPBL": "on",
            "var_WEASD": "on",
            "var_SNOD": "on",
        }
        return params

    async def detect_latest_run(self, now: datetime | None = None) -> GfsRun:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        candidates = self.candidate_runs(now)
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        )
        try:
            for run in candidates:
                url = self.index_url(run, 0)
                try:
                    response = await client.get(url, headers={"Range": "bytes=0-255"})
                    if response.status_code in {200, 206} and response.text:
                        return run
                except httpx.HTTPError:
                    continue
        finally:
            if own_client:
                await client.aclose()
        raise RuntimeError("Не удалось определить доступный цикл GFS на NOAA NOMADS")

    @staticmethod
    def candidate_runs(now: datetime, publication_lag_hours: int = 5, count: int = 8) -> list[GfsRun]:
        shifted = now.astimezone(UTC) - timedelta(hours=publication_lag_hours)
        cycle_hour = (shifted.hour // 6) * 6
        current = shifted.replace(hour=cycle_hour, minute=0, second=0, microsecond=0)
        candidates = [current - timedelta(hours=6 * index) for index in range(count)]
        return [GfsRun(candidate.date(), candidate.hour) for candidate in candidates]

    @classmethod
    def index_url(cls, run: GfsRun, forecast_hour: int) -> str:
        return (
            f"{cls.data_root}/gfs.{run.run_date:%Y%m%d}/{run.cycle:02d}/atmos/"
            f"gfs.t{run.cycle:02d}z.pgrb2.0p25.f{forecast_hour:03d}.idx"
        )

    def _run_from_options(self, options: dict[str, Any]) -> GfsRun | None:
        raw = options.get("cycle")
        if raw is None:
            return None
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        parsed = parsed.astimezone(UTC)
        if parsed.hour not in {0, 6, 12, 18}:
            raise ValueError("Цикл GFS должен начинаться в 00, 06, 12 или 18 UTC")
        return GfsRun(parsed.date(), parsed.hour)

    async def _download_all(
        self,
        *,
        location: Location,
        run: GfsRun,
        hours: list[int],
        max_concurrency: int,
        box_degrees: float,
    ) -> tuple[list[tuple[int, Path]], list[str]]:
        semaphore = asyncio.Semaphore(max_concurrency)
        warnings: list[str] = []
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        )

        async def download(hour: int) -> tuple[int, Path] | None:
            async with semaphore:
                try:
                    return hour, await self._download_one(client, location, run, hour, box_degrees)
                except Exception as exc:  # individual forecast hour must not stop the run
                    LOGGER.warning("GFS f%03d download failed: %s", hour, exc)
                    warnings.append(f"Не получен срок GFS +{hour} ч: {exc}")
                    return None

        try:
            results = await asyncio.gather(*(download(hour) for hour in hours))
        finally:
            if own_client:
                await client.aclose()
        return [result for result in results if result is not None], warnings

    async def _download_one(
        self,
        client: httpx.AsyncClient,
        location: Location,
        run: GfsRun,
        forecast_hour: int,
        box_degrees: float,
    ) -> Path:
        target = self.cache_dir / "gfs" / run.stamp / location.id / f"f{forecast_hour:03d}.grib2"
        if target.exists() and target.stat().st_size > 16:
            with target.open("rb") as stream:
                if stream.read(4) == b"GRIB":
                    return target
        target.parent.mkdir(parents=True, exist_ok=True)
        params = self.subset_params(
            location=location,
            run=run,
            forecast_hour=forecast_hour,
            box_degrees=box_degrees,
        )
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.get(self.filter_endpoint, params=params)
                response.raise_for_status()
                content = response.content
                if not content.startswith(b"GRIB"):
                    snippet = content[:200].decode("utf-8", errors="replace")
                    raise RuntimeError(f"NOMADS вернул не GRIB2: {snippet}")
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                    stream.write(content)
                    temporary = Path(stream.name)
                temporary.replace(target)
                return target
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** (attempt - 1), 5))
        raise RuntimeError(f"срок +{forecast_hour} ч не загружен: {last_error}")

    def _parse_grib_file(
        self,
        path: Path,
        location: Location,
        run: GfsRun,
        forecast_hour: int,
    ) -> ForecastPoint | None:
        try:
            from eccodes import (
                codes_get,
                codes_grib_find_nearest,
                codes_grib_new_from_file,
                codes_release,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Для прямого источника GFS установите системный ecCodes и Python-пакет: "
                "pip install 'weather-to-docx[grib]'"
            ) from exc

        timezone = ZoneInfo(location.timezone)
        values: dict[str, ForecastValue] = {}
        valid_time = run.cycle_time_utc + timedelta(hours=forecast_hour)
        with path.open("rb") as stream:
            while True:
                gid = codes_grib_new_from_file(stream)
                if gid is None:
                    break
                try:
                    short_name = str(_safe_codes_get(codes_get, gid, "shortName", ""))
                    type_of_level = str(_safe_codes_get(codes_get, gid, "typeOfLevel", ""))
                    level = _safe_codes_get(codes_get, gid, "level", None)
                    units = str(_safe_codes_get(codes_get, gid, "units", ""))
                    start_step = _as_int(_safe_codes_get(codes_get, gid, "startStep", None))
                    end_step = _as_int(_safe_codes_get(codes_get, gid, "endStep", forecast_hour))
                    nearest = codes_grib_find_nearest(gid, location.latitude, location.longitude)[0]
                    raw_value = float(nearest["value"])
                    mapped = self._map_grib_value(
                        short_name=short_name,
                        type_of_level=type_of_level,
                        level=level,
                        value=raw_value,
                        units=units,
                        start_step=start_step,
                        end_step=end_step,
                    )
                    if mapped is not None:
                        code, measurement = mapped
                        values[code] = measurement
                    validity_date = _safe_codes_get(codes_get, gid, "validityDate", None)
                    validity_time = _safe_codes_get(codes_get, gid, "validityTime", None)
                    if validity_date and validity_time is not None:
                        text = f"{int(validity_date):08d}{int(validity_time):04d}"
                        valid_time = datetime.strptime(text, "%Y%m%d%H%M").replace(tzinfo=UTC)
                finally:
                    codes_release(gid)

        if not values:
            return None
        return ForecastPoint(
            valid_time_utc=valid_time,
            valid_time_local=valid_time.astimezone(timezone),
            lead_hours=forecast_hour,
            values=values,
        )

    @staticmethod
    def _map_grib_value(
        *,
        short_name: str,
        type_of_level: str,
        level: Any,
        value: float,
        units: str,
        start_step: int | None,
        end_step: int | None,
    ) -> tuple[str, ForecastValue] | None:
        name = short_name.lower()
        level_number = _as_float(level)
        code: str | None = None
        output_value = value
        output_unit = units

        if name in {"2t", "t"} and type_of_level in {"heightAboveGround", "heightAboveGroundLayer"} and level_number == 2:
            code, output_value, output_unit = "temperature_2m", _kelvin_to_celsius(value, units), "°C"
        elif name in {"2d", "dpt", "d"} and type_of_level in {"heightAboveGround", "heightAboveGroundLayer"} and level_number == 2:
            code, output_value, output_unit = "dew_point_2m", _kelvin_to_celsius(value, units), "°C"
        elif name in {"2r", "r", "rh"} and type_of_level in {"heightAboveGround", "heightAboveGroundLayer"} and level_number == 2:
            code, output_unit = "relative_humidity_2m", "%"
        elif name in {"prmsl", "msl"}:
            code, output_value, output_unit = "pressure_msl", _pressure_to_hpa(value, units), "гПа"
        elif name in {"sp", "pres"} and type_of_level == "surface":
            code, output_value, output_unit = "surface_pressure", _pressure_to_hpa(value, units), "гПа"
        elif name in {"10u", "u"} and type_of_level == "heightAboveGround" and level_number == 10:
            code, output_unit = "u_wind_10m", "м/с"
        elif name in {"10v", "v"} and type_of_level == "heightAboveGround" and level_number == 10:
            code, output_unit = "v_wind_10m", "м/с"
        elif name in {"gust", "10fg"}:
            code, output_unit = "wind_gusts_10m", "м/с"
        elif name in {"tp", "apcp"}:
            code, output_unit = "precipitation_accumulated", "мм"
        elif name in {"acpcp", "cprat"}:
            code, output_unit = "convective_precipitation", "мм"
        elif name in {"tcc", "tcdc"}:
            code, output_value, output_unit = "cloud_cover", _cloud_to_percent(value, units), "%"
        elif name in {"lcc", "lcdc"}:
            code, output_value, output_unit = "cloud_cover_low", _cloud_to_percent(value, units), "%"
        elif name in {"mcc", "mcdc"}:
            code, output_value, output_unit = "cloud_cover_mid", _cloud_to_percent(value, units), "%"
        elif name in {"hcc", "hcdc"}:
            code, output_value, output_unit = "cloud_cover_high", _cloud_to_percent(value, units), "%"
        elif name in {"vis", "visibility"}:
            code, output_unit = "visibility", "м"
        elif name == "cape":
            code, output_unit = "cape", "Дж/кг"
        elif name == "cin":
            code, output_unit = "cin", "Дж/кг"
        elif name in {"dswrf", "ssrd"}:
            code, output_unit = "shortwave_radiation", "Вт/м²"
        elif name in {"pwat", "tcwv"}:
            code, output_unit = "precipitable_water", "кг/м²"
        elif name in {"hpbl", "blh"}:
            code, output_unit = "boundary_layer_height", "м"
        elif name in {"sde", "snod"}:
            code, output_unit = "snow_depth", "м"
        elif name in {"sdwe", "weasd"}:
            code, output_unit = "snow_water_equivalent", "кг/м²"

        if code is None:
            return None
        return code, ForecastValue(
            value=output_value,
            unit=output_unit,
            quality=QualityFlag.SOURCE,
            source_parameter=f"{short_name}:{type_of_level}:{level}",
            note=f"GRIB units={units}" if units and units != output_unit else None,
            source_start_step=start_step,
            source_end_step=end_step,
        )

    @staticmethod
    def _derive_wind(point: ForecastPoint) -> None:
        u = point.raw("u_wind_10m")
        v = point.raw("v_wind_10m")
        if u is None or v is None:
            return
        speed, direction = wind_speed_direction_from_uv(float(u), float(v))
        point.values["wind_speed_10m"] = ForecastValue(
            value=speed,
            unit="м/с",
            quality=QualityFlag.CALCULATED,
            source_parameter="u_wind_10m,v_wind_10m",
        )
        point.values["wind_direction_10m"] = ForecastValue(
            value=direction,
            unit="°",
            quality=QualityFlag.CALCULATED,
            source_parameter="u_wind_10m,v_wind_10m",
        )

    @staticmethod
    def _derive_interval_precipitation(points: list[ForecastPoint]) -> None:
        previous_accumulated: float | None = None
        previous_end_step: int | None = None
        for point in points:
            measurement = point.measurement("precipitation_accumulated")
            if measurement is None or measurement.value is None:
                continue
            accumulated = float(measurement.value)
            interval = accumulated
            if (
                measurement.source_start_step == 0
                and previous_accumulated is not None
                and previous_end_step is not None
                and measurement.source_end_step is not None
                and measurement.source_end_step > previous_end_step
            ):
                interval = max(0.0, accumulated - previous_accumulated)
            point.values["precipitation"] = ForecastValue(
                value=interval,
                unit="мм",
                quality=QualityFlag.CALCULATED,
                source_parameter="precipitation_accumulated",
                note="Интервальная сумма рассчитана из накопленного поля GRIB2",
                source_start_step=measurement.source_start_step,
                source_end_step=measurement.source_end_step,
            )
            previous_accumulated = accumulated
            previous_end_step = measurement.source_end_step

    def _first_grid_metadata(self, path: Path, location: Location) -> dict[str, float | None]:
        try:
            from eccodes import codes_grib_find_nearest, codes_grib_new_from_file, codes_release
        except ImportError:
            return {"lat": None, "lon": None, "distance": None}
        with path.open("rb") as stream:
            gid = codes_grib_new_from_file(stream)
            if gid is None:
                return {"lat": None, "lon": None, "distance": None}
            try:
                nearest = codes_grib_find_nearest(gid, location.latitude, location.longitude)[0]
                lat = float(nearest.get("lat"))
                lon = float(nearest.get("lon"))
                return {
                    "lat": lat,
                    "lon": lon,
                    "distance": float(nearest.get("distance", haversine_km(location.latitude, location.longitude, lat, lon))),
                }
            finally:
                codes_release(gid)


def _safe_codes_get(function: Any, gid: Any, key: str, default: Any) -> Any:
    try:
        return function(gid, key)
    except Exception:
        return default


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _kelvin_to_celsius(value: float, units: str) -> float:
    return value - 273.15 if units.lower() in {"k", "kelvin"} or value > 150 else value


def _pressure_to_hpa(value: float, units: str) -> float:
    return value / 100 if units.lower() in {"pa", "pascal", "pascals"} or value > 2000 else value


def _cloud_to_percent(value: float, units: str) -> float:
    return value * 100 if units in {"0-1", "fraction"} or 0 <= value <= 1 else value
