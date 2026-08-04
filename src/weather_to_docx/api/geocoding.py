from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from weather_to_docx.domain.models import Location, TimezoneSource
from weather_to_docx.geocoding.dadata import GeocodedPlace
from weather_to_docx.geocoding.factory import create_geocoder
from weather_to_docx.geocoding.parser import parse_location_bytes
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


class ParseLocationFileRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(max_length=20 * 1024 * 1024)
    max_locations: int = Field(default=1000, ge=1, le=1000)


class ParseLocationFileResponse(BaseModel):
    locations: list[Location]
    warnings: list[str]


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

    def geocoder():
        return create_geocoder(settings)

    @router.post("/suggest", response_model=list[GeocodingCandidate])
    async def suggest(request: SuggestRequest) -> list[GeocodingCandidate]:
        try:
            client = geocoder()
            places = await client.suggest_address(request.query, count=request.count)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return [_candidate(place, settings.default_timezone) for place in places]

    @router.post("/resolve", response_model=GeocodingCandidate)
    async def resolve(request: ResolveRequest) -> GeocodingCandidate:
        try:
            client = geocoder()
            place = await client.resolve_one(
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
            client = geocoder()
            places = await client.reverse(
                request.latitude,
                request.longitude,
                count=request.count,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return [_candidate(place, settings.default_timezone) for place in places]

    @router.post(
        "/parse-file",
        response_model=ParseLocationFileResponse,
    )
    async def parse_file(
        request: ParseLocationFileRequest,
    ) -> ParseLocationFileResponse:
        """Единый предварительный разбор TXT/CSV/JSON без записи в справочник."""

        suffix = request.filename.lower().rsplit(".", 1)[-1]
        if suffix not in {"txt", "csv", "json"}:
            raise HTTPException(
                status_code=422,
                detail="Поддерживаются только TXT, CSV и JSON",
            )
        try:
            result = await parse_location_bytes(
                request.filename,
                request.content.encode("utf-8"),
                geocoder=geocoder(),
                default_timezone=settings.default_timezone,
                max_locations=request.max_locations,
            )
        except (UnicodeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return ParseLocationFileResponse(
            locations=result.locations,
            warnings=result.warnings,
        )

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
