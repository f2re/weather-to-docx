# 📦 Автономная установка на Astra Linux

## 1. Как устроено развёртывание

Приложение и свежие прогнозные данные доставляются раздельно.

```text
машина сборки с Интернетом
        │
        ├── офлайн-комплект приложения
        │
        └── подписанные пакеты прогнозов
                    │
                    ▼
              Astra Linux
```

Офлайн-комплект необходимо собирать в среде, совместимой с целевой системой по:

- выпуску Astra Linux;
- архитектуре;
- версии `glibc`;
- версии Python;
- разрешённым системным репозиториям;
- режиму защищённости.

Копирование `venv` с Ubuntu, macOS или другой версии Debian не поддерживается.

## 2. Состав комплекта 0.3.1

```text
weather-to-docx-offline-0.3.1-astra17-amd64/
├── VERSION
├── build-info.json
├── README.md
├── SHA256SUMS
├── SHA256SUMS.sig
├── wheelhouse/
├── apt-repository/
├── runtime/
├── config/
├── examples/
├── docs/
├── systemd/
│   ├── weather-to-docx-api.service
│   ├── weather-to-docx-worker.service
│   └── weather-to-docx-telegram.service
├── setup.sh
├── install.sh
├── configure.sh
├── upgrade.sh
├── rollback.sh
├── doctor.sh
└── uninstall.sh
```

`setup.sh` — основная точка входа для человека. `install.sh` выполняет техническое развёртывание и используется для автоматизации.

## 3. Подготовка локального APT

На подключённой Astra Linux:

```bash
sudo APT_PACKAGES='python3.11 python3.11-venv ca-certificates zstd fonts-liberation2 libeccodes0 libeccodes-data' \
  bash scripts/build-astra-apt-repository.sh dist/apt-repository
```

Если утверждённый репозиторий не содержит Python 3.11, добавьте одобренный частный runtime через `RUNTIME_DIR`.

## 4. Сборка полного архива

```bash
TARGET_TAG=astra17-amd64 \
INCLUDE_GRIB=1 \
APT_REPOSITORY=dist/apt-repository \
RUNTIME_DIR=/opt/python311 \
SIGNING_KEY='ОТПЕЧАТОК_GPG_КЛЮЧА' \
OUTPUT_DIR=dist \
  bash scripts/build-offline-bundle.sh
```

Результат:

```text
dist/weather-to-docx-offline-0.3.1-astra17-amd64.tar.zst
dist/weather-to-docx-offline-0.3.1-astra17-amd64.tar.zst.sha256
dist/weather-to-docx-offline-0.3.1-astra17-amd64.tar.zst.asc
```

В `wheelhouse` включаются все Python-зависимости, в том числе:

- FastAPI;
- python-docx;
- python-telegram-bot;
- timezonefinder и его локальная база часовых поясов;
- ecCodes Python binding при `INCLUDE_GRIB=1`.

Целевая установка использует `pip --no-index`.

## 5. Проверка перед переносом

```bash
cd dist
sha256sum -c weather-to-docx-offline-*.tar.zst.sha256

gpg --verify \
  weather-to-docx-offline-*.tar.zst.asc \
  weather-to-docx-offline-*.tar.zst
```

Архив, контрольная сумма и подпись переносятся разрешённым носителем.

## 6. Установка одной командой

```bash
tar --zstd -xf weather-to-docx-offline-0.3.1-astra17-amd64.tar.zst
cd weather-to-docx-offline-0.3.1-astra17-amd64
sudo ./setup.sh \
  --keyring /root/weather-release-keyring.gpg
```

Для неподписанного стендового комплекта:

```bash
sudo ./setup.sh
```

`--keyring` реально передаётся техническому установщику через `WTD_GPG_KEYRING`. Если внутри комплекта есть `SHA256SUMS.sig`, а доверенный keyring не указан, установка останавливается до изменения системы.

Дополнительные режимы:

```bash
sudo ./setup.sh --non-interactive
sudo ./setup.sh --skip-configure
```

## 7. Что делает setup.sh

1. Проверяет права root.
2. Проверяет SHA-256 и GPG-подпись.
3. Проверяет Astra Linux и архитектуру.
4. Устанавливает `.deb` только из вложенного APT.
5. Устанавливает Python-пакеты только из `wheelhouse`.
6. Создаёт пользователя `weatherdoc`.
7. Останавливает службы на короткое время.
8. Сохраняет SQLite-базу.
9. Разворачивает новый выпуск в `/opt/weather-to-docx/releases`.
10. Атомарно переключает ссылку `current`.
11. Запускает `doctor --deep`.
12. Открывает мастер настройки.
13. Запускает API, worker и выбранный Telegram-бот.

Для стендовой проверки вне Astra:

```bash
sudo WTD_ALLOW_NON_ASTRA=1 ./setup.sh
```

В рабочем контуре этот флаг использовать нельзя.

## 8. Мастер настройки

