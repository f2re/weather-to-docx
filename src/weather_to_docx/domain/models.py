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


class SourceKind(StrEnum):
    """Физический смысл прогностического ряда."""

    DETERMINISTIC = "deterministic"
    ENSEMBLE = "ensemble"
    SYNTHETIC = "synthetic"


class TimezoneSource(StrEnum):
    """Происхождение часового пояса точки."""

    EXPLICIT = "explicit"
    COORDINATES = "coordinates"
    GEOCODER = "geocoder"
    SYSTEM_DEFAULT = "system_default"


class LeadTimeReference(StrEnum):
    """От какой временной точки отсчитывается `lead_hours`."""

    CYCLE = "cycle"
    RESPONSE_START = "response_start"
    UNKNOWN = "unknown"


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
    timezone_source: TimezoneSource = TimezoneSource.EXPLICIT
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
    sample_count: int | None = Field(default=None, ge=1)
    event_count: int | None = Field(default=None, ge=0)
    accumulation_hours: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_event_count(self) -> ForecastValue:
        if (
            self.sample_count is not None
            and self.event_count is not None
            and self.event_count > self.sample_count
        ):
            raise ValueError("Число событий не может превышать размер выборки")
        return self


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_id: str
    provider: str
    model: str
    product: str
    source_kind: SourceKind = SourceKind.DETERMINISTIC
    cycle_time_utc: datetime | None = None
    retrieved_at_utc: datetime
    horizon_hours: int | None = None
    native_time_step_hours: float | None = None
    lead_time_reference: LeadTimeReference = LeadTimeReference.CYCLE
    grid_type: str | None = None
    spatial_resolution: str | None = None
    grid_latitude: float | None = None
    grid_longitude: float | None = None
    grid_distance_km: float | None = None
    model_elevation_m: float | None = None
    licence: str | None = None
    source_reference: str | None = None
    attribution: str | None = None
    adapter_version: str = "0.3.2"
    exact_cycle_known: bool = True

    ensemble_member_count: int | None = Field(default=None, ge=1)
    ensemble_expected_member_count: int | None = Field(default=None, ge=1)
    ensemble_member_coverage_percent: float | None = Field(default=None, ge=0, le=100)
    member_weighting: str | None = None
    primary_statistic_policy: str | None = None
    quantile_method: str | None = None
    probability_calibration: str | None = None

    @model_validator(mode="before")
    @classmethod
    def infer_legacy_lead_reference(cls, value: Any) -> Any:
        if isinstance(value, dict) and "lead_time_reference" not in value:
            value = dict(value)
            value["lead_time_reference"] = (
                LeadTimeReference.CYCLE.value
                if value.get("exact_cycle_known", True)
                else LeadTimeReference.RESPONSE_START.value
            )
        return value

    @field_validator("cycle_time_utc", "retrieved_at_utc")
    @classmethod
    def validate_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Дата и время должны содержать часовой пояс")
        return value

    @model_validator(mode="after")
    def validate_ensemble_metadata(self) -> SourceMetadata:
        ensemble_fields = (
            self.ensemble_member_count,
            self.ensemble_expected_member_count,
            self.ensemble_member_coverage_percent,
        )
        has_ensemble_metadata = any(value is not None for value in ensemble_fields)
        if (
            has_ensemble_metadata
            and self.source_kind == SourceKind.DETERMINISTIC
            and _looks_like_legacy_ensemble(self.source_id, self.model, self.product)
        ):
            self.source_kind = SourceKind.ENSEMBLE
        elif has_ensemble_metadata and self.source_kind != SourceKind.ENSEMBLE:
            raise ValueError(
                "Число членов и полнота допустимы только для ансамблевого источника"
            )
        if (
            self.lead_time_reference == LeadTimeReference.CYCLE
            and not self.exact_cycle_known
        ):
            self.lead_time_reference = LeadTimeReference.RESPONSE_START
        return self


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
    summary_interval_hours: int = Field(default=6, ge=1, le=24)
    extended_summary_interval_hours: int = Field(default=12, ge=1, le=24)
    summary_switch_hour: int = Field(default=72, ge=1, le=1000)
    ensemble_interval_hours: int = Field(default=12, ge=1, le=24)
    ensemble_extended_interval_hours: int = Field(default=24, ge=1, le=24)
    ensemble_switch_hour: int = Field(default=72, ge=1, le=1000)
    include_detailed_table: bool = True
    include_all_parameters: bool = False
    include_ensemble_section: bool = True
    parameter_profile: str = Field(
        default="operational",
        pattern=r"^(operational|extended|all)$",
    )
    page_size: str = Field(default="A4", pattern=r"^(A3|A4)$")
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
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Один источник нельзя добавлять в задание дважды")
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
    worker_id: str | None = None
    lease_expires_at_utc: datetime | None = None
    attempt_count: int = Field(default=0, ge=0)
    progress_current: int = Field(default=0, ge=0)
    progress_total: int = Field(default=0, ge=0)
    progress_message: str | None = None

    @field_validator("created_at_utc", "updated_at_utc", "lease_expires_at_utc")
    @classmethod
    def validate_job_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Дата задания должна содержать часовой пояс")
        return value


def _looks_like_legacy_ensemble(source_id: str, model: str, product: str) -> bool:
    text = f"{source_id} {model} {product}".lower()
    return any(token in text for token in ("ensemble", "gefs", "geps", "eps", "ансамб"))
