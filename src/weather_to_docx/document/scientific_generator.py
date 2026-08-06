"""Точка импорта профессионального генератора DOCX."""

import math
from datetime import datetime
from pathlib import Path

import numpy as np
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.shared import Mm, Pt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from weather_to_docx.document import audit_generator as _audit_generator
from weather_to_docx.document import compact_generator as _compact_generator
from weather_to_docx.document.consistent_controls import (
    consistent_control_point,
    detail_precipitation_text,
    detail_wind_text,
    shade_daily_hazard,
)
from weather_to_docx.document.consistent_summary import (
    build_consistent_risk_signals,
    build_highlights,
    consistent_daily_model_metrics,
    consistent_daily_presentation_point,
    daily_agreement_from_metrics,
    daily_precipitation_metrics_text,
)
from weather_to_docx.document.impact_labels import (
    daily_precipitation_text,
    daily_pressure_text,
    daily_temperature_text,
    daily_wind_text,
)
from weather_to_docx.document.russian_labels import apply_russian_display_names
from weather_to_docx.document.source_names import source_display_name
from weather_to_docx.domain.models import ForecastSeries
from weather_to_docx.plotting.meteogram import _values
from weather_to_docx.plotting.professional_meteogram import WIND_ARROWS
from weather_to_docx.plotting.semantic_meteogram import (
    SemanticMeteogramRenderer,
)


class DocumentMeteogramRenderer(SemanticMeteogramRenderer):
    """Рендерер для DOCX с самодостаточными и читаемыми подписями."""

    def _new_professional_figure(self, title: str):
        figure, axes = super()._new_professional_figure(title)
        figure.set_size_inches(11.4, 5.55, forward=True)
        figure.subplots_adjust(hspace=0.38)
        return figure, axes

    def _finish_professional(
        self,
        figure: Figure,
        axes: tuple[Axes, ...],
        times: list[datetime],
        *,
        ensemble: bool,
    ) -> None:
        super()._finish_professional(
            figure,
            axes,
            times,
            ensemble=ensemble,
        )
        figure.subplots_adjust(
            left=0.065,
            right=0.93,
            top=0.93,
            bottom=0.12,
            hspace=0.38,
        )

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
    def _complete_title(
        forecast: ForecastSeries,
        title: str | None,
    ) -> str:
        base = title or source_display_name(forecast)
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

    def _plot_precipitation(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
        *,
        ensemble: bool,
    ) -> None:
        super()._plot_precipitation(
            axis,
            x,
            forecast,
            ensemble=ensemble,
        )
        axis.set_yticks((0.5, 2.0, 5.0, 10.0))

    def _add_wind_direction_arrows(
        self,
        axis: Axes,
        x: np.ndarray,
        forecast: ForecastSeries,
    ) -> None:
        direction = _values(forecast, "wind_direction_10m")
        finite = np.flatnonzero(np.isfinite(direction))
        if finite.size == 0:
            return
        step = max(1, math.ceil(finite.size / 28))
        for index in finite[::step]:
            arrow_index = int(
                ((direction[index] % 360) + 22.5) // 45
            ) % 8
            axis.text(
                x[index],
                0.04,
                WIND_ARROWS[arrow_index],
                transform=axis.get_xaxis_transform(),
                ha="center",
                va="bottom",
                fontsize=8.5,
                fontfamily="DejaVu Sans",
                color="#2f5d46",
                fontweight="bold",
            )


def _add_meteogram_image(
    document: Document,
    image_path: Path,
    *,
    description: str,
) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(1)
    paragraph.paragraph_format.line_spacing = Mm(140)
    paragraph.paragraph_format.line_spacing_rule = (
        WD_LINE_SPACING.AT_LEAST
    )
    run = paragraph.add_run()
    shape = run.add_picture(str(image_path), width=Mm(276))
    shape._inline.docPr.set("descr", description)
    shape._inline.docPr.set("title", description)


def _translated_chart_note(
    document: Document,
    text: str,
) -> None:
    replacements = {
        (
            "Серые полосы обозначают ночь. Осадки показаны за исходный "
            "интервал; стрелки внизу показывают направление ветра."
        ): (
            "Серые полосы обозначают ночь. Столбики показывают среднюю "
            "интенсивность осадков за расчётный интервал, мм/ч; подписи "
            "над панелью — сумму за местные сутки. Стрелки внизу "
            "показывают направление ветра."
        ),
        (
            "Тёмная полоса — 25–75-й процентили, светлая — 10–90-й. "
            "Вероятности осадков относятся к указанным порогам и "
            "интервалам."
        ): (
            "Тёмная полоса — 25–75-й процентили, светлая — 10–90-й. "
            "Столбики показывают медианную интенсивность осадков, мм/ч; "
            "линии P ≥ показывают сырую некалиброванную вероятность "
            "превышения суммы за один исходный расчётный интервал, а не "
            "вероятность суточной суммы."
        ),
    }
    _ORIGINAL_ADD_CHART_NOTE(document, replacements.get(text, text))


