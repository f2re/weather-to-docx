# 🌦️ Weather to DOCX

`weather-to-docx` получает прогнозы по городам и координатам, сравнивает выбранные модели и формирует профессиональный документ Microsoft Word.

Текущая версия: **0.4.0**.

## 📄 Структура документа

Документ разделён на оперативную сводку и наглядные приложения.

### Страницы 1–2 — короткая сводка

- главное на выбранный период;
- прогноз по дням до 7 суток;
- температура, осадки, ветер, порывы и давление;
- оценка согласованности моделей;
- контрольные сроки через 6 часов в первые трое суток и через 12 часов далее.

### Далее — по одной странице на модель

Для каждой модели, содержащей полноценный набор данных:

- компактная суточная таблица;
- профессиональная метеограмма на весь срок.

Метеограмма показывает:

- температуру и точку росы;
- относительную влажность;
- низкую, среднюю и высокую облачность полупрозрачными слоями;
- осадки за исходный интервал;
- ветер и порывы;
- давление;
- ночные периоды мягким затемнением.

### Последняя страница — ансамбль

Для одной выбранной ансамблевой системы формируются:

- компактная вероятностная таблица;
- медианный прогноз;
- диапазон `q10–q90`;
- внутренний температурный диапазон `mean ± σ`;
- вероятности превышения порогов осадков;
- диапазоны влажности, облачности, ветра и давления.

Разные ансамблевые системы не смешиваются.

## 🎨 Сглаживание

Температура, влажность, облачность, давление и ветер сглаживаются shape-preserving методом PCHIP. Он проходит через исходные сроки и не создаёт новых экстремумов.

Осадки не сглаживаются и выводятся столбиками в нативных интервалах источника.

Подробно: [`docs/METEOGRAMS.md`](docs/METEOGRAMS.md).

## 🧹 Контроль качества данных

Перед формированием сводки оценивается полнота каждой модели:

```text
температура
осадки
ветер
порывы
давление
облачность
влажность
```

Неполная модель:

- не получает пустую страницу;
- не участвует в сводном расчёте;
- кратко указывается как исключённая.

Если ни одна модель не содержит температуры, ветра и давления, система возвращает понятную ошибку вместо документа из прочерков.

## 📦 Выходные файлы

```text
одна точка      → DOCX
несколько точек → отдельные DOCX и общий ZIP
```

Также создаётся `manifest.json` с источниками, предупреждениями, ошибками и SHA-256.

## 🚀 Запуск для разработки

Требуется Python 3.11 или новее.

```bash
git clone https://github.com/f2re/weather-to-docx.git
cd weather-to-docx

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

weather-to-docx init
```

Запустить API:

```bash
weather-to-docx-api
```

В другом терминале:

```bash
weather-to-docx worker --poll-interval 5
```

Открыть:

```text
http://127.0.0.1:8080/
```

## 🖥️ Работа в браузере

1. Добавить город, адрес, координаты или TXT/CSV/JSON.
2. Выбрать несколько детерминированных моделей.
3. При необходимости выбрать один ансамбль.
4. Указать срок 1–7 суток и пороги осадков.
5. Оставить включённым пункт «Добавить метеограммы».
6. Сформировать документ.

Метеограммы можно отключить. Тогда останется прежний компактный двухстраничный отчёт.

## 🛰️ Источники

Детерминированные модели:

```text
open_meteo_gfs
open_meteo_ecmwf_ifs
open_meteo_ecmwf_aifs
open_meteo_dwd_icon_global
open_meteo_gem_gdps
noaa_gfs_0p25
```

Ансамбли:

```text
open_meteo_gefs_0p25
open_meteo_gefs_0p5
open_meteo_ecmwf_ifs_ensemble
open_meteo_ecmwf_aifs_ensemble
open_meteo_dwd_icon_eps
open_meteo_gem_geps
```

Open-Meteo используется как транспорт явно выбранной модели. Автоматическое смешивание моделей не применяется.

## 🧭 Часовые пояса

IANA timezone определяется локально по координатам. Для каждой точки сохраняется происхождение значения:

```text
explicit        — задал оператор
coordinates     — определено по координатам
geocoder        — получено при геокодировании
system_default  — резервное значение, требуется проверка
```

Все подписи времени и метеограммы используют локальное время точки.

## 🤖 Telegram

Боту можно отправить город, координаты, TXT, CSV, JSON или Telegram-геопозицию.

Команды:

```text
/forecast  — справка
/cancel    — отменить активное задание
/sources   — модели
/settings  — настройки и состояние worker
/help      — помощь
```

Telegram и браузер используют одну SQLite-очередь. Одна точка возвращает DOCX, несколько — ZIP.

## ⏱️ Очередь

Worker использует lease, heartbeat, идентификатор worker, число попыток, прогресс `точка × источник`, возврат просроченного задания и защиту от записи результата старым worker.

Диагностика:

```bash
curl -sS http://127.0.0.1:8080/api/v1/diagnostics | python3 -m json.tool
```

Журнал:

```bash
journalctl -u weather-to-docx-worker -f
```

## 📦 Astra Linux без Интернета

Офлайн-комплект собирается на подключённой машине с совместимой версией Astra Linux.

После переноса:

```bash
sudo ./setup.sh
```

Подписанный комплект:

```bash
sudo ./setup.sh --keyring /root/weather-release-keyring.gpg
```

В wheelhouse включаются Matplotlib, NumPy и все их зависимости. SciPy для сглаживания не нужен.

Worker запускает Matplotlib в headless-режиме:

```text
MPLBACKEND=Agg
MPLCONFIGDIR=/var/lib/weather-to-docx/cache/matplotlib
```

Полная инструкция: [`docs/OFFLINE_INSTALL.md`](docs/OFFLINE_INSTALL.md).

## 🔒 Изолированный контур

На сетевом шлюзе:

```bash
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

## 🧪 Проверки

```bash
ruff check .
pytest
python -m compileall -q src
node --check src/weather_to_docx/static/app.js
node --check src/weather_to_docx/static/reliability.js
node --check src/weather_to_docx/static/compact_report.js
```

CI проверяет Python 3.11–3.13, PCHIP, пропуски, детерминированный и ансамблевый PNG, встраивание изображений, русские единицы, реальную пагинацию LibreOffice, wheel и автономный комплект.

## 📚 Документация

- [`docs/METEOGRAMS.md`](docs/METEOGRAMS.md) — устройство и научная семантика графиков;
- [`docs/ENSEMBLES.md`](docs/ENSEMBLES.md) — ансамблевая методика;
- [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) — приёмка;
- [`docs/OFFLINE_INSTALL.md`](docs/OFFLINE_INSTALL.md) — Astra Linux;
- [`docs/TELEGRAM.md`](docs/TELEGRAM.md) — Telegram;
- [`docs/DADATA.md`](docs/DADATA.md) — геокодирование;
- [`docs/API.md`](docs/API.md) — HTTP API;
- [`CHANGELOG.md`](CHANGELOG.md) — история изменений.
