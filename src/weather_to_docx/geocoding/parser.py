from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from weather_to_docx.domain.models import Location, TimezoneSource
from weather_to_docx.geocoding.dadata import DadataClient
from weather_to_docx.geocoding.timezone import resolve_timezone

_COORDINATES = re.compile(
    r"^\s*(?P<lat>[+-]?\d{1,2}(?:[.,]\d+)?)\s*[,;\s]\s*"
    r"(?P<lon>[+-]?\d{1,3}(?:[.,]\d+)?)\s*$"
)


@dataclass(slots=True)
class LocationParseResult:
    locations: list[Location] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


async def parse_location_bytes(
    filename: str,
    content: bytes,
    *,
    geocoder: DadataClient | None,
    default_timezone: str,
    max_locations: int,
) -> LocationParseResult:
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("Файл превышает 20 МБ")
    text = content.decode("utf-8-sig", errors="strict")
    suffix = Path(filename).suffix.lower()
    if suffix == ".json":
        items = _json_items(text)
    elif suffix == ".csv":
        items = _csv_items(text)
    else:
        items = [line.strip() for line in text.splitlines() if _meaningful(line)]
    return await resolve_items(
        items,
        geocoder=geocoder,
        default_timezone=default_timezone,
        max_locations=max_locations,
        automatic=True,
    )


async def resolve_items(
    items: list[Any],
    *,
    geocoder: DadataClient | None,
    default_timezone: str,
    max_locations: int,
    automatic: bool,
) -> LocationParseResult:
    result = LocationParseResult()
    seen: set[tuple[float, float]] = set()
    for index, item in enumerate(items, start=1):
        if len(result.locations) >= max_locations:
            result.warnings.append(
                f"Обработаны первые {max_locations} точек; остальные пропущены"
            )
            break
        try:
            location = await resolve_item(
                item,
                geocoder=geocoder,
                default_timezone=default_timezone,
                automatic=automatic,
                ordinal=index,
            )
        except Exception as exc:
            result.warnings.append(f"Строка {index}: {exc}")
            continue
        key = (round(location.latitude, 6), round(location.longitude, 6))
        if key in seen:
            result.warnings.append(f"Строка {index}: повтор координат пропущен")
            continue
        seen.add(key)
        if location.timezone_source == TimezoneSource.SYSTEM_DEFAULT:
            result.warnings.append(
                f"Строка {index}: часовой пояс {location.timezone} взят из "
                "системной настройки; проверьте его"
            )
        result.locations.append(location)
    if not result.locations:
        raise ValueError("Не удалось определить ни одной координаты")
    return result


async def resolve_item(
    item: Any,
    *,
    geocoder: DadataClient | None,
    default_timezone: str,
    automatic: bool,
    ordinal: int = 1,
) -> Location:
    if isinstance(item, dict):
        if "latitude" in item and "longitude" in item:
            payload = dict(item)
            payload.setdefault("id", f"input-{ordinal}")
            payload.setdefault("name", payload["id"])
            latitude = float(str(payload["latitude"]).replace(",", "."))
            longitude = float(str(payload["longitude"]).replace(",", "."))
            payload["latitude"] = latitude
            payload["longitude"] = longitude
            if payload.get("timezone"):
                payload.setdefault("timezone_source", TimezoneSource.EXPLICIT)
            else:
                timezone, source = resolve_timezone(
                    latitude,
                    longitude,
                    fallback=default_timezone,
                )
                payload["timezone"] = timezone
                payload["timezone_source"] = source
            return Location.model_validate(payload)
        query = str(
            item.get("address")
            or item.get("city")
            or item.get("name")
            or ""
        )
    else:
        query = str(item).strip()
    coordinates = parse_coordinates(query)
    if coordinates:
        lat, lon = coordinates
        timezone, source = resolve_timezone(
            lat,
            lon,
            fallback=default_timezone,
        )
        return Location(
            id=f"coordinates-{ordinal}",
            name=f"Координаты {lat:.5f}, {lon:.5f}",
            latitude=lat,
            longitude=lon,
            timezone=timezone,
            timezone_source=TimezoneSource(source),
            group="Входной файл",
        )
    if not query:
        raise ValueError("пустой город или адрес")
    if geocoder is None:
        raise ValueError("для названий городов требуется настроенный DaData token")
    place = await geocoder.resolve_one(query, automatic=automatic)
    if place is None:
        raise ValueError(f"DaData не нашла координаты для «{query}»")
    timezone, source = resolve_timezone(
        place.latitude,
        place.longitude,
        fallback=default_timezone,
    )
    return place.to_location(
        timezone=timezone,
        prefix=f"input{ordinal}",
    ).model_copy(update={"timezone_source": TimezoneSource(source)})


def parse_coordinates(text: str) -> tuple[float, float] | None:
    match = _COORDINATES.fullmatch(text)
    if not match:
        return None
    latitude = float(match.group("lat").replace(",", "."))
    longitude = float(match.group("lon").replace(",", "."))
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("координаты находятся вне допустимого диапазона")
    return latitude, longitude


def _json_items(text: str) -> list[Any]:
    payload = json.loads(text)
    if isinstance(payload, dict):
        payload = payload.get("locations") or payload.get("items") or [payload]
    if not isinstance(payload, list):
        raise ValueError("JSON должен содержать массив точек или поле locations")
    return payload


def _csv_items(text: str) -> list[Any]:
    lines = [line for line in text.splitlines() if _meaningful(line)]
    if not lines:
        return []
    if lines[0].lower().startswith("sep="):
        delimiter = lines.pop(0)[4:5] or ";"
    else:
        try:
            delimiter = csv.Sniffer().sniff(
                "\n".join(lines[:10]),
                delimiters=";,\t",
            ).delimiter
        except csv.Error:
            delimiter = ";"
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    normalized: list[Any] = []
    for row in reader:
        lowered = {str(key).strip().lower(): value for key, value in row.items()}
        lat = _first(lowered, "latitude", "lat", "широта")
        lon = _first(lowered, "longitude", "lon", "lng", "долгота")
        if lat not in (None, "") and lon not in (None, ""):
            normalized.append(
                {
                    "id": _first(lowered, "id", "идентификатор")
                    or f"csv-{len(normalized) + 1}",
                    "name": _first(lowered, "name", "название", "город")
                    or f"Точка {len(normalized) + 1}",
                    "latitude": str(lat).replace(",", "."),
                    "longitude": str(lon).replace(",", "."),
                    "timezone": _first(
                        lowered,
                        "timezone",
                        "часовой пояс",
                        "часовой_пояс",
                    )
                    or "",
                }
            )
        else:
            normalized.append(
                _first(
                    lowered,
                    "address",
                    "адрес",
                    "city",
                    "город",
                    "name",
                    "название",
                )
                or ""
            )
    return normalized


def _first(row: dict[str, Any], *keys: str) -> Any:
    return next((row[key] for key in keys if key in row), None)


def _meaningful(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped and not stripped.startswith("#"))
