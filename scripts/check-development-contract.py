#!/usr/bin/env python3
"""Проверить наличие и связность обязательных контрактов разработки."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "docs/DEVELOPMENT_CONTRACT.md",
    "docs/DEVELOPMENT.md",
    ".github/copilot-instructions.md",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/development-task.yml",
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
    ".github/ISSUE_TEMPLATE/development-task.yml": (
        "description: Контрактная постановка задачи",
        "SHA актуальной main",
        "Текущая версия из pyproject.toml",
        "Решение по версии",
        "Критерии приёмки",
        "Исправленный дефект получит регрессионный тест",
        "повторной проверки main",
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

ISSUE_FORM_PATH = ".github/ISSUE_TEMPLATE/development-task.yml"
REQUIRED_ISSUE_FORM_IDS = {
    "main_sha",
    "current_version",
    "version_decision",
    "problem",
    "acceptance",
    "tests",
    "compatibility",
    "contract",
}


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def validate_issue_form(errors: list[str]) -> None:
    path = ROOT / ISSUE_FORM_PATH
    if not path.is_file():
        return
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        errors.append(f"{ISSUE_FORM_PATH}: некорректный YAML: {exc}")
        return

    if not isinstance(document, dict):
        errors.append(f"{ISSUE_FORM_PATH}: корнем должен быть объект")
        return
    if "about" in document:
        errors.append(
            f"{ISSUE_FORM_PATH}: issue forms используют description, а не about"
        )
    for key in ("name", "description", "title", "body"):
        if key not in document:
            errors.append(f"{ISSUE_FORM_PATH}: отсутствует обязательное поле {key}")

    body = document.get("body")
    if not isinstance(body, list):
        errors.append(f"{ISSUE_FORM_PATH}: body должен быть списком")
        return
    ids = {
        item.get("id")
        for item in body
        if isinstance(item, dict) and item.get("id") is not None
    }
    missing = REQUIRED_ISSUE_FORM_IDS - ids
    if missing:
        errors.append(
            f"{ISSUE_FORM_PATH}: отсутствуют обязательные id: {sorted(missing)}"
        )

    for item in body:
        if not isinstance(item, dict) or item.get("type") == "markdown":
            continue
        item_id = item.get("id", "<без id>")
        if item.get("type") == "checkboxes":
            options = item.get("attributes", {}).get("options", [])
            if not options or any(
                not isinstance(option, dict) or option.get("required") is not True
                for option in options
            ):
                errors.append(
                    f"{ISSUE_FORM_PATH}: все checkbox-условия {item_id} должны быть required"
                )
        elif item.get("validations", {}).get("required") is not True:
            errors.append(
                f"{ISSUE_FORM_PATH}: поле {item_id} должно быть обязательным"
            )


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

    validate_issue_form(errors)

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
