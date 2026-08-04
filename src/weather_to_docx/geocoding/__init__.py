"""Геокодирование и разбор пользовательских списков точек."""

from weather_to_docx.geocoding.dadata import DadataClient, GeocodedPlace
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
    "LocationParseResult",
    "parse_coordinates",
    "parse_location_bytes",
    "resolve_item",
    "resolve_items",
]
