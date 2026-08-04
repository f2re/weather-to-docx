from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from weather_to_docx.domain.models import Location, TimezoneSource
from weather_to_docx.geocoding.dadata import DadataClient, GeocodedPlace
from weather_to_docx.geocoding.timezone import resolve_timezone
from weather_to_docx.settings import Settings


class SuggestRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    count: int = Field(default=5, ge=1, le=20)


class ResolveRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    automatic: bool = False


class ReverseRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    count: int = Field(default=5, ge=1, le=20)


class GeocodingCandidate(BaseModel):
    name: str
    address: str
    latitude: float
    longitude: float
    timezone: str
    timezone_source: TimezoneSource
    quality_code: str | None = None
    location: Location


def create_geocoding_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/geocoding", tags=["geocoding"])

    def client() -> DadataClient:
        if not settings.dadata_token:
            raise HTTPException(
                status_code=503,
                detail=(
                    "DaData не настроена. Задайте WTD_DADATA_TOKEN в "
                    "/etc/weather-to-docx/weather-to-docx.env"
                ),
            )
        return DadataClient(
            settings.dadata_token,
            secret=settings.dadata_secret,
            timeout_seconds=settings.dadata_timeout_seconds,
            user_agent=settings.http_user_agent,
        )

    @router.post("/suggest", response_model=list[GeocodingCandidate])
    async def suggest(request: SuggestRequest) -> list[GeocodingCandidate]:
        try:
            places = await client().suggest_address(request.query, count=request.count)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return [_candidate(place, settings.default_timezone) for place in places]

    @router.post("/resolve", response_model=GeocodingCandidate)
    async def resolve(request: ResolveRequest) -> GeocodingCandidate:
        try:
            place = await client().resolve_one(
                request.query,
                automatic=request.automatic,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if place is None:
            raise HTTPException(status_code=404, detail="Координаты не найдены")
        return _candidate(place, settings.default_timezone)

    @router.post("/reverse", response_model=list[GeocodingCandidate])
    async def reverse(request: ReverseRequest) -> list[GeocodingCandidate]:
        try:
            places = await client().reverse(
                request.latitude,
                request.longitude,
                count=request.count,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return [_candidate(place, settings.default_timezone) for place in places]

    return router


def _candidate(place: GeocodedPlace, fallback_timezone: str) -> GeocodingCandidate:
    timezone, timezone_source = resolve_timezone(
        place.latitude,
        place.longitude,
        fallback=fallback_timezone,
    )
    source = TimezoneSource(timezone_source)
    location = place.to_location(timezone=timezone).model_copy(
        update={"timezone_source": source}
    )
    return GeocodingCandidate(
        name=place.name,
        address=place.address,
        latitude=place.latitude,
        longitude=place.longitude,
        timezone=timezone,
        timezone_source=source,
        quality_code=place.quality_code,
        location=location,
    )
