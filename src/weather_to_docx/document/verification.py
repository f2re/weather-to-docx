from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile

MIN_METEOGRAM_IMAGE_BYTES = 12_000


@dataclass(frozen=True, slots=True)
class MeteogramDocumentInspection:
    """Результат структурной проверки сформированного DOCX."""

    path: Path
    media_count: int
    large_media_count: int
    has_meteogram_marker: bool
    large_media_names: tuple[str, ...]
    error: str | None = None

    @property
    def ready(self) -> bool:
        return (
            self.error is None
            and self.has_meteogram_marker
            and self.large_media_count >= 1
        )


def inspect_meteogram_docx(
    path: Path,
    *,
    minimum_image_bytes: int = MIN_METEOGRAM_IMAGE_BYTES,
) -> MeteogramDocumentInspection:
    """Проверить, что DOCX действительно содержит встроенную метеограмму.

    Маленькие погодные пиктограммы не считаются графиком. Для подтверждения
    требуется одновременно найти подпись/alt-текст с корнем ``метеограмм`` и
    хотя бы одно достаточно крупное изображение в ``word/media``.
    """

    path = Path(path)
    if minimum_image_bytes < 1:
        raise ValueError("Минимальный размер изображения должен быть положительным")
    if not path.is_file():
        return MeteogramDocumentInspection(
            path=path,
            media_count=0,
            large_media_count=0,
            has_meteogram_marker=False,
            large_media_names=(),
            error="Файл DOCX не найден",
        )

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
            path=path,
            media_count=0,
            large_media_count=0,
            has_meteogram_marker=False,
            large_media_names=(),
            error=f"DOCX не читается: {exc}",
        )

    marker = "метеограмм" in document_xml.casefold()
    return MeteogramDocumentInspection(
        path=path,
        media_count=len(media),
        large_media_count=len(large),
        has_meteogram_marker=marker,
        large_media_names=large,
    )


def require_meteogram_docx(path: Path) -> MeteogramDocumentInspection:
    """Завершить генерацию ошибкой, если график не попал в DOCX."""

    inspection = inspect_meteogram_docx(path)
    if inspection.ready:
        return inspection
    details = inspection.error or (
        f"медиафайлов: {inspection.media_count}, "
        f"крупных изображений: {inspection.large_media_count}, "
        f"метка метеограммы: {'есть' if inspection.has_meteogram_marker else 'нет'}"
    )
    raise RuntimeError(
        "Метеограммы были запрошены, но итоговый DOCX не содержит графика: "
        f"{details}"
    )
