# 🤖 Telegram-бот

Telegram использует ту же SQLite-очередь и тот же worker, что веб-интерфейс. Бот не выполняет длительный расчёт внутри обработчика сообщения.

## 1. Что можно отправить

Город:

```text
Псков
```

Адрес:

```text
Псков, Октябрьский проспект, 15
```

Координаты:

```text
57.8193, 28.3325
```

Несколько строк:

```text
Псков
Великий Новгород
59.9386, 30.3141
```

Также поддерживаются:

- Telegram-геопозиция;
- TXT;
- CSV;
- JSON.

Ответ:

- одна точка → DOCX;
- несколько точек → ZIP;
- слишком большой ZIP → отдельные DOCX.

## 2. Общая очередь

После получения входных данных бот:

1. проверяет доступность worker;
2. нормализует координаты и timezone;
3. создаёт задание в SQLite;
4. сообщает короткий идентификатор;
5. показывает состояние и прогресс;
6. получает готовый артефакт из общей очереди;
7. отправляет DOCX или ZIP.

Перезапуск процесса Telegram не удаляет уже созданное задание. Оно остаётся доступно в веб-интерфейсе и API.

Если worker не отвечает, бот не создаёт задание и сообщает, какую службу проверить.

## 3. Создание бота

1. Откройте `@BotFather`.
2. Выполните `/newbot`.
3. Задайте имя и username.
4. Скопируйте token.
5. Запустите мастер:

```bash
sudo weather-to-docx-configure
```

6. Включите Telegram.
7. Вставьте token.
8. Укажите разрешённые Telegram user ID.

Настройки:

```text
/etc/weather-to-docx/weather-to-docx.env
```

## 4. Безопасная конфигурация

```dotenv
WTD_TELEGRAM_ENABLED="true"
WTD_TELEGRAM_BOT_TOKEN="123456:token"
WTD_TELEGRAM_ALLOWED_USER_IDS="123456789,987654321"
WTD_TELEGRAM_MAX_LOCATIONS="100"
WTD_TELEGRAM_CONCURRENCY="2"
WTD_TELEGRAM_JOB_POLL_SECONDS="3"
WTD_TELEGRAM_JOB_TIMEOUT_SECONDS="1800"
```

Если `WTD_TELEGRAM_ALLOWED_USER_IDS` пуст, бот отвечает любому пользователю, который знает его username. Для рабочего контура так делать не следует.

Token нельзя:

- добавлять в Git;
- показывать в журнале;
- передавать в браузер;
- записывать в unit-файл;
- отправлять в диагностический чат.

Права файла:

```bash
sudo chown root:weatherdoc /etc/weather-to-docx/weather-to-docx.env
sudo chmod 0640 /etc/weather-to-docx/weather-to-docx.env
```

## 5. Запуск

```bash
sudo systemctl enable --now weather-to-docx-worker
sudo systemctl enable --now weather-to-docx-telegram
```

Состояние:

```bash
systemctl status weather-to-docx-worker
systemctl status weather-to-docx-telegram
```

Журнал:

```bash
journalctl -u weather-to-docx-telegram -f
```

Ручной запуск:

```bash
sudo -u weatherdoc \
  /opt/weather-to-docx/current/venv/bin/weather-to-docx-telegram
```

## 6. Меню

При старте бот регистрирует:

```text
/forecast  — как отправить точку или файл
/cancel    — отменить последнее активное задание
/sources   — используемые модели
/settings  — горизонт, интеграции и состояние worker
/help      — краткая справка
```

`/cancel` меняет состояние общей очереди. Worker получает отмену по heartbeat и прекращает асинхронное выполнение.

Можно указать идентификатор явно:

```text
/cancel 2f31a9c4...
```

## 7. Часовой пояс

Для координат timezone определяется локально по базе IANA.

Для города или адреса:

1. DaData возвращает координаты;
2. локальный модуль определяет timezone по координатам;
3. в задание сохраняются timezone и его происхождение.

Резервный `WTD_DEFAULT_TIMEZONE` применяется только тогда, когда локальное определение не удалось. В этом случае пользователь получает предупреждение.

## 8. Файлы

### TXT

```text
# комментарий
Псков
Великий Новгород
59.9386, 30.3141
```

### CSV

```csv
name;latitude;longitude;timezone
Псков;57.8193;28.3325;Europe/Moscow
Хельсинки;60.1699;24.9384;Europe/Helsinki
```

Поддерживаются русские заголовки:

```csv
название;широта;долгота;часовой_пояс
Псков;57,8193;28,3325;Europe/Moscow
```

### JSON

```json
{
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

Проблемная строка не блокирует корректные точки. Бот присылает отдельный список предупреждений до создания документов.

## 9. Модели

Telegram использует:

```dotenv
WTD_DEFAULT_SOURCE_IDS="open_meteo_gfs,open_meteo_ecmwf_ifs,open_meteo_dwd_icon_global,open_meteo_gefs_0p25"
WTD_DEFAULT_FORECAST_DAYS="7"
```

Для ансамблей передаются пороги:

```text
0.1 мм
1.0 мм
5.0 мм
```

Детерминированные модели выводятся первыми. Ансамбли находятся в одной таблице в конце.

## 10. Ограничения файлов

При использовании обычного Telegram Bot API:

```dotenv
WTD_TELEGRAM_MAX_INPUT_BYTES="20971520"
WTD_TELEGRAM_MAX_OUTPUT_BYTES="52428800"
```

Если общий архив превышает выходной лимит, бот пытается отправить отдельные DOCX.

## 11. Диагностика

Worker:

```bash
journalctl -u weather-to-docx-worker -n 100 --no-pager
```

Telegram:

```bash
journalctl -u weather-to-docx-telegram -n 100 --no-pager
```

Очередь:

```bash
curl -sS http://127.0.0.1:8080/api/v1/diagnostics | python3 -m json.tool
```

Проверить настройки без вывода token:

```bash
sudo grep -E '^WTD_TELEGRAM_(ENABLED|ALLOWED_USER_IDS)=' \
  /etc/weather-to-docx/weather-to-docx.env
```

## 12. Полностью закрытый контур

Telegram требует исходящий доступ к Telegram Bot API. Если закрытый контур не имеет такого доступа, бот внутри него работать не сможет.

Прогнозные данные при этом можно доставлять отдельными подписанными пакетами через сетевой шлюз. Сам бот должен быть размещён в разрешённом сетевом сегменте либо не использоваться.
