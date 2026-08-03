from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from weather_to_docx.domain.models import ForecastSeries, Location


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    source_id: str
    name: str
    provider: str
    model: str
    horizon_days: int
    exact_cycle: bool
    implementation_status: str = "ready"
    notes: str | None = None


class ForecastSource(ABC):
    descriptor: SourceDescriptor

    @abstractmethod
    async def fetch(
        self,
        location: Location,
        forecast_days: int,
        options: dict[str, Any] | None = None,
    ) -> ForecastSeries:
        raise NotImplementedError
