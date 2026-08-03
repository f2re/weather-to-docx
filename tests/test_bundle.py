from __future__ import annotations

import asyncio
from pathlib import Path

from weather_to_docx.domain.models import Location
from weather_to_docx.services.bundle import ForecastBundle
from weather_to_docx.services.signatures import generate_ed25519_keypair
from weather_to_docx.sources.demo import DemoSource


def test_signed_bundle_roundtrip(tmp_path: Path) -> None:
    location = Location(id="point", name="Точка", latitude=55, longitude=37, timezone="UTC")
    series = asyncio.run(DemoSource().fetch(location, 1, {"hours": 3}))
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    generate_ed25519_keypair(private_key, public_key)
    bundle = tmp_path / "forecast.tar.zst"
    ForecastBundle.write(
        locations=[location],
        series=[series],
        output_path=bundle,
        private_key_path=private_key,
    )
    content = ForecastBundle.read(bundle, public_key_path=public_key, require_signature=True)
    assert content.signed is True
    assert content.locations[0].id == "point"
    assert content.series[0].source.source_id == "demo"
