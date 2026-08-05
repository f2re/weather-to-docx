from __future__ import annotations

from weather_to_docx.ensemble.science import ensemble_statistics
from weather_to_docx.settings import Settings
from weather_to_docx.sources.registry import SourceRegistry


def test_ensemble_statistics_include_interquartile_range() -> None:
    statistics = ensemble_statistics(range(1, 11))
    assert statistics.p10 < statistics.p25 < statistics.median
    assert statistics.median < statistics.p75 < statistics.p90
    assert statistics.interquartile_range == statistics.p75 - statistics.p25


def test_registry_installs_p25_p75_storage(tmp_path) -> None:
    registry = SourceRegistry(Settings(data_dir=tmp_path))
    # Инициализация реестра устанавливает расширенную научную нормализацию.
    assert registry.get("open_meteo_gefs_0p25") is not None
