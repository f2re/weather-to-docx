"""Точка импорта профессионального генератора DOCX."""

from weather_to_docx.document.audit_generator import ScientificDocumentGenerator
from weather_to_docx.document.russian_labels import apply_russian_display_names

apply_russian_display_names()

__all__ = ["ScientificDocumentGenerator"]
