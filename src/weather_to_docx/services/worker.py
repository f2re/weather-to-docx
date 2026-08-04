from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import time
import uuid

from weather_to_docx.services.batch import ForecastBatchService
from weather_to_docx.settings import Settings
from weather_to_docx.storage.jobs import JobRepository

LOGGER = logging.getLogger(__name__)


def run_worker(
    settings: Settings,
    *,
    once: bool = False,
    poll_interval: float = 5.0,
) -> int:
    repository = JobRepository(settings.database_path)
    repository.initialise()
    service = ForecastBatchService(settings)
    processed = 0
    worker_id = _worker_id()
    details = {
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "version": "0.3.1",
    }

    LOGGER.info("Worker started: %s", worker_id)
    while True:
        repository.touch_worker(worker_id, details=details)
        job = repository.claim_next(
            worker_id=worker_id,
            lease_seconds=settings.worker_lease_seconds,
        )
        if job is None:
            if once:
                return processed
            time.sleep(max(0.2, poll_interval))
            continue

        if job.attempt_count > settings.worker_max_attempts:
            _safe_fail(
                repository,
                job.id,
                (
                    "Превышено допустимое число попыток выполнения: "
                    f"{settings.worker_max_attempts}"
                ),
                worker_id=worker_id,
            )
            processed += 1
            if once:
                return processed
            continue

        LOGGER.info(
            "Processing job %s, attempt %s",
            job.id,
            job.attempt_count,
        )
        try:
            result = asyncio.run(
                _run_with_heartbeat(
                    repository=repository,
                    service=service,
                    settings=settings,
                    worker_id=worker_id,
                    details=details,
                    job_id=job.id,
                    request=job.request,
                )
            )
            if result is None or repository.is_cancelled(job.id):
                LOGGER.info("Job %s was cancelled", job.id)
            else:
                try:
                    repository.complete(job.id, result, worker_id=worker_id)
                except (RuntimeError, KeyError) as exc:
                    # Другой worker уже мог вернуть просроченное задание в
                    # очередь и получить новую аренду. Старый результат нельзя
                    # записывать поверх более нового выполнения.
                    LOGGER.warning(
                        "Job %s result discarded after lease loss: %s",
                        job.id,
                        exc,
                    )
            processed += 1
        except Exception as exc:
            LOGGER.exception("Job %s failed", job.id)
            _safe_fail(
                repository,
                job.id,
                str(exc),
                worker_id=worker_id,
            )
            processed += 1
        if once:
            return processed


async def _run_with_heartbeat(
    *,
    repository: JobRepository,
    service: ForecastBatchService,
    settings: Settings,
    worker_id: str,
    details: dict,
    job_id: str,
    request,
):
    task = asyncio.create_task(service.generate(request, batch_id=job_id))
    interval = max(1.0, settings.worker_heartbeat_seconds)
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=interval)
            repository.touch_worker(worker_id, details=details)
            if repository.is_cancelled(job_id):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                return None
            if not repository.heartbeat(
                job_id,
                worker_id=worker_id,
                lease_seconds=settings.worker_lease_seconds,
                progress_message="Получение прогнозов и формирование документов",
            ):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                raise RuntimeError(
                    "Worker потерял аренду задания; выполнение остановлено"
                )
            if done:
                break
        return await task
    except asyncio.CancelledError:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        raise


def _safe_fail(
    repository: JobRepository,
    job_id: str,
    error: str,
    *,
    worker_id: str,
) -> None:
    try:
        repository.fail(job_id, error, worker_id=worker_id)
    except (RuntimeError, KeyError) as exc:
        LOGGER.warning(
            "Job %s failure was not persisted after lease loss: %s",
            job_id,
            exc,
        )


def _worker_id() -> str:
    return (
        f"{socket.gethostname()}:{os.getpid()}:"
        f"{uuid.uuid4().hex[:8]}"
    )
