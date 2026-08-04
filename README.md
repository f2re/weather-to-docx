# 🌦️ Weather to DOCX

Система получает прогнозы погоды по городам или координатам и формирует профессиональные документы Microsoft Word.

- одна точка → один `DOCX`;
- несколько точек → отдельный `DOCX` для каждой точки и общий `ZIP`;
- детерминированные модели идут первыми;
- ансамблевая неопределённость выводится **одной отдельной таблицей в конце**;
- веб-интерфейс, HTTP API, командная строка и Telegram-бот используют одно вычислительное ядро;
- приложение устанавливается на Astra Linux без обращения к Интернету.

Текущая версия: **0.3.0**.

## 📄 Как выглядит документ

Для каждой детерминированной модели создаются ровно две таблицы:

1. **Наглядный прогноз** — пиктограмма погоды, температура, осадки, ветер, порывы, давление и облачность.
2. **Подробный отчёт по срокам** — влажность, точка росы, давление, ветер, типы осадков, снег, облачность, видимость, конвекция, радиация, почва и дополнительные поля.

После всех моделей создаётся один раздел:

> **Ансамблевая оценка неопределённости**

В нём сравниваются выбранные ансамблевые системы, но их члены **не смешиваются** в искусственный супер-ансамбль.

Ансамблевая таблица содержит:

- количество доступных и ожидаемых членов;
- полноту ансамбля;
- минимальный шаг вероятности `100 / N`;
- температуру: среднее, стандартное отклонение, `q10–q90`;
- осадки и ветер: медиану `q50`, `q10–q90`;
- сырые вероятности превышения заданных порогов осадков;
- порывы, давление и CAPE;
- пояснения по интерпретации.

Подробнее: [`docs/ENSEMBLES.md`](docs/ENSEMBLES.md).

## 🚀 Установка на Astra Linux

Офлайн-комплект собирается на машине с Интернетом в совместимой версии Astra Linux, переносится на целевую систему и устанавливается одной командой:

```bash
sudo ./setup.sh
```

`setup.sh`:

1. проверяет комплект;
2. устанавливает локальные системные и Python-зависимости;
3. разворачивает новую версию атомарно;
4. запускает мастер настройки;
5. спрашивает адрес и порт интерфейса;
6. предлагает набор моделей;
7. запрашивает DaData token и secret;
8. предлагает включить Telegram-бота;
9. запрашивает Telegram token и список разрешённых пользователей;
10. запускает нужные службы.

После установки:

```bash
sudo /opt/weather-to-docx/current/venv/bin/weather-to-docx doctor --deep
systemctl status weather-to-docx-api
systemctl status weather-to-docx-worker
systemctl status weather-to-docx-telegram   # если бот включён
```

Интерфейс по умолчанию:

```text
http://127.0.0.1:8080/
```

Повторно открыть мастер:

```bash
sudo weather-to-docx-configure
```

Редактировать настройки вручную:

```bash
sudoedit /etc/weather-to-docx/weather-to-docx.env
sudo systemctl restart weather-to-docx-api weather-to-docx-worker
sudo systemctl restart weather-to-docx-telegram
```

Полная инструкция: [`docs/OFFLINE_INSTALL.md`](docs/OFFLINE_INSTALL.md).

## 🖥️ Веб-интерфейс

Рабочий процесс состоит из трёх шагов:

1. добавить город, адрес, координаты или файл;
2. выбрать модели и ансамбли;
3. выбрать горизонт и сформировать документы.

Поддерживаются:

- поиск города или адреса через DaData;
- ручные координаты;
- импорт `TXT`, `CSV` и `JSON`;
- пакет до 1000 сохранённых точек;
- отдельный выбор детерминированных и ансамблевых источников;
- пороги вероятности осадков;
- форматы A3 и A4;
- очередь заданий;
- загрузка DOCX, ZIP и `manifest.json`.

Интерфейс не использует CDN и внешние JavaScript-библиотеки.

## 🤖 Telegram-бот

Боту достаточно отправить:

```text
Псков
```

или:

```text
57.8193, 28.3325
```

или несколько строк:

```text
Псков
Великий Новгород
59.9386, 30.3141
```

Также принимаются файлы:

- `.txt` — по одному городу, адресу или паре координат в строке;
- `.csv` — русские или английские заголовки;
- `.json` — массив точек или объект с полем `locations`.

Результат:

- одна точка → DOCX;
- несколько точек → ZIP;
- если архив превышает лимит Telegram, бот отправляет DOCX отдельно.

При запуске бот регистрирует меню:

```text
/forecast  — как сформировать прогноз
/sources   — используемые модели
/settings  — текущие параметры
/help      — краткая справка
```

Запуск вручную:

```bash
weather-to-docx-telegram
```

Журнал службы:

```bash
journalctl -u weather-to-docx-telegram -f
```

Рекомендуется ограничить доступ:

```dotenv
WTD_TELEGRAM_ALLOWED_USER_IDS="123456789,987654321"
```

Подробнее: [`docs/TELEGRAM.md`](docs/TELEGRAM.md).

## 🗺️ DaData

