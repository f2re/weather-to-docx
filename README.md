# 🌦️ Weather to DOCX

Система получает прогнозы погоды по одной или нескольким координатам и формирует **отдельный профессионально оформленный DOCX для каждой точки**.

В каждой секции модели создаются ровно две рабочие таблицы:

1. ☀️ **Наглядный прогноз** — локальные PNG-пиктограммы, температура, осадки, ветер, порывы, давление и облачность.
2. 📊 **Подробный почасовой отчёт** — температура и влажность, давление, ветер, осадки, снег, облачность, видимость, конвекция, радиация, почва и поверхностный обмен.

Проект рассчитан на Astra Linux и закрытые контуры: приложение и зависимости собираются на машине с Интернетом, переносятся одним комплектом и устанавливаются **без сетевых обращений**.

> Статус: рабочий MVP `0.1.0`. Уже реализованы генерация DOCX, пакетная обработка координат, очередь SQLite, HTTP API, источник Open-Meteo/GFS, прямой загрузчик NOAA GFS/NOMADS, автономная диагностика и подписанные пакеты прогноза `.tar.zst`.

---

## ✨ Что уже работает

- несколько координат в одном задании;
- отдельный DOCX по каждой координате;
- несколько моделей в одном документе, каждая подписана отдельно;
- две таблицы по каждой модели;
- локальные PNG-иконки без CDN, эмодзи-шрифтов и доступа к Интернету;
- A3/A4 в альбомной ориентации, повтор заголовков на новых страницах;
- маркировка рассчитанных, интерполированных и сомнительных величин;
- ошибка одного источника не блокирует остальные координаты и модели;
- ZIP с документами и `manifest.json` с контрольными суммами;
- очередь заданий SQLite WAL;
- FastAPI и Swagger UI;
- прямое получение подмножеств GRIB2 NOAA GFS 0.25°;
- перенос нормализованных прогнозов в изолированный контур;
- подпись пакетов Ed25519 и проверка SHA-256;
- автономный тестовый источник для проверки установки без Интернета;
- установочные и откатные сценарии для Astra Linux.

---

## 🛰️ Источники: что и откуда

| `source_id` | Что используется | Откуда поступают данные | Горизонт | Состояние |
|---|---|---|---:|---|
| `open_meteo_gfs` | NOAA GFS, почасовой ряд после обработки Open-Meteo | `https://api.open-meteo.com/v1/gfs` | до 16 суток | готов |
| `noaa_gfs_0p25` | исходные подмножества GFS 0.25° в GRIB2 | NOAA/NCEP NOMADS, `filter_gfs_0p25.pl` | до 384 часов | готов, требуется ecCodes |
| `demo` | синтетический ряд | встроенный генератор | до 16 суток | только проверка |

### `open_meteo_gfs`

Используется для быстрого запуска и как резервный канал. Получаются почасовые поля:

- температура, точка росы, относительная влажность, ощущаемая температура;
- давление на уровне моря и у поверхности;
- скорость, направление и порывы ветра;
- осадки, дождь, ливни, снег, вероятность осадков;
- общая, нижняя, средняя и верхняя облачность;
- видимость, CAPE;
- коротковолновая, прямая и рассеянная радиация;
- продолжительность солнечного сияния;
- эвапотранспирация, ET₀, дефицит давления водяного пара;
- температура и влажность почвы по слоям.

Ограничение: стандартный ответ Open-Meteo не сообщает точное время исходного цикла GFS. Это автоматически отмечается в документе. Для строгой воспроизводимости применяется `noaa_gfs_0p25`.

### `noaa_gfs_0p25`

Загрузчик формирует запрос к официальному фильтру NOAA NOMADS и получает только нужные поля и небольшой прямоугольник вокруг координаты. Полные глобальные GRIB-файлы не скачиваются.

Основные поля:

- TMP/RH/DPT на 2 м;
- UGRD/VGRD на 10 м и GUST;
- PRMSL/PRES;
- APCP/ACPCP;
- TCDC/LCDC/MCDC/HCDC;
- VIS, CAPE, CIN, DSWRF, PWAT, HPBL, снег.

