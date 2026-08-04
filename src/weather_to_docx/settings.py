from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WTD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("var")
    database_path: Path | None = None
    documents_dir: Path | None = None
    cache_dir: Path | None = None
    incoming_dir: Path | None = None
    icon_cache_dir: Path | None = None

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8080, ge=1, le=65535)
    default_timezone: str = "Europe/Moscow"
    default_forecast_days: int = Field(default=7, ge=1, le=35)
    default_source_ids: str = (
        "open_meteo_gfs,open_meteo_ecmwf_ifs,open_meteo_dwd_icon_global,"
        "open_meteo_gefs_0p25"
    )

    http_timeout_seconds: float = Field(default=60, gt=0, le=600)
    http_max_retries: int = Field(default=3, ge=1, le=10)
    http_user_agent: str = (
        "weather-to-docx/0.3.1 (+https://github.com/f2re/weather-to-docx)"
    )

    worker_heartbeat_seconds: float = Field(default=5, ge=1, le=60)
    worker_lease_seconds: int = Field(default=30, ge=10, le=3600)
    worker_online_max_age_seconds: int = Field(default=20, ge=5, le=600)
    worker_max_attempts: int = Field(default=3, ge=1, le=20)

    dadata_token: str | None = None
    dadata_secret: str | None = None
    dadata_timeout_seconds: float = Field(default=20, gt=0, le=120)
    dadata_suggestion_count: int = Field(default=5, ge=1, le=20)

    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_allowed_user_ids: str = ""
    telegram_max_locations: int = Field(default=100, ge=1, le=1000)
    telegram_max_input_bytes: int = Field(default=20 * 1024 * 1024, ge=1024)
    telegram_max_output_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    telegram_concurrency: int = Field(default=2, ge=1, le=20)
    telegram_job_poll_seconds: float = Field(default=3, ge=1, le=30)
    telegram_job_timeout_seconds: int = Field(default=1800, ge=30, le=86400)

    require_bundle_signature: bool = False
    bundle_public_key: Path | None = None
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(
                "Допустимые уровни журнала: DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )
        return value

    @field_validator("default_source_ids", "telegram_allowed_user_ids")
    @classmethod
    def normalize_comma_lists(cls, value: str) -> str:
        return ",".join(item.strip() for item in value.split(",") if item.strip())

    @model_validator(mode="after")
    def resolve_paths(self) -> Settings:
        self.data_dir = self.data_dir.expanduser().resolve()
        self.database_path = (
            self.database_path.expanduser().resolve()
            if self.database_path
            else self.data_dir / "database" / "weather-to-docx.sqlite3"
        )
        self.documents_dir = (
            self.documents_dir.expanduser().resolve()
            if self.documents_dir
            else self.data_dir / "documents"
        )
        self.cache_dir = (
            self.cache_dir.expanduser().resolve()
            if self.cache_dir
            else self.data_dir / "cache"
        )
        self.incoming_dir = (
            self.incoming_dir.expanduser().resolve()
            if self.incoming_dir
            else self.data_dir / "incoming"
        )
        self.icon_cache_dir = (
            self.icon_cache_dir.expanduser().resolve()
            if self.icon_cache_dir
            else self.cache_dir / "icons"
        )
        if self.bundle_public_key:
            self.bundle_public_key = self.bundle_public_key.expanduser().resolve()
        if self.telegram_enabled and not self.telegram_bot_token:
            raise ValueError(
                "WTD_TELEGRAM_ENABLED=true требует WTD_TELEGRAM_BOT_TOKEN"
            )
        if self.worker_lease_seconds <= self.worker_heartbeat_seconds * 2:
            raise ValueError(
                "WTD_WORKER_LEASE_SECONDS должен быть больше двойного интервала heartbeat"
            )
        return self

    @property
    def default_sources(self) -> tuple[str, ...]:
        return tuple(item for item in self.default_source_ids.split(",") if item)

    @property
    def allowed_telegram_users(self) -> frozenset[int]:
        users: set[int] = set()
        for raw in self.telegram_allowed_user_ids.split(","):
            if not raw:
                continue
            try:
                users.add(int(raw))
            except ValueError as exc:
                raise ValueError(
                    "WTD_TELEGRAM_ALLOWED_USER_IDS должен содержать целые ID через запятую"
                ) from exc
        return frozenset(users)

    @property
    def dadata_configured(self) -> bool:
        return bool(self.dadata_token)

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.database_path.parent,
            self.documents_dir,
            self.cache_dir,
            self.incoming_dir,
            self.icon_cache_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