Для интерактивного поиска города или адреса достаточно токена:

```dotenv
WTD_DADATA_TOKEN="ваш-токен"
```

Для автоматической обработки списков адресов рекомендуется также secret key:

```dotenv
WTD_DADATA_SECRET="ваш-secret"
```

Разделение сделано намеренно:

- API подсказок подходит для выбора человеком;
- API стандартизации подходит для автоматической обработки файла;
- secret никогда не передаётся в браузер и хранится только на сервере.

Без DaData система продолжает работать по координатам.

Подробнее: [`docs/DADATA.md`](docs/DADATA.md).

## 🛰️ Источники прогнозов

### Детерминированные

| `source_id` | Модель | Горизонт |
|---|---|---:|
| `open_meteo_gfs` | NOAA GFS 0.25° | до 16 суток |
| `open_meteo_ecmwf_ifs` | ECMWF IFS Open Data | до 15 суток |
| `open_meteo_ecmwf_aifs` | ECMWF AIFS | до 15 суток |
| `open_meteo_dwd_icon_global` | DWD ICON Global | до 8 суток |
| `open_meteo_gem_gdps` | ECCC GEM/GDPS | до 10 суток |
| `noaa_gfs_0p25` | прямой NOAA/NCEP GFS GRIB2 | до 384 часов |

### Ансамблевые

| `source_id` | Система | Горизонт |
|---|---|---:|
| `open_meteo_gefs_0p25` | NOAA GEFS 0.25° | до 10 суток |
| `open_meteo_gefs_0p5` | NOAA GEFS 0.5° | до 35 суток |
| `open_meteo_ecmwf_ifs_ensemble` | ECMWF IFS ENS | до 15 суток |
| `open_meteo_ecmwf_aifs_ensemble` | ECMWF AIFS ENS | до 15 суток |
| `open_meteo_dwd_icon_eps` | DWD ICON Global EPS | до 8 суток |
| `open_meteo_gem_geps` | ECCC GEPS | до 16 суток |

Open-Meteo используется как транспорт конкретной явно выбранной модели. Режимы `best_match` и `seamless` не используются, поэтому значения разных моделей не смешиваются.

Прямой `noaa_gfs_0p25` получает небольшие подмножества GRIB2 с NOAA/NCEP NOMADS и требует ecCodes.

Подробнее: [`docs/SOURCES.md`](docs/SOURCES.md).

## 🌧️ Научные правила ансамбля

Основные правила реализации:

- все члены одной системы имеют равный вес;
- температура и давление: среднее и стандартное отклонение относительно среднего;
- осадки, ветер и другие асимметричные величины: медиана;
- диапазон неопределённости: `q10–q90`;
- квантили рассчитываются методом Hyndman–Fan type 8;
- направление ветра усредняется на окружности;
- вероятность события: `100 × M / N`;
- вероятность явно называется сырой и некалиброванной;
- неполный ансамбль помечается как сомнительный;
- Brier Skill Score, CRPSS и калиброванные вероятности не создаются без архива наблюдений и ретропрогнозов.

## 🔒 Полностью закрытый контур

На шлюзе с Интернетом:

```bash
weather-to-docx keys generate \
  --private-key keys/forecast-private.pem \
  --public-key keys/forecast-public.pem

weather-to-docx collect-bundle \
  --config examples/locations.yml \
  --output forecast-bundle.tar.zst \
  --private-key keys/forecast-private.pem
```

На изолированном сервере:

```bash
weather-to-docx generate-bundle \
  --bundle forecast-bundle.tar.zst \
  --public-key /etc/weather-to-docx/keys/forecast-public.pem \
  --require-signature \
  --output /var/lib/weather-to-docx/documents
```

Внутри закрытого контура ключи внешних сервисов не нужны.

## 🧪 Разработка

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

ruff check .
pytest
node --check src/weather_to_docx/static/app.js
weather-to-docx sample --output var/sample --hours 24
```

Запуск API и worker:

```bash
weather-to-docx-api
weather-to-docx worker
```

Swagger:

```text
http://127.0.0.1:8080/docs
```

## 📚 Документация

- [`docs/ENSEMBLES.md`](docs/ENSEMBLES.md) — научная обработка ансамблей;
- [`docs/TELEGRAM.md`](docs/TELEGRAM.md) — Telegram-бот;
- [`docs/DADATA.md`](docs/DADATA.md) — геокодирование;
- [`docs/OFFLINE_INSTALL.md`](docs/OFFLINE_INSTALL.md) — Astra Linux и закрытый контур;
- [`docs/API.md`](docs/API.md) — HTTP API;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — архитектура;
- [`docs/SOURCES.md`](docs/SOURCES.md) — модели и происхождение данных;
- [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) — приёмка.

## ⚠️ Ограничения

- прогноз не заменяет официальные штормовые предупреждения;
- точность зависит от модели, разрешения, рельефа и срока;
- сырая ансамблевая вероятность не равна локально откалиброванной вероятности;
- город или адрес необходимо проверять по координатам;
- для производственного Astra-релиза комплект нужно собирать в совместимой Astra Linux той же архитектуры и версии `glibc`.