Цикл определяется и сохраняется точно: `00`, `06`, `12` или `18 UTC`. Для декодирования требуется системная библиотека ECMWF ecCodes и Python-дополнение `weather-to-docx[grib]`.

Подробная таблица источников и ограничений: [`docs/SOURCES.md`](docs/SOURCES.md).

---

## 🧱 Архитектура

```text
Open-Meteo JSON ───────┐
NOAA GFS GRIB2 ────────┼──► адаптеры источников
Прогнозный пакет ──────┘             │
                                     ▼
                         единая модель ForecastSeries
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
              контроль/расчёты                manifest.json
                     │
                     ▼
           генератор DOCX + локальные PNG
                     │
                     ▼
        отдельные DOCX по координатам + общий ZIP
```

Ключевой принцип: генератор Word не знает, пришёл прогноз из JSON, GRIB2 или автономного пакета. Все источники сначала приводятся к единой нормализованной схеме.

Подробнее: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 🚀 Быстрый запуск для разработки

Требуется Python 3.11 или новее.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Проверка без Интернета:

```bash
weather-to-docx init
weather-to-docx doctor --deep
weather-to-docx sample --output var/sample --hours 48
```

Результат:

```text
var/sample/<batch-id>/
├── Прогноз_Демонстрационная_точка_YYYY-MM-DD.docx
├── manifest.json
└── demo_forecast.zip
```

Запуск тестов:

```bash
pytest
# или
make check
```

---

## 📍 Настройка координат и моделей

Пример: [`examples/locations.yml`](examples/locations.yml).

```yaml
batch_name: forecast_for_objects

locations:
  - id: spb-office
    name: Санкт-Петербург, объект 1
    latitude: 59.9386
    longitude: 30.3141
    elevation_m: 12
    timezone: Europe/Moscow

  - id: pskov-field
    name: Псковская область, поле 7
    latitude: 57.8136
    longitude: 28.3496
    elevation_m: 48
    timezone: Europe/Moscow

sources:
  - source_id: open_meteo_gfs
    forecast_days: 10

  # Прямой официальный GFS. Нужен ecCodes.
  - source_id: noaa_gfs_0p25
    forecast_days: 7
    options:
      hourly_to_120: true
      max_concurrency: 4
      box_degrees: 0.5

document:
  title: Метеорологический прогноз по объекту
  page_size: A3
  summary_interval_hours: 3
  extended_summary_interval_hours: 6
  summary_switch_hour: 120
```

Сформировать документы непосредственно:

```bash
weather-to-docx generate \
  --config examples/locations.yml \
  --output var/documents
```

---

## 🧰 Полезные команды

```bash
# Версия установленного приложения
weather-to-docx --version

# Инициализация каталогов и SQLite
weather-to-docx init

# Список источников и статус реализации
weather-to-docx sources

# Немедленная пакетная генерация
weather-to-docx generate -c examples/locations.yml -o var/documents

# Поставить задание в очередь
weather-to-docx enqueue -c examples/locations.yml

# Обработать одно задание
weather-to-docx worker --once

# Постоянный обработчик очереди
weather-to-docx worker --poll-interval 5

# HTTP API и Swagger
weather-to-docx api --host 127.0.0.1 --port 8080
# Swagger: http://127.0.0.1:8080/docs

# Полная локальная диагностика
weather-to-docx doctor --deep
```

---

## 🔐 Полностью изолированный контур

На шлюзе с Интернетом:

```bash
weather-to-docx keys generate \
  --private-key keys/forecast-bundle-private.pem \
  --public-key keys/forecast-bundle-public.pem

weather-to-docx collect-bundle \
  --config examples/locations.yml \
  --output forecast-bundle-20260803T1200Z.tar.zst \
  --private-key keys/forecast-bundle-private.pem
```

В закрытом контуре передаётся только:

- `forecast-bundle-*.tar.zst`;
- открытый ключ `forecast-bundle-public.pem`.

Проверка подписи и формирование DOCX без Интернета:

```bash
weather-to-docx generate-bundle \
  --bundle forecast-bundle-20260803T1200Z.tar.zst \
  --public-key /etc/weather-to-docx/keys/forecast-bundle-public.pem \
  --require-signature \
  --output /var/lib/weather-to-docx/documents
```