```text
Адрес HTTP-интерфейса
Порт
Резервный часовой пояс
Горизонт прогноза
Набор моделей
DaData API token
DaData secret
Включение Telegram
Telegram bot token
Разрешённые Telegram user ID
```

Резервный timezone применяется только тогда, когда локальная база IANA не смогла определить зону по координатам.

Секреты вводятся без отображения и хранятся здесь:

```text
/etc/weather-to-docx/weather-to-docx.env
```

Права:

```text
root:weatherdoc
0640
```

Повторно открыть мастер:

```bash
sudo weather-to-docx-configure
```

Ручное редактирование:

```bash
sudoedit /etc/weather-to-docx/weather-to-docx.env
```

После изменения:

```bash
sudo systemctl restart weather-to-docx-api weather-to-docx-worker
sudo systemctl restart weather-to-docx-telegram
```

## 9. Службы

```text
weather-to-docx-api.service
weather-to-docx-worker.service
weather-to-docx-telegram.service
```

API и worker включаются всегда. Telegram включается только при заполненных параметрах:

```dotenv
WTD_TELEGRAM_ENABLED="true"
WTD_TELEGRAM_BOT_TOKEN="token"
```

Состояние:

```bash
systemctl status weather-to-docx-api
systemctl status weather-to-docx-worker
systemctl status weather-to-docx-telegram
```

Журналы:

```bash
journalctl -u weather-to-docx-api -n 200 --no-pager
journalctl -u weather-to-docx-worker -n 200 --no-pager
journalctl -u weather-to-docx-telegram -n 200 --no-pager
```

## 10. Проверка очереди и worker

```bash
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8080/api/v1/diagnostics | python3 -m json.tool
```

В диагностике должны быть:

```text
worker.online
worker.last_seen_utc
queue.queued
queue.running
queue.stale_running
timezonefinder
```

Worker использует ограниченную аренду и heartbeat. После аварии просроченное задание возвращается в очередь автоматически.

## 11. Общая диагностика

```bash
sudo /opt/weather-to-docx/current/venv/bin/weather-to-docx doctor --deep
```

Автономный пример:

```bash
sudo -u weatherdoc \
  /opt/weather-to-docx/current/venv/bin/weather-to-docx \
  sample \
  --output /var/lib/weather-to-docx/documents/sample \
  --hours 24
```

## 12. Каталоги

```text
/opt/weather-to-docx/
├── releases/
├── current
└── previous

/etc/weather-to-docx/
├── weather-to-docx.env
└── keys/

/var/lib/weather-to-docx/
├── database/
├── cache/
├── documents/
├── incoming/
└── backups/
```

Данные и настройки не находятся внутри каталога релиза и сохраняются при обновлении.

## 13. Обновление

Распакуйте новый комплект и выполните:

```bash
sudo ./upgrade.sh
```

`upgrade.sh` использует тот же проверяемый `install.sh`. Для подписанного обновления заранее задайте доверенный keyring:

```bash
sudo WTD_GPG_KEYRING=/root/weather-release-keyring.gpg ./upgrade.sh
```

Проверка:

```bash
readlink -f /opt/weather-to-docx/current
readlink -f /opt/weather-to-docx/previous
sudo /opt/weather-to-docx/current/venv/bin/weather-to-docx doctor --deep
```

## 14. Откат

```bash
sudo ./rollback.sh
```

или:

```bash
sudo /opt/weather-to-docx/current/bin/rollback-release
```

Откат переключает `current` и `previous`, затем перезапускает доступные службы. Резервные копии SQLite находятся здесь:

```text
/var/lib/weather-to-docx/backups/
```

## 15. Удаление

Удалить приложение, сохранив базу, документы и настройки:

```bash
sudo ./uninstall.sh
```

Полное удаление:

```bash
sudo ./uninstall.sh --purge-data
```

## 16. Полностью изолированные прогнозы

Сервер без исходящего доступа не может обращаться к NOAA, ECMWF, DWD, ECCC, Open-Meteo, DaData или Telegram.

На шлюзе с Интернетом:

```bash
weather-to-docx collect-bundle \
  --config examples/locations.yml \
  --output forecast-bundle.tar.zst \
  --private-key /secure/forecast-private.pem
```

В закрытом контуре:

```bash
weather-to-docx generate-bundle \
  --bundle forecast-bundle.tar.zst \
  --public-key /etc/weather-to-docx/keys/forecast-public.pem \
  --require-signature \
  --output /var/lib/weather-to-docx/documents
```

Проверяются Ed25519-подпись и SHA-256 нормализованных рядов.

## 17. Рекомендации по безопасности

- оставляйте API на `127.0.0.1`;
- для сетевого доступа используйте reverse proxy с TLS и аутентификацией;
- ограничивайте Telegram через `WTD_TELEGRAM_ALLOWED_USER_IDS`;
- не публикуйте DaData и Telegram token;
- подписывайте установочные и прогнозные пакеты;
- резервируйте `/etc/weather-to-docx` и `/var/lib/weather-to-docx`;
- проверяйте новый комплект на отдельном стенде Astra Linux.