def _replace_text_in_paragraph(
    paragraph,
    old: str,
    new: str,
) -> bool:
    if old not in paragraph.text:
        return False
    for run in paragraph.runs:
        if old in run.text:
            run.text = run.text.replace(old, new)
            return True
    if paragraph.runs:
        paragraph.runs[0].text = paragraph.text.replace(old, new)
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(paragraph.text.replace(old, new))
    return True


def _precise_ensemble_summary(
    self,
    document: Document,
    ensembles,
    report_dates,
) -> None:
    table_start = len(document.tables)
    paragraph_start = len(document.paragraphs)
    _ORIGINAL_ENSEMBLE_SUMMARY(
        self,
        document,
        ensembles,
        report_dates,
    )

    replacements = {
        "Осадки ≥0,1 мм": "Макс. P интервала ≥0,1 мм",
        "Осадки ≥1 мм": "Макс. P интервала ≥1 мм",
    }
    for table in document.tables[table_start:]:
        for row in table.rows:
            for cell in row.cells:
                for old, new in replacements.items():
                    for paragraph in cell.paragraphs:
                        _replace_text_in_paragraph(
                            paragraph,
                            old,
                            new,
                        )

    old_note = (
        "Диапазон 10–90 % охватывает центральные 80 % вариантов "
        "ансамбля; вероятность осадков — максимальная доля членов за "
        "сутки."
    )
    new_note = (
        "Диапазон 10–90 % охватывает центральные 80 % вариантов "
        "ансамбля. В таблице показан максимум за сутки среди сырых "
        "некалиброванных вероятностей превышения суммы за один исходный "
        "расчётный интервал; это не вероятность суточной суммы."
    )
    for paragraph in document.paragraphs[paragraph_start:]:
        _replace_text_in_paragraph(paragraph, old_note, new_note)


def _precise_risk_cards(
    self,
    document: Document,
    risks,
) -> None:
    paragraph_start = len(document.paragraphs)
    _ORIGINAL_RISK_CARDS(self, document, risks)
    if risks and all(signal.model_count == 1 for signal in risks):
        for paragraph in document.paragraphs[paragraph_start:]:
            if _replace_text_in_paragraph(
                paragraph,
                "Ключевые риски",
                "Потенциальные риски по одной модели",
            ):
                break


apply_russian_display_names()

_compact_generator._short_model_name = source_display_name
_compact_generator._daily_model_metrics = consistent_daily_model_metrics
_compact_generator._daily_presentation_point = (
    consistent_daily_presentation_point
)
_compact_generator._daily_temperature_text = daily_temperature_text
_compact_generator._daily_precipitation_text = (
    daily_precipitation_metrics_text
)
_compact_generator._daily_wind_text = daily_wind_text
_compact_generator._daily_pressure_text = daily_pressure_text
_compact_generator._daily_agreement = daily_agreement_from_metrics
_compact_generator._build_highlights = build_highlights
_compact_generator._consensus_point = consistent_control_point
_compact_generator._detail_precipitation_text = detail_precipitation_text
_compact_generator._detail_wind_text = detail_wind_text
_compact_generator._shade_daily_hazard = shade_daily_hazard

_audit_generator._short_model_name = source_display_name
_audit_generator.ProfessionalMeteogramRenderer = (
    DocumentMeteogramRenderer
)
_audit_generator.build_risk_signals = build_consistent_risk_signals
_audit_generator._daily_model_metrics = consistent_daily_model_metrics
_audit_generator._daily_presentation_point = (
    consistent_daily_presentation_point
)
_audit_generator._daily_temperature_text = daily_temperature_text
_audit_generator._daily_wind_text = daily_wind_text
_audit_generator._daily_pressure_text = daily_pressure_text
_audit_generator._daily_precipitation_text_professional = (
    daily_precipitation_text
)
_audit_generator._shade_daily_hazard = shade_daily_hazard

_ORIGINAL_ADD_CHART_NOTE = (
    _audit_generator.ScientificDocumentGenerator._add_chart_note
)
_audit_generator.ScientificDocumentGenerator._add_chart_note = staticmethod(
    _translated_chart_note
)
_audit_generator.ScientificDocumentGenerator._add_meteogram_image = (
    staticmethod(_add_meteogram_image)
)

_ORIGINAL_ENSEMBLE_SUMMARY = (
    _compact_generator.ScientificDocumentGenerator._add_ensemble_summary
)
_compact_generator.ScientificDocumentGenerator._add_ensemble_summary = (
    _precise_ensemble_summary
)

_ORIGINAL_RISK_CARDS = (
    _audit_generator.ScientificDocumentGenerator._add_risk_cards
)
_audit_generator.ScientificDocumentGenerator._add_risk_cards = (
    _precise_risk_cards
)

ScientificDocumentGenerator = (
    _audit_generator.ScientificDocumentGenerator
)

__all__ = ["ScientificDocumentGenerator"]
