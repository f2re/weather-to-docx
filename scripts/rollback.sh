#!/usr/bin/env bash
set -Eeuo pipefail

[[ ${EUID} -eq 0 ]] || {
  echo "Ошибка: откат должен выполняться от root." >&2
  exit 1
}

OPT_ROOT=/opt/weather-to-docx
CURRENT=$OPT_ROOT/current
PREVIOUS=$OPT_ROOT/previous
ENV_FILE=/etc/weather-to-docx/weather-to-docx.env
CURRENT_TARGET=$(readlink -f "$CURRENT" 2>/dev/null || true)
PREVIOUS_TARGET=$(readlink -f "$PREVIOUS" 2>/dev/null || true)

[[ -n "$PREVIOUS_TARGET" && -d "$PREVIOUS_TARGET" ]] || {
  echo "Ошибка: предыдущий релиз отсутствует." >&2
  exit 2
}

ln -sfn "$PREVIOUS_TARGET" "$CURRENT.new"
mv -Tf "$CURRENT.new" "$CURRENT"
if [[ -n "$CURRENT_TARGET" && -d "$CURRENT_TARGET" ]]; then
  ln -sfn "$CURRENT_TARGET" "$PREVIOUS.new"
  mv -Tf "$PREVIOUS.new" "$PREVIOUS"
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl restart weather-to-docx-api.service weather-to-docx-worker.service
  telegram_enabled=$(sed -n 's/^WTD_TELEGRAM_ENABLED=//p' "$ENV_FILE" 2>/dev/null | tail -1 | tr -d '"' || true)
  if [[ ${telegram_enabled,,} == true ]]; then
    systemctl enable weather-to-docx-telegram.service >/dev/null 2>&1 || true
    systemctl restart weather-to-docx-telegram.service
  else
    systemctl disable --now weather-to-docx-telegram.service >/dev/null 2>&1 || true
  fi
fi

echo "Откат выполнен: $CURRENT -> $(readlink -f "$CURRENT")"
echo "Предыдущий текущий релиз сохранён: $PREVIOUS -> $(readlink -f "$PREVIOUS")"
