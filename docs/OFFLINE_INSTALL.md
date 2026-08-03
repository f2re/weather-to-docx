# 📦 Автономная установка на Astra Linux

## 1. Принцип

Офлайн-комплект собирается на машине с Интернетом, которая совпадает с целевой системой по:

- выпуску Astra Linux;
- архитектуре (`amd64`, `arm64`);
- версии `glibc`;
- **основной и дополнительной версии Python**;
- источникам системных пакетов;
- режиму защищённости, если он влияет на разрешённые пакеты.

Копировать готовый `venv` с Ubuntu, Debian другой версии или macOS нельзя. Бинарные колёса `cryptography`, `Pillow`, `lxml`, `pydantic-core` и `eccodes` должны собираться или скачиваться в совместимой среде.

Сборщик записывает в `build-info.json` точную пару `python_major_minor`, например `3.11`. Установщик принимает только совместимый интерпретатор. Wheelhouse, собранный для Python 3.11, не будет ошибочно установлен через Python 3.12.

## 2. Что содержит комплект

```text
weather-to-docx-offline-<version>-<target>/
├── VERSION
├── build-info.json
├── README.md
├── CHANGELOG.md
├── SHA256SUMS
├── SHA256SUMS.sig              # при включённой подписи GPG
├── wheelhouse/                 # приложение и Python-зависимости
├── apt-repository/             # необязательный локальный APT-репозиторий
├── runtime/                    # необязательный частный Python runtime
├── sbom/cyclonedx.json
├── config/
├── examples/
├── docs/
├── systemd/
├── install.sh
├── upgrade.sh
├── rollback.sh
├── doctor.sh
└── uninstall.sh
```

Установочные сценарии не выполняют сетевые `pip install` и не добавляют внешние APT-репозитории.

## 3. Сборка локального APT-репозитория

На подключённой Astra Linux:

```bash
sudo bash scripts/build-astra-apt-repository.sh dist/apt-repository
```

Пакеты задаются переменной `APT_PACKAGES`. Значение по умолчанию:

```text
ca-certificates zstd fonts-liberation2 libeccodes0 libeccodes-data
```

Пример с явно выбранным Python:

```bash
sudo APT_PACKAGES='python3.11 python3.11-venv ca-certificates zstd fonts-liberation2 libeccodes0 libeccodes-data' \
  bash scripts/build-astra-apt-repository.sh dist/apt-repository
```

Сценарий скачивает `.deb`, формирует `Packages`, `Packages.gz` и `requested-packages.txt`. При установке `apt-get` получает пакеты только из вложенного файлового репозитория.

Если в разрешённом репозитории Astra нет Python 3.11, используйте утверждённый частный runtime.

## 4. Сборка Python-колёс и архива

```bash
bash scripts/build-offline-bundle.sh
```

Основные переменные:

```bash
TARGET_TAG=astra17-amd64          # имя целевой платформы
INCLUDE_GRIB=1                    # включить Python-обвязку ecCodes
APT_REPOSITORY=dist/apt-repository
RUNTIME_DIR=/opt/python311        # необязательно
PYTHON_BIN=python3.11             # интерпретатор сборки wheelhouse
SIGNING_KEY='GPG_KEY_ID'          # необязательно
OUTPUT_DIR=dist
```

Полный пример:

```bash
TARGET_TAG=astra17-amd64 \
INCLUDE_GRIB=1 \
APT_REPOSITORY=dist/apt-repository \
RUNTIME_DIR=/opt/python311 \
PYTHON_BIN=python3.11 \
SIGNING_KEY='release@example.org' \
  bash scripts/build-offline-bundle.sh
```

Результат версии 0.2.0:

```text
dist/weather-to-docx-offline-0.2.0-astra17-amd64.tar.zst
dist/weather-to-docx-offline-0.2.0-astra17-amd64.tar.zst.sha256
```

## 5. Проверка перед переносом

Проверка внешней контрольной суммы:

```bash
sha256sum -c dist/weather-to-docx-offline-0.2.0-astra17-amd64.tar.zst.sha256
```

Проверка содержимого после распаковки:

```bash
tar --zstd -xf dist/weather-to-docx-offline-0.2.0-astra17-amd64.tar.zst
cd weather-to-docx-offline-0.2.0-astra17-amd64
sha256sum -c SHA256SUMS
```

При использовании GPG:

```bash
gpg --verify weather-to-docx-offline-*.tar.zst.asc weather-to-docx-offline-*.tar.zst
```

Архив, контрольная сумма и подпись переносятся в закрытый контур через разрешённый носитель.

## 6. Установка в закрытом контуре

```bash
tar --zstd -xf weather-to-docx-offline-0.2.0-astra17-amd64.tar.zst
cd weather-to-docx-offline-0.2.0-astra17-amd64
sudo ./install.sh
```

Установщик:

