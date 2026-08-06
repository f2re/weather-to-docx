from __future__ import annotations

from datetime import date

from weather_to_docx.analysis.consensus import RiskSignal
from weather_to_docx.document.consistent_summary import (
    build_consistent_risk_signals as _build_consistent_risk_signals,
)
from weather_to_docx.domain.models import ForecastSeries


def build_consistent_risk_signals(
    forecasts: list[ForecastSeries],
    ensembles: list[ForecastSeries],
    report_dates: list[date],
    *,
    maximum: int = 3,
) -> list[RiskSignal]:
    """Вернуть только риски, подтверждённые минимум двумя независимыми моделями."""

    if len(forecasts) < 2:
        return []
    return _build_consistent_risk_signals(
        forecasts,
        ensembles,
        report_dates,
        maximum=maximum,
    )


__all__ = ["build_consistent_risk_signals"]
