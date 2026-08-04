from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx

from weather_to_docx.domain.models import Location


@dataclass(frozen=True, slots=True)
class GeocodedPlace:
    name: str
    latitude: float
    longitude: float
    address: str
    quality_code: str | None = None
    source: str = "DaData"

    def to_location(self, *, timezone: str, prefix: str = "geo") -> Location:
        digest = hashlib.sha1(
            f"{self.latitude:.6f},{self.longitude:.6f},{self.name}".encode()
        ).hexdigest()[:12]
        return Location(
            id=f"{prefix}-{digest}",
            name=self.name,
            latitude=self.latitude,
            longitude=self.longitude,
            timezone=timezone,
            group="Геокодирование",
        )


class DadataClient:
    suggestions_url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"
    geolocate_url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/geolocate/address"
    clean_url = "https://cleaner.dadata.ru/api/v1/clean/address"

    def __init__(
        self,
        token: str,
        *,
        secret: str | None = None,
        timeout_seconds: float = 20,
        user_agent: str = "weather-to-docx/0.3.0",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not token.strip():
            raise ValueError("Для DaData требуется API-токен")
        self.token = token.strip()
        self.secret = secret.strip() if secret else None
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
        payload = await self._post(
            self.suggestions_url,
            {"query": query, "count": max(1, min(count, 20))},
        )
        return [
            place
            for suggestion in payload.get("suggestions", [])
            if (place := _place_from_dadata(suggestion)) is not None
        ]

    async def reverse(
        self,
        latitude: float,
        longitude: float,
        *,
        count: int = 5,
    ) -> list[GeocodedPlace]:
        payload = await self._post(
            self.geolocate_url,
            {
                "lat": latitude,
                "lon": longitude,
                "count": max(1, min(count, 20)),
            },
        )
        return [
            place
            for suggestion in payload.get("suggestions", [])
            if (place := _place_from_dadata(suggestion)) is not None
        ]

    async def clean_address(self, query: str) -> GeocodedPlace | None:
        if not self.secret:
            raise RuntimeError(
                "Автоматическая пакетная стандартизация DaData требует secret key"
            )
        payload = await self._post(
            self.clean_url,
            [query.strip()],
            include_secret=True,
        )
        if not isinstance(payload, list) or not payload:
            return None
        return _place_from_clean(payload[0])

    async def resolve_one(
        self,
        query: str,
        *,
        automatic: bool = False,
    ) -> GeocodedPlace | None:
        if automatic and self.secret:
            cleaned = await self.clean_address(query)
            if cleaned is not None:
                return cleaned
        suggestions = await self.suggest_address(query, count=1)
        return suggestions[0] if suggestions else None

    async def _post(
        self,
        url: str,
        payload: Any,
        *,
        include_secret: bool = False,
    ) -> Any:
        headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if include_secret:
            if not self.secret:
                raise RuntimeError("Для запроса очистки DaData требуется secret key")
            headers["X-Secret"] = self.secret
        own_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=True,
        )
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise RuntimeError(
                f"DaData отклонила запрос: HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"DaData недоступна: {exc}") from exc
        finally:
            if own_client:
                await client.aclose()


def _place_from_dadata(item: dict[str, Any]) -> GeocodedPlace | None:
    data = item.get("data") or {}
    return _build_place(
        name=(
            data.get("city_with_type")
            or data.get("settlement_with_type")
            or data.get("region_with_type")
            or item.get("value")
        ),
        address=item.get("unrestricted_value") or item.get("value"),
        latitude=data.get("geo_lat"),
        longitude=data.get("geo_lon"),
        quality=data.get("qc_geo"),
    )


def _place_from_clean(item: dict[str, Any]) -> GeocodedPlace | None:
    return _build_place(
        name=(
            item.get("city_with_type")
            or item.get("settlement_with_type")
            or item.get("region_with_type")
            or item.get("result")
            or item.get("source")
        ),
        address=item.get("result") or item.get("source"),
        latitude=item.get("geo_lat"),
        longitude=item.get("geo_lon"),
        quality=item.get("qc_geo"),
    )


def _build_place(
    *,
    name: Any,
    address: Any,
    latitude: Any,
    longitude: Any,
    quality: Any,
) -> GeocodedPlace | None:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    title = str(name or address or f"{lat:.5f}, {lon:.5f}").strip()
    return GeocodedPlace(
        name=title[:250],
        latitude=lat,
        longitude=lon,
        address=str(address or title)[:500],
        quality_code=str(quality) if quality is not None else None,
    )
