#!/usr/bin/env bash
set -Eeuo pipefail

BUNDLE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ENV_FILE=/etc/weather-to-docx/weather-to-docx.env
CONFIGURE_COMMAND=/usr/local/sbin/weather-to-docx-configure
KEYRING=${WTD_GPG_KEYRING:-}
NON_INTERACTIVE=0
SKIP_CONFIGURE=0

usage() {
  cat <<'EOF'
Использование:
  sudo ./setup.sh [--keyring ФАЙЛ] [--non-interactive] [--skip-configure]

Параметры:
  --keyring ФАЙЛ       доверенный GPG keyring для SHA256SUMS.sig
  --non-interactive    не задавать вопросы; сохранить существующие настройки
  --skip-configure     выполнить только установку без мастера настройки

Примеры:
  sudo ./setup.sh
  sudo ./setup.sh --keyring /root/weather-release-keyring.gpg
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keyring)
      [[ $# -ge 2 ]] || { echo "После --keyring требуется путь" >&2; exit 2; }
      KEYRING=$2
      shift 2
      ;;
    --non-interactive)
      NON_INTERACTIVE=1
      shift
      ;;
    --skip-configure)
      SKIP_CONFIGURE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Неизвестный параметр: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ ${EUID:-$(id -u)} -eq 0 ]] || {
  echo "Ошибка: запустите sudo ./setup.sh" >&2
  exit 1
}

[[ -x "$BUNDLE_DIR/install.sh" ]] || {
  echo "Ошибка: рядом не найден install.sh" >&2
  exit 1
}

if [[ -f "$BUNDLE_DIR/SHA256SUMS.sig" && -z "$KEYRING" ]]; then
  if [[ $NON_INTERACTIVE -eq 0 && -t 0 ]]; then
    read -r -p "Путь к доверенному GPG keyring: " KEYRING
  fi
  [[ -n "$KEYRING" ]] || {
    echo "Ошибка: комплект подписан, укажите --keyring ФАЙЛ" >&2
    exit 3
  }
fi

if [[ -n "$KEYRING" ]]; then
  [[ -r "$KEYRING" ]] || {
    echo "Ошибка: доверенный keyring не читается: $KEYRING" >&2
    exit 3
  }
  export WTD_GPG_KEYRING=$KEYRING
fi

"$BUNDLE_DIR/install.sh"

if [[ $SKIP_CONFIGURE -eq 0 && -x "$BUNDLE_DIR/configure.sh" ]]; then
  install -m 0750 "$BUNDLE_DIR/configure.sh" "$CONFIGURE_COMMAND"
  if [[ $NON_INTERACTIVE -eq 1 || ! -t 0 ]]; then
    "$CONFIGURE_COMMAND" \
      --env "$ENV_FILE" \
      --group weatherdoc \
      --non-interactive
  else
    "$CONFIGURE_COMMAND" --env "$ENV_FILE" --group weatherdoc
  fi
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl enable weather-to-docx-api.service weather-to-docx-worker.service
  systemctl restart weather-to-docx-api.service weather-to-docx-worker.service

  telegram_enabled=$(sed -n 's/^WTD_TELEGRAM_ENABLED=//p' "$ENV_FILE" | tail -1 | tr -d '"' || true)
  if [[ ${telegram_enabled,,} == true ]]; then
    systemctl enable --now weather-to-docx-telegram.service
  else
    systemctl disable --now weather-to-docx-telegram.service >/dev/null 2>&1 || true
  fi
fi

cat <<'EOF'

Установка и настройка завершены.

Проверка:
  sudo /opt/weather-to-docx/current/venv/bin/weather-to-docx doctor --deep
  systemctl status weather-to-docx-api weather-to-docx-worker
  systemctl status weather-to-docx-telegram   # если включён

Интерфейс по умолчанию:
  http://127.0.0.1:8080/

Изменить настройки:
  sudo weather-to-docx-configure
  sudoedit /etc/weather-to-docx/weather-to-docx.env
EOF
