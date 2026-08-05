from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from weather_to_docx import __version__
from weather_to_docx.domain.models import SourceMetadata

ROOT = Path(__file__).resolve().parents[1]


def test_all_active_version_sources_are_consistent() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check-version.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert f"Версия {__version__} согласована" in result.stdout


def test_source_metadata_uses_package_version() -> None:
    metadata = SourceMetadata(
        source_id="test",
        provider="test",
        model="test",
        product="test",
        retrieved_at_utc=datetime.now(UTC),
    )
    assert metadata.adapter_version == __version__
