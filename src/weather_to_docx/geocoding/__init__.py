"""Геокодирование и разбор пользовательских списков точек."""

from weather_to_docx.geocoding.dadata import DadataClient, GeocodedPlace
from weather_to_docx.geocoding.factory import create_geocoder
from weather_to_docx.geocoding.nominatim import NominatimClient
from weather_to_docx.geocoding.parser import (
    LocationParseResult,
    parse_coordinates,
    parse_location_bytes,
    resolve_item,
    resolve_items,
)

__all__ = [
    "DadataClient",
    "GeocodedPlace",
    "NominatimClient",
    "create_geocoder",
    "LocationParseResult",
    "parse_coordinates",
    "parse_location_bytes",
    "resolve_item",
    "resolve_items",
]
