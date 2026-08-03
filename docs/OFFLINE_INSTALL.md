# 📦 Автономная установка на Astra Linux

## 1. Принцип

Офлайн-комплект собирается на машине с Интернетом, которая совпадает с целевой системой по:

- выпуску Astra Linux;
- архитектуре (`amd64`, `arm64`);
- версии `glibc`;
- версии Python;
- источникам системных пакетов;
- режиму защищённости, если он влияет на разрешённые пакеты.

Копировать готовый `venv` с Ubuntu, Debian другой версии или macOS нельзя. Бинарные колёса `cryptography`, `Pillow` и `eccodes` должны собираться или скачиваться в совместимой среде.

## 2. Что содержит комплект

```text
weather-to-docx-offline-<version>-<target>/
├── VERSION
├── build-info.json
├── README.md
├── SHA256SUMS
├── SHA256SUMS.sig              # при включённой подписи GPG
├── wheelhouse/                 # приложение и Python-зависимости
├── apt-repository/             # необязательный локальный APT-репозиторий
├── runtime/                    # необязательный частный Python runtime
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

Пример с явно выбранным Python из репозитория организации:

```bash
sudo APT_PACKAGES='python3.11 python3.11-venv ca-certificates zstd fonts-liberation2 libeccodes0 libeccodes-data' \
  bash scripts/build-astra-apt-repository.sh dist/apt-repository
```

Сценарий скачивает `.deb`, формирует `Packages` и `Packages.gz`. Если в разрешённом репозитории Astra нет Python 3.11, используйте утверждённый частный runtime.

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
SIGNING_KEY='GPG_KEY_ID'          # необязательно
OUTPUT_DIR=dist
```

Полный пример:

```bash
TARGET_TAG=astra17-amd64 \
INCLUDE_GRIB=1 \
APT_REPOSITORY=dist/apt-repository \
RUNTIME_DIR=/opt/python311 \
SIGNING_KEY='release@example.org' \
  bash scripts/build-offline-bundle.sh
```

Результат:

```text
dist/weather-to-docx-offline-0.1.0-astra17-amd64.tar.zst
```

## 5. Проверка перед переносом

```bash
cd dist
sha256sum weather-to-docx-offline-*.tar.zst
```

При использовании GPG:

```bash
gpg --verify weather-to-docx-offline-*.tar.zst.asc weather-to-docx-offline-*.tar.zst
```

Архив и его подпись переносятся в закрытый контур через разрешённый носитель.

## 6. Установка в закрытом контуре

```bash
tar --zstd -xf weather-to-docx-offline-0.1.0-astra17-amd64.tar.zst
cd weather-to-docx-offline-0.1.0-astra17-amd64
sudo ./install.sh
```

Установщик:

1. проверяет контрольные суммы содержимого;
2. проверяет Astra Linux и архитектуру;
3. при наличии устанавливает `.deb` только из вложенного APT-репозитория;
4. создаёт пользователя `weatherdoc` без интерактивного входа;
5. создаёт каталог новой версии;
6. создаёт изолированный `venv`;
7. устанавливает Python-пакеты только из `wheelhouse`;
8. сохраняет базу и пользовательские данные;
9. выполняет `weather-to-docx init` и диагностику;
10. атомарно переключает `/opt/weather-to-docx/current`;
11. устанавливает и перезапускает systemd-службы;
12. при ошибке возвращает прежнюю версию.

Для испытаний на Debian-подобной системе, не являющейся Astra, проверку можно явно отключить:

```bash
sudo WTD_ALLOW_NON_ASTRA=1 ./install.sh
```

В производственной установке так делать не следует.

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

Автономный DOCX:

```bash
sudo -u weatherdoc /opt/weather-to-docx/current/venv/bin/weather-to-docx \
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

Данные не находятся внутри каталога релиза, поэтому не удаляются:

```text
/etc/weather-to-docx/
/var/lib/weather-to-docx/
```

Перед переключением создаётся резервная копия SQLite.

## 10. Откат

```bash
sudo /opt/weather-to-docx/current/bin/rollback-release
```

или:

```bash
sudo ./rollback.sh
```

Откат меняет символические ссылки `current` и `previous` местами и перезапускает службы. База не откатывается автоматически, поскольку обратимость миграции данных должна оцениваться отдельно. Перед обновлением резервная копия находится в:

```text
/var/lib/weather-to-docx/backups/
```

## 11. Удаление

Остановить приложение, сохранив данные:

```bash
sudo ./uninstall.sh
```

Полное удаление, включая базу, документы, кэш и настройки:

```bash
sudo ./uninstall.sh --purge-data
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
