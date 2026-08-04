# 🧱 Архитектура Weather to DOCX

## Назначение

`weather-to-docx` принимает город, адрес или координаты, получает несколько независимых прогнозных моделей и формирует отдельный DOCX для каждой точки.

Архитектура разделяет:

1. пользовательские точки входа;
2. геокодирование;
3. получение прогнозов;
4. нормализацию и научную обработку;
5. формирование DOCX;
6. очередь и хранение;
7. автономную доставку приложения и данных.

Генератор DOCX не читает JSON или GRIB2 напрямую. Каждый адаптер возвращает `ForecastSeries`.

## Схема компонентов

```text
Веб-интерфейс ───┐
HTTP API ─────────┤
CLI ──────────────┼──► Location / BatchRequest
Telegram-бот ─────┘              │
                                 ├──► DaData suggest / clean / reverse
                                 │
                                 ▼
                     ForecastBatchService
                                 │
            ┌────────────────────┴────────────────────┐
            ▼                                         ▼
 детерминированные источники                  ансамблевые источники
 GFS / IFS / AIFS / ICON / GDPS              GEFS / IFS ENS / AIFS ENS /
 прямой GFS GRIB2                             ICON-EPS / GEPS
            │                                         │
            ▼                                         ▼
  ForecastSeries(kind=deterministic)        ForecastSeries(kind=ensemble)
                                                      │
                                                      ▼
                                           ensemble/science.py
                                           mean / σ / q10 / q50 / q90 /
                                           M/N / circular mean / coverage
            │                                         │
            └────────────────────┬────────────────────┘
                                 ▼
                    ScientificDocumentGenerator
                                 │
                   ┌─────────────┴─────────────┐
                   ▼                           ▼
       модельные секции DOCX          одна ансамблевая таблица
       по две таблицы на модель       в конце документа
                   │                           │
                   └─────────────┬─────────────┘
                                 ▼
                     DOCX + manifest.json + ZIP
```

## Каталоги исходного кода

```text
src/weather_to_docx/
├── api/                 HTTP API и геокодирование
├── document/            DOCX, стили, пиктограммы, научная композиция
├── domain/              предметная модель и типы источников
├── ensemble/            научные операции над ансамблем
├── geocoding/           DaData и разбор TXT/CSV/JSON
├── services/            пакетная обработка и прогнозные пакеты
├── sources/             адаптеры моделей
├── static/              автономный интерфейс
├── storage/             SQLite WAL
├── api_entrypoint.py    отдельная точка запуска API
├── telegram_bot.py      обработчики Telegram
├── telegram_entrypoint.py
├── cli.py
└── settings.py
```

## Предметная модель

### `Location`

```text
id
name
latitude
longitude
elevation_m
timezone
group
output_name
```

### `SourceKind`

```text
deterministic
ensemble
synthetic
```

Тип передаётся явно. Генератор не определяет ансамбль только по названию модели, кроме режима чтения старых пакетов 0.2.x.

### `SourceMetadata`

Помимо поставщика, модели, цикла, сетки и лицензии содержит ансамблевые метаданные:

```text
ensemble_member_count
ensemble_expected_member_count
ensemble_member_coverage_percent
member_weighting
primary_statistic_policy
quantile_method
probability_calibration
```

### `ForecastValue`

Каждое значение содержит:

```text
value
unit
quality
source_parameter
note
source_start_step
source_end_step
```

Признаки качества:

| Код | Значение | Маркер |
|---|---|---|
| `source` | исходное поле | нет |
| `calculated` | рассчитанное поле | `*` |
| `interpolated` | интерполяция | `≈` |
| `corrected` | исправление контроля качества | `†` |
| `stale` | устаревшее | `!` |
| `suspect` | сомнительное или неполный ансамбль | `?` |
| `missing` | отсутствует | `—` |

## Геокодирование

`DadataClient` реализует три серверных метода:

```text
suggest_address
clean_address
reverse
```

Token и secret находятся только в EnvironmentFile. Браузер и Telegram получают нормализованный результат, но не ключи.

`geocoding/parser.py` преобразует:

- строку города;
- адрес;
- координаты;
- TXT;
- CSV;
- JSON;

в список `Location`.

