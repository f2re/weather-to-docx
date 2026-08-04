#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE=/etc/weather-to-docx/weather-to-docx.env
NON_INTERACTIVE=0
SERVICE_GROUP=weatherdoc

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV_FILE=$2; shift 2 ;;
    --group) SERVICE_GROUP=$2; shift 2 ;;
    --non-interactive) NON_INTERACTIVE=1; shift ;;
    -h|--help)
      cat <<'EOF'
Использование: configure.sh [--env ФАЙЛ] [--non-interactive]

Интерактивно настраивает API, модели, DaData и Telegram. Секреты вводятся
без отображения и сохраняются в EnvironmentFile с правами 0640.
EOF
      exit 0
      ;;
    *) echo "Неизвестный параметр: $1" >&2; exit 2 ;;
  esac
done

[[ ${EUID:-$(id -u)} -eq 0 ]] || {
  echo "Ошибка: настройка должна выполняться от root" >&2
  exit 1
}

mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"
chmod 0640 "$ENV_FILE"
chown root:"$SERVICE_GROUP" "$ENV_FILE" 2>/dev/null || true

get_value() {
  local key=$1 default=${2:-}
  local value
  value=$(sed -n "s/^${key}=//p" "$ENV_FILE" | tail -1)
  value=${value#\"}; value=${value%\"}
  printf '%s' "${value:-$default}"
}

set_value() {
  local key=$1 value=$2
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
line = f"{key}={json.dumps(value, ensure_ascii=False)}\n"
lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
result = []
replaced = False
for current in lines:
    if current.startswith(f"{key}="):
        if not replaced:
            result.append(line)
            replaced = True
    else:
        result.append(current)
if not replaced:
    if result and not result[-1].endswith("\n"):
        result[-1] += "\n"
    result.append(line)
path.write_text("".join(result), encoding="utf-8")
PY
}

ask() {
  local label=$1 default=$2 result
  if [[ $NON_INTERACTIVE -eq 1 ]]; then printf '%s' "$default"; return; fi
  read -r -p "$label [$default]: " result
  printf '%s' "${result:-$default}"
}

ask_secret() {
  local label=$1 current=$2 result
  if [[ $NON_INTERACTIVE -eq 1 ]]; then printf '%s' "$current"; return; fi
  if [[ -n "$current" ]]; then
    read -r -s -p "$label [уже задан; Enter — оставить]: " result
  else
    read -r -s -p "$label [необязательно]: " result
  fi
  echo >&2
  printf '%s' "${result:-$current}"
}

ask_yes_no() {
  local label=$1 default=$2 answer
  if [[ $NON_INTERACTIVE -eq 1 ]]; then printf '%s' "$default"; return; fi
  read -r -p "$label [$([[ $default == true ]] && echo Д/н || echo д/Н)]: " answer
  answer=${answer,,}
  if [[ -z "$answer" ]]; then printf '%s' "$default"; return; fi
  [[ "$answer" =~ ^(д|да|y|yes)$ ]] && printf true || printf false
}

if [[ $NON_INTERACTIVE -eq 0 ]]; then
  cat <<'EOF'

Weather to DOCX — первичная настройка
-------------------------------------
Enter принимает рекомендуемое значение. Токены не отображаются на экране.
Настройки можно позже изменить командой:
  sudoedit /etc/weather-to-docx/weather-to-docx.env
EOF
fi

api_host=$(ask "Адрес HTTP-интерфейса" "$(get_value WTD_API_HOST 127.0.0.1)")
api_port=$(ask "Порт HTTP-интерфейса" "$(get_value WTD_API_PORT 8080)")
timezone=$(ask "Часовой пояс точек по умолчанию" "$(get_value WTD_DEFAULT_TIMEZONE Europe/Moscow)")
days=$(ask "Горизонт по умолчанию, суток" "$(get_value WTD_DEFAULT_FORECAST_DAYS 7)")

current_sources=$(get_value WTD_DEFAULT_SOURCE_IDS "open_meteo_gfs,open_meteo_ecmwf_ifs,open_meteo_dwd_icon_global,open_meteo_gefs_0p25")
if [[ $NON_INTERACTIVE -eq 0 ]]; then
  cat <<'EOF'

Набор моделей:
  1 — рекомендуемый: GFS + ECMWF IFS + ICON + GEFS
  2 — компактный: GFS + GEFS
  3 — расширенный: GFS + IFS + AIFS + ICON + GDPS + GEFS
  4 — указать source_id вручную
EOF
  preset=$(ask "Выбор" 1)
  case "$preset" in
    1) sources="open_meteo_gfs,open_meteo_ecmwf_ifs,open_meteo_dwd_icon_global,open_meteo_gefs_0p25" ;;
    2) sources="open_meteo_gfs,open_meteo_gefs_0p25" ;;
    3) sources="open_meteo_gfs,open_meteo_ecmwf_ifs,open_meteo_ecmwf_aifs,open_meteo_dwd_icon_global,open_meteo_gem_gdps,open_meteo_gefs_0p25" ;;
    4) sources=$(ask "source_id через запятую" "$current_sources") ;;
    *) echo "Неизвестный вариант, сохранён текущий набор" >&2; sources=$current_sources ;;
  esac
