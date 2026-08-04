from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import BotCommand, MenuButtonCommands, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from weather_to_docx.domain.models import (
    BatchRequest,
    DocumentOptions,
    Location,
    SourceKind,
    SourceRequest,
)
from weather_to_docx.geocoding.dadata import DadataClient
from weather_to_docx.geocoding.parser import (
    LocationParseResult,
    parse_location_bytes,
    resolve_items,
)
from weather_to_docx.services.batch import ForecastBatchService
from weather_to_docx.settings import Settings
from weather_to_docx.sources.registry import SourceRegistry

LOGGER = logging.getLogger(__name__)
SUPPORTED_DOCUMENTS = {".txt", ".csv", ".json"}


class TelegramForecastBot:
    def __init__(self, settings: Settings) -> None:
        if not settings.telegram_bot_token:
            raise ValueError("Не задан WTD_TELEGRAM_BOT_TOKEN")
        self.settings = settings
        self.registry = SourceRegistry(settings)
        self.service = ForecastBatchService(settings, self.registry)
        self.geocoder = (
            DadataClient(
                settings.dadata_token,
                secret=settings.dadata_secret,
                timeout_seconds=settings.dadata_timeout_seconds,
                user_agent=settings.http_user_agent,
            )
            if settings.dadata_token
            else None
        )
        self.semaphore = asyncio.Semaphore(settings.telegram_concurrency)

    def build_application(self) -> Application:
        application = (
            ApplicationBuilder()
            .token(self.settings.telegram_bot_token)
            .post_init(self._post_init)
            .build()
        )
        application.bot_data["forecast_bot"] = self
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help))
        application.add_handler(CommandHandler("forecast", self.help))
        application.add_handler(CommandHandler("sources", self.sources))
        application.add_handler(CommandHandler("settings", self.show_settings))
        application.add_handler(
            MessageHandler(filters.LOCATION, self.location_message)
        )
        application.add_handler(
            MessageHandler(filters.Document.ALL, self.document_message)
        )
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_message)
        )
        application.add_error_handler(self.error_handler)
        return application

    async def _post_init(self, application: Application) -> None:
        await application.bot.set_my_commands(
            [
                BotCommand("forecast", "Как отправить город, координаты или файл"),
                BotCommand("sources", "Какие модели используются"),
                BotCommand("settings", "Текущие настройки прогноза"),
                BotCommand("help", "Краткая справка"),
            ]
        )
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonCommands()
        )

    async def start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not await self._authorize(update):
            return
        await update.effective_message.reply_text(
            "Пришлите город, адрес, координаты или файл со списком точек.\n\n"
            "Примеры:\n"
            "• Санкт-Петербург\n"
            "• 59.9386, 30.3141\n"
            "• несколько строк с городами и координатами\n"
            "• TXT, CSV или JSON\n\n"
            "Для одной точки вернётся DOCX, для нескольких — ZIP."
        )

    async def help(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        await self.start(update, context)

    async def sources(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not await self._authorize(update):
            return
        descriptors = {
            item.source_id: item for item in self.registry.descriptors()
        }
        lines = []
        for source_id in self.settings.default_sources:
            descriptor = descriptors.get(source_id)
            if descriptor is None:
                lines.append(f"• {source_id}: не зарегистрирован")
                continue
            kind = (
                "ансамбль"
                if descriptor.source_kind == SourceKind.ENSEMBLE
                else "модель"
            )
            lines.append(
                f"• {descriptor.model} — {kind}, до {descriptor.horizon_days} сут."
            )
        await update.effective_message.reply_text(
            "Источники по умолчанию:\n" + "\n".join(lines)
        )

    async def show_settings(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not await self._authorize(update):
            return
        await update.effective_message.reply_text(
            f"Горизонт: {self.settings.default_forecast_days} сут.\n"
            f"Часовой пояс: {self.settings.default_timezone}\n"
            f"DaData: {'настроена' if self.geocoder else 'не настроена'}\n"
            f"Максимум точек в файле: {self.settings.telegram_max_locations}\n"
            "Ансамбли выводятся одной отдельной таблицей в конце документа."
        )

    async def text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not await self._authorize(update):
            return
        text = (update.effective_message.text or "").strip()
        items = [line.strip() for line in text.splitlines() if line.strip()]
        try:
            parsed = await resolve_items(
                items,
                geocoder=self.geocoder,
                default_timezone=self.settings.default_timezone,
                max_locations=self.settings.telegram_max_locations,
                automatic=len(items) > 1,
            )
        except Exception as exc:
            await update.effective_message.reply_text(
                f"Не удалось определить точку: {exc}"
            )
            return
        await self._generate_and_send(update, parsed)

    async def location_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not await self._authorize(update):
            return
        location = update.effective_message.location
        if location is None:
            return
        name = f"Координаты {location.latitude:.5f}, {location.longitude:.5f}"
        if self.geocoder:
            try:
                places = await self.geocoder.reverse(
                    location.latitude,
                    location.longitude,
                    count=1,
                )
                if places:
                    name = places[0].name
            except Exception:
                LOGGER.warning("Reverse geocoding failed", exc_info=True)
        parsed = LocationParseResult(
            locations=[
                Location(
                    id=f"telegram-{update.effective_user.id}-{update.update_id}",
                    name=name,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    timezone=self.settings.default_timezone,
                    group="Telegram",
                )
            ]
        )
        await self._generate_and_send(update, parsed)

    async def document_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not await self._authorize(update):
            return
        document = update.effective_message.document
        if document is None:
            return
        filename = document.file_name or "locations.txt"
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_DOCUMENTS:
            await update.effective_message.reply_text(
                "Поддерживаются только TXT, CSV и JSON."
            )
            return
        if (
            document.file_size
            and document.file_size > self.settings.telegram_max_input_bytes
        ):
            await update.effective_message.reply_text(
                "Файл превышает допустимые 20 МБ."
            )
            return
        try:
            telegram_file = await context.bot.get_file(document.file_id)
            content = bytes(await telegram_file.download_as_bytearray())
            parsed = await parse_location_bytes(
                filename,
                content,
                geocoder=self.geocoder,
                default_timezone=self.settings.default_timezone,
                max_locations=self.settings.telegram_max_locations,
            )
        except Exception as exc:
            await update.effective_message.reply_text(
                f"Файл не обработан: {exc}"
            )
            return
        await self._generate_and_send(update, parsed)

    async def _generate_and_send(
        self,
        update: Update,
        parsed: LocationParseResult,
    ) -> None:
        message = update.effective_message
        status = await message.reply_text(
            f"Точек: {len(parsed.locations)}. Получаю модели и формирую документ…"
        )
        async with self.semaphore:
            try:
                request = self._request(parsed.locations)
                await message.chat.send_action(ChatAction.TYPING)
                result = await self.service.generate(request)
                if result.status.value == "failed":
                    raise RuntimeError("Ни один документ не сформирован")
                artifact = self._result_artifact(
                    result,
                    len(parsed.locations),
                )
                await message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
                if artifact.size_bytes > self.settings.telegram_max_output_bytes:
                    await self._send_documents_separately(message, result)
                else:
                    with Path(artifact.path).open("rb") as stream:
                        await message.reply_document(
                            document=stream,
                            filename=Path(artifact.path).name,
                            caption=self._caption(parsed, result),
                        )
                await status.edit_text("Готово.")
            except Exception as exc:
                LOGGER.exception("Telegram forecast generation failed")
                await status.edit_text(
                    f"Не удалось сформировать прогноз: {exc}"
                )

    def _request(self, locations: list[Location]) -> BatchRequest:
        descriptors = {
            item.source_id: item for item in self.registry.descriptors()
        }
        sources: list[SourceRequest] = []
        for source_id in self.settings.default_sources:
            descriptor = descriptors.get(source_id)
            if descriptor is None:
                continue
            options = (
                {"precipitation_thresholds_mm": [0.1, 1.0, 5.0]}
                if descriptor.source_kind == SourceKind.ENSEMBLE
                else {}
            )
            sources.append(
                SourceRequest(
                    source_id=source_id,
                    forecast_days=min(
                        self.settings.default_forecast_days,
                        descriptor.horizon_days,
                    ),
                    options=options,
                )
            )
        if not sources:
            raise RuntimeError("Не настроен ни один доступный источник")
        return BatchRequest(
            locations=locations,
            sources=sources,
            document=DocumentOptions(
                title="Метеорологический прогноз",
                page_size="A3",
                parameter_profile="extended",
                include_all_parameters=True,
                include_ensemble_section=True,
            ),
            batch_name=f"telegram_{locations[0].id}_{len(locations)}",
        )

    @staticmethod
    def _result_artifact(result, location_count: int):
        preferred = "docx" if location_count == 1 else "zip"
        return next(
            artifact
            for artifact in result.artifacts
            if artifact.kind == preferred
        )

    async def _send_documents_separately(self, message, result) -> None:
        documents = [
            item for item in result.artifacts if item.kind == "docx"
        ]
        if not documents:
            raise RuntimeError(
                "Архив превышает 50 МБ, а отдельных DOCX нет"
            )
        for artifact in documents:
            if artifact.size_bytes > self.settings.telegram_max_output_bytes:
                raise RuntimeError(
                    f"Файл {Path(artifact.path).name} превышает лимит Telegram 50 МБ"
                )
            with Path(artifact.path).open("rb") as stream:
                await message.reply_document(
                    document=stream,
                    filename=Path(artifact.path).name,
                )

    @staticmethod
    def _caption(parsed: LocationParseResult, result) -> str:
        lines = [
            f"Точек: {len(parsed.locations)}",
            (
                "Детерминированные модели — сначала; ансамблевая "
                "неопределённость — отдельной таблицей в конце."
            ),
        ]
        warning_count = len(parsed.warnings) + len(result.errors)
        if warning_count:
            lines.append(
                f"Предупреждений: {warning_count}; подробности находятся в manifest.json."
            )
        return "\n".join(lines)

    async def _authorize(self, update: Update) -> bool:
        user = update.effective_user
        allowed = self.settings.allowed_telegram_users
        if user is None:
            return False
        if allowed and user.id not in allowed:
            await update.effective_message.reply_text(
                "Доступ к боту не разрешён."
            )
            LOGGER.warning("Telegram access denied for user %s", user.id)
            return False
        return True

    async def error_handler(
        self,
        update: object,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        LOGGER.exception("Unhandled Telegram error", exc_info=context.error)


def build_telegram_application(settings: Settings) -> Application:
    return TelegramForecastBot(settings).build_application()


def run_telegram_bot(settings: Settings) -> None:
    build_telegram_application(settings).run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )
