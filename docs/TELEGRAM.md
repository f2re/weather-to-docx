# 🤖 Telegram-бот

## Назначение

Telegram является минимальной точкой входа в тот же генератор, который используется веб-интерфейсом и командной строкой.

Пользователь не настраивает таблицы вручную. Достаточно отправить:

- город;
- адрес;
- координаты;
- несколько строк;
- файл TXT, CSV или JSON.

В ответ:

- одна точка → один DOCX;
- несколько точек → ZIP с отдельными DOCX и `manifest.json`;
- большой ZIP → отдельные DOCX, если каждый укладывается в лимит Telegram.

## Создание бота

1. Откройте `@BotFather`.
2. Выполните `/newbot`.
3. Задайте имя и username.
4. Скопируйте token.
5. Запустите мастер:

```bash
sudo weather-to-docx-configure
```

6. Выберите включение Telegram.
7. Вставьте token.
8. Укажите разрешённые Telegram user ID.

Настройки сохраняются в:

```text
/etc/weather-to-docx/weather-to-docx.env
```

## Безопасная конфигурация

```dotenv
WTD_TELEGRAM_ENABLED="true"
WTD_TELEGRAM_BOT_TOKEN="123456:token"
WTD_TELEGRAM_ALLOWED_USER_IDS="123456789,987654321"
WTD_TELEGRAM_MAX_LOCATIONS="100"
WTD_TELEGRAM_CONCURRENCY="2"
```

Если `WTD_TELEGRAM_ALLOWED_USER_IDS` пуст, бот отвечает всем пользователям, которые нашли его username. Для рабочего контура это не рекомендуется.

Token нельзя:

- добавлять в Git;
- показывать в журналах;
- передавать в браузер;
- записывать в README или unit-файл.

Права файла настроек:

```bash
sudo chown root:weatherdoc /etc/weather-to-docx/weather-to-docx.env
sudo chmod 0640 /etc/weather-to-docx/weather-to-docx.env
```

## Запуск

```bash
sudo systemctl enable --now weather-to-docx-telegram
systemctl status weather-to-docx-telegram
```

Журнал:

```bash
journalctl -u weather-to-docx-telegram -f
```

Ручной запуск для диагностики:

```bash
sudo -u weatherdoc \
  /opt/weather-to-docx/current/venv/bin/weather-to-docx-telegram
```

## Меню

При каждом запуске бот регистрирует меню через Telegram Bot API:

```text
/forecast  — как передать точку или файл
/sources   — модели по умолчанию
/settings  — горизонт, часовой пояс и интеграции
/help      — краткая справка
```

## Форматы сообщений

### Город

```text
Псков
```

Для города нужен `WTD_DADATA_TOKEN`.

### Адрес

```text
Псков, Октябрьский проспект, 15
```

В интерактивном сообщении используется лучший результат DaData. Для производственной пакетной обработки адресов рекомендуется задать также `WTD_DADATA_SECRET`.

### Координаты

```text
57.8193, 28.3325
```

Также поддерживается разделитель `;`:

```text
57,8193; 28,3325
```

### Несколько строк

```text
Псков
Великий Новгород
59.9386, 30.3141
```

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
Санкт-Петербург;59.9386;30.3141;Europe/Moscow
```

Можно использовать русские заголовки:

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

## Модели

Telegram использует список:

```dotenv
WTD_DEFAULT_SOURCE_IDS="open_meteo_gfs,open_meteo_ecmwf_ifs,open_meteo_dwd_icon_global,open_meteo_gefs_0p25"
```

Горизонт:

```dotenv
WTD_DEFAULT_FORECAST_DAYS="7"
```

Для ансамблей бот передаёт пороги осадков:

```text
0.1 мм
1.0 мм
5.0 мм
```

Детерминированные модели выводятся первыми. Ансамбли попадают в одну отдельную таблицу в конце.

## Ограничения Telegram

При использовании обычных серверов Telegram Bot API:

- бот скачивает входные файлы размером до 20 МБ;
- `sendDocument` отправляет файлы размером до 50 МБ.

Эти лимиты отражены в настройках:

```dotenv
WTD_TELEGRAM_MAX_INPUT_BYTES="20971520"
WTD_TELEGRAM_MAX_OUTPUT_BYTES="52428800"
```

Локальный Telegram Bot API Server поддерживает более крупные файлы, но в текущей конфигурации не включается автоматически.

Официальная документация:

- https://core.telegram.org/bots/api
- https://docs.python-telegram-bot.org/en/stable/

## Ошибки

### Бот не запускается

```bash
journalctl -u weather-to-docx-telegram -n 100 --no-pager
```

Проверьте:

```bash
sudo grep -E '^WTD_TELEGRAM_(ENABLED|BOT_TOKEN|ALLOWED_USER_IDS)=' \
  /etc/weather-to-docx/weather-to-docx.env
```

Не публикуйте вывод с token.

### Город не находится

Проверьте DaData:

```bash
sudo grep '^WTD_DADATA_TOKEN=' \
  /etc/weather-to-docx/weather-to-docx.env
```

Координаты работают без DaData.

### Нет ответа от моделей

Проверьте исходящий HTTPS-доступ шлюза и выбранные `source_id`:

```bash
weather-to-docx sources
```

В полностью закрытом контуре Telegram может раздавать документы только из заранее доставленных прогнозных пакетов; прямое получение внешних моделей требует шлюза с Интернетом.
