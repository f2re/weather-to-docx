# 🔌 HTTP API

API предназначен для постановки пакетных заданий, контроля очереди и загрузки созданных файлов. Интерактивная схема доступна по `/docs`, OpenAPI JSON — по `/openapi.json`.

## Запуск

```bash
weather-to-docx api --host 127.0.0.1 --port 8080
weather-to-docx worker --poll-interval 5
```

В установленной системе API и worker запускаются отдельными systemd-службами.

## Системные методы

### `GET /health`

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

### `GET /api/v1/diagnostics`

Показывает пути данных, доступность записи, наличие `zstd`, Python-модуля `eccodes` и политику подписи прогнозных пакетов. Секретные ключи в ответ не попадают.

## Источники

### `GET /api/v1/sources`

Возвращает зарегистрированные адаптеры и их свойства.

```bash
curl -sS http://127.0.0.1:8080/api/v1/sources | python -m json.tool
```

## Задания

### `POST /api/v1/jobs`

Создаёт задание в SQLite-очереди.

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/jobs \
  -H 'Content-Type: application/json' \
  --data-binary @examples/job.json
```

### `GET /api/v1/jobs`

Параметры:

- `limit` — от 1 до 1000;
- `status` — `queued`, `running`, `completed`, `partial`, `failed`, `cancelled`.

```bash
curl -sS 'http://127.0.0.1:8080/api/v1/jobs?status=completed&limit=20'
```

### `GET /api/v1/jobs/{job_id}`

Возвращает состояние, исходный запрос, ошибки и артефакты.

### `POST /api/v1/jobs/{job_id}/cancel`

Отмечает ожидающее или выполняющееся задание отменённым. Уже начатый HTTP-запрос может завершиться, однако итог отменённого задания не переводится в состояние `completed`.

### `POST /api/v1/jobs/{job_id}/retry`

Создаёт новое задание на основе завершённого, частичного, ошибочного или отменённого.

## Артефакты

### `GET /api/v1/jobs/{job_id}/artifacts/{artifact_index}`

Выдаёт DOCX, JSON-манифест или ZIP. Путь проверяется относительно разрешённого каталога документов, поэтому произвольный файл системы скачать через метод нельзя.

Пример:

```bash
curl -fLo result.docx \
  http://127.0.0.1:8080/api/v1/jobs/JOB_ID/artifacts/0
```

## Пример тела задания

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
      "timezone": "Europe/Moscow"
    }
  ],
  "sources": [
    {
      "source_id": "open_meteo_gfs",
      "forecast_days": 7,
      "options": {}
    }
  ],
  "document": {
    "title": "Метеорологический прогноз",
    "page_size": "A3",
    "summary_interval_hours": 3,
    "extended_summary_interval_hours": 6,
    "summary_switch_hour": 120,
    "include_detailed_table": true,
    "language": "ru"
  }
}
```

## Ошибки

- `404` — задание или артефакт не найден;
- `409` — операция не соответствует текущему состоянию;
- `422` — структура запроса или координаты некорректны;
- `403` — путь артефакта вышел за разрешённый каталог;
- `500` — непредвиденная ошибка приложения; подробности записываются в журнал systemd.

## Защита внешнего доступа

Текущая версия не реализует собственную корпоративную аутентификацию. По умолчанию systemd запускает API только на `127.0.0.1`. Для доступа по сети следует разместить перед приложением Nginx/HAProxy с TLS, ограничением адресов и принятой в организации схемой аутентификации.
