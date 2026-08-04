from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
import yaml

from weather_to_docx import __version__
from weather_to_docx.domain.models import (
    BatchRequest,
    DocumentOptions,
    Location,
    SourceRequest,
)
from weather_to_docx.logging_config import configure_logging
from weather_to_docx.services.batch import ForecastBatchService
from weather_to_docx.services.bundle import ForecastBundle
from weather_to_docx.services.signatures import generate_ed25519_keypair
from weather_to_docx.services.worker import run_worker
from weather_to_docx.settings import Settings, is_loopback_host
from weather_to_docx.sources.registry import SourceRegistry
from weather_to_docx.storage.jobs import JobRepository
from weather_to_docx.storage.locations import LocationRepository

app = typer.Typer(
    name="weather-to-docx",
    help="Формирование DOCX-прогнозов погоды по одной или нескольким координатам.",
    no_args_is_help=True,
)
keys_app = typer.Typer(help="Ключи подписи прогнозных пакетов.")
app.add_typer(keys_app, name="keys")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Показать версию и завершиться.",
        ),
    ] = None,
) -> None:
    """Weather to DOCX."""


def _settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    configure_logging(settings.log_level)
    return settings


def _load_batch_request(path: Path) -> BatchRequest:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise typer.BadParameter("Корень YAML должен быть объектом")
    return BatchRequest.model_validate(payload)


@app.command("init")
def initialise() -> None:
    """Создать каталоги и схему SQLite без сетевых обращений."""
    settings = _settings()
    JobRepository(settings.database_path).initialise()
    LocationRepository(settings.database_path).initialise()
    typer.echo(f"Каталог данных: {settings.data_dir}")
    typer.echo(f"База данных: {settings.database_path}")
    typer.echo("Инициализация завершена.")


@app.command("sources")
def list_sources() -> None:
    """Показать зарегистрированные источники и статус их реализации."""
    settings = _settings()
    descriptors = [asdict(item) for item in SourceRegistry(settings).descriptors()]
    typer.echo(json.dumps(descriptors, ensure_ascii=False, indent=2))


@app.command("generate")
def generate(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            exists=True,
            readable=True,
            help="YAML с координатами и источниками",
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Каталог результатов"),
    ] = None,
) -> None:
    """Сразу получить прогнозы и сформировать отдельный DOCX для каждой координаты."""
    settings = _settings()
    request = _load_batch_request(config)
    result = asyncio.run(
        ForecastBatchService(settings).generate(request, output_root=output)
    )
    typer.echo(result.model_dump_json(indent=2))
    if result.status.value == "failed":
        raise typer.Exit(code=2)


@app.command("enqueue")
def enqueue(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", exists=True, readable=True),
    ],
) -> None:
    """Поставить пакетную генерацию в устойчивую очередь SQLite."""
    settings = _settings()
    repository = JobRepository(settings.database_path)
    record = repository.create(_load_batch_request(config))
    typer.echo(record.model_dump_json(indent=2))


@app.command("worker")
def worker(
    once: Annotated[
        bool,
        typer.Option(
            "--once",
            help="Обработать не более одного задания и завершиться",
        ),
    ] = False,
    poll_interval: Annotated[
        float,
        typer.Option("--poll-interval", min=0.2, max=300),
    ] = 5.0,
) -> None:
    """Запустить обработчик очереди; используется systemd-службой."""
    settings = _settings()
    processed = run_worker(settings, once=once, poll_interval=poll_interval)
    if once:
        typer.echo(f"Обработано заданий: {processed}")


@app.command("api")
def api(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", min=1, max=65535),
    ] = 8080,
) -> None:
    """Запустить HTTP API и Swagger UI."""
    from weather_to_docx.api.app import create_app

    settings = _settings()
    if not is_loopback_host(host) and not settings.allow_insecure_network_api:
        raise typer.BadParameter(
            "Сетевой API без аутентификации запрещён. Используйте "
            "127.0.0.1 и reverse proxy либо явно задайте "
            "WTD_ALLOW_INSECURE_NETWORK_API=true."
        )
    uvicorn.run(
        create_app(settings),
        host=host,
        port=port,
        log_level=settings.log_level.lower(),
    )


@app.command("sample")
def sample(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Каталог примера"),
    ] = Path("var/sample"),
    hours: Annotated[
        int,
        typer.Option("--hours", min=6, max=168),
    ] = 48,
) -> None:
    """Автономно сформировать тестовый DOCX без Интернета."""
    settings = _settings()
    request = BatchRequest(
        locations=[
            Location(
                id="demo-point",
                name="Демонстрационная точка",
                latitude=59.9386,
                longitude=30.3141,
                elevation_m=12,
                timezone="Europe/Moscow",
            )
        ],
        sources=[
            SourceRequest(
                source_id="demo",
                forecast_days=max(1, (hours + 23) // 24),
                options={"hours": hours},
            )
        ],
        document=DocumentOptions(
            title="Демонстрационный метеорологический прогноз"
        ),
        batch_name="demo_forecast",
    )
    result = asyncio.run(
        ForecastBatchService(settings).generate(request, output_root=output)
    )
    typer.echo(result.model_dump_json(indent=2))


@app.command("collect-bundle")
def collect_bundle(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", exists=True, readable=True),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Файл .tar.zst"),
    ],
    private_key: Annotated[
        Path | None,
        typer.Option("--private-key", exists=True, readable=True),
    ] = None,
) -> None:
    """На сетевом шлюзе получить прогнозы и собрать переносимый пакет."""
    settings = _settings()
    request = _load_batch_request(config)
    collected = asyncio.run(ForecastBatchService(settings).collect(request))
    series = [forecast for item in collected for forecast in item.series]
    errors = [
        f"{item.location.name}: {error}"
        for item in collected
        for error in item.errors
    ]
    if not series:
        typer.echo("Не получен ни один прогнозный ряд.", err=True)
        for error in errors:
            typer.echo(error, err=True)
        raise typer.Exit(code=2)
    ForecastBundle.write(
        locations=request.locations,
        series=series,
        output_path=output,
        private_key_path=private_key,
    )
    typer.echo(f"Пакет создан: {output}")
    for error in errors:
        typer.echo(f"Предупреждение: {error}", err=True)


