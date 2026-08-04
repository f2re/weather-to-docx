from __future__ import annotations

import uvicorn

from weather_to_docx.api.app import create_app
from weather_to_docx.logging_config import configure_logging
from weather_to_docx.settings import Settings


def main() -> None:
    settings = Settings()
    settings.ensure_directories()
    configure_logging(settings.log_level)
    uvicorn.run(
        create_app(settings),
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
