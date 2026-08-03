#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Использование:
  sudo APT_PACKAGES='...' scripts/build-astra-apt-repository.sh [КАТАЛОГ]

Скачивает указанные пакеты и доступные недостающие зависимости из настроенных
репозиториев сборочной Astra Linux, затем формирует локальный APT-репозиторий.
USAGE
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

if [[ ${EUID} -ne 0 ]]; then
  echo "Ошибка: сценарий должен выполняться от root, поскольку apt-get использует системные списки пакетов." >&2
  exit 2
fi

for command in apt-get apt-cache dpkg-scanpackages gzip sha256sum; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Ошибка: не найдена команда $command. На сборочной машине установите apt и dpkg-dev." >&2
    exit 3
  }
done

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUTPUT_DIR=${1:-"$ROOT_DIR/dist/apt-repository"}
APT_PACKAGES=${APT_PACKAGES:-"ca-certificates zstd fonts-liberation2 libeccodes0 libeccodes-data"}

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR=$(cd "$OUTPUT_DIR" && pwd)
WORK_DIR=$(mktemp -d -t weather-to-docx-apt-XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT
mkdir -p "$WORK_DIR/archives/partial"

echo "==> Обновление индексов настроенных репозиториев сборочной системы"
apt-get update

echo "==> Расчёт полного дерева обязательных зависимостей: $APT_PACKAGES"
read -r -a REQUESTED <<< "$APT_PACKAGES"
mapfile -t DEPENDENCY_CLOSURE < <(
  {
    printf '%s\n' "${REQUESTED[@]}"
    apt-cache depends --recurse \
      --no-recommends --no-suggests --no-conflicts --no-breaks \
      --no-replaces --no-enhances "${REQUESTED[@]}" \
      | awk '/^[[:alnum:]][^[:space:]]*$/ { print $1 }'
  } \
    | sort -u \
    | while IFS= read -r package; do
        apt-cache show "$package" >/dev/null 2>&1 && printf '%s\n' "$package"
      done
)
[[ ${#DEPENDENCY_CLOSURE[@]} -gt 0 ]] || {
  echo "Ошибка: не удалось рассчитать дерево зависимостей." >&2
  exit 4
}

echo "==> Загрузка ${#DEPENDENCY_CLOSURE[@]} пакетов с обязательными зависимостями"
# --reinstall заставляет скачать пакеты, уже установленные на сборочной машине.
DEBIAN_FRONTEND=noninteractive apt-get \
  -y --download-only --reinstall --no-install-recommends \
  -o Dir::Cache::archives="$WORK_DIR/archives" \
  install "${DEPENDENCY_CLOSURE[@]}"

find "$OUTPUT_DIR" -maxdepth 1 -type f \
  \( -name '*.deb' -o -name 'Packages*' -o -name 'SHA256SUMS' \
     -o -name 'requested-packages.txt' -o -name 'dependency-closure.txt' \) -delete
find "$WORK_DIR/archives" -maxdepth 1 -type f -name '*.deb' -exec cp -a '{}' "$OUTPUT_DIR/" ';'

if ! compgen -G "$OUTPUT_DIR/*.deb" >/dev/null; then
  echo "Ошибка: apt-get не загрузил ни одного .deb." >&2
  exit 4
fi

printf '%s\n' "${REQUESTED[@]}" > "$OUTPUT_DIR/requested-packages.txt"
printf '%s\n' "${DEPENDENCY_CLOSURE[@]}" > "$OUTPUT_DIR/dependency-closure.txt"
(
  cd "$OUTPUT_DIR"
  dpkg-scanpackages --multiversion . /dev/null > Packages
  gzip -9 -c Packages > Packages.gz
  find . -maxdepth 1 -type f ! -name SHA256SUMS -printf '%P\0' \
    | sort -z \
    | xargs -0 sha256sum > SHA256SUMS
)

COUNT=$(find "$OUTPUT_DIR" -maxdepth 1 -type f -name '*.deb' | wc -l)
echo "==> Локальный APT-репозиторий готов: $OUTPUT_DIR"
echo "==> Пакетов .deb: $COUNT"
