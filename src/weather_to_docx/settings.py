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

    http_timeout_seconds: float = Field(default=60, gt=0, le=600)
    http_max_retries: int = Field(default=3, ge=1, le=10)
    http_user_agent: str = (
        "weather-to-docx/0.2.0 (+https://github.com/f2re/weather-to-docx)"
    )

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
        return self

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
