from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageStat


@dataclass(frozen=True, slots=True)
class RenderValidation:
    status: str
    page_count: int | None
    checked_pages: int
    blank_pages: tuple[int, ...]
    edge_touch_pages: tuple[int, ...]
    error: str | None = None

    @property
    def passed(self) -> bool:
        return (
            self.status == "passed"
            and not self.blank_pages
            and not self.edge_touch_pages
        )

    def metadata(self) -> dict[str, object]:
        return {
            "visual_check": self.status,
            "rendered_pages": self.page_count,
            "checked_pages": self.checked_pages,
            "blank_pages": list(self.blank_pages),
            "edge_touch_pages": list(self.edge_touch_pages),
            "visual_error": self.error,
        }


def extract_primary_meteogram(docx_path: Path) -> tuple[bytes, str] | None:
    """Вернуть самое крупное встроенное изображение как миниатюру."""

    with ZipFile(docx_path) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if name.startswith("word/media/")
            and name.lower().endswith((".png", ".jpg", ".jpeg"))
        ]
        if not candidates:
            return None
        selected = max(candidates, key=lambda name: archive.getinfo(name).file_size)
        extension = Path(selected).suffix.lower()
        media_type = "image/png" if extension == ".png" else "image/jpeg"
        return archive.read(selected), media_type


def validate_rendered_document(docx_path: Path) -> RenderValidation:
    """Проверить физические страницы через LibreOffice и Poppler.

    Контроль не пытается распознавать текст. Он выявляет пустые страницы и
    содержимое, прижатое к физическому краю листа, что обычно указывает на
    обрезание изображения или ошибочные размеры страницы.
    """

    libreoffice = shutil.which("libreoffice")
    pdftoppm = shutil.which("pdftoppm")
    pdfinfo = shutil.which("pdfinfo")
    if not libreoffice or not pdftoppm or not pdfinfo:
        return RenderValidation(
            status="not-available",
            page_count=None,
            checked_pages=0,
            blank_pages=(),
            edge_touch_pages=(),
            error="LibreOffice или Poppler не установлены",
        )

    with tempfile.TemporaryDirectory(prefix="weather-to-docx-render-") as temporary:
        root = Path(temporary)
        profile = root / "profile"
        profile.mkdir()
        try:
            subprocess.run(
                [
                    libreoffice,
                    "--headless",
                    f"-env:UserInstallation=file://{profile}",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(root),
                    str(docx_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            pdf_path = root / f"{docx_path.stem}.pdf"
            if not pdf_path.is_file():
                raise RuntimeError("LibreOffice не создал PDF")
            info = subprocess.run(
                [pdfinfo, str(pdf_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout
            match = re.search(r"^Pages:\s+(\d+)$", info, re.MULTILINE)
            page_count = int(match.group(1)) if match else None
            prefix = root / "page"
            subprocess.run(
                [pdftoppm, "-png", "-r", "96", str(pdf_path), str(prefix)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            return RenderValidation(
                status="failed",
                page_count=None,
                checked_pages=0,
                blank_pages=(),
                edge_touch_pages=(),
                error=str(exc),
            )

        images = sorted(root.glob("page-*.png"))
        blank_pages: list[int] = []
        edge_pages: list[int] = []
        for number, image_path in enumerate(images, start=1):
            with Image.open(image_path).convert("L") as image:
                histogram = image.histogram()
                dark_pixels = sum(histogram[:245])
                ratio = dark_pixels / max(1, image.width * image.height)
                if ratio < 0.0012:
                    blank_pages.append(number)
                    continue
                inverted = image.point(lambda value: 255 if value < 245 else 0)
                box = inverted.getbbox()
                if box is None:
                    blank_pages.append(number)
                    continue
                left, top, right, bottom = box
                margin_x = max(4, round(image.width * 0.008))
                margin_y = max(4, round(image.height * 0.008))
                if (
                    left <= margin_x
                    or top <= margin_y
                    or right >= image.width - margin_x
                    or bottom >= image.height - margin_y
                ):
                    edge_pages.append(number)
                # Предотвращает ложный успех на странице только с одной точкой.
                if ImageStat.Stat(image).mean[0] > 253.8:
                    blank_pages.append(number)

        status = "passed" if not blank_pages and not edge_pages else "failed"
        return RenderValidation(
            status=status,
            page_count=page_count,
            checked_pages=len(images),
            blank_pages=tuple(sorted(set(blank_pages))),
            edge_touch_pages=tuple(edge_pages),
        )
