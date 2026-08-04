from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from weather_to_docx.cli import app
from weather_to_docx.settings import Settings, is_loopback_host


def test_loopback_hosts_are_recognised() -> None:
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("127.12.1.8")
    assert is_loopback_host("::1")
    assert is_loopback_host("[::1]")
    assert is_loopback_host("localhost")
    assert not is_loopback_host("0.0.0.0")
    assert not is_loopback_host("192.168.1.10")


def test_network_api_requires_explicit_dangerous_override(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="Сетевой HTTP API"):
        Settings(data_dir=tmp_path, api_host="0.0.0.0")

    settings = Settings(
        data_dir=tmp_path,
        api_host="0.0.0.0",
        allow_insecure_network_api=True,
    )
    assert settings.api_exposed_without_authentication is True


def test_default_api_remains_loopback(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    assert settings.api_host == "127.0.0.1"
    assert settings.api_exposed_without_authentication is False


def test_cli_rejects_non_loopback_without_override(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["api", "--host", "0.0.0.0", "--port", "18080"],
        env={
            "WTD_DATA_DIR": str(tmp_path / "data"),
            "WTD_API_HOST": "127.0.0.1",
            "WTD_ALLOW_INSECURE_NETWORK_API": "false",
        },
    )
    assert result.exit_code != 0
    assert "Сетевой API без аутентификации запрещён" in result.output