else
  sources=$current_sources
fi

dadata_token=$(ask_secret "DaData API token" "$(get_value WTD_DADATA_TOKEN '')")
dadata_secret=$(ask_secret "DaData secret для пакетной очистки адресов" "$(get_value WTD_DADATA_SECRET '')")
telegram_enabled=$(ask_yes_no "Включить Telegram-бота" "$(get_value WTD_TELEGRAM_ENABLED false)")
telegram_token=$(get_value WTD_TELEGRAM_BOT_TOKEN '')
allowed_users=$(get_value WTD_TELEGRAM_ALLOWED_USER_IDS '')
if [[ $telegram_enabled == true ]]; then
  telegram_token=$(ask_secret "Telegram bot token от @BotFather" "$telegram_token")
  allowed_users=$(ask "Разрешённые Telegram user ID через запятую (пусто — доступ всем)" "$allowed_users")
  if [[ -z "$telegram_token" ]]; then
    echo "Предупреждение: Telegram включён, но токен пуст. Служба не будет запущена." >&2
    telegram_enabled=false
  fi
  if [[ -z "$allowed_users" ]]; then
    echo "Предупреждение: список пользователей пуст — бот будет доступен всем, кто знает его имя." >&2
  fi
fi

set_value WTD_DATA_DIR "$(get_value WTD_DATA_DIR /var/lib/weather-to-docx)"
set_value WTD_API_HOST "$api_host"
set_value WTD_API_PORT "$api_port"
set_value WTD_DEFAULT_TIMEZONE "$timezone"
set_value WTD_DEFAULT_FORECAST_DAYS "$days"
set_value WTD_DEFAULT_SOURCE_IDS "$sources"
set_value WTD_DADATA_TOKEN "$dadata_token"
set_value WTD_DADATA_SECRET "$dadata_secret"
set_value WTD_TELEGRAM_ENABLED "$telegram_enabled"
set_value WTD_TELEGRAM_BOT_TOKEN "$telegram_token"
set_value WTD_TELEGRAM_ALLOWED_USER_IDS "$allowed_users"
set_value WTD_TELEGRAM_MAX_LOCATIONS "$(get_value WTD_TELEGRAM_MAX_LOCATIONS 100)"
set_value WTD_HTTP_TIMEOUT_SECONDS "$(get_value WTD_HTTP_TIMEOUT_SECONDS 60)"
set_value WTD_HTTP_MAX_RETRIES "$(get_value WTD_HTTP_MAX_RETRIES 3)"
set_value WTD_LOG_LEVEL "$(get_value WTD_LOG_LEVEL INFO)"

chmod 0640 "$ENV_FILE"
chown root:"$SERVICE_GROUP" "$ENV_FILE" 2>/dev/null || true

cat <<EOF

Настройка сохранена: $ENV_FILE

Проверка и обслуживание:
  sudo /opt/weather-to-docx/current/venv/bin/weather-to-docx doctor --deep
  sudo systemctl restart weather-to-docx-api weather-to-docx-worker
  sudo systemctl restart weather-to-docx-telegram   # если бот включён
  sudo journalctl -u weather-to-docx-telegram -n 100 --no-pager

Редактирование:
  sudoedit $ENV_FILE

После изменения токенов перезапустите соответствующую службу.
EOF
