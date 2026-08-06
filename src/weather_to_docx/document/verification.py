from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from weather_to_docx.document.render_validation import validate_rendered_document

MIN_METEOGRAM_IMAGE_BYTES = 12_000
MAX_METEOGRAM_IMAGE_HEIGHT_MM = 145.0
EMU_PER_MM = 36_000


@dataclass(frozen=True, slots=True)
class MeteogramDocumentInspection:
    path: Path
    media_count: int
    large_media_count: int
    has_meteogram_marker: bool
    large_media_names: tuple[str, ...]
    page_break_count: int
    structured_page_count: int
    has_risk_section: bool
    has_russian_weekdays: bool
    oversized_image_count: int = 0
    max_image_height_mm: float | None = None
    visual_check: str = "not-requested"
    rendered_page_count: int | None = None
    blank_pages: tuple[int, ...] = ()
    edge_touch_pages: tuple[int, ...] = ()
    visual_error: str | None = None
    error: str | None = None

    @property
    def ready(self) -> bool:
        return (
            self.error is None
            and self.has_meteogram_marker
            and self.large_media_count >= 1
            and self.oversized_image_count == 0
        )

    def metadata(self) -> dict[str, object]:
        return {
            "structural_check": "passed" if self.error is None else "failed",
            "meteograms": self.large_media_count,
            "media_count": self.media_count,
            "structured_pages": self.structured_page_count,
            "risk_section": self.has_risk_section,
            "russian_weekdays": self.has_russian_weekdays,
            "oversized_meteogram_images": self.oversized_image_count,
            "max_image_height_mm": self.max_image_height_mm,
            "visual_check": self.visual_check,
            "rendered_pages": self.rendered_page_count,
            "blank_pages": list(self.blank_pages),
            "edge_touch_pages": list(self.edge_touch_pages),
            "visual_error": self.visual_error,
            "error": self.error,
        }


def inspect_meteogram_docx(
    path: Path,
    *,
    minimum_image_bytes: int = MIN_METEOGRAM_IMAGE_BYTES,
    render_check: bool = False,
) -> MeteogramDocumentInspection:
    path = Path(path)
    empty = {
        "path": path,
        "media_count": 0,
        "large_media_count": 0,
        "has_meteogram_marker": False,
        "large_media_names": (),
        "page_break_count": 0,
        "structured_page_count": 0,
        "has_risk_section": False,
        "has_russian_weekdays": False,
        "oversized_image_count": 0,
        "max_image_height_mm": None,
    }
    if minimum_image_bytes < 1:
        raise ValueError("Минимальный размер изображения должен быть положительным")
    if not path.is_file():
        return MeteogramDocumentInspection(**empty, error="Файл DOCX не найден")

    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            media = [name for name in names if name.startswith("word/media/")]
            large = tuple(
                name
                for name in media
                if archive.getinfo(name).file_size >= minimum_image_bytes
            )
            try:
                document_xml = archive.read("word/document.xml").decode(
                    "utf-8",
                    errors="replace",
                )
            except KeyError:
                document_xml = ""
    except (BadZipFile, OSError) as exc:
        return MeteogramDocumentInspection(
            **empty,
            error=f"DOCX не читается: {exc}",
        )

    folded = document_xml.casefold()
    page_break_count = document_xml.count('w:type="page"')
    russian_weekdays = any(
        token in folded for token in ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
    )
    image_heights_mm = tuple(
        int(value) / EMU_PER_MM
        for value in re.findall(r'<wp:extent\b[^>]*\bcy="(\d+)"', document_xml)
    )
    oversized = tuple(
        height
        for height in image_heights_mm
        if height > MAX_METEOGRAM_IMAGE_HEIGHT_MM
    )
    render = validate_rendered_document(path) if render_check else None
    return MeteogramDocumentInspection(
        path=path,
        media_count=len(media),
        large_media_count=len(large),
        has_meteogram_marker="метеограмм" in folded,
        large_media_names=large,
        page_break_count=page_break_count,
        structured_page_count=page_break_count + 1,
        has_risk_section="ключевые риски" in folded,
        has_russian_weekdays=russian_weekdays,
        oversized_image_count=len(oversized),
        max_image_height_mm=max(image_heights_mm, default=None),
        visual_check=render.status if render else "not-requested",
        rendered_page_count=render.page_count if render else None,
        blank_pages=render.blank_pages if render else (),
        edge_touch_pages=render.edge_touch_pages if render else (),
        visual_error=render.error if render else None,
    )


def require_meteogram_docx(path: Path) -> MeteogramDocumentInspection:
    inspection = inspect_meteogram_docx(path)
    if inspection.ready:
        return inspection
    details = inspection.error or (
        f"медиафайлов: {inspection.media_count}, "
        f"крупных изображений: {inspection.large_media_count}, "
        f"метка метеограммы: {'есть' if inspection.has_meteogram_marker else 'нет'}, "
        f"изображений выше {MAX_METEOGRAM_IMAGE_HEIGHT_MM:g} мм: "
        f"{inspection.oversized_image_count}"
    )
    raise RuntimeError(
        "Метеограммы были запрошены, но итоговый DOCX не содержит графика "
        "или не прошёл проверку: "
        f"{details}"
    )
