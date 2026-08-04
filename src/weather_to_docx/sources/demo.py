from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from weather_to_docx.document.weather_rules import derive_weather_code
from weather_to_docx.domain.models import (
    ForecastPoint,
    ForecastSeries,
    ForecastValue,
    Location,
    QualityFlag,
    SourceKind,
    SourceMetadata,
)
from weather_to_docx.sources.base import ForecastSource, SourceDescriptor


class DemoSource(ForecastSource):
    descriptor = SourceDescriptor(
        source_id="demo",
        name="Демонстрационный ряд",
        provider="weather-to-docx",
        model="Синтетические данные",
        horizon_days=16,
        exact_cycle=True,
        source_kind=SourceKind.SYNTHETIC,
        implementation_status="test-only",
        notes="Используется только для автономной проверки генератора документов.",
    )

    async def fetch(
        self,
        location: Location,
        forecast_days: int,
        options: dict[str, Any] | None = None,
    ) -> ForecastSeries:
        options = options or {}
        hours = min(forecast_days * 24, int(options.get("hours", 72)))
        cycle = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        timezone = ZoneInfo(location.timezone)
        points: list[ForecastPoint] = []

        for lead in range(hours + 1):
            valid_utc = cycle + timedelta(hours=lead)
            local = valid_utc.astimezone(timezone)
            solar_phase = math.sin((local.hour - 6) / 24 * 2 * math.pi)
            temperature = 13.0 + 8.0 * solar_phase + 0.8 * math.sin(lead / 9)
            cloud = max(0.0, min(100.0, 48.0 + 45.0 * math.sin(lead / 11)))
            precipitation = 2.8 if 18 <= lead % 48 <= 22 else 0.0
            wind_speed = 3.0 + 2.2 * (1 + math.sin(lead / 7)) / 2
            values = {
                "temperature_2m": ForecastValue(value=temperature, unit="°C"),
                "apparent_temperature": ForecastValue(
                    value=temperature - wind_speed * 0.25,
                    unit="°C",
                    quality=QualityFlag.CALCULATED,
                ),
                "dew_point_2m": ForecastValue(value=temperature - 4.5, unit="°C"),
                "relative_humidity_2m": ForecastValue(
                    value=max(35, min(98, 78 - solar_phase * 22)),
                    unit="%",
                ),
                "pressure_msl": ForecastValue(
                    value=1012 + 5 * math.sin(lead / 18),
                    unit="гПа",
                ),
                "surface_pressure": ForecastValue(
                    value=1003 + 5 * math.sin(lead / 18),
                    unit="гПа",
                ),
                "wind_speed_10m": ForecastValue(value=wind_speed, unit="м/с"),
                "wind_direction_10m": ForecastValue(
                    value=(210 + lead * 7) % 360,
                    unit="°",
                ),
                "wind_gusts_10m": ForecastValue(
                    value=wind_speed * 1.65,
                    unit="м/с",
                ),
                "precipitation": ForecastValue(value=precipitation, unit="мм"),
                "rain": ForecastValue(value=precipitation, unit="мм"),
                "precipitation_probability": ForecastValue(
                    value=75 if precipitation else 10,
                    unit="%",
                ),
                "snowfall": ForecastValue(value=0.0, unit="см"),
                "snow_depth": ForecastValue(value=0.0, unit="м"),
                "cloud_cover": ForecastValue(value=cloud, unit="%"),
                "cloud_cover_low": ForecastValue(value=cloud * 0.55, unit="%"),
                "cloud_cover_mid": ForecastValue(value=cloud * 0.35, unit="%"),
                "cloud_cover_high": ForecastValue(value=cloud * 0.25, unit="%"),
                "visibility": ForecastValue(
                    value=15_000 if precipitation else 30_000,
                    unit="м",
                ),
                "cape": ForecastValue(
                    value=900 if precipitation else 80,
                    unit="Дж/кг",
                ),
                "cin": ForecastValue(
                    value=-25 if precipitation else -90,
                    unit="Дж/кг",
                ),
                "shortwave_radiation": ForecastValue(
                    value=max(0, solar_phase) * 620,
                    unit="Вт/м²",
                ),
                "direct_radiation": ForecastValue(
                    value=max(0, solar_phase) * 410,
                    unit="Вт/м²",
                ),
                "diffuse_radiation": ForecastValue(
                    value=max(0, solar_phase) * 210,
                    unit="Вт/м²",
                ),
                "sunshine_duration": ForecastValue(
                    value=3600 if solar_phase > 0.35 and cloud < 65 else 0,
                    unit="с",
                ),
                "vapour_pressure_deficit": ForecastValue(
                    value=max(0, 1.5 + solar_phase),
                    unit="кПа",
                ),
                "et0_fao_evapotranspiration": ForecastValue(
                    value=max(0, solar_phase) * 0.14,
                    unit="мм",
                ),
                "soil_temperature_0cm": ForecastValue(
                    value=temperature - 1,
                    unit="°C",
                ),
                "soil_temperature_6cm": ForecastValue(
                    value=12.5 + 3 * solar_phase,
                    unit="°C",
                ),
                "soil_temperature_18cm": ForecastValue(value=11.5, unit="°C"),
                "soil_temperature_54cm": ForecastValue(value=10.5, unit="°C"),
                "soil_moisture_0_to_1cm": ForecastValue(value=0.22, unit="м³/м³"),
                "soil_moisture_1_to_3cm": ForecastValue(value=0.24, unit="м³/м³"),
                "soil_moisture_3_to_9cm": ForecastValue(value=0.27, unit="м³/м³"),
                "soil_moisture_9_to_27cm": ForecastValue(value=0.29, unit="м³/м³"),
                "soil_moisture_27_to_81cm": ForecastValue(value=0.31, unit="м³/м³"),
            }
            point = ForecastPoint(
                valid_time_utc=valid_utc,
                valid_time_local=local,
                lead_hours=lead,
                is_day=6 <= local.hour < 21,
                values=values,
            )
            point.weather_code = derive_weather_code(point)
            points.append(point)

        return ForecastSeries(
            location=location,
            source=SourceMetadata(
                source_id=self.descriptor.source_id,
                provider=self.descriptor.provider,
                model=self.descriptor.model,
                product="demo-hourly",
                source_kind=SourceKind.SYNTHETIC,
                cycle_time_utc=cycle,
                retrieved_at_utc=datetime.now(UTC),
                horizon_hours=hours,
                native_time_step_hours=1,
                grid_type="synthetic",
                spatial_resolution="не применяется",
                grid_latitude=location.latitude,
                grid_longitude=location.longitude,
                model_elevation_m=location.elevation_m,
                licence="Только для тестирования",
                source_reference="internal://demo",
                attribution="Синтетические данные; не являются прогнозом погоды",
            ),
            points=points,
            warnings=[
                "Демонстрационный ряд не является реальным прогнозом и не должен использоваться в работе."
            ],
        )