@app.command("generate-bundle")
def generate_bundle(
    bundle: Annotated[
        Path,
        typer.Option("--bundle", "-b", exists=True, readable=True),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o"),
    ] = None,
    public_key: Annotated[
        Path | None,
        typer.Option("--public-key", exists=True, readable=True),
    ] = None,
    require_signature: Annotated[
        bool,
        typer.Option("--require-signature"),
    ] = False,
    page_size: Annotated[
        str,
        typer.Option("--page-size", case_sensitive=False),
    ] = "A3",
) -> None:
    """В закрытом контуре проверить пакет и сформировать DOCX без Интернета."""
    settings = _settings()
    content = ForecastBundle.read(
        bundle,
        public_key_path=public_key or settings.bundle_public_key,
        require_signature=(
            require_signature or settings.require_bundle_signature
        ),
    )
    result = ForecastBatchService(settings).generate_from_series(
        locations=content.locations,
        series=content.series,
        document_options=DocumentOptions(page_size=page_size.upper()),
        output_root=output,
        batch_name=f"bundle_{bundle.stem}",
    )
    typer.echo(result.model_dump_json(indent=2))


@keys_app.command("generate")
def generate_keys(
    private_key: Annotated[
        Path,
        typer.Option("--private-key", help="Закрытый ключ PEM"),
    ] = Path("keys/forecast-bundle-private.pem"),
    public_key: Annotated[
        Path,
        typer.Option("--public-key", help="Открытый ключ PEM"),
    ] = Path("keys/forecast-bundle-public.pem"),
) -> None:
    """Создать пару Ed25519 для подписи переносимых прогнозных пакетов."""
    if private_key.exists() or public_key.exists():
        raise typer.BadParameter(
            "Файл ключа уже существует; автоматическая перезапись запрещена"
        )
    generate_ed25519_keypair(private_key, public_key)
    typer.echo(f"Закрытый ключ: {private_key}")
    typer.echo(f"Открытый ключ: {public_key}")


@app.command("doctor")
def doctor(
    deep: Annotated[
        bool,
        typer.Option("--deep", help="Дополнительно сформировать короткий DOCX"),
    ] = False,
) -> None:
    """Проверить каталоги, очередь, timezone, ecCodes и генератор Word."""
    settings = _settings()
    repository = JobRepository(settings.database_path)
    repository.initialise()
    LocationRepository(settings.database_path).initialise()
    worker_status = repository.worker_status(
        max_age_seconds=settings.worker_online_max_age_seconds
    )
    queue = repository.queue_metrics()
    checks = {
        "python": True,
        "data_dir": settings.data_dir.is_dir(),
        "database": settings.database_path.exists(),
        "documents_writable": _probe_write(settings.documents_dir),
        "zstd": shutil.which("zstd") is not None,
        "timezonefinder": (
            importlib.util.find_spec("timezonefinder") is not None
        ),
        "eccodes_python": importlib.util.find_spec("eccodes") is not None,
        "api_loopback": not settings.api_exposed_without_authentication,
        "worker_online": worker_status["online"],
        "worker_last_seen_utc": worker_status["last_seen_utc"],
        "queue": queue,
    }
    if deep:
        with tempfile.TemporaryDirectory(
            prefix="weather-to-docx-doctor-"
        ) as temporary:
            request = BatchRequest(
                locations=[
                    Location(
                        id="doctor",
                        name="Проверка",
                        latitude=0,
                        longitude=0,
                        timezone="UTC",
                    )
                ],
                sources=[
                    SourceRequest(
                        source_id="demo",
                        forecast_days=1,
                        options={"hours": 6},
                    )
                ],
            )
            result = asyncio.run(
                ForecastBatchService(settings).generate(
                    request,
                    output_root=Path(temporary),
                )
            )
            checks["docx_generation"] = (
                bool(result.artifacts)
                and result.status.value != "failed"
            )
    typer.echo(json.dumps(checks, ensure_ascii=False, indent=2))
    required = [
        "python",
        "data_dir",
        "database",
        "documents_writable",
        "zstd",
        "timezonefinder",
    ]
    if not all(checks[item] for item in required):
        raise typer.Exit(code=2)


def _probe_write(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".doctor-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False
