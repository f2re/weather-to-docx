#!/usr/bin/env python3
"""Проверить согласованность текущей версии во всех активных источниках."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    pyproject = tomllib.loads(read("pyproject.toml"))
    version = str(pyproject["project"]["version"]).strip()
    tag = f"v{version}"
    release_document = f"docs/RELEASE_{version}.md"
    errors: list[str] = []

    def require_exact(path: str, expected: str) -> None:
        actual = read(path).strip()
        if actual != expected:
            errors.append(f"{path}: ожидалось {expected!r}, получено {actual!r}")

    def require_text(path: str, expected: str) -> None:
        if expected not in read(path):
            errors.append(f"{path}: отсутствует {expected!r}")

    require_exact("VERSION", version)
    require_exact("docs/.release-ready", tag)
    require_exact("docs/RELEASE_TAG.txt", tag)

    init_text = read("src/weather_to_docx/__init__.py")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_text, re.MULTILINE)
    if match is None:
        errors.append("src/weather_to_docx/__init__.py: не найден __version__")
    elif match.group(1) != version:
        errors.append(
            "src/weather_to_docx/__init__.py: "
            f"__version__={match.group(1)!r}, ожидалось {version!r}"
        )

    user_agent = f"weather-to-docx/{version} (+https://github.com/f2re/weather-to-docx)"
    for path in (
        ".env.example",
        "packaging/weather-to-docx.env",
        "src/weather_to_docx/settings.py",
    ):
        require_text(path, user_agent)

    require_text("README.md", f"Текущая версия: **{version}**.")
    require_text("README.md", f"## Смысловые шкалы {version}")
    require_text("CHANGELOG.md", f"## {version} —")
    require_text("docs/METEOGRAMS.md", f"Версия {version}")
    require_text("docs/ACCEPTANCE.md", f"Weather to DOCX {version}")
    require_text("docs/REMEDIATION_PLAN.md", f"Текущая версия {version}")
    require_text("docs/RELEASE_STATUS.md", f"Текущая версия исходного кода: **{version}**.")
    require_text("docs/RELEASE_NOTES.md", f"Текущий выпуск: Weather to DOCX {version}")
    require_text("docs/RELEASE_NOTES.md", f"RELEASE_{version}.md")

    release_path = ROOT / release_document
    if not release_path.is_file():
        errors.append(f"{release_document}: отсутствует документ текущего выпуска")
    else:
        require_text(release_document, f"Weather to DOCX {version}")

    models_text = read("src/weather_to_docx/domain/models.py")
    if "adapter_version: str = __version__" not in models_text:
        errors.append(
            "src/weather_to_docx/domain/models.py: adapter_version должен "
            "получаться из weather_to_docx.__version__"
        )

    if errors:
        print(f"Обнаружены расхождения версии {version}:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Версия {version} согласована во всех активных источниках.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
