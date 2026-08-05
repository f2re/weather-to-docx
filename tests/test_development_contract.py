from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_development_contract_checker_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check-development-contract.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "Контракты разработки" in result.stdout


def test_agents_contract_is_not_placeholder() -> None:
    content = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Каноническая текущая версия задаётся в `pyproject.toml`" in content
    assert "не является реальным Git-тегом" in content
    assert "После слияния повторно получить `main`" in content
    assert "PR остаётся черновиком" in content
