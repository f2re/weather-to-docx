# 🔌 HTTP API

API предназначен для справочника точек, предварительной проверки импорта, постановки устойчивых заданий и загрузки результатов.

Интерактивная схема:

```text
http://127.0.0.1:8080/docs
```

OpenAPI JSON:

```text
http://127.0.0.1:8080/openapi.json
```

## Безопасность

По умолчанию API слушает только:

```text
127.0.0.1:8080
```

Приложение не разрешает случайный bind на `0.0.0.0` или сетевой адрес. Для доступа из сети используйте Nginx/HAProxy с TLS и принятой схемой аутентификации.

Опасное исключение:

```dotenv
WTD_ALLOW_INSECURE_NETWORK_API=true
```

не является заменой аутентификации и не рекомендуется для рабочего контура.

## Системные методы

### `GET /health`

Возвращает состояние API и worker:

```json
{
  "status": "ok",
  "version": "0.3.1",
  "worker_online": true,
  "worker_last_seen_utc": "2026-08-04T12:00:00+00:00"
}
```

### `GET /api/v1/diagnostics`

Основные поля:

```text
version
worker.online
worker.worker_id
worker.last_seen_utc
worker.age_seconds
queue.queued
queue.running
queue.stale_running
timezonefinder
eccodes_python
dadata_configured
geocoder_provider
telegram_enabled
default_sources
default_forecast_days
```

Секретные токены в ответ не включаются.

## Источники

### `GET /api/v1/sources`

Возвращает зарегистрированные адаптеры:

```bash
curl -sS http://127.0.0.1:8080/api/v1/sources \
  | python3 -m json.tool
```

Для каждого источника доступны:

- `source_id`;
- поставщик;
- модель;
- тип `deterministic`, `ensemble` или `synthetic`;
- горизонт;
- наличие точного цикла;
- краткое назначение.

## Часовые пояса

### `POST /api/v1/timezone/resolve`

Локальное определение IANA timezone по координатам:

```bash
curl -sS -X POST \
  http://127.0.0.1:8080/api/v1/timezone/resolve \
  -H 'Content-Type: application/json' \
  -d '{"latitude":60.1699,"longitude":24.9384}'
```

Ответ:

```json
{
  "timezone": "Europe/Helsinki",
  "source": "coordinates",
  "used_fallback": false
}
```

Метод не требует Интернета.

## Геокодирование и предварительный импорт

### `POST /api/v1/geocoding/suggest`

Интерактивные кандидаты DaData:

```json
{
  "query": "Псков",
  "count": 5
}
```

### `POST /api/v1/geocoding/resolve`

Определение одного города или адреса:

```json
{
  "query": "Псков, Октябрьский проспект, 15",
  "automatic": false
}
```

### `POST /api/v1/geocoding/reverse`

Обратное геокодирование координат.

### `POST /api/v1/geocoding/parse-file`

Единый серверный разбор TXT, CSV или JSON без записи в справочник:

```json
{
  "filename": "locations.csv",
  "content": "name;latitude;longitude\nХельсинки;60.1699;24.9384\n",
  "max_locations": 1000
}
```

Ответ:

```json
{
  "locations": [
    {
      "id": "csv-1",
      "name": "Хельсинки",
      "latitude": 60.1699,
      "longitude": 24.9384,
      "timezone": "Europe/Helsinki",
      "timezone_source": "coordinates"
    }
  ],
  "warnings": []
}
```

Ошибочная строка не блокирует корректные точки. Сохранение выполняется отдельным запросом только после подтверждения оператора.

## Справочник точек

### `GET /api/v1/locations`

Параметры:

- `group` — точное имя группы;
- `limit` — от 1 до 10 000.

### `POST /api/v1/locations`

Создать точку.

### `GET /api/v1/locations/{location_id}`

Получить точку.

### `PUT /api/v1/locations/{location_id}`

Полностью заменить точку.

### `DELETE /api/v1/locations/{location_id}`

Удалить точку.

### `POST /api/v1/locations/import`

Сохранить подтверждённый набор:

```json
{
  "locations": [
    {
      "id": "helsinki",
      "name": "Хельсинки",
      "latitude": 60.1699,
      "longitude": 24.9384,
      "timezone": "Europe/Helsinki",
      "timezone_source": "coordinates"
    }
  ],
  "replace_existing": false
}
```

## Задания

### `POST /api/v1/jobs`

Создать задание:

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
      "timezone_source": "coordinates"
    }
  ],
  "sources": [
    {
      "source_id": "open_meteo_gfs",
      "forecast_days": 7,
      "options": {}
    },
    {
      "source_id": "open_meteo_gefs_0p25",
      "forecast_days": 7,
      "options": {
        "precipitation_thresholds_mm": [0.1, 1, 5]
      }
    }
  ],
  "document": {
    "title": "Метеорологический прогноз",
    "page_size": "A3",
    "parameter_profile": "extended",
    "include_detailed_table": true,
    "include_ensemble_section": true
  }
}
```

Перед сохранением задания API перепроверяет точки с `timezone_source=system_default` по координатам.

### `GET /api/v1/jobs`

Параметры:

- `limit` — от 1 до 1000;
- `status` — `queued`, `running`, `completed`, `partial`, `failed`, `cancelled`.

Запись задания содержит:

```text
worker_id
lease_expires_at_utc
attempt_count
progress_current
progress_total
progress_message
```

### `GET /api/v1/jobs/{job_id}`

Получить полное состояние, ошибки и артефакты.

### `POST /api/v1/jobs/{job_id}/cancel`

Отменить ожидающее или выполняющееся задание. Worker получает отмену по heartbeat и прекращает активные асинхронные операции. Результат старого выполнения не может перезаписать новое.

### `POST /api/v1/jobs/{job_id}/retry`

Создать новую задачу на основе завершённой, частичной, ошибочной или отменённой.

## Артефакты

### `GET /api/v1/jobs/{job_id}/artifacts/{artifact_index}`

Выдаёт:

- DOCX;
- `manifest.json`;
- ZIP.

Путь проверяется относительно каталога документов, поэтому произвольный файл системы скачать нельзя.

```bash
curl -fLo result.docx \
  http://127.0.0.1:8080/api/v1/jobs/JOB_ID/artifacts/0
```

## Ошибки

- `403` — запрещён путь или операция;
- `404` — точка, задание или артефакт не найдены;
- `409` — конфликт идентификатора или состояния;
- `422` — некорректная структура, координаты или режим документа;
- `502` — внешний сервис отклонил запрос;
- `503` — требуемая интеграция не настроена;
- `500` — непредвиденная ошибка приложения.
