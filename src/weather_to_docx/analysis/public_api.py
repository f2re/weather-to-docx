from __future__ import annotations

from datetime import date

from weather_to_docx.analysis.consensus import RiskSignal
from weather_to_docx.domain.models import ForecastSeries


def build_risk_signals(
    forecasts: list[ForecastSeries],
    ensembles: list[ForecastSeries],
    report_dates: list[date],
    *,
    maximum: int = 3,
) -> list[RiskSignal]:
    """Use the same operational risk policy as the DOCX generator."""

    # Lazy import avoids a package-initialisation cycle while keeping the
    # public analysis API aligned with the document pipeline.
    from weather_to_docx.document.consistent_summary import (
        build_consistent_risk_signals,
    )

    return build_consistent_risk_signals(
        forecasts,
        ensembles,
        report_dates,
        maximum=maximum,
    )


__all__ = ["build_risk_signals"]
