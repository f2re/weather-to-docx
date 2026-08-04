# 📦 Автономная установка на Astra Linux

## 1. Схема развёртывания

Приложение и свежие прогнозные данные доставляются раздельно:

```text
машина сборки с Интернетом
        │
        ├── офлайн-комплект приложения
        │
        └── подписанные пакеты свежих прогнозов
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

## 2. Состав комплекта

```text
weather-to-docx-offline-0.3.0-astra17-amd64/
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

`setup.sh` — рекомендуемая точка входа. `install.sh` выполняет только техническую установку и полезен для автоматизированного развёртывания.

## 3. Подготовка локального APT

На подключённой Astra Linux:

```bash
sudo APT_PACKAGES='python3.11 python3.11-venv ca-certificates zstd fonts-liberation2 libeccodes0 libeccodes-data' \
  bash scripts/build-astra-apt-repository.sh dist/apt-repository
```

Если утверждённый репозиторий не содержит Python 3.11, используйте одобренный частный runtime через `RUNTIME_DIR`.

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

Формируются:

```text
dist/weather-to-docx-offline-0.3.0-astra17-amd64.tar.zst
dist/weather-to-docx-offline-0.3.0-astra17-amd64.tar.zst.sha256
dist/weather-to-docx-offline-0.3.0-astra17-amd64.tar.zst.asc
```

Сценарий включает в `wheelhouse` все зависимости, в том числе `python-telegram-bot`. Установка на целевой машине использует `pip --no-index`.

## 5. Проверка перед переносом

```bash
cd dist
sha256sum -c weather-to-docx-offline-*.tar.zst.sha256

gpg --verify \
  weather-to-docx-offline-*.tar.zst.asc \
  weather-to-docx-offline-*.tar.zst
```

Архив и подпись переносятся разрешённым носителем.

## 6. Установка одной командой

```bash
tar --zstd -xf weather-to-docx-offline-0.3.0-astra17-amd64.tar.zst
cd weather-to-docx-offline-0.3.0-astra17-amd64
sudo ./setup.sh
```

`setup.sh` последовательно:

1. запускает проверяемый `install.sh`;
2. проверяет SHA-256 и подпись комплекта;
3. проверяет Astra Linux и архитектуру;
4. устанавливает `.deb` только из вложенного APT;
5. устанавливает Python-пакеты только из `wheelhouse`;
6. создаёт системного пользователя `weatherdoc`;
7. сохраняет существующую базу;
8. разворачивает новую версию в `/opt/weather-to-docx/releases`;
9. атомарно переключает ссылку `current`;
10. запускает автономную диагностику и тестовый DOCX;
11. открывает мастер настройки;
12. спрашивает модели, DaData и Telegram;
13. запускает выбранные systemd-службы.

Для стендовой проверки вне Astra разрешено явно указать:

```bash
sudo WTD_ALLOW_NON_ASTRA=1 ./setup.sh
```

В рабочем контуре этот флаг использовать не следует.

## 7. Что спрашивает мастер

```text
Адрес HTTP-интерфейса
Порт
Часовой пояс
Горизонт прогноза
Набор моделей
DaData API token
DaData secret
Нужно ли включить Telegram
Telegram bot token
Разрешённые Telegram user ID
```

Секреты вводятся без отображения. Настройки сохраняются с правами `0640`:

```text
/etc/weather-to-docx/weather-to-docx.env
```

Повторно запустить мастер:

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

## 8. Службы

```text
weather-to-docx-api.service
weather-to-docx-worker.service
weather-to-docx-telegram.service
```

API и worker включаются всегда. Telegram включается только при:

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

## 9. Диагностика

```bash
sudo /opt/weather-to-docx/current/venv/bin/weather-to-docx doctor --deep
curl -fsS http://127.0.0.1:8080/health
```

Автономный пример:

```bash
sudo -u weatherdoc \
  /opt/weather-to-docx/current/venv/bin/weather-to-docx \
  sample \
  --output /var/lib/weather-to-docx/documents/sample \
  --hours 24
```

## 10. Каталоги

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

## 11. Обновление

Распакуйте новый комплект и выполните:

```bash
sudo ./upgrade.sh
```

После технического обновления мастер обычно не нужен: существующие токены и настройки сохраняются.

Проверка:

```bash
readlink -f /opt/weather-to-docx/current
readlink -f /opt/weather-to-docx/previous
sudo /opt/weather-to-docx/current/venv/bin/weather-to-docx doctor --deep
```

## 12. Откат

```bash
sudo ./rollback.sh
```

или:

```bash
sudo /opt/weather-to-docx/current/bin/rollback-release
```

Откат переключает `current` и `previous` и перезапускает API, worker и Telegram. Резервные копии SQLite находятся в:

```text
/var/lib/weather-to-docx/backups/
```

## 13. Удаление

Удалить приложение, сохранив базу, документы и токены:

```bash
sudo ./uninstall.sh
```

Полностью удалить приложение и данные:

```bash
sudo ./uninstall.sh --purge-data
```

## 14. Полностью изолированные прогнозы

Сервер без исходящего доступа не может самостоятельно обращаться к NOAA, ECMWF, DWD, ECCC, Open-Meteo, DaData или Telegram.

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

## 15. Рекомендации по безопасности

- ограничьте Telegram через `WTD_TELEGRAM_ALLOWED_USER_IDS`;
- не публикуйте DaData и Telegram token;
- не передавайте secret в веб-интерфейс;
- держите API на `127.0.0.1` либо используйте reverse proxy с TLS;
- подписывайте установочные и прогнозные пакеты;
- сохраняйте резервные копии `/etc/weather-to-docx` и `/var/lib/weather-to-docx`;
- проверяйте новый комплект на отдельном стенде Astra Linux.
