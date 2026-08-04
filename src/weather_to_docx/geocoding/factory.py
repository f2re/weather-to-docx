from __future__ import annotations

from weather_to_docx.geocoding.base import Geocoder
from weather_to_docx.geocoding.dadata import DadataClient
from weather_to_docx.geocoding.nominatim import NominatimClient
from weather_to_docx.settings import Settings


def create_geocoder(settings: Settings) -> Geocoder:
    """Use DaData when configured; otherwise use free OpenStreetMap Nominatim."""
    if settings.dadata_token:
        return DadataClient(
            settings.dadata_token,
            secret=settings.dadata_secret,
            timeout_seconds=settings.dadata_timeout_seconds,
            user_agent=settings.http_user_agent,
        )
    return NominatimClient(
        base_url=settings.nominatim_url,
        timeout_seconds=settings.nominatim_timeout_seconds,
        user_agent=settings.http_user_agent,
    )
