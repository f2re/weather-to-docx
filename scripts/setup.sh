#!/usr/bin/env bash
set -Eeuo pipefail

BUNDLE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ENV_FILE=/etc/weather-to-docx/weather-to-docx.env

[[ ${EUID:-$(id -u)} -eq 0 ]] || {
  echo "Ошибка: запустите sudo ./setup.sh" >&2
  exit 1
}

[[ -x "$BUNDLE_DIR/install.sh" ]] || {
  echo "Ошибка: рядом не найден install.sh" >&2
  exit 1
}

# Базовая установка остаётся полностью автономной. Мастер токенов запускается
# после атомарного развёртывания приложения.
"$BUNDLE_DIR/install.sh"

if [[ -x "$BUNDLE_DIR/configure.sh" ]]; then
  if [[ -t 0 ]]; then
    "$BUNDLE_DIR/configure.sh" --env "$ENV_FILE" --group weatherdoc
  else
    echo "Нет интерактивного терминала: сохранены существующие настройки." >&2
    echo "Позже выполните: sudo $BUNDLE_DIR/configure.sh" >&2
  fi
fi

if command -v systemctl >/dev/null 2>&1; then
  if [[ -f "$BUNDLE_DIR/systemd/weather-to-docx-telegram.service" ]]; then
    install -m 0644 \
      "$BUNDLE_DIR/systemd/weather-to-docx-telegram.service" \
      /etc/systemd/system/weather-to-docx-telegram.service
  fi
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
  sudo /opt/weather-to-docx/current/share/scripts/configure.sh
  sudoedit /etc/weather-to-docx/weather-to-docx.env
EOF
