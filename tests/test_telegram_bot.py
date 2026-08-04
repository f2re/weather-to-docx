from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from telegram import Chat

from weather_to_docx.domain.models import Location, SourceKind
from weather_to_docx.settings import Settings
from weather_to_docx.telegram_queue_bot import TelegramQueueBot


class FakeBot:
    def __init__(self) -> None:
        self.commands = None
        self.menu_button = None

    async def set_my_commands(self, commands) -> None:
        self.commands = commands

    async def set_chat_menu_button(self, *, menu_button) -> None:
        self.menu_button = menu_button


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        telegram_enabled=True,
        telegram_bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        default_source_ids=(
            "open_meteo_gfs,open_meteo_ecmwf_ifs,"
            "open_meteo_gefs_0p25"
        ),
        default_forecast_days=7,
    )


def test_telegram_application_has_minimal_handlers(tmp_path: Path) -> None:
    forecast_bot = TelegramQueueBot(_settings(tmp_path))
    application = forecast_bot.build_application()
    registered = [
        handler
        for handlers in application.handlers.values()
        for handler in handlers
    ]
    assert len(registered) >= 9
    assert application.bot_data["forecast_bot"] is forecast_bot


@pytest.mark.asyncio
async def test_bot_registers_commands_and_command_menu(tmp_path: Path) -> None:
    forecast_bot = TelegramQueueBot(_settings(tmp_path))
    fake_bot = FakeBot()
    await forecast_bot._post_init(SimpleNamespace(bot=fake_bot))

    command_names = [command.command for command in fake_bot.commands]
    assert command_names == ["forecast", "cancel", "sources", "settings", "help"]
    assert fake_bot.menu_button is not None


def test_bot_uses_supported_chat_action_shortcut() -> None:
    assert hasattr(Chat, "send_chat_action")
    source = inspect.getsource(TelegramQueueBot._enqueue_and_send)
    assert ".send_chat_action(" in source
    assert ".send_action(" not in source


def test_bot_request_separates_model_and_ensemble_sources(tmp_path: Path) -> None:
    forecast_bot = TelegramQueueBot(_settings(tmp_path))
    request = forecast_bot._request(
        [
            Location(
                id="p1",
                name="Псков",
                latitude=57.8193,
                longitude=28.3325,
                timezone="Europe/Moscow",
            )
        ]
    )
    descriptors = {
        item.source_id: item for item in forecast_bot.registry.descriptors()
    }
    kinds = [descriptors[item.source_id].source_kind for item in request.sources]
    assert kinds.count(SourceKind.DETERMINISTIC) == 2
    assert kinds.count(SourceKind.ENSEMBLE) == 1
    ensemble_request = next(
        item
        for item in request.sources
        if descriptors[item.source_id].source_kind is SourceKind.ENSEMBLE
    )
    assert ensemble_request.options["precipitation_thresholds_mm"] == [0.1, 1.0, 5.0]
    assert request.document.include_ensemble_section is True
    assert request.document.parameter_profile == "extended"


def test_telegram_uses_shared_job_repository(tmp_path: Path) -> None:
    forecast_bot = TelegramQueueBot(_settings(tmp_path))
    forecast_bot.repository.touch_worker("test-worker", details={"pid": 1})
    request = forecast_bot._request(
        [
            Location(
                id="p1",
                name="Псков",
                latitude=57.8193,
                longitude=28.3325,
                timezone="Europe/Moscow",
            )
        ]
    )
    job = forecast_bot.repository.create(request)
    stored = forecast_bot.repository.get(job.id)
    assert stored.status.value == "queued"
    assert stored.progress_total == 3


def test_telegram_allowlist_parsing(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        telegram_allowed_user_ids="123, 456",
    )
    assert settings.allowed_telegram_users == frozenset({123, 456})