## Источники прогнозов

Интерфейс адаптера:

```python
async def fetch(
    location: Location,
    forecast_days: int,
    options: dict[str, Any] | None = None,
) -> ForecastSeries:
    ...
```

`SourceRegistry` хранит экземпляры источников. `SourceDescriptor` сообщает UI и Telegram:

```text
source_id
provider
model
horizon_days
source_kind
exact_cycle
implementation_status
notes
```

## Научная обработка ансамбля

`ensemble/science.py` не зависит от Open-Meteo или DOCX.

Операции:

```text
ensemble_statistics
primary_centre
quantile_type8
raw_probability
probability_resolution
circular_mean_degrees
```

Правила:

- равные веса членов одной системы;
- среднее и σ для температуры и давления;
- медиана для осадков, ветра и асимметричных величин;
- q10–q90 методом Hyndman–Fan type 8;
- вероятность `100 × M/N`;
- круговое среднее направления ветра;
- явная полнота членов;
- отсутствие выдуманной калибровки.

Разные ансамблевые системы не объединяются.

## DOCX

`ScientificDocumentGenerator` наследует базовые стили и форматирование, но управляет композицией документа.

Алгоритм:

```text
partition ForecastSeries by SourceKind
        │
        ├── deterministic → по две таблицы на модель
        │
        └── ensemble → одна сравнительная таблица в конце
```

Вероятностные показатели не выводятся в детерминированной обзорной таблице.

Встроенные PNG-пиктограммы создаются Pillow и не требуют CDN или шрифта эмодзи.

## Очередь

SQLite WAL хранит запрос и итог:

```text
queued → running → completed
                  ├── partial
                  ├── failed
                  └── cancelled
```

Worker транзакционно захватывает одно задание. Ошибка одной точки или источника не уничтожает успешные результаты остальных комбинаций.

## Манифест

`manifest.json` содержит:

- версию схемы;
- точки;
- исходный `BatchRequest`;
- метаданные источников;
- тип источника;
- число сроков;
- предупреждения;
- состав DOCX;
- SHA-256 и размер файлов;
- ошибки частичной задачи.

Схема 2 сохраняет совместимые поля `locations` и `artifacts` для клиентов 0.2.x.

## Telegram

`TelegramForecastBot` использует тот же `ForecastBatchService`.

```text
Update
  ├── text        → город / адрес / координаты
  ├── location    → координаты + reverse DaData
  └── document    → TXT / CSV / JSON
                           │
                           ▼
                    BatchRequest
                           │
                           ▼
                   DOCX или ZIP
```

Доступ можно ограничить user ID. Команды регистрируются при запуске через Bot API.

## Автономная установка

```text
build-offline-bundle.sh
        │
        ├── wheelhouse
        ├── локальный APT
        ├── SBOM
        ├── systemd units
        ├── setup/configure/install/rollback
        └── SHA-256 + необязательная GPG-подпись
```

На целевой Astra Linux:

```text
setup.sh
  ├── install.sh
  ├── configure.sh
  └── conditional systemd start
```

Релизы расположены в `/opt/weather-to-docx/releases`, а данные и токены находятся вне каталога релиза.

## Закрытый контур

`ForecastBundle` переносит нормализованные ряды. Он подписывается Ed25519 и проверяется до генерации DOCX.

Telegram и DaData требуют внешнего HTTPS-доступа. В полностью изолированном контуре они либо отключаются, либо размещаются на сетевом шлюзе.

## Добавление новой модели

Новый адаптер обязан:

1. определить `SourceDescriptor` и `SourceKind`;
2. не подменять модель seamless-продуктом;
3. привести единицы к внутренним;
4. заполнить `SourceMetadata`;
5. отметить рассчитанные значения;
6. предоставить автономную фикстуру;
7. добавить тест разбора;
8. зарегистрироваться в `SourceRegistry`;
9. быть описан в `docs/SOURCES.md`.

Для нового ансамбля дополнительно требуются:

1. известное число членов или явное значение «неизвестно»;
2. документированная схема весов;
3. сохранение распределения, а не только среднего;
4. проверка неполных членов;
5. запрет скрытой калибровки;
6. тесты квантилей, вероятностей и круговых величин.
