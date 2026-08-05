"""Точка импорта профессионального генератора DOCX."""

from weather_to_docx.document import audit_generator as _audit_generator
from weather_to_docx.document.impact_labels import (
    daily_precipitation_text,
    daily_pressure_text,
    daily_temperature_text,
    daily_wind_text,
)
from weather_to_docx.document.russian_labels import apply_russian_display_names
from weather_to_docx.plotting.semantic_meteogram import SemanticMeteogramRenderer

apply_russian_display_names()
_audit_generator.ProfessionalMeteogramRenderer = SemanticMeteogramRenderer
_audit_generator._daily_temperature_text = daily_temperature_text
_audit_generator._daily_wind_text = daily_wind_text
_audit_generator._daily_pressure_text = daily_pressure_text
_audit_generator._daily_precipitation_text_professional = daily_precipitation_text

ScientificDocumentGenerator = _audit_generator.ScientificDocumentGenerator

__all__ = ["ScientificDocumentGenerator"]