Пакет содержит нормализованные ряды, координаты, происхождение модели, цикл, контрольные суммы и подпись манифеста. Закрытому серверу не нужны API-ключи внешних сервисов.

---

## 🖥️ HTTP API

Запуск:

```bash
weather-to-docx api --host 0.0.0.0 --port 8080
weather-to-docx worker
```

Создание задания:

```bash
curl -X POST http://127.0.0.1:8080/api/v1/jobs \
  -H 'Content-Type: application/json' \
  --data-binary @examples/job.json
```

Проверка:

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/api/v1/sources
curl http://127.0.0.1:8080/api/v1/jobs
curl http://127.0.0.1:8080/api/v1/diagnostics
```

Описание API: [`docs/API.md`](docs/API.md).

---

## 📦 Astra Linux: автономная установка

Сборка должна выполняться **в Astra Linux той же версии и архитектуры, что и целевая система**. Это принципиально для `glibc`, Python, Pillow, cryptography и ecCodes.

На подключённой сборочной машине:

```bash
sudo bash scripts/build-astra-apt-repository.sh dist/apt-repository
bash scripts/build-offline-bundle.sh
```

Получится файл вида:

```text
dist/weather-to-docx-offline-0.1.0-astra17-amd64.tar.zst
```

На изолированной Astra Linux:

```bash
tar --zstd -xf weather-to-docx-offline-0.1.0-astra17-amd64.tar.zst
cd weather-to-docx-offline-0.1.0-astra17-amd64
sudo ./install.sh
sudo ./doctor.sh
```

Обновление:

```bash
sudo ./upgrade.sh
```

Откат:

```bash
sudo /opt/weather-to-docx/current/bin/rollback-release
# либо из распакованного комплекта
sudo ./rollback.sh
```

Установщик не выполняет `pip install` из Интернета и не обращается к внешним APT-репозиториям. База, настройки, документы, входящие пакеты и ключи располагаются вне каталога версии и не удаляются при обновлении.

Полное руководство: [`docs/OFFLINE_INSTALL.md`](docs/OFFLINE_INSTALL.md).

---

## 🗂️ Каталоги установленной системы

```text
/opt/weather-to-docx/
├── releases/<version>/
├── runtime/
└── current -> releases/<version>

/etc/weather-to-docx/
├── weather-to-docx.env
└── keys/

/var/lib/weather-to-docx/
├── database/
├── cache/
├── documents/
└── incoming/
```

---

## ⚠️ Правила достоверности

Система намеренно не маскирует неопределённость:

- отсутствующий параметр выводится как `—`, а не как ноль;
- рассчитанное значение получает `*`;
- интерполированное значение получает `≈`;
- точный цикл модели выводится только тогда, когда он известен;
- детерминированные осадки не выдаются за вероятность;
- одна модель не подменяется другой;
- старый цикл не используется скрытно;
- отказ одного источника фиксируется в манифесте, но не блокирует остальные документы.

---

## 🧭 Ближайшие этапы

- ECMWF IFS Open Data и AIFS;
- NOAA GEFS: вероятности, среднее и разброс ансамбля;
- DWD ICON и ECCC GDPS;
- Vue 3 + OpenLayers для карты, точек, задач и архива;
- редактор профилей столбцов и шаблонов DOCX;
- верификация прогнозов по наблюдениям;
- систематические поправки по точкам;
- Debian-пакеты и подписанный локальный APT-репозиторий релизов.

---

## 📚 Официальные ссылки

- Open-Meteo Forecast API: https://open-meteo.com/en/docs
- Open-Meteo GFS API: https://open-meteo.com/en/docs/gfs-api
- NOAA GFS product inventory: https://www.nco.ncep.noaa.gov/pmb/products/gfs/
- NOAA GFS NOMADS inventory: https://www.nco.ncep.noaa.gov/pmb/products/gfs/nomads/
- NOAA NOMADS GRIB filter: https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl
- ECMWF ecCodes: https://github.com/ecmwf/eccodes
- ECMWF Open Data: https://www.ecmwf.int/en/forecasts/datasets/open-data
- python-docx: https://python-docx.readthedocs.io/
- FastAPI: https://fastapi.tiangolo.com/
