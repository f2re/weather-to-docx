#!/usr/bin/env python3
"""Проверить наличие и связность обязательных контрактов разработки."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "docs/DEVELOPMENT_CONTRACT.md",
    "docs/DEVELOPMENT.md",
    ".github/copilot-instructions.md",
    ".github/pull_request_template.md",
    "scripts/check-version.py",
    "scripts/check-development-contract.py",
    "tests/test_development_contract.py",
)

REQUIRED_MARKERS: dict[str, tuple[str, ...]] = {
    "AGENTS.md": (
        "актуальную `main`",
        "Каноническая текущая версия задаётся в `pyproject.toml`",
        "не является реальным Git-тегом",
        "python scripts/check-version.py",
        "python scripts/check-development-contract.py",
        "PR остаётся черновиком",
        "После слияния повторно получить `main`",
    ),
    "CLAUDE.md": (
        "AGENTS.md",
        "docs/DEVELOPMENT_CONTRACT.md",
        "актуальной `main`",
        "python scripts/check-development-contract.py",
        "после слияния повторно проверить `main`",
    ),
    "GEMINI.md": (
        "AGENTS.md",
        "docs/DEVELOPMENT_CONTRACT.md",
        "актуальную `main`",
        "python scripts/check-development-contract.py",
        "после слияния повторно проверить `main`",
    ),
    "docs/DEVELOPMENT_CONTRACT.md": (
        "## 1. Источники истины",
        "## 2. Протокол начала работы",
        "## 3. Контракт версионирования",
        "## 4. Контракт веток и PR",
        "## 6. Контракт доказательств и отчётности",
        "## 8. Стоп-условия для агента",
        "## 9. Definition of Done",
        "реальный Git-тег",
        "python scripts/check-version.py",
        "python scripts/check-development-contract.py",
    ),
    ".github/copilot-instructions.md": (
        "/AGENTS.md",
        "/docs/DEVELOPMENT_CONTRACT.md",
        "актуальной `main`",
        "python scripts/check-version.py",
        "python scripts/check-development-contract.py",
        "После слияния повторно прочитайте `main`",
    ),
    ".github/pull_request_template.md": (
        "SHA `main` перед началом работы",
        "Версия в базовой `main`",
        "python scripts/check-version.py",
        "python scripts/check-development-contract.py",
        "Все обязательные jobs имеют статус `success`",
        "повторно проверена актуальная `main`",
    ),
    "docs/DEVELOPMENT.md": (
        "docs/DEVELOPMENT_CONTRACT.md",
        "AGENTS.md",
        "make agent-check",
    ),
    ".github/workflows/ci.yml": (
        "python scripts/check-version.py",
        "python scripts/check-development-contract.py",
    ),
    "Makefile": (
        "version-contract:",
        "development-contract:",
        "agent-check:",
        "python scripts/check-version.py",
        "python scripts/check-development-contract.py",
    ),
}


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []

    for path in REQUIRED_FILES:
        if not (ROOT / path).is_file():
            errors.append(f"Отсутствует обязательный файл: {path}")

    for path, markers in REQUIRED_MARKERS.items():
        file_path = ROOT / path
        if not file_path.is_file():
            errors.append(f"Нельзя проверить отсутствующий файл: {path}")
            continue
        content = read(path)
        for marker in markers:
            if marker not in content:
                errors.append(f"{path}: отсутствует обязательный маркер {marker!r}")

    agents = ROOT / "AGENTS.md"
    contract = ROOT / "docs/DEVELOPMENT_CONTRACT.md"
    if agents.is_file() and contract.is_file():
        if agents.stat().st_size < 1500:
            errors.append("AGENTS.md слишком краток для обязательного контракта")
        if contract.stat().st_size < 5000:
            errors.append("docs/DEVELOPMENT_CONTRACT.md слишком краток")

    if errors:
        print("Нарушен контракт разработки:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Контракты разработки и агентов присутствуют и связаны с CI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
