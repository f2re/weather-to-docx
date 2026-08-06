from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_launch_script_has_a_valid_help_interface() -> None:
    result = subprocess.run(
        ["bash", "scripts/run-local.sh", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "--no-worker" in result.stdout


def test_service_installer_has_a_valid_help_interface() -> None:
    result = subprocess.run(
        ["bash", "scripts/install-service.sh", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "weather-to-docx-local-api" in result.stdout


def test_checkout_service_units_are_parameterised_and_hardened() -> None:
    for name in ("weather-to-docx-local-api.service.in", "weather-to-docx-local-worker.service.in"):
        unit = (ROOT / "packaging/systemd" / name).read_text(encoding="utf-8")
        assert "User=@SERVICE_USER@" in unit
        assert "Environment=WTD_DATA_DIR=@DATA_DIR@" in unit
        assert "NoNewPrivileges=true" in unit
        assert "ReadWritePaths=@DATA_DIR@" in unit
