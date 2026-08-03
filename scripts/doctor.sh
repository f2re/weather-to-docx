#!/usr/bin/env bash
set -Eeuo pipefail

COMMAND=/opt/weather-to-docx/current/venv/bin/weather-to-docx
DATA_DIR=${WTD_DATA_DIR:-/var/lib/weather-to-docx}
USER_NAME=${WTD_SERVICE_USER:-weatherdoc}

[[ -x "$COMMAND" ]] || {
  echo "Ошибка: приложение не установлено: $COMMAND" >&2
  exit 1
}

if [[ ${EUID} -eq 0 ]] && id "$USER_NAME" >/dev/null 2>&1; then
  exec runuser -u "$USER_NAME" -- env WTD_DATA_DIR="$DATA_DIR" "$COMMAND" doctor --deep
fi
exec env WTD_DATA_DIR="$DATA_DIR" "$COMMAND" doctor --deep
