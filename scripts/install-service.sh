#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VENV_DIR=${WTD_VENV_DIR:-"$ROOT_DIR/.venv"}
DATA_DIR=${WTD_DATA_DIR:-"$ROOT_DIR/var/service"}
SERVICE_USER=${WTD_SERVICE_USER:-${SUDO_USER:-}}
SERVICE_GROUP=${WTD_SERVICE_GROUP:-}
API_HOST=${WTD_API_HOST:-127.0.0.1}
API_PORT=${WTD_API_PORT:-8080}
POLL_INTERVAL=${WTD_WORKER_POLL_INTERVAL:-5}

usage() {
  cat <<'EOF'
Использование:
  sudo ./scripts/install-service.sh [параметры]

Устанавливает две systemd-службы для запуска текущего checkout: API и worker.
По умолчанию службы запускаются от пользователя, вызвавшего sudo, и хранят
данные в var/service. Для production-установки из автономного комплекта
используйте setup.sh, а не этот скрипт.

Параметры:
  --user ИМЯ          пользователь службы (по умолчанию SUDO_USER)
  --group ИМЯ         группа службы (по умолчанию основная группа пользователя)
  --venv КАТАЛОГ      виртуальное окружение (по умолчанию .venv)
  --data-dir КАТАЛОГ  каталог данных (по умолчанию var/service)
  --host АДРЕС        адрес API (по умолчанию 127.0.0.1)
  --port ПОРТ         порт API (по умолчанию 8080)
  --poll-interval С   интервал worker в секундах (по умолчанию 5)

После установки:
  sudo systemctl status weather-to-docx-local-api weather-to-docx-local-worker
  sudo journalctl -u weather-to-docx-local-api -f
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) SERVICE_USER=${2:?После --user нужно имя}; shift 2 ;;
    --group) SERVICE_GROUP=${2:?После --group нужно имя}; shift 2 ;;
    --venv) VENV_DIR=${2:?После --venv нужен каталог}; shift 2 ;;
    --data-dir) DATA_DIR=${2:?После --data-dir нужен каталог}; shift 2 ;;
    --host) API_HOST=${2:?После --host нужен адрес}; shift 2 ;;
    --port) API_PORT=${2:?После --port нужен порт}; shift 2 ;;
    --poll-interval) POLL_INTERVAL=${2:?После --poll-interval нужно значение}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный параметр: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ ${EUID:-$(id -u)} -eq 0 ]] || {
  echo "Ошибка: запустите через sudo." >&2
  exit 1
}
[[ -n "$SERVICE_USER" && "$SERVICE_USER" != root ]] || {
  echo "Ошибка: укажите непривилегированного пользователя через --user." >&2
  exit 2
}
id "$SERVICE_USER" >/dev/null 2>&1 || {
  echo "Ошибка: пользователь не существует: $SERVICE_USER" >&2
  exit 2
}
SERVICE_GROUP=${SERVICE_GROUP:-$(id -gn "$SERVICE_USER")}
getent group "$SERVICE_GROUP" >/dev/null || {
  echo "Ошибка: группа не существует: $SERVICE_GROUP" >&2
  exit 2
}

COMMAND="$VENV_DIR/bin/weather-to-docx"
[[ -x "$COMMAND" ]] || {
  echo "Ошибка: не найдено виртуальное окружение: $VENV_DIR" >&2
  exit 2
}
[[ "$API_PORT" =~ ^[0-9]+$ && "$API_PORT" -ge 1 && "$API_PORT" -le 65535 ]] || {
  echo "Ошибка: порт должен быть числом от 1 до 65535." >&2
  exit 2
}

install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0750 \
  "$DATA_DIR" "$DATA_DIR/cache" "$DATA_DIR/cache/matplotlib"

escape_sed() {
  sed 's/[\\/&]/\\&/g' <<<"$1"
}

render_unit() {
  local source=$1 target=$2
  sed \
    -e "s|@SERVICE_USER@|$(escape_sed "$SERVICE_USER")|g" \
    -e "s|@SERVICE_GROUP@|$(escape_sed "$SERVICE_GROUP")|g" \
    -e "s|@DATA_DIR@|$(escape_sed "$DATA_DIR")|g" \
    -e "s|@API_HOST@|$(escape_sed "$API_HOST")|g" \
    -e "s|@API_PORT@|$(escape_sed "$API_PORT")|g" \
    -e "s|@POLL_INTERVAL@|$(escape_sed "$POLL_INTERVAL")|g" \
    -e "s|@COMMAND@|$(escape_sed "$COMMAND")|g" \
    "$source" > "$target"
}

render_unit "$ROOT_DIR/packaging/systemd/weather-to-docx-local-api.service.in" \
  /etc/systemd/system/weather-to-docx-local-api.service
render_unit "$ROOT_DIR/packaging/systemd/weather-to-docx-local-worker.service.in" \
  /etc/systemd/system/weather-to-docx-local-worker.service
chmod 0644 /etc/systemd/system/weather-to-docx-local-{api,worker}.service

systemctl daemon-reload
systemctl enable --now weather-to-docx-local-api.service weather-to-docx-local-worker.service
systemctl --no-pager --full status \
  weather-to-docx-local-api.service weather-to-docx-local-worker.service
