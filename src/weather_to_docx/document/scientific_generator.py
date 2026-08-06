"""Точка импорта профессионального генератора DOCX."""

from pathlib import Path

from docx import Document

from weather_to_docx.document import audit_generator as _audit_generator
from weather_to_docx.document.impact_labels import (
    daily_precipitation_text,
    daily_pressure_text,
    daily_temperature_text,
    daily_wind_text,
)
from weather_to_docx.document.russian_labels import apply_russian_display_names
from weather_to_docx.domain.models import ForecastSeries
from weather_to_docx.plotting.semantic_meteogram import SemanticMeteogramRenderer


class DocumentMeteogramRenderer(SemanticMeteogramRenderer):
    """Рендерер с самодостаточным заголовком изображения."""

    def render_deterministic(
        self,
        forecast: ForecastSeries,
        output_path: Path,
        *,
        title: str | None = None,
    ) -> Path:
        return super().render_deterministic(
            forecast,
            output_path,
            title=self._complete_title(forecast, title),
        )

    def render_ensemble(
        self,
        forecast: ForecastSeries,
        output_path: Path,
        *,
        title: str | None = None,
    ) -> Path:
        return super().render_ensemble(
            forecast,
            output_path,
            title=self._complete_title(forecast, title),
        )

    @staticmethod
    def _complete_title(forecast: ForecastSeries, title: str | None) -> str:
        base = title or forecast.source.model
        if not forecast.points:
            return f"{forecast.location.name} · {base}"
        start = forecast.points[0].valid_time_local
        end = forecast.points[-1].valid_time_local
        period = (
            f"{start:%d.%m.%Y}"
            if start.date() == end.date()
            else f"{start:%d.%m}–{end:%d.%m.%Y}"
        )
        return f"{forecast.location.name} · {base} · {period}"


apply_russian_display_names()
_audit_generator.ProfessionalMeteogramRenderer = DocumentMeteogramRenderer
_audit_generator._daily_temperature_text = daily_temperature_text
_audit_generator._daily_wind_text = daily_wind_text
_audit_generator._daily_pressure_text = daily_pressure_text
_audit_generator._daily_precipitation_text_professional = daily_precipitation_text


class ScientificDocumentGenerator(_audit_generator.ScientificDocumentGenerator):
    """Генератор с согласованными пояснениями к метеограммам."""

    @staticmethod
    def _add_chart_note(document: Document, text: str) -> None:
        replacements = {
            (
                "Серые полосы обозначают ночь. Осадки показаны за исходный интервал; "
                "стрелки внизу показывают направление ветра."
            ): (
                "Серые полосы обозначают ночь. Столбики показывают среднюю "
                "интенсивность осадков за расчётный интервал, мм/ч; подписи над "
                "панелью — сумму за местные сутки. Стрелки внизу показывают "
                "направление ветра."
            ),
            (
                "Тёмная полоса — 25–75-й процентили, светлая — 10–90-й. "
                "Вероятности осадков относятся к указанным порогам и интервалам."
            ): (
                "Тёмная полоса — 25–75-й процентили, светлая — 10–90-й. "
                "Столбики показывают медианную интенсивность осадков, мм/ч; "
                "линии P ≥ показывают вероятность превышения суммы за исходный "
                "расчётный интервал."
            ),
        }
        _audit_generator.ScientificDocumentGenerator._add_chart_note(
            document,
            replacements.get(text, text),
        )


__all__ = ["ScientificDocumentGenerator"]
