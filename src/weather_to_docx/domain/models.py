from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class QualityFlag(StrEnum):
    SOURCE = "source"
    INTERPOLATED = "interpolated"
    CALCULATED = "calculated"
    CORRECTED = "corrected"
    STALE = "stale"
    MISSING = "missing"
    SUSPECT = "suspect"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9А-Яа-яЁё._-]+$")
    name: str = Field(min_length=1, max_length=250)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation_m: float | None = Field(default=None, ge=-500, le=9000)
    timezone: str = "UTC"
    group: str | None = Field(default=None, max_length=250)
    output_name: str | None = Field(default=None, max_length=250)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Неизвестный часовой пояс: {value}") from exc
        return value


class ForecastValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | int | str | bool | None
    unit: str | None = None
    quality: QualityFlag = QualityFlag.SOURCE
    source_parameter: str | None = None
    note: str | None = None
    source_start_step: int | None = None
    source_end_step: int | None = None


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_id: str
    provider: str
    model: str
    product: str
    cycle_time_utc: datetime | None = None
    retrieved_at_utc: datetime
    horizon_hours: int | None = None
    native_time_step_hours: float | None = None
    grid_type: str | None = None
    spatial_resolution: str | None = None
    grid_latitude: float | None = None
    grid_longitude: float | None = None
    grid_distance_km: float | None = None
    model_elevation_m: float | None = None
    licence: str | None = None
    source_reference: str | None = None
    attribution: str | None = None
    adapter_version: str = "0.2.0"
    exact_cycle_known: bool = True

    @field_validator("cycle_time_utc", "retrieved_at_utc")
    @classmethod
    def validate_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Дата и время должны содержать часовой пояс")
        return value


class ForecastPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid_time_utc: datetime
    valid_time_local: datetime
    lead_hours: int | None = None
    weather_code: int | None = None
    is_day: bool | None = None
    values: dict[str, ForecastValue] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("valid_time_utc", "valid_time_local")
    @classmethod
    def validate_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Дата и время должны содержать часовой пояс")
        return value

    def raw(self, code: str, default: Any = None) -> Any:
        value = self.values.get(code)
        return default if value is None or value.value is None else value.value

    def measurement(self, code: str) -> ForecastValue | None:
        return self.values.get(code)


class ForecastSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: Location
    source: SourceMetadata
    points: list[ForecastPoint]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_points(self) -> ForecastSeries:
        if not self.points:
            raise ValueError("Прогностический ряд не содержит ни одной точки")
        ordered = sorted(self.points, key=lambda point: point.valid_time_utc)
        if ordered != self.points:
            raise ValueError("Прогностические сроки должны быть отсортированы")
        return self


class SourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    forecast_days: int = Field(default=7, ge=1, le=35)
    options: dict[str, Any] = Field(default_factory=dict)


class DocumentOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = "Метеорологический прогноз"
    summary_interval_hours: int = Field(default=3, ge=1, le=24)
    extended_summary_interval_hours: int = Field(default=6, ge=1, le=24)
    summary_switch_hour: int = Field(default=120, ge=1, le=1000)
    include_detailed_table: bool = True
    include_all_parameters: bool = True
    parameter_profile: str = Field(
        default="all",
        pattern=r"^(operational|extended|all)$",
    )
    page_size: str = Field(default="A3", pattern=r"^(A3|A4)$")
    language: str = Field(default="ru", pattern=r"^ru$")
    organisation: str | None = None
    prepared_by: str | None = None


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locations: list[Location] = Field(min_length=1, max_length=1000)
    sources: list[SourceRequest] = Field(min_length=1, max_length=20)
    document: DocumentOptions = Field(default_factory=DocumentOptions)
    batch_name: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def unique_location_ids(self) -> BatchRequest:
        ids = [location.id for location in self.locations]
        if len(ids) != len(set(ids)):
            raise ValueError("Идентификаторы координат должны быть уникальными")
        return self


class CollectedLocation(BaseModel):
    location: Location
    series: list[ForecastSeries] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BatchArtifact(BaseModel):
    kind: str
    path: Path
    sha256: str
    size_bytes: int
    location_id: str | None = None


class BatchResult(BaseModel):
    batch_id: str
    status: JobStatus
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    artifacts: list[BatchArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class JobRecord(BaseModel):
    id: str
    status: JobStatus
    request: BatchRequest
    result: BatchResult | None = None
    error: str | None = None
    created_at_utc: datetime
    updated_at_utc: datetime
