# 🌦️ Weather to DOCX

**Weather to DOCX** получает прогнозы погоды по одной или нескольким координатам и формирует отдельный профессионально оформленный документ Microsoft Word для каждой точки.

В секции каждой прогностической модели создаются ровно две таблицы:

1. ☀️ **Наглядный прогноз** — локальные пиктограммы погоды, температура, осадки, вероятность осадков, ветер, порывы, давление и облачность.
2. 📊 **Подробный метеорологический отчёт по срокам** — оперативные параметры, ансамблевые статистики, вертикальные уровни и остальные доступные поля модели.

Система рассчитана на **Astra Linux, Debian-подобные системы и закрытые контуры**. Приложение, Python-зависимости, системные пакеты, документация и сценарии обслуживания собираются на машине с Интернетом, после чего устанавливаются на целевой системе без сетевых обращений.

> Текущая версия: **0.2.0**. Реализованы многомодельная генерация DOCX, детерминированные и ансамблевые источники, локальный интерфейс оператора, очередь SQLite, прямой NOAA GFS/GRIB2, подписанные прогнозные пакеты и автономная установка.

---

## ✨ Возможности

- до 1000 координат в одном задании;
- отдельный DOCX по каждой координате;
- несколько моделей в одном документе без смешивания источников и циклов;
- две подписанные таблицы по каждой модели;
- локальные PNG-пиктограммы без CDN и внешних шрифтов;
- формат A3 или A4, альбомная ориентация, повтор заголовков таблиц;
- явная маркировка рассчитанных, интерполированных, исправленных и сомнительных значений;
- вывод всех доступных параметров модели во второй таблице;
- среднее, разброс, 10-й и 90-й процентили ансамбля;
- вероятность осадков только по членам ансамбля и заданному порогу;
- круговое усреднение направления ветра;
- ошибка одной точки или модели не блокирует остальные результаты;
- ZIP-архив пакета, `manifest.json` и SHA-256 каждого артефакта;
- постоянный справочник координат в SQLite WAL;
- локальный интерфейс оператора, REST API и Swagger;
- отдельная служба обработки очереди;
- перенос нормализованных прогнозов в полностью изолированный контур;
- подпись прогнозных пакетов Ed25519;
- атомарная установка, обновление и откат на Astra Linux;
- автономная проверка через встроенный демонстрационный источник.

---

## 🛰️ Источники прогнозов

Каждый адаптер имеет отдельный `source_id`. В документ записываются организация, модель, способ доставки, горизонт, сетка, время получения, цикл при его наличии, условия использования и технический источник.

### Детерминированные модели

| `source_id` | Модель | Доставка данных | Максимальный горизонт |
|---|---|---|---:|
| `open_meteo_gfs` | NOAA GFS 0.25° | Open-Meteo GFS API | 16 суток |
| `open_meteo_ecmwf_ifs` | ECMWF IFS 0.25° Open Data | Open-Meteo ECMWF API | 15 суток |
| `open_meteo_ecmwf_aifs` | ECMWF AIFS 0.25° Single | Open-Meteo ECMWF API | 15 суток |
| `open_meteo_dwd_icon_global` | DWD ICON Global | Open-Meteo DWD ICON API | 8 суток |
| `open_meteo_gem_gdps` | ECCC GEM Global / GDPS | Open-Meteo GEM API | 10 суток |
| `noaa_gfs_0p25` | NOAA GFS 0.25° GRIB2 | прямой NOAA/NCEP NOMADS | 384 часа |

### Ансамблевые модели

| `source_id` | Ансамбль | Рассчитываемые продукты | Максимальный горизонт |
|---|---|---|---:|
| `open_meteo_gefs_0p25` | NOAA GEFS 0.25° | среднее, σ, p10, p90, PoP | 10 суток |
| `open_meteo_gefs_0p5` | NOAA GEFS 0.5° | дальняя ансамблевая тенденция | 35 суток |
| `open_meteo_ecmwf_ifs_ensemble` | ECMWF IFS ENS 0.25° | среднее, σ, p10, p90, PoP | 15 суток |
| `open_meteo_ecmwf_aifs_ensemble` | ECMWF AIFS ENS 0.25° | среднее, σ, p10, p90, PoP | 15 суток |
| `open_meteo_dwd_icon_eps` | DWD ICON Global EPS | среднее, σ, p10, p90, PoP | 8 суток |
| `open_meteo_gem_geps` | ECCC GEPS | среднее, σ, p10, p90, PoP | 16 суток |

### Служебный источник

| `source_id` | Назначение |
|---|---|
| `demo` | автономная проверка установки, DOCX, иконок, SQLite и прав каталогов; не является реальным прогнозом |

### Важное различие источников

