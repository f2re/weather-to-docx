from __future__ import annotations

from weather_to_docx.domain.profiles import (
    COMPACT_ENSEMBLE_HOURLY_PARAMETERS,
    OPERATIONAL_HOURLY_PARAMETERS,
)
from weather_to_docx.settings import Settings
from weather_to_docx.sources.registry import SourceRegistry


def test_operational_profile_contains_only_report_fields() -> None:
    required = {
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "pressure_msl",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
        "cloud_cover",
        "weather_code",
    }
    excluded = {
        "surface_pressure",
        "shortwave_radiation",
        "direct_radiation",
        "diffuse_radiation",
        "soil_temperature_0cm",
        "soil_moisture_0_to_1cm",
        "evapotranspiration",
        "et0_fao_evapotranspiration",
        "vapour_pressure_deficit",
    }
    assert required <= set(OPERATIONAL_HOURLY_PARAMETERS)
    assert not excluded & set(OPERATIONAL_HOURLY_PARAMETERS)


def test_ensemble_profile_is_even_smaller() -> None:
    assert {
        "temperature_2m",
        "precipitation",
        "pressure_msl",
        "wind_speed_10m",
        "wind_gusts_10m",
        "weather_code",
    } == set(COMPACT_ENSEMBLE_HOURLY_PARAMETERS)


def test_registry_applies_profiles_to_all_open_meteo_sources(tmp_path) -> None:
    registry = SourceRegistry(Settings(data_dir=tmp_path))

    for source_id in (
        "open_meteo_gfs",
        "open_meteo_ecmwf_ifs",
        "open_meteo_ecmwf_aifs",
        "open_meteo_dwd_icon_global",
        "open_meteo_gem_gdps",
    ):
        assert (
            registry.get(source_id).hourly_parameters
            == OPERATIONAL_HOURLY_PARAMETERS
        )

    for source_id in (
        "open_meteo_gefs_0p25",
        "open_meteo_gefs_0p5",
        "open_meteo_ecmwf_ifs_ensemble",
        "open_meteo_ecmwf_aifs_ensemble",
        "open_meteo_dwd_icon_eps",
        "open_meteo_gem_geps",
    ):
        assert (
            registry.get(source_id).hourly_parameters
            == COMPACT_ENSEMBLE_HOURLY_PARAMETERS
        )
