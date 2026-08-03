#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUTPUT_DIR=${OUTPUT_DIR:-"$ROOT_DIR/dist"}
TARGET_TAG=${TARGET_TAG:-"astra17-$(dpkg --print-architecture 2>/dev/null || uname -m)"}
INCLUDE_GRIB=${INCLUDE_GRIB:-1}
APT_REPOSITORY=${APT_REPOSITORY:-"$OUTPUT_DIR/apt-repository"}
RUNTIME_DIR=${RUNTIME_DIR:-}
SIGNING_KEY=${SIGNING_KEY:-}
PYTHON_BIN=${PYTHON_BIN:-python3}

for command in "$PYTHON_BIN" zstd sha256sum; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Ошибка: не найдена команда $command" >&2
    exit 2
  }
done

VERSION=$(
  "$PYTHON_BIN" - <<'PY' "$ROOT_DIR/pyproject.toml"
import sys, tomllib
with open(sys.argv[1], "rb") as stream:
    print(tomllib.load(stream)["project"]["version"])
PY
)
ARCH=$(dpkg --print-architecture 2>/dev/null || uname -m)
BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
BUNDLE_NAME="weather-to-docx-offline-${VERSION}-${TARGET_TAG}"
mkdir -p "$OUTPUT_DIR"
WORK_DIR=$(mktemp -d -t weather-to-docx-bundle-XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT
STAGE="$WORK_DIR/$BUNDLE_NAME"
mkdir -p "$STAGE"/{wheelhouse,docs,config,examples,systemd,scripts,sbom}

PACKAGE_SPEC="$ROOT_DIR"
if [[ "$INCLUDE_GRIB" == "1" ]]; then
  PACKAGE_SPEC="$ROOT_DIR[grib]"
  touch "$STAGE/wheelhouse/grib.enabled"
fi

echo "==> Сборка wheelhouse для $TARGET_TAG"
"$PYTHON_BIN" -m pip wheel \
  --disable-pip-version-check \
  --wheel-dir "$STAGE/wheelhouse" \
  "$PACKAGE_SPEC"

cp "$ROOT_DIR/README.md" "$ROOT_DIR/CHANGELOG.md" "$ROOT_DIR/SECURITY.md" \
   "$ROOT_DIR/THIRD_PARTY_NOTICES.md" "$STAGE/"
cp -a "$ROOT_DIR/docs/." "$STAGE/docs/"
cp -a "$ROOT_DIR/config/." "$STAGE/config/"
cp -a "$ROOT_DIR/examples/." "$STAGE/examples/"
cp -a "$ROOT_DIR/packaging/systemd/." "$STAGE/systemd/"
cp "$ROOT_DIR/packaging/weather-to-docx.env" "$STAGE/weather-to-docx.env.example"
cp "$ROOT_DIR/scripts/install.sh" "$ROOT_DIR/scripts/upgrade.sh" \
   "$ROOT_DIR/scripts/rollback.sh" "$ROOT_DIR/scripts/doctor.sh" \
   "$ROOT_DIR/scripts/uninstall.sh" "$STAGE/"
chmod 0755 "$STAGE"/*.sh

if [[ -d "$APT_REPOSITORY" && -f "$APT_REPOSITORY/Packages" ]]; then
  echo "==> Добавление локального APT-репозитория"
  cp -a "$APT_REPOSITORY" "$STAGE/apt-repository"
else
  echo "==> Локальный APT-репозиторий не добавлен: $APT_REPOSITORY не найден" >&2
fi

if [[ -n "$RUNTIME_DIR" ]]; then
  [[ -d "$RUNTIME_DIR" ]] || {
    echo "Ошибка: RUNTIME_DIR не существует: $RUNTIME_DIR" >&2
    exit 3
  }
  echo "==> Добавление частного Python runtime: $RUNTIME_DIR"
  cp -a "$RUNTIME_DIR" "$STAGE/runtime"
fi

printf '%s\n' "$VERSION" > "$STAGE/VERSION"
cat > "$STAGE/build-info.json" <<JSON
{
  "project": "weather-to-docx",
  "version": "$VERSION",
  "target_tag": "$TARGET_TAG",
  "architecture": "$ARCH",
  "built_at_utc": "$BUILD_TIME",
  "python": "$($PYTHON_BIN -VV 2>&1 | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g')",
  "grib_python_enabled": $([[ "$INCLUDE_GRIB" == "1" ]] && echo true || echo false),
  "apt_repository_included": $([[ -d "$STAGE/apt-repository" ]] && echo true || echo false),
  "private_runtime_included": $([[ -d "$STAGE/runtime" ]] && echo true || echo false)
}
JSON

"$PYTHON_BIN" - <<'PY' "$STAGE/wheelhouse" "$STAGE/sbom/cyclonedx.json"
import hashlib
import json
import sys
from pathlib import Path
try:
    from packaging.utils import parse_wheel_filename
except ImportError as exc:
    raise SystemExit("Для формирования SBOM требуется пакет packaging, входящий в pip") from exc

wheelhouse = Path(sys.argv[1])
output = Path(sys.argv[2])
components = []
for wheel in sorted(wheelhouse.glob("*.whl")):
    name, version, build, tags = parse_wheel_filename(wheel.name)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    components.append({
        "type": "library",
        "name": str(name),
        "version": str(version),
        "purl": f"pkg:pypi/{name}@{version}",
        "hashes": [{"alg": "SHA-256", "content": digest}],
        "properties": [{"name": "weather-to-docx:wheel", "value": wheel.name}],
    })
payload = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.5",
    "version": 1,
    "metadata": {"component": {"type": "application", "name": "weather-to-docx"}},
    "components": components,
}
output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

(
  cd "$STAGE"
  find . -type f ! -name SHA256SUMS ! -name SHA256SUMS.sig -printf '%P\0' \
    | sort -z \
    | xargs -0 sha256sum > SHA256SUMS
)

if [[ -n "$SIGNING_KEY" ]]; then
  command -v gpg >/dev/null 2>&1 || {
    echo "Ошибка: задан SIGNING_KEY, но не найдена команда gpg" >&2
    exit 4
  }
  gpg --batch --yes --local-user "$SIGNING_KEY" \
    --armor --detach-sign --output "$STAGE/SHA256SUMS.sig" "$STAGE/SHA256SUMS"
fi

ARCHIVE="$OUTPUT_DIR/$BUNDLE_NAME.tar.zst"
echo "==> Упаковка $ARCHIVE"
tar -C "$WORK_DIR" --sort=name --owner=0 --group=0 --numeric-owner \
  -cf - "$BUNDLE_NAME" | zstd -q -f -19 -o "$ARCHIVE"
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"

if [[ -n "$SIGNING_KEY" ]]; then
  gpg --batch --yes --local-user "$SIGNING_KEY" \
    --armor --detach-sign --output "$ARCHIVE.asc" "$ARCHIVE"
fi

echo "==> Офлайн-комплект готов"
echo "    $ARCHIVE"
echo "    $ARCHIVE.sha256"
[[ -f "$ARCHIVE.asc" ]] && echo "    $ARCHIVE.asc"