Адаптеры с префиксом `open_meteo_` получают данные конкретной явно выбранной модели через Open-Meteo. Режимы `best_match` и `seamless` не используются, поэтому GFS, IFS, AIFS, ICON и GDPS не смешиваются между собой.

Стандартная выдача Open-Meteo не всегда сообщает точное время исходного расчётного цикла. В таком случае документ содержит время получения и предупреждение **«цикл не указан поставщиком»**. Для строгой воспроизводимости GFS используется `noaa_gfs_0p25`, который получает исходные GRIB2 и фиксирует цикл `00`, `06`, `12` или `18 UTC`.

Подробности, лицензии и ограничения: [`docs/SOURCES.md`](docs/SOURCES.md).

---

## 🌧️ Как рассчитывается вероятность осадков

Детерминированная сумма осадков не выдаётся за вероятность.

Для ансамбля применяется формула:

```text
PoP = N(члены с осадками ≥ порога) / N(доступные члены) × 100 %
```

Порог задаётся в миллиметрах за интервал:

```yaml
sources:
  - source_id: open_meteo_gefs_0p25
    forecast_days: 10
    options:
      precipitation_threshold_mm: 0.1
```

В примечании к значению сохраняются порог и фактическое число доступных членов. При неполном ансамбле расчёт продолжается по имеющимся членам с явным указанием их количества.

---

## 📄 Состав DOCX

### Титульный блок

- название объекта;
- координаты и высота;
- часовой пояс;
- дата формирования;
- перечень источников;
- организация и ответственный специалист.

### Секция модели

Перед таблицами указываются:

- поставщик и название модели;
- внутренний `source_id`;
- идентификатор модели внешнего поставщика;
- цикл либо отметка об отсутствии точного цикла;
- время получения;
- горизонт и шаг выдачи;
- разрешение и тип сетки;
- число членов ансамбля;
- продукт и способ доставки.

### Таблица 1 — наглядный прогноз

- локальное время;
- пиктограмма и описание явления;
- температура и ощущаемая температура;
- осадки и вероятность;
- скорость, направление и румб ветра;
- порывы;
- давление;
- облачность.

### Таблица 2 — подробный отчёт

Основные группы:

- температура и влажность;
- давление;
- ветер;
- осадки и снег;
- облачность и видимость;
- конвекция;
- радиация;
- температура и влажность почвы;
- эвапотранспирация и пограничный слой;
- ансамблевые статистики;
- изобарические уровни;
- остальные поля, предоставленные адаптером.

Отсутствующее значение отображается как `—`. Рассчитанное значение получает `*`, интерполированное — `≈`, исправленное контролем качества — `†`, устаревшее — `!`, сомнительное — `?`.

---

## 🖥️ Интерфейс оператора

Запустите API и обработчик очереди:

```bash
weather-to-docx api --host 127.0.0.1 --port 8080
weather-to-docx worker --poll-interval 5
```

Откройте:

```text
http://127.0.0.1:8080/
```

Интерфейс полностью локальный: JavaScript, стили и шрифтовой стек не загружаются из Интернета.

В интерфейсе можно:

- добавлять, изменять и удалять координаты;
- группировать точки;
- импортировать и экспортировать справочник JSON;
- выбирать несколько координат;
- выбирать детерминированные модели и ансамбли;
- задавать горизонт отдельно для каждого источника;
- выбирать A3/A4 и шаг обзорной таблицы;
- включать полный набор параметров;
- ставить пакет в очередь;
- отслеживать состояние выполнения;
- повторять и отменять задания;
- скачивать DOCX, ZIP и манифесты.

Swagger доступен по адресу:

```text
http://127.0.0.1:8080/docs
```

---

## 🚀 Быстрый запуск из исходного кода

Требуется Python 3.11 или новее.

