from __future__ import annotations

import hashlib
import re
from pathlib import Path


_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9А-Яа-яЁё._-]+")


def safe_filename(value: str, fallback: str = "forecast") -> str:
    cleaned = _UNSAFE_FILENAME.sub("_", value.strip()).strip("._-")
    return cleaned[:180] or fallback


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_within(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    resolved_root = root.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError("Путь выходит за пределы разрешённого каталога")
    return resolved