1. проверяет SHA-256 каждого файла комплекта;
2. при наличии проверяет GPG-подпись `SHA256SUMS` доверенным keyring;
3. проверяет Astra Linux и архитектуру;
4. проверяет совместимость версии Python с wheelhouse;
5. при наличии устанавливает `.deb` только из вложенного APT-репозитория;
6. создаёт пользователя `weatherdoc` без интерактивного входа;
7. создаёт каталог новой версии во временном месте;
8. создаёт изолированный `venv` и выполняет `pip --no-index`;
9. сохраняет базу и пользовательские данные;
10. атомарно переключает `/opt/weather-to-docx/current`;
11. выполняет `weather-to-docx init` и глубокую диагностику от имени `weatherdoc`;
12. устанавливает и перезапускает systemd-службы;
13. при ошибке возвращает прежнюю версию и перезапускает старые службы.

### Явный выбор Python

Обычно установщик находит версию из `build-info.json` автоматически. При нескольких интерпретаторах можно указать путь:

```bash
sudo WTD_PYTHON=/usr/bin/python3.11 ./install.sh
```

Версия должна точно совпадать с `python_major_minor` wheelhouse.

### Испытание не на Astra Linux

Для CI или отдельного Debian-стенда:

```bash
sudo WTD_ALLOW_NON_ASTRA=1 ./install.sh
```

Отключение systemd допускается только для контейнера/CI:

```bash
sudo WTD_ALLOW_NON_ASTRA=1 WTD_SKIP_SYSTEMD=1 ./install.sh
```

В производственной Astra Linux эти обходы применять не следует.

## 7. Конфигурация

Основной файл окружения:

```text
/etc/weather-to-docx/weather-to-docx.env
```

Пример:

```bash
WTD_DATA_DIR=/var/lib/weather-to-docx
WTD_LOG_LEVEL=INFO
WTD_HTTP_TIMEOUT_SECONDS=60
WTD_HTTP_MAX_RETRIES=3
WTD_REQUIRE_BUNDLE_SIGNATURE=true
WTD_BUNDLE_PUBLIC_KEY=/etc/weather-to-docx/keys/forecast-bundle-public.pem
```

После изменения:

```bash
sudo systemctl restart weather-to-docx-api weather-to-docx-worker
```

## 8. Проверка системы

```bash
sudo ./doctor.sh
sudo systemctl status weather-to-docx-api weather-to-docx-worker
curl -fsS http://127.0.0.1:8080/health
```

Интерфейс:

```text
http://127.0.0.1:8080/
```

Автономный DOCX без сетевых запросов:

```bash
sudo runuser -u weatherdoc -- env \
  WTD_DATA_DIR=/var/lib/weather-to-docx \
  /opt/weather-to-docx/current/venv/bin/weather-to-docx \
  sample --output /var/lib/weather-to-docx/documents/sample --hours 24
```

Журналы:

```bash
journalctl -u weather-to-docx-api -n 200 --no-pager
journalctl -u weather-to-docx-worker -n 200 --no-pager
```

## 9. Обновление

Распакуйте новый комплект и выполните:

```bash
sudo ./upgrade.sh
```

Данные находятся вне каталога релиза и сохраняются:

```text
/etc/weather-to-docx/
/var/lib/weather-to-docx/
```

Перед переключением создаётся архив SQLite в:

```text
/var/lib/weather-to-docx/backups/
```

## 10. Откат

```bash
sudo /opt/weather-to-docx/current/bin/rollback-release
```

или:

```bash
sudo ./rollback.sh
```

Откат меняет ссылки `current` и `previous` местами и перезапускает службы. База автоматически не откатывается, поскольку обратимость миграции данных должна оцениваться отдельно.

## 11. Удаление

Удалить приложение, сохранив настройки и данные:

```bash
sudo ./uninstall.sh
```

Полное удаление:

```bash
sudo ./uninstall.sh --purge-data
```

Для CI без systemd:

```bash
sudo WTD_SKIP_SYSTEMD=1 ./uninstall.sh --purge-data
```

## 12. Полностью изолированные прогнозные данные

Установка приложения и доставка свежих прогнозов — разные процессы. Если сервер не имеет исходящего доступа, на шлюзе выполняется:

```bash
weather-to-docx collect-bundle \
  --config examples/locations.yml \
  --output forecast-bundle.tar.zst \
  --private-key /secure/forecast-bundle-private.pem
```

В закрытом контуре:

```bash
weather-to-docx generate-bundle \
  --bundle forecast-bundle.tar.zst \
  --public-key /etc/weather-to-docx/keys/forecast-bundle-public.pem \
  --require-signature \
  --output /var/lib/weather-to-docx/documents
```

Закрытый сервер проверяет Ed25519-подпись манифеста и SHA-256 каждого нормализованного ряда.

## 13. Что проверяет CI

Для Python 3.11 CI выполняет реальный цикл:

1. собирает wheelhouse;
2. формирует `.tar.zst`;
3. проверяет внешнюю и внутренние контрольные суммы;
4. распаковывает комплект;
5. устанавливает его в `/opt`, `/etc` и `/var/lib` без Интернета;
6. запускает установленную CLI;
7. проверяет наличие локального интерфейса в wheel;
8. формирует DOCX от имени `weatherdoc`;
9. выполняет полное удаление.

Это не заменяет приёмку на целевой Astra Linux, но исключает повреждённые архивы, несовместимую версию Python, сетевой `pip`, ошибки путей и неработающий установленный entrypoint.
