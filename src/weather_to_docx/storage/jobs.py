"""Совместимый импорт устойчивой очереди заданий."""

from weather_to_docx.storage.jobs_v2 import JobRepository as _JobRepository


class JobRepository(_JobRepository):
    """Очередь 0.3.1 с совместимостью вызовов версии 0.3.0."""

    def claim_next(
        self,
        *,
        worker_id: str | None = None,
        lease_seconds: int = 30,
    ):
        return super().claim_next(
            worker_id=worker_id or "legacy-worker",
            lease_seconds=lease_seconds,
        )


__all__ = ["JobRepository"]
