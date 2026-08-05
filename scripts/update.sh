#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PROJECT=weather-to-docx
CURRENT_ROOT=/opt/$PROJECT/current
CURRENT_CLI=$CURRENT_ROOT/venv/bin/weather-to-docx
VERIFY_CLI=$CURRENT_ROOT/venv/bin/weather-to-docx-verify
INCLUDE_GRIB=${INCLUDE_GRIB:-0}
SKIP_DEEP_CHECK=0

usage() {
  cat <<'EOF'
Использование:
  ./scripts/update.sh [--with-grib] [--without-grib] [--skip-deep-check]

Команда предназначена для обновления установленной службы из git-каталога.
Обычный git pull сам по себе НЕ обновляет /opt/weather-to-docx/current.

Параметры:
  --with-grib       включить Python ecCodes в новый автономный комплект
  --without-grib    не включать ecCodes (по умолчанию)
  --skip-deep-check не формировать контрольный DOCX после установки
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-grib)
      INCLUDE_GRIB=1
      shift
      ;;
    --without-grib)
      INCLUDE_GRIB=0
      shift
      ;;
    --skip-deep-check)
      SKIP_DEEP_CHECK=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Ошибка: неизвестный параметр $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -f "$ROOT_DIR/pyproject.toml" ]] || {
  echo "Ошибка: команда должна запускаться из git-каталога проекта." >&2
  exit 2
}

for command in python3 zstd tar; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Ошибка: не найдена команда $command" >&2
    exit 2
  }
done

VERSION=$(python3 - <<'PY' "$ROOT_DIR/pyproject.toml"
import sys
import tomllib

with open(sys.argv[1], "rb") as stream:
    print(tomllib.load(stream)["project"]["version"])
PY
)
CURRENT_VERSION=""
if [[ -x "$CURRENT_CLI" ]]; then
  CURRENT_VERSION=$($CURRENT_CLI --version 2>/dev/null || true)
fi

printf 'Исходный код: %s\n' "$ROOT_DIR"
printf 'Версия исходного кода: %s\n' "$VERSION"
printf 'Установленная версия: %s\n' "${CURRENT_VERSION:-не установлена}"
printf 'Текущий runtime: %s\n' "$(readlink -f "$CURRENT_ROOT" 2>/dev/null || echo отсутствует)"

if [[ "$CURRENT_VERSION" == "$VERSION" && -x "$VERIFY_CLI" ]]; then
  echo "Версия уже установлена. Проверяется фактическое наличие метеограмм."
  if [[ $SKIP_DEEP_CHECK -eq 1 ]]; then
    exec "$VERIFY_CLI"
  fi
  exec "$VERIFY_CLI" --deep
fi

WORK_DIR=$(mktemp -d -t weather-to-docx-update-XXXXXX)
cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT
OUTPUT_DIR=$WORK_DIR/dist
mkdir -p "$OUTPUT_DIR" "$WORK_DIR/unpacked"

printf 'Сборка автономного комплекта %s (GRIB=%s)…\n' "$VERSION" "$INCLUDE_GRIB"
OUTPUT_DIR="$OUTPUT_DIR" INCLUDE_GRIB="$INCLUDE_GRIB" \
  "$ROOT_DIR/scripts/build-offline-bundle.sh"

ARCHIVE=$(find "$OUTPUT_DIR" -maxdepth 1 -type f \
  -name "weather-to-docx-offline-${VERSION}-*.tar.zst" -print -quit)
[[ -n "$ARCHIVE" && -f "$ARCHIVE" ]] || {
  echo "Ошибка: автономный комплект не создан." >&2
  exit 3
}
[[ -f "$ARCHIVE.sha256" ]] || {
  echo "Ошибка: рядом с комплектом нет контрольной суммы." >&2
  exit 3
}
(
  cd "$OUTPUT_DIR"
  sha256sum -c "$(basename "$ARCHIVE.sha256")"
)
tar --zstd -xf "$ARCHIVE" -C "$WORK_DIR/unpacked"
BUNDLE_DIR=$(find "$WORK_DIR/unpacked" -mindepth 1 -maxdepth 1 -type d -print -quit)
[[ -n "$BUNDLE_DIR" && -x "$BUNDLE_DIR/setup.sh" ]] || {
  echo "Ошибка: распакованный комплект неполон." >&2
  exit 3
}

INSTALL_COMMAND=("$BUNDLE_DIR/setup.sh" --non-interactive --skip-configure)
if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
  WTD_ALLOW_NON_ASTRA=${WTD_ALLOW_NON_ASTRA:-0} "${INSTALL_COMMAND[@]}"
else
  command -v sudo >/dev/null 2>&1 || {
    echo "Ошибка: для установки в /opt требуется sudo." >&2
    exit 4
  }
  sudo --preserve-env=WTD_ALLOW_NON_ASTRA \
    env WTD_ALLOW_NON_ASTRA="${WTD_ALLOW_NON_ASTRA:-0}" \
    "${INSTALL_COMMAND[@]}"
fi

[[ -x "$CURRENT_CLI" ]] || {
  echo "Ошибка: после установки отсутствует $CURRENT_CLI" >&2
  exit 5
}
INSTALLED_VERSION=$($CURRENT_CLI --version)
[[ "$INSTALLED_VERSION" == "$VERSION" ]] || {
  echo "Ошибка: служба использует версию $INSTALLED_VERSION вместо $VERSION" >&2
  exit 5
}
[[ -x "$VERIFY_CLI" ]] || {
  echo "Ошибка: в установленном runtime нет weather-to-docx-verify" >&2
  exit 5
}

if [[ $SKIP_DEEP_CHECK -eq 1 ]]; then
  "$VERIFY_CLI"
else
  "$VERIFY_CLI" --deep
fi

if command -v curl >/dev/null 2>&1; then
  curl -fsS http://127.0.0.1:8080/health || true
  echo
fi

echo "Обновление завершено: $CURRENT_ROOT -> $(readlink -f "$CURRENT_ROOT")"
