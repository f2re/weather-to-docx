from __future__ import annotations

import json

import httpx
import pytest

from weather_to_docx.geocoding.dadata import DadataClient
from weather_to_docx.geocoding.parser import (
    parse_coordinates,
    parse_location_bytes,
    resolve_items,
)


def _suggestion() -> dict:
    return {
        "value": "г Санкт-Петербург",
        "unrestricted_value": "190000, г Санкт-Петербург",
        "data": {
            "city_with_type": "г Санкт-Петербург",
            "geo_lat": "59.938955",
            "geo_lon": "30.315644",
            "qc_geo": "0",
        },
    }


@pytest.mark.asyncio
async def test_dadata_suggest_reverse_and_clean() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Token test-token"
        if "/clean/address" in str(request.url):
            assert request.headers["X-Secret"] == "test-secret"
            return httpx.Response(
                200,
                json=[
                    {
                        "result": "г Санкт-Петербург",
                        "city_with_type": "г Санкт-Петербург",
                        "geo_lat": "59.938955",
                        "geo_lon": "30.315644",
                        "qc_geo": "0",
                    }
                ],
            )
        return httpx.Response(200, json={"suggestions": [_suggestion()]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        dadata = DadataClient(
            "test-token",
            secret="test-secret",
            client=client,
        )
        suggestions = await dadata.suggest_address("Санкт-Петербург", count=3)
        reverse = await dadata.reverse(59.94, 30.31, count=1)
        cleaned = await dadata.clean_address("СПб")

    assert suggestions[0].latitude == pytest.approx(59.938955)
    assert reverse[0].longitude == pytest.approx(30.315644)
    assert cleaned is not None
    assert cleaned.name == "г Санкт-Петербург"
    assert len(requests) == 3


def test_parse_coordinates() -> None:
    assert parse_coordinates("59.9386, 30.3141") == pytest.approx(
        (59.9386, 30.3141)
    )
    assert parse_coordinates("59,9386; 30,3141") == pytest.approx(
        (59.9386, 30.3141)
    )
    with pytest.raises(ValueError, match="диапазона"):
        parse_coordinates("95, 30")


@pytest.mark.asyncio
async def test_text_batch_combines_coordinates_and_city() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"suggestions": [_suggestion()]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        dadata = DadataClient("token", client=client)
        result = await resolve_items(
            ["59.9386, 30.3141", "Санкт-Петербург", "59.9386, 30.3141"],
            geocoder=dadata,
            default_timezone="Europe/Moscow",
            max_locations=10,
            automatic=True,
        )

    assert len(result.locations) == 2
    assert any("повтор координат" in warning for warning in result.warnings)
    assert result.locations[1].name == "г Санкт-Петербург"


@pytest.mark.asyncio
async def test_json_file_locations() -> None:
    payload = {
        "locations": [
            {
                "id": "point-one",
                "name": "Точка 1",
                "latitude": 55.75,
                "longitude": 37.62,
                "timezone": "Europe/Moscow",
            }
        ]
    }
    result = await parse_location_bytes(
        "locations.json",
        json.dumps(payload).encode(),
        geocoder=None,
        default_timezone="UTC",
        max_locations=100,
    )
    assert len(result.locations) == 1
    assert result.locations[0].id == "point-one"
    assert result.locations[0].timezone == "Europe/Moscow"


@pytest.mark.asyncio
async def test_city_without_dadata_is_rejected() -> None:
    with pytest.raises(ValueError, match="ни одной координаты"):
        await resolve_items(
            ["Псков"],
            geocoder=None,
            default_timezone="Europe/Moscow",
            max_locations=10,
            automatic=False,
        )
