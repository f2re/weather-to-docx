# 🔌 HTTP API

API обслуживает веб-интерфейс, справочник точек, DaData, очередь заданий и загрузку результатов.

Интерактивная схема:

```text
http://127.0.0.1:8080/docs
```

OpenAPI JSON:

```text
http://127.0.0.1:8080/openapi.json
```

## Запуск

Установленная служба:

```bash
sudo systemctl start weather-to-docx-api weather-to-docx-worker
```

Ручной запуск с параметрами из `WTD_API_HOST` и `WTD_API_PORT`:

```bash
weather-to-docx-api
weather-to-docx worker --poll-interval 5
```

## Состояние системы

### `GET /health`

```json
{
  "status": "ok",
  "version": "0.3.0"
}
```

### `GET /api/v1/diagnostics`

Возвращает:

- версию;
- пути базы и документов;
- доступность записи;
- наличие `zstd` и ecCodes;
- число детерминированных и ансамблевых источников;
- состояние DaData и Telegram;
- набор моделей и горизонт по умолчанию.

DaData token, secret и Telegram token не возвращаются.

## Геокодирование

### `POST /api/v1/geocoding/suggest`

Интерактивные подсказки DaData:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/geocoding/suggest \
  -H 'Content-Type: application/json' \
  -d '{"query":"Псков","count":5}'
```

### `POST /api/v1/geocoding/resolve`

Один выбранный адрес:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/geocoding/resolve \
  -H 'Content-Type: application/json' \
  -d '{"query":"Псков","automatic":false}'
```

При `automatic=true` используется DaData Clean API, если задан `WTD_DADATA_SECRET`. Без secret возвращается первая подсказка.

### `POST /api/v1/geocoding/reverse`

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/geocoding/reverse \
  -H 'Content-Type: application/json' \
  -d '{"latitude":57.8193,"longitude":28.3325,"count":1}'
```

## Источники

### `GET /api/v1/sources`

```bash
curl -sS http://127.0.0.1:8080/api/v1/sources \
  | python3 -m json.tool
```

Для каждого адаптера возвращаются:

```json
{
  "source_id": "open_meteo_gefs_0p25",
  "name": "NOAA GEFS 0.25° через Open-Meteo",
  "provider": "Open-Meteo / NOAA",
  "model": "NOAA GEFS 0.25°",
  "horizon_days": 10,
  "exact_cycle": false,
  "source_kind": "ensemble",
  "implementation_status": "ready"
}
```

`source_kind` принимает:

```text
deterministic
ensemble
synthetic
```

## Справочник координат

### `GET /api/v1/locations`

Параметры:

- `group` — необязательная группа;
- `limit` — от 1 до 10000.

### `POST /api/v1/locations`

```json
{
  "id": "pskov",
  "name": "Псков",
  "latitude": 57.8193,
  "longitude": 28.3325,
  "elevation_m": 45,
  "timezone": "Europe/Moscow",
  "group": "Основные",
  "output_name": null
}
```

### `GET /api/v1/locations/{location_id}`

### `PUT /api/v1/locations/{location_id}`

### `DELETE /api/v1/locations/{location_id}`

### `POST /api/v1/locations/import`

```json
{
  "replace_existing": false,
  "locations": [
    {
      "id": "pskov",
      "name": "Псков",
      "latitude": 57.8193,
      "longitude": 28.3325,
      "timezone": "Europe/Moscow"
    }
  ]
}
```

### `GET /api/v1/locations/export`

Совместимый адрес:

```text
/api/v1/location-catalog/export
```

## Задания

### `POST /api/v1/jobs`

Пример с двумя детерминированными моделями и одним ансамблем:

```json
{
  "batch_name": "forecast_for_objects",
  "locations": [
    {
      "id": "pskov",
      "name": "Псков",
      "latitude": 57.8193,
      "longitude": 28.3325,
      "timezone": "Europe/Moscow"
    }
  ],
  "sources": [
    {
      "source_id": "open_meteo_gfs",
      "forecast_days": 7,
      "options": {}
    },
    {
      "source_id": "open_meteo_ecmwf_ifs",
      "forecast_days": 7,
      "options": {}
    },
    {
      "source_id": "open_meteo_gefs_0p25",
      "forecast_days": 7,
      "options": {
        "precipitation_thresholds_mm": [0.1, 1.0, 5.0]
      }
    }
  ],
  "document": {
    "title": "Метеорологический прогноз",
    "page_size": "A3",
    "summary_interval_hours": 3,
    "extended_summary_interval_hours": 6,
    "summary_switch_hour": 120,
    "ensemble_interval_hours": 6,
    "ensemble_extended_interval_hours": 12,
    "ensemble_switch_hour": 120,
    "include_detailed_table": true,
    "include_all_parameters": true,
    "include_ensemble_section": true,
    "parameter_profile": "extended",
    "language": "ru"
  }
}
```

Результирующий DOCX всегда располагает детерминированные модели первыми. Все ансамблевые источники выводятся одной отдельной таблицей в конце.

### `GET /api/v1/jobs`

Параметры:

- `limit` — от 1 до 1000;
- `status` — `queued`, `running`, `completed`, `partial`, `failed`, `cancelled`.

### `GET /api/v1/jobs/{job_id}`

Возвращает запрос, статус, ошибки, предупреждения и артефакты.

### `POST /api/v1/jobs/{job_id}/cancel`

### `POST /api/v1/jobs/{job_id}/retry`

## Артефакты

### `GET /api/v1/jobs/{job_id}/artifacts/{artifact_index}`

Виды:

```text
docx
manifest
zip
```

Пример:

```bash
curl -fLo result.docx \
  http://127.0.0.1:8080/api/v1/jobs/JOB_ID/artifacts/0
```

Путь проверяется относительно каталога документов. Произвольный системный файл через этот метод получить нельзя.

## Коды ошибок

| Код | Значение |
|---:|---|
| 403 | недопустимый путь или ограничение доступа |
| 404 | точка, задание, кандидат или артефакт не найден |
| 409 | конфликт идентификатора или недопустимое состояние |
| 422 | ошибка структуры данных |
| 502 | внешний сервис DaData или источник прогноза недоступен |
| 503 | интеграция не настроена |

## Доступ из сети

Приложение не реализует собственную корпоративную аутентификацию. По умолчанию API слушает `127.0.0.1`.

Для сетевого доступа используйте Nginx или HAProxy с:

- TLS;
- ограничением адресов;
- принятой в организации аутентификацией;
- лимитами размера запросов;
- журналом доступа.
