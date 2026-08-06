from weather_to_docx.document.generator import DocumentGenerator


def __getattr__(name: str):
    if name == "ScientificDocumentGenerator":
        from weather_to_docx.document.scientific_generator import (
            ScientificDocumentGenerator,
        )

        return ScientificDocumentGenerator
    raise AttributeError(name)


__all__ = [
    "DocumentGenerator",
    "ScientificDocumentGenerator",
]
