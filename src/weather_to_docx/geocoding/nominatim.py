from __future__ import annotations

import asyncio
import time
from typing import Any, ClassVar

import httpx

from weather_to_docx.geocoding.dadata import GeocodedPlace


class NominatimClient:
    """Free OpenStreetMap Nominatim geocoder used when DaData is not configured."""

    # The public service permits at most one request per second per application.
    _rate_limit_lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _last_request_at: ClassVar[float] = 0.0

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 20,
        user_agent: str = "weather-to-docx/0.3.1",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self._client = client

    async def suggest_address(
        self,
        query: str,
        *,
        count: int = 5,
    ) -> list[GeocodedPlace]:
        query = query.strip()
        if not query:
            return []
        payload = await self._get(
            "/search",
            {
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "accept-language": "ru",
                "limit": max(1, min(count, 20)),
            },
        )
        if not isinstance(payload, list):
            return []
        return [
            place
            for item in payload
            if isinstance(item, dict)
            and (place := _place_from_nominatim(item)) is not None
        ]

    async def reverse(
        self,
        latitude: float,
        longitude: float,
        *,
        count: int = 5,
    ) -> list[GeocodedPlace]:
        # Public Nominatim returns one best match for a reverse lookup.
        payload = await self._get(
            "/reverse",
            {
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "addressdetails": 1,
                "accept-language": "ru",
                "zoom": 18,
            },
        )
        if not isinstance(payload, dict):
            return []
        place = _place_from_nominatim(payload)
        return [place] if place is not None else []

    async def resolve_one(
        self,
        query: str,
        *,
        automatic: bool = False,
    ) -> GeocodedPlace | None:
        del automatic  # Nominatim has no equivalent address-cleaning endpoint.
        places = await self.suggest_address(query, count=1)
        return places[0] if places else None

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=True,
        )
        try:
            await self._wait_for_rate_limit()
            response = await client.get(
                f"{self.base_url}{path}",
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": self.user_agent,
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise RuntimeError(
                "Nominatim отклонил запрос: "
                f"HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Nominatim недоступен: {exc}") from exc
        finally:
            if own_client:
                await client.aclose()

    @classmethod
    async def _wait_for_rate_limit(cls) -> None:
        async with cls._rate_limit_lock:
            delay = 1 - (time.monotonic() - cls._last_request_at)
            if delay > 0:
                await asyncio.sleep(delay)
            cls._last_request_at = time.monotonic()


def _place_from_nominatim(item: dict[str, Any]) -> GeocodedPlace | None:
    try:
        latitude = float(item["lat"])
        longitude = float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    address = item.get("address") or {}
    if not isinstance(address, dict):
        address = {}
    name = next(
        (
            address[key]
            for key in ("city", "town", "village", "municipality", "county", "state")
            if address.get(key)
        ),
        item.get("name") or item.get("display_name"),
    )
    display_name = str(item.get("display_name") or name or "").strip()
    title = str(name or display_name or f"{latitude:.5f}, {longitude:.5f}").strip()
    quality = item.get("addresstype") or item.get("type") or item.get("place_rank")
    return GeocodedPlace(
        name=title[:250],
        latitude=latitude,
        longitude=longitude,
        address=display_name[:500],
        quality_code=str(quality) if quality is not None else None,
        source="OpenStreetMap Nominatim",
    )
