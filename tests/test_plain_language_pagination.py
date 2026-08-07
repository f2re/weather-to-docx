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
    not shutil.which("libreoffice") or not shutil.which("pdfinfo"),
    reason="LibreOffice и pdfinfo нужны для проверки физической пагинации",
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
    info = subprocess.run(
        ["pdfinfo", str(output.with_suffix(".pdf"))],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    match = re.search(r"^Pages:\s+(\d+)$", info, re.MULTILINE)
    assert match is not None
    assert int(match.group(1)) == 2
