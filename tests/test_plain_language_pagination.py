from __future__ import annotations

import os
import re
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

from weather_to_docx.document.scientific_generator import ScientificDocumentGenerator
from weather_to_docx.domain.models import DocumentOptions


@pytest.mark.skipif(
    not shutil.which("libreoffice")
    or not shutil.which("pdfinfo")
    or not shutil.which("pdftotext"),
    reason="LibreOffice и poppler нужны для проверки физической пагинации",
)
def test_brief_ensemble_has_no_note_only_page(tmp_path: Path) -> None:
    namespace = runpy.run_path(
        str(Path(__file__).with_name("test_scientific_document.py"))
    )
    location = namespace["_location"]()
    output = tmp_path / "brief-ensemble.docx"
    ScientificDocumentGenerator(tmp_path / "icons").generate(
        location=location,
        series=namespace["_report_series"](location),
        options=DocumentOptions(
            document_mode="brief",
            include_meteograms=False,
            page_size="A4",
            parameter_profile="operational",
        ),
        output_path=output,
    )

    profile = tmp_path / "libreoffice-profile"
    profile.mkdir()
    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path)
    subprocess.run(
        [
            "libreoffice",
            "--headless",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(tmp_path),
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
        env=environment,
    )
    pdf = output.with_suffix(".pdf")
    info = subprocess.run(
        ["pdfinfo", str(pdf)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    match = re.search(r"^Pages:\s+(\d+)$", info, re.MULTILINE)
    assert match is not None
    pages = int(match.group(1))
    assert 2 <= pages <= 3

    full_text = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    assert "Например, 5 % вариантов означает:" not in full_text

    if pages == 3:
        last_page = subprocess.run(
            [
                "pdftotext",
                "-f",
                "3",
                "-l",
                "3",
                "-layout",
                str(pdf),
                "-",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
        # Третья страница допустима только как продолжение полезной таблицы,
        # но не ради отдельного поясняющего абзаца или пустого листа.
        assert "GEFS" in last_page
        assert len(last_page.strip()) >= 120
