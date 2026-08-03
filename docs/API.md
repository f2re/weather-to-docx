# 🔌 HTTP API

API обслуживает локальный интерфейс оператора, справочник координат, каталог источников, SQLite-очередь и выдачу сформированных DOCX/ZIP. Интерактивная схема доступна по `/docs`, OpenAPI JSON — по `/openapi.json`.

## 1. Запуск

```bash
weather-to-docx api --host 127.0.0.1 --port 8080
weather-to-docx worker --poll-interval 5
```

Адреса:

```text
Интерфейс: http://127.0.0.1:8080/
Swagger:   http://127.0.0.1:8080/docs
OpenAPI:   http://127.0.0.1:8080/openapi.json
```

В установленной системе API и worker запускаются отдельными systemd-службами.

## 2. Системные методы

### `GET /health`

```json
{
  "status": "ok",
  "version": "0.2.0"
}
```

### `GET /api/v1/diagnostics`

Возвращает:

- версию;
- пути базы и документов;
- доступность записи;
- наличие `zstd`;
- наличие Python-модуля `eccodes`;
- политику подписи пакетов;
- число сохранённых координат;
- число зарегистрированных источников.

Секретные и закрытые ключи в ответ не попадают.

```bash
curl -sS http://127.0.0.1:8080/api/v1/diagnostics | python -m json.tool
```

## 3. Источники

### `GET /api/v1/sources`

Возвращает зарегистрированные адаптеры:

```bash
curl -sS http://127.0.0.1:8080/api/v1/sources | python -m json.tool
```

Пример элемента:

```json
{
  "source_id": "open_meteo_ecmwf_ifs",
  "name": "ECMWF IFS 0.25° Open Data через Open-Meteo",
  "provider": "Open-Meteo / ECMWF",
  "model": "ECMWF IFS 0.25° Open Data",
  "horizon_days": 15,
  "exact_cycle": false,
  "notes": "Независимый глобальный детерминированный прогноз ECMWF."
}
```

## 4. Справочник координат

### `GET /api/v1/locations`

Параметры:

- `group` — точное имя группы;
- `limit` — от 1 до 10000.

```bash
curl -sS 'http://127.0.0.1:8080/api/v1/locations?limit=1000'
```

### `POST /api/v1/locations`

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/locations \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "spb-office",
    "name": "Санкт-Петербург, объект 1",
    "latitude": 59.9386,
    "longitude": 30.3141,
    "elevation_m": 12,
    "timezone": "Europe/Moscow",
    "group": "Основные объекты",
    "output_name": null
  }'
```

При совпадении идентификатора возвращается `409`.

### `GET /api/v1/locations/{location_id}`

Возвращает одну координату либо `404`.

### `PUT /api/v1/locations/{location_id}`

Полностью заменяет запись. Идентификатор в URL и теле должен совпадать.

### `DELETE /api/v1/locations/{location_id}`

Удаляет запись и возвращает `204`.

### `POST /api/v1/locations/import`

Атомарный массовый импорт:

```json
{
  "replace_existing": true,
  "locations": [
    {
      "id": "point-1",
      "name": "Точка 1",
      "latitude": 55.75,
      "longitude": 37.62,
      "timezone": "Europe/Moscow"
    }
  ]
}
```

Если `replace_existing=false`, совпадение идентификатора останавливает импорт без частичной записи.

### `GET /api/v1/location-catalog/export`

Возвращает полный JSON-массив координат.

## 5. Задания

### `POST /api/v1/jobs`

Создаёт задание в SQLite-очереди.

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/jobs \
  -H 'Content-Type: application/json' \
  --data-binary @examples/job.json
```

Пример многомодельного тела:

```json
{
  "batch_name": "forecast_for_objects",
  "locations": [
    {
      "id": "spb-office",
      "name": "Санкт-Петербург, объект 1",
      "latitude": 59.9386,
      "longitude": 30.3141,
      "elevation_m": 12,
      "timezone": "Europe/Moscow",
      "group": "Основные объекты"
    }
  ],
  "sources": [
    {
      "source_id": "open_meteo_gfs",
      "forecast_days": 10,
      "options": {}
    },
    {
      "source_id": "open_meteo_ecmwf_ifs",
      "forecast_days": 10,
      "options": {}
    },
    {
      "source_id": "open_meteo_gefs_0p25",
      "forecast_days": 10,
      "options": {
        "precipitation_threshold_mm": 0.1
      }
    }
  ],
  "document": {
    "title": "Метеорологический прогноз",
    "page_size": "A3",
    "summary_interval_hours": 3,
    "extended_summary_interval_hours": 6,
    "summary_switch_hour": 120,
    "include_detailed_table": true,
    "include_all_parameters": true,
    "parameter_profile": "all",
    "language": "ru"
  }
}
```

Ограничения схемы:

- 1–1000 координат;
- 1–20 источников;
- горизонт источника — 1–35 суток;
- идентификаторы координат в одном задании должны быть уникальными.

### `GET /api/v1/jobs`

Параметры:

- `limit` — от 1 до 1000;
- `status` — `queued`, `running`, `completed`, `partial`, `failed`, `cancelled`.

```bash
curl -sS 'http://127.0.0.1:8080/api/v1/jobs?status=completed&limit=20'
```

### `GET /api/v1/jobs/{job_id}`

Возвращает исходный запрос, состояние, ошибки и артефакты.

### `POST /api/v1/jobs/{job_id}/cancel`

Отмечает ожидающее или выполняющееся задание отменённым. Уже начавшийся внешний HTTP-запрос может завершиться, однако отменённое задание не переводится в `completed`.

### `POST /api/v1/jobs/{job_id}/retry`

Создаёт новое задание с теми же параметрами на основе завершённого, частичного, ошибочного или отменённого.

## 6. Артефакты

### `GET /api/v1/jobs/{job_id}/artifacts/{artifact_index}`

Выдаёт DOCX, JSON-манифест или ZIP.

```bash
curl -fLo result.docx \
  http://127.0.0.1:8080/api/v1/jobs/JOB_ID/artifacts/0
```

Путь артефакта проверяется относительно разрешённого каталога документов. Получить произвольный файл операционной системы через этот метод нельзя.

## 7. Коды ошибок

- `403` — путь артефакта вышел за разрешённый каталог;
- `404` — координата, задание или артефакт не найден;
- `409` — конфликт идентификатора или операция не соответствует текущему состоянию;
- `422` — тело запроса, координаты, часовой пояс или диапазон некорректны;
- `500` — непредвиденная ошибка приложения; подробности записываются в systemd journal.

## 8. Защита внешнего доступа

Приложение не реализует собственную корпоративную аутентификацию. По умолчанию systemd запускает API только на `127.0.0.1`.

Для сетевого доступа необходимо разместить перед приложением Nginx или HAProxy и настроить:

- TLS;
- корпоративную аутентификацию;
- ограничение сетевых адресов;
- ограничение размера запроса;
- журналирование доступа;
- таймауты загрузки документов.
