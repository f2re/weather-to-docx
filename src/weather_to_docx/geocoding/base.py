from __future__ import annotations

from typing import Protocol

from weather_to_docx.geocoding.dadata import GeocodedPlace


class Geocoder(Protocol):
    """Common interface used by HTTP, file import and Telegram clients."""

    async def suggest_address(
        self,
        query: str,
        *,
        count: int = 5,
    ) -> list[GeocodedPlace]: ...

    async def reverse(
        self,
        latitude: float,
        longitude: float,
        *,
        count: int = 5,
    ) -> list[GeocodedPlace]: ...

    async def resolve_one(
        self,
        query: str,
        *,
        automatic: bool = False,
    ) -> GeocodedPlace | None: ...
