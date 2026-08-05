"""Совместимая точка импорта русифицированного генератора DOCX."""

from weather_to_docx.document import meteogram_document as _meteogram_document
from weather_to_docx.document.localized_meteogram_document import (
    ScientificDocumentGenerator,
)
from weather_to_docx.document.russian_labels import apply_russian_display_names
from weather_to_docx.plotting.russian_meteogram import RussianMeteogramRenderer

apply_russian_display_names()
_meteogram_document.MeteogramRenderer = RussianMeteogramRenderer

__all__ = ["ScientificDocumentGenerator"]
