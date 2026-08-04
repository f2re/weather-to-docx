from __future__ import annotations

from weather_to_docx.domain.profiles import (
    COMPACT_ENSEMBLE_HOURLY_PARAMETERS,
    OPERATIONAL_HOURLY_PARAMETERS,
)
from weather_to_docx.settings import Settings
from weather_to_docx.sources.base import ForecastSource, SourceDescriptor
from weather_to_docx.sources.demo import DemoSource
from weather_to_docx.sources.ensemble_catalog import (
    OpenMeteoEcmwfAifsEnsembleSource,
    OpenMeteoEcmwfIfsEnsembleSource,
    OpenMeteoGemGepsSource,
)
from weather_to_docx.sources.gfs_nomads import GfsNomadsSource
from weather_to_docx.sources.open_meteo import (
    OpenMeteoDwdIconGlobalSource,
    OpenMeteoEcmwfAifsSource,
    OpenMeteoEcmwfIfsSource,
    OpenMeteoGemGdpsSource,
    OpenMeteoGfsSource,
)
from weather_to_docx.sources.open_meteo_ensemble import (
    OpenMeteoDwdIconEpsSource,
    OpenMeteoGefS025Source,
    OpenMeteoGefS05Source,
)


class SourceRegistry:
    def __init__(self, settings: Settings) -> None:
        self._sources: dict[str, ForecastSource] = {}
        self.register(DemoSource())

        deterministic_types = (
            OpenMeteoGfsSource,
            OpenMeteoEcmwfIfsSource,
            OpenMeteoEcmwfAifsSource,
            OpenMeteoDwdIconGlobalSource,
            OpenMeteoGemGdpsSource,
        )
        for source_type in deterministic_types:
            source = source_type(
                timeout_seconds=settings.http_timeout_seconds,
                max_retries=settings.http_max_retries,
                user_agent=settings.http_user_agent,
            )
            # Обычный отчёт не должен запрашивать десятки исследовательских
            # полей. При явном options["hourly"] адаптер всё равно использует
            # пользовательский набор и не ограничивает специальный сценарий.
            source.hourly_parameters = OPERATIONAL_HOURLY_PARAMETERS
            self.register(source)

        ensemble_types = (
            OpenMeteoGefS025Source,
            OpenMeteoGefS05Source,
            OpenMeteoEcmwfIfsEnsembleSource,
            OpenMeteoEcmwfAifsEnsembleSource,
            OpenMeteoDwdIconEpsSource,
            OpenMeteoGemGepsSource,
        )
        for source_type in ensemble_types:
            source = source_type(
                timeout_seconds=max(settings.http_timeout_seconds, 90),
                max_retries=settings.http_max_retries,
                user_agent=settings.http_user_agent,
            )
            source.hourly_parameters = COMPACT_ENSEMBLE_HOURLY_PARAMETERS
            self.register(source)

        self.register(
            GfsNomadsSource(
                cache_dir=settings.cache_dir,
                timeout_seconds=max(settings.http_timeout_seconds, 120),
                max_retries=settings.http_max_retries,
                user_agent=settings.http_user_agent,
            )
        )

    def register(self, source: ForecastSource) -> None:
        self._sources[source.descriptor.source_id] = source

    def get(self, source_id: str) -> ForecastSource:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._sources))
            raise KeyError(
                f"Неизвестный источник {source_id!r}. Доступны: {available}"
            ) from exc

    def descriptors(self) -> list[SourceDescriptor]:
        return [source.descriptor for source in self._sources.values()]
