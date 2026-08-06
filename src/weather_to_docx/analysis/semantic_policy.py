from __future__ import annotations

from dataclasses import dataclass


def strict_majority(model_count: int) -> int:
    """Return the smallest integer strictly greater than half of the sample."""

    if model_count < 1:
        raise ValueError("Число моделей должно быть положительным")
    return 1 if model_count == 1 else model_count // 2 + 1


@dataclass(frozen=True, slots=True)
class SupportAssessment:
    scenario: str
    confidence: str


def support_assessment(
    support_count: int,
    model_count: int,
) -> SupportAssessment:
    """Describe support without inventing inter-model confidence for one model."""

    if model_count < 1:
        raise ValueError("Число моделей должно быть положительным")
    if not 0 <= support_count <= model_count:
        raise ValueError("Число подтверждающих моделей вне допустимого диапазона")
    if model_count == 1:
        return SupportAssessment(
            scenario="Сценарий одной модели",
            confidence="не оценивается",
        )

    ratio = support_count / model_count
    if support_count >= strict_majority(model_count) and ratio >= 0.67:
        return SupportAssessment(
            scenario="Устойчивый сигнал",
            confidence="высокая",
        )
    if support_count >= strict_majority(model_count):
        return SupportAssessment(
            scenario="Вероятный сигнал",
            confidence="средняя",
        )
    return SupportAssessment(
        scenario="Отдельный сценарий",
        confidence="низкая",
    )


__all__ = [
    "SupportAssessment",
    "strict_majority",
    "support_assessment",
]
