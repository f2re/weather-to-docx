from __future__ import annotations

from weather_to_docx.logging_config import configure_logging
from weather_to_docx.settings import Settings
from weather_to_docx.telegram_bot import run_telegram_bot


def main() -> None:
    settings = Settings()
    settings.ensure_directories()
    configure_logging(settings.log_level)
    run_telegram_bot(settings)


if __name__ == "__main__":
    main()
