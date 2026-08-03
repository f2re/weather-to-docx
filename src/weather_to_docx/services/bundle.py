from __future__ import annotations

import inspect
import json
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from weather_to_docx.domain.models import ForecastSeries, Location
from weather_to_docx.services.signatures import sign_bytes, verify_bytes
from weather_to_docx.utils.files import ensure_within, safe_filename, sha256_file


@dataclass(slots=True)
class BundleContent:
    locations: list[Location]
    series: list[ForecastSeries]
    manifest: dict[str, Any]
    signed: bool


class ForecastBundle:
    schema_version = 1

    @classmethod
    def write(
        cls,
        *,
        locations: list[Location],
        series: list[ForecastSeries],
        output_path: Path,
        private_key_path: Path | None = None,
    ) -> Path:
        if not series:
            raise ValueError("Нельзя создать пакет без прогностических рядов")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cls._require_zstd()

        with tempfile.TemporaryDirectory(prefix="weather-bundle-") as temporary_directory:
            root = Path(temporary_directory) / "bundle"
            data_dir = root / "data"
            data_dir.mkdir(parents=True)
            locations_path = root / "locations.json"
            locations_path.write_text(
                json.dumps([location.model_dump(mode="json") for location in locations], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            entries: list[dict[str, Any]] = []
            for index, forecast in enumerate(series):
                location_name = safe_filename(forecast.location.id)
                source_name = safe_filename(forecast.source.source_id)
                relative_path = Path("data") / location_name / f"{index:03d}-{source_name}.json"
                target = root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(forecast.model_dump_json(indent=2), encoding="utf-8")
                entries.append(
                    {
                        "location_id": forecast.location.id,
                        "source_id": forecast.source.source_id,
                        "path": relative_path.as_posix(),
                        "sha256": sha256_file(target),
                        "size_bytes": target.stat().st_size,
                        "cycle_time_utc": (
                            forecast.source.cycle_time_utc.isoformat()
                            if forecast.source.cycle_time_utc
                            else None
                        ),
                    }
                )

            manifest = {
                "schema_version": cls.schema_version,
                "created_at_utc": datetime.now(UTC).isoformat(),
                "generator": "weather-to-docx",
                "locations_file": "locations.json",
                "locations_sha256": sha256_file(locations_path),
                "series": entries,
            }
            manifest_bytes = cls._canonical_json(manifest)
            (root / "manifest.json").write_bytes(manifest_bytes)
            if private_key_path:
                signature = sign_bytes(manifest_bytes, private_key_path)
                (root / "manifest.sig").write_text(signature + "\n", encoding="ascii")

            checksums = []
            for path in sorted(item for item in root.rglob("*") if item.is_file()):
                relative = path.relative_to(root).as_posix()
                checksums.append(f"{sha256_file(path)}  {relative}")
            (root / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")

            tar_path = Path(temporary_directory) / "forecast-bundle.tar"
            with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as archive:
                for path in sorted(root.rglob("*")):
                    archive.add(path, arcname=path.relative_to(root), recursive=False)
            subprocess.run(
                ["zstd", "-q", "-f", "-19", str(tar_path), "-o", str(output_path)],
                check=True,
            )
        return output_path

    @classmethod
    def read(
        cls,
        bundle_path: Path,
        *,
        public_key_path: Path | None = None,
        require_signature: bool = False,
    ) -> BundleContent:
        cls._require_zstd()
        if not bundle_path.is_file():
            raise FileNotFoundError(bundle_path)

        with tempfile.TemporaryDirectory(prefix="weather-bundle-read-") as temporary_directory:
            temporary = Path(temporary_directory)
            tar_path = temporary / "bundle.tar"
            with tar_path.open("wb") as stream:
                subprocess.run(["zstd", "-q", "-d", "-c", str(bundle_path)], check=True, stdout=stream)
            root = temporary / "extracted"
            root.mkdir()
            with tarfile.open(tar_path, "r") as archive:
                cls._safe_extract(archive, root)

            manifest_path = root / "manifest.json"
            manifest_bytes = manifest_path.read_bytes()
            manifest = json.loads(manifest_bytes)
            if manifest.get("schema_version") != cls.schema_version:
                raise ValueError(
                    f"Неподдерживаемая версия схемы пакета: {manifest.get('schema_version')}"
                )

            signature_path = root / "manifest.sig"
            signed = signature_path.exists()
            if require_signature and not signed:
                raise ValueError("Политика безопасности требует подписанный пакет прогноза")
            if signed:
                if public_key_path is None:
                    if require_signature:
                        raise ValueError("Не задан открытый ключ для проверки подписи")
                else:
                    verify_bytes(
                        manifest_bytes,
                        signature_path.read_text(encoding="ascii").strip(),
                        public_key_path,
                    )

            locations_path = ensure_within(root / manifest["locations_file"], root)
            if sha256_file(locations_path) != manifest["locations_sha256"]:
                raise ValueError("Контрольная сумма locations.json не совпадает")
            locations = [Location.model_validate(item) for item in json.loads(locations_path.read_text(encoding="utf-8"))]

            series: list[ForecastSeries] = []
            for entry in manifest.get("series", []):
                path = ensure_within(root / entry["path"], root)
                if sha256_file(path) != entry["sha256"]:
                    raise ValueError(f"Контрольная сумма не совпадает: {entry['path']}")
                series.append(ForecastSeries.model_validate_json(path.read_text(encoding="utf-8")))
            if not series:
                raise ValueError("Пакет не содержит прогностических рядов")
            return BundleContent(locations=locations, series=series, manifest=manifest, signed=signed)

    @staticmethod
    def _canonical_json(value: dict[str, Any]) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _safe_extract(archive: tarfile.TarFile, root: Path) -> None:
        for member in archive.getmembers():
            target = root / member.name
            ensure_within(target, root)
            if member.islnk() or member.issym():
                raise ValueError("Символические и жёсткие ссылки в прогнозном пакете запрещены")
        # Python 3.11 compatibility: filter= was backported only to some
        # maintenance releases. Paths and links are validated before extraction.
        parameters = inspect.signature(archive.extractall).parameters
        if "filter" in parameters:
            archive.extractall(root, filter="data")
        else:
            archive.extractall(root)

    @staticmethod
    def _require_zstd() -> None:
        if shutil.which("zstd") is None:
            raise RuntimeError("Не найдена утилита zstd. Установите пакет zstd из локального APT-репозитория.")
