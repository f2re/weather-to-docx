from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_api_unit_remains_compatible_with_02_cli() -> None:
    unit = (
        ROOT / "packaging/systemd/weather-to-docx-api.service"
    ).read_text(encoding="utf-8")
    assert "weather-to-docx api" in unit
    assert "${WTD_API_HOST}" in unit
    assert "${WTD_API_PORT}" in unit
    assert "weather-to-docx-api\n" not in unit


def test_rollback_disables_telegram_for_legacy_release() -> None:
    script = (ROOT / "scripts/rollback.sh").read_text(encoding="utf-8")
    assert 'telegram_command="$CURRENT/venv/bin/weather-to-docx-telegram"' in script
    assert '-x "$telegram_command"' in script
    assert "старый релиз не содержит Telegram-бот" in script


def test_offline_builder_has_zero_exit_without_signature() -> None:
    script = (
        ROOT / "scripts/build-offline-bundle.sh"
    ).read_text(encoding="utf-8")
    assert 'if [[ -f "$ARCHIVE.asc" ]]; then' in script
    assert '[[ -f "$ARCHIVE.asc" ]] &&' not in script
