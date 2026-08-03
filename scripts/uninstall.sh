#!/usr/bin/env bash
set -Eeuo pipefail

[[ ${EUID} -eq 0 ]] || {
  echo "Ошибка: удаление должно выполняться от root." >&2
  exit 1
}

PURGE=0
[[ ${1:-} == "--purge-data" ]] && PURGE=1

systemd_enabled() {
  [[ ${WTD_SKIP_SYSTEMD:-0} != 1 ]] && command -v systemctl >/dev/null 2>&1
}

if systemd_enabled; then
  systemctl disable --now weather-to-docx-api.service weather-to-docx-worker.service >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/weather-to-docx-api.service /etc/systemd/system/weather-to-docx-worker.service
  systemctl daemon-reload
fi

rm -rf /opt/weather-to-docx

if [[ $PURGE -eq 1 ]]; then
  rm -rf /etc/weather-to-docx /var/lib/weather-to-docx
  userdel weatherdoc >/dev/null 2>&1 || true
  groupdel weatherdoc >/dev/null 2>&1 || true
  echo "Приложение, настройки и данные удалены."
else
  echo "Приложение удалено. Настройки и данные сохранены в /etc/weather-to-docx и /var/lib/weather-to-docx."
fi
