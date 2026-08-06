"""Оперативный анализ рисков, согласованности и качества прогноза."""

from weather_to_docx.analysis.consensus import (
    DailyAgreement,
    RiskSignal,
    daily_agreement,
    daily_precipitation_total,
)
from weather_to_docx.analysis.public_api import build_risk_signals
from weather_to_docx.analysis.semantic_policy import (
    SupportAssessment,
    strict_majority,
    support_assessment,
)

__all__ = [
    "DailyAgreement",
    "RiskSignal",
    "SupportAssessment",
    "build_risk_signals",
    "daily_agreement",
    "daily_precipitation_total",
    "strict_majority",
    "support_assessment",
]
