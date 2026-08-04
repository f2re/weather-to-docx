#!/usr/bin/env bash
set -Eeuo pipefail

[[ ${EUID} -eq 0 ]] || {
  echo "Ошибка: удаление должно выполняться от root." >&2
  exit 1
}

PURGE=0
[[ ${1:-} == "--purge-data" ]] && PURGE=1

if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now \
    weather-to-docx-api.service \
    weather-to-docx-worker.service \
    weather-to-docx-telegram.service \
    >/dev/null 2>&1 || true
  rm -f \
    /etc/systemd/system/weather-to-docx-api.service \
    /etc/systemd/system/weather-to-docx-worker.service \
    /etc/systemd/system/weather-to-docx-telegram.service
  systemctl daemon-reload
fi

rm -f /usr/local/sbin/weather-to-docx-configure
rm -rf /opt/weather-to-docx

if [[ $PURGE -eq 1 ]]; then
  rm -rf /etc/weather-to-docx /var/lib/weather-to-docx
  userdel weatherdoc >/dev/null 2>&1 || true
  groupdel weatherdoc >/dev/null 2>&1 || true
  echo "Приложение, настройки и данные удалены."
else
  echo "Приложение удалено. Настройки и данные сохранены в /etc/weather-to-docx и /var/lib/weather-to-docx."
fi
