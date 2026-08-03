from __future__ import annotations

import asyncio
import logging
import time

from weather_to_docx.services.batch import ForecastBatchService
from weather_to_docx.settings import Settings
from weather_to_docx.storage.jobs import JobRepository

LOGGER = logging.getLogger(__name__)


def run_worker(settings: Settings, *, once: bool = False, poll_interval: float = 5.0) -> int:
    repository = JobRepository(settings.database_path)
    repository.initialise()
    service = ForecastBatchService(settings)
    processed = 0

    while True:
        job = repository.claim_next()
        if job is None:
            if once:
                return processed
            time.sleep(max(0.2, poll_interval))
            continue

        LOGGER.info("Processing job %s", job.id)
        try:
            if repository.is_cancelled(job.id):
                continue
            result = asyncio.run(service.generate(job.request, batch_id=job.id))
            if repository.is_cancelled(job.id):
                LOGGER.info("Job %s was cancelled during processing", job.id)
            else:
                repository.complete(job.id, result)
            processed += 1
        except Exception as exc:
            LOGGER.exception("Job %s failed", job.id)
            repository.fail(job.id, str(exc))
            processed += 1
        if once:
            return processed