```bash
git clone https://github.com/f2re/weather-to-docx.git
cd weather-to-docx

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Инициализация и автономная проверка:

```bash
weather-to-docx init
weather-to-docx doctor --deep
weather-to-docx sample --output var/sample --hours 48
```

Проверки разработчика:

```bash
ruff check .
pytest
python -m compileall -q src
node --check src/weather_to_docx/static/app.js
for script in scripts/*.sh; do bash -n "$script"; done
```

Или одной командой:

```bash
make check
```

---

## 📍 Пакетная генерация из YAML

Полный пример: [`examples/locations.yml`](examples/locations.yml).

Минимальная конфигурация:

```yaml
batch_name: operational_forecast

locations:
  - id: spb-office
    name: Санкт-Петербург, объект 1
    latitude: 59.9386
    longitude: 30.3141
    elevation_m: 12
    timezone: Europe/Moscow
    group: Основные объекты

  - id: pskov-field
    name: Псковская область, поле 7
    latitude: 57.8136
    longitude: 28.3496
    elevation_m: 48
    timezone: Europe/Moscow
    group: Поля

sources:
  - source_id: open_meteo_gfs
    forecast_days: 10

  - source_id: open_meteo_ecmwf_ifs
    forecast_days: 10

  - source_id: open_meteo_dwd_icon_global
    forecast_days: 8

  - source_id: open_meteo_gefs_0p25
    forecast_days: 10
    options:
      precipitation_threshold_mm: 0.1

document:
  title: Метеорологический прогноз по объекту
  page_size: A3
  summary_interval_hours: 3
  extended_summary_interval_hours: 6
  summary_switch_hour: 120
  include_detailed_table: true
  include_all_parameters: true
  parameter_profile: all
```

Немедленная генерация:

```bash
weather-to-docx generate \
  --config examples/locations.yml \
  --output var/documents
```

Через очередь:

```bash
weather-to-docx enqueue --config examples/locations.yml
weather-to-docx worker --once
```

---

## 🧰 Полезные команды

```bash
# Версия
weather-to-docx --version

# Создать каталоги и SQLite
weather-to-docx init

# Показать зарегистрированные источники
weather-to-docx sources

# Проверить окружение, права, zstd и ecCodes
weather-to-docx doctor --deep

# Автономный тестовый DOCX
weather-to-docx sample --output var/sample --hours 48

# Немедленная многомодельная генерация
weather-to-docx generate -c examples/locations.yml -o var/documents

# Поставить пакетное задание
weather-to-docx enqueue -c examples/locations.yml

# Обработать одно задание
weather-to-docx worker --once

# Постоянно обрабатывать очередь
weather-to-docx worker --poll-interval 5

# Локальный интерфейс и API
weather-to-docx api --host 127.0.0.1 --port 8080

# Создать резервную копию служебных данных
weather-to-docx backup
```

Полный список:

```bash
weather-to-docx --help
```

---

## 🔌 Основные методы API

```text
GET    /health
GET    /api/v1/diagnostics
GET    /api/v1/sources

GET    /api/v1/locations
POST   /api/v1/locations
GET    /api/v1/locations/{id}
PUT    /api/v1/locations/{id}
DELETE /api/v1/locations/{id}
POST   /api/v1/locations/import
GET    /api/v1/location-catalog/export

POST   /api/v1/jobs
GET    /api/v1/jobs
GET    /api/v1/jobs/{id}
POST   /api/v1/jobs/{id}/cancel
POST   /api/v1/jobs/{id}/retry
GET    /api/v1/jobs/{id}/artifacts/{index}
```

Создание задания:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/jobs \
  -H 'Content-Type: application/json' \
  --data-binary @examples/job.json
```

Подробности: [`docs/API.md`](docs/API.md).

---

## 🔐 Полностью изолированный контур

Сервер формирования документов может не иметь доступа к Интернету. Сетевые запросы выполняются на отдельном шлюзе, после чего нормализованные прогнозы переносятся подписанным пакетом.

### На шлюзе с Интернетом

Один раз создайте ключи:

```bash
weather-to-docx keys generate \
  --private-key keys/forecast-bundle-private.pem \
  --public-key keys/forecast-bundle-public.pem
```

Получите прогнозы и создайте пакет:

```bash
weather-to-docx collect-bundle \
  --config examples/locations.yml \
  --output forecast-bundle-20260803T1200Z.tar.zst \
  --private-key keys/forecast-bundle-private.pem
```

### В закрытом контуре

```bash
weather-to-docx generate-bundle \
  --bundle forecast-bundle-20260803T1200Z.tar.zst \
  --public-key /etc/weather-to-docx/keys/forecast-bundle-public.pem \
  --require-signature \
  --output /var/lib/weather-to-docx/documents
```

Пакет содержит:

- нормализованные временные ряды;
- координаты;
- происхождение каждой модели;
- цикл, когда он известен;
- параметры, единицы и признаки качества;
- контрольные суммы;
- подпись манифеста.

Закрытой системе не нужны ключи внешних погодных сервисов.

---

## 📦 Автономная установка на Astra Linux

Сборочный комплект необходимо создавать **в Astra Linux той же версии и архитектуры, что и целевая система**. Это важно для совместимости `glibc`, Python, Pillow, cryptography и ecCodes.

### Сборка на подключённой машине

```bash
sudo bash scripts/build-astra-apt-repository.sh dist/apt-repository

TARGET_TAG=astra17-amd64 \
INCLUDE_GRIB=1 \
APT_REPOSITORY=dist/apt-repository \
bash scripts/build-offline-bundle.sh
```

Результат:

```text
dist/weather-to-docx-offline-0.2.0-astra17-amd64.tar.zst
dist/weather-to-docx-offline-0.2.0-astra17-amd64.tar.zst.sha256
```

Опционально комплект подписывается GPG:

```bash
SIGNING_KEY='GPG_KEY_ID' bash scripts/build-offline-bundle.sh
```

### Установка без Интернета

```bash
tar --zstd -xf weather-to-docx-offline-0.2.0-astra17-amd64.tar.zst
cd weather-to-docx-offline-0.2.0-astra17-amd64

sudo ./install.sh
sudo ./doctor.sh
```

### Обновление

```bash
sudo ./upgrade.sh
```

### Откат

```bash
sudo /opt/weather-to-docx/current/bin/rollback-release
# либо
sudo ./rollback.sh
```

Установщик не выполняет загрузку Python-пакетов из Интернета. База, координаты, конфигурация, пользовательские документы, входящие прогнозные пакеты и ключи находятся вне каталога версии и сохраняются при обновлении.

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

Службы:

```bash
systemctl status weather-to-docx-api.service
systemctl status weather-to-docx-worker.service
journalctl -u weather-to-docx-api.service -f
journalctl -u weather-to-docx-worker.service -f
```

---

## ⚠️ Правила достоверности

Система намеренно не скрывает ограничения прогноза:

- отсутствующий параметр выводится как `—`, а не как ноль;
- рассчитанные и интерполированные значения имеют разные признаки;
- точный цикл указывается только при наличии подтверждённых метаданных;
- Open-Meteo подписывается как служба доставки, а исходная модель — отдельно;
- GFS, IFS, AIFS, ICON, GDPS и ансамбли не смешиваются в один ряд;
- вероятность осадков не копируется из детерминированной суммы;
- старый цикл не используется скрытно;
- одна модель не подменяется другой;
- отказ отдельного источника фиксируется, но не блокирует успешные результаты;
- документ содержит предупреждение о необходимости учитывать наблюдения и официальные штормовые предупреждения.

---

## 🧪 Проверка качества

GitHub Actions выполняет:

- Ruff;
- автономные модульные и интеграционные тесты;
- проверку API, справочника координат и очереди;
- проверку ансамблевых статистик и PoP;
- формирование и чтение DOCX;
- проверку наличия всех параметров во второй таблице;
- проверку JavaScript;
- синтаксическую проверку установочных сценариев;
- сборку wheel и контроль включения локального интерфейса;
- формирование автономного DOCX;
- сборку офлайн-комплекта без GRIB-дополнения.

Матрица Python: `3.11`, `3.12`, `3.13`.

---

## 🧱 Архитектура

```text
NOAA GFS GRIB2 ───────────────┐
Open-Meteo: GFS / IFS / AIFS ─┤
Open-Meteo: ICON / GDPS ──────┤
Open-Meteo: ансамбли ─────────┼──► адаптеры источников
Подписанный прогнозный пакет ──┘             │
                                            ▼
                                ForecastSeries / ForecastPoint
                                            │
                  ┌─────────────────────────┼─────────────────────────┐
                  ▼                         ▼                         ▼
          контроль и расчёты         manifest + SHA-256       SQLite-очередь
                  │
                  ▼
        генератор DOCX + локальные PNG
                  │
                  ▼
     отдельные DOCX по координатам + общий ZIP
```

Генератор DOCX не зависит от формата внешнего источника. JSON, GRIB2 и автономный пакет сначала приводятся к единой нормализованной схеме.

Подробнее: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## 📚 Документация

- [`docs/SOURCES.md`](docs/SOURCES.md) — модели, происхождение, горизонты и ограничения;
- [`docs/API.md`](docs/API.md) — REST API;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — устройство системы;
- [`docs/OFFLINE_INSTALL.md`](docs/OFFLINE_INSTALL.md) — автономная установка Astra Linux;
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — разработка и тестирование;
- [`SECURITY.md`](SECURITY.md) — сообщения об уязвимостях;
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — сторонние компоненты и лицензии.

## 🔗 Официальные источники

- [Open-Meteo Forecast API](https://open-meteo.com/en/docs)
- [Open-Meteo Ensemble API](https://open-meteo.com/en/docs/ensemble-api)
- [Open-Meteo ECMWF API](https://open-meteo.com/en/docs/ecmwf-api)
- [Open-Meteo DWD ICON API](https://open-meteo.com/en/docs/dwd-api)
- [Open-Meteo GEM API](https://open-meteo.com/en/docs/gem-api)
- [NOAA GFS products](https://www.nco.ncep.noaa.gov/pmb/products/gfs/)
- [NOAA GEFS products](https://www.nco.ncep.noaa.gov/pmb/products/gens/)
- [NOAA NOMADS](https://nomads.ncep.noaa.gov/)
- [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data)
- [ECMWF ecCodes](https://github.com/ecmwf/eccodes)
- [DWD Open Data](https://opendata.dwd.de/)
- [ECCC Open Data](https://eccc-msc.github.io/open-data/)
- [python-docx](https://python-docx.readthedocs.io/)
- [FastAPI](https://fastapi.tiangolo.com/)
