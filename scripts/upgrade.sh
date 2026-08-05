#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)

# В git-каталоге install.sh запускать напрямую нельзя: он устанавливает только
# уже собранный автономный комплект и ожидает VERSION/wheelhouse рядом с собой.
# Обновление исходного дерева сначала собирает новый комплект, затем атомарно
# переключает /opt/weather-to-docx/current.
if [[ -f "$ROOT_DIR/pyproject.toml" && -x "$SCRIPT_DIR/update.sh" ]]; then
  exec "$SCRIPT_DIR/update.sh" "$@"
fi

# В распакованном автономном комплекте upgrade.sh лежит рядом с install.sh.
exec "$SCRIPT_DIR/install.sh" "$@"
