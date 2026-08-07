from __future__ import annotations

from weather_to_docx.telegram_queue_bot import TelegramQueueBot

_ORIGINAL_ENQUEUE_AND_SEND = TelegramQueueBot._enqueue_and_send


async def _show_settings(self, update, context) -> None:
    if not await self._authorize(update):
        return
    worker = self.repository.worker_status(
        max_age_seconds=self.settings.worker_online_max_age_seconds
    )
    await update.effective_message.reply_text(
        f"Горизонт прогноза: {self.settings.default_forecast_days} сут.\n"
        f"Резервный часовой пояс: {self.settings.default_timezone}\n"
        f"Поиск городов: {self.settings.geocoder_provider}\n"
        f"Обработчик заданий: {'работает' if worker['online'] else 'не отвечает'}\n"
        f"Максимум точек в одном задании: {self.settings.telegram_max_locations}\n"
        "Если выбран ансамбль, в документе отдельно показывается разброс "
        "вариантов прогноза."
    )


async def _enqueue_and_send(self, update, context, parsed) -> None:
    worker = self.repository.worker_status(
        max_age_seconds=self.settings.worker_online_max_age_seconds
    )
    if not worker["online"]:
        await update.effective_message.reply_text(
            "Обработчик заданий не отвечает. Прогноз пока не запущен. "
            "Проверьте службу weather-to-docx-worker."
        )
        return
    await _ORIGINAL_ENQUEUE_AND_SEND(self, update, context, parsed)


def _caption(parsed, result) -> str:
    lines = [
        f"Точек: {len(parsed.locations)}",
        "Основные модели приведены в сводке. Для ансамбля отдельно показан "
        "разброс вариантов прогноза.",
    ]
    warning_count = len(parsed.warnings) + len(result.errors)
    if warning_count:
        lines.append(f"Предупреждений: {warning_count}.")
    return "\n".join(lines)


def install_plain_language_messages() -> None:
    TelegramQueueBot.show_settings = _show_settings
    TelegramQueueBot._enqueue_and_send = _enqueue_and_send
    TelegramQueueBot._caption = staticmethod(_caption)


__all__ = ["install_plain_language_messages"]
