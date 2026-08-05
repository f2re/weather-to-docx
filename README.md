# 🌦️ Weather to DOCX

`weather-to-docx` получает прогнозы по городам и координатам, сравнивает выбранные модели и формирует документ Microsoft Word с оперативной сводкой и метеограммами.

Текущая версия: **0.4.1**.

## Что создаётся

Для каждой точки формируется отдельный DOCX.

Страницы 1–2 содержат краткую оперативную сводку:

- главное на выбранный период;
- прогноз по дням до 7 суток;
- температуру, осадки, ветер, порывы и давление;
- оценку согласованности моделей;
- контрольные сроки через 6 часов в первые трое суток и через 12 часов далее.

Далее добавляется по одной странице на каждую пригодную детерминированную модель:

- компактная суточная таблица;
- метеограмма на весь срок.

Последняя страница выбранного ансамбля содержит:

- вероятностную таблицу;
- медианный прогноз;
- диапазон `q10–q90`;
- внутренний температурный диапазон `mean ± σ`;
- вероятности превышения порогов осадков.

## Состав метеограммы

Детерминированная метеограмма показывает:

- температуру и точку росы;
- относительную влажность;
- низкую, среднюю и высокую облачность;
- осадки за исходный интервал;
- скорость и направление ветра;
- порывы;
- давление;
- ночные периоды мягким затемнением.

Непрерывные величины сглаживаются shape-preserving методом PCHIP. Он проходит через исходные сроки и не создаёт новых экстремумов. Осадки не сглаживаются и остаются в нативных интервалах источника.

Подробная методика: [`docs/METEOGRAMS.md`](docs/METEOGRAMS.md).

## Важно: `git pull` не обновляет установленную службу

Рабочая служба запускается не из каталога git, а из атомарно установленного релиза:

```text
/opt/weather-to-docx/current/venv
```

Поэтому команды

```bash
git pull
sudo systemctl restart weather-to-docx-api weather-to-docx-worker
```

обновляют исходники, но могут оставить API и worker на старом Python-пакете. В этом случае интерфейс и документы выглядят так же, как до обновления.

Для обновления установленной системы из git-каталога используется одна команда:

```bash
cd /путь/к/weather-to-docx
git switch main
git pull --ff-only origin main
./scripts/update.sh
```

Скрипт:

1. определяет версию исходного кода и установленного runtime;
2. собирает автономный wheelhouse;
3. проверяет SHA-256 комплекта;
4. атомарно устанавливает новый релиз в `/opt/weather-to-docx/releases`;
5. переключает `/opt/weather-to-docx/current`;
6. перезапускает API и worker;
7. формирует контрольный DOCX;
8. проверяет, что внутри DOCX действительно есть крупное изображение метеограммы.

Для сборки с Python-дополнением ecCodes:

```bash
./scripts/update.sh --with-grib
```

## Проверка фактически запущенной версии

Проверить установленный пакет:

```bash
/opt/weather-to-docx/current/venv/bin/weather-to-docx --version
```

Проверить путь Python, загруженный генератор и зависимости:

```bash
/opt/weather-to-docx/current/venv/bin/weather-to-docx-verify
```

Полная проверка с формированием DOCX:

```bash
/opt/weather-to-docx/current/venv/bin/weather-to-docx-verify --deep
```

Успешный результат должен содержать:

```json
{
  "version": "0.4.1",
  "document_generator": "weather_to_docx.document.meteogram_document",
  "meteogram_ready": true,
  "meteogram_embedded": true,
  "large_media_count": 1
}
```

Диагностика через API:

```bash
curl -sS http://127.0.0.1:8080/api/v1/diagnostics | python3 -m json.tool
```

Ключевые поля:

```text
version
python_executable
package_file
document_generator
meteogram_generator_active
matplotlib_available
numpy_available
meteogram_ready
```

Интерфейс блокирует создание задания с метеограммами, если сервер работает из старого или неполного runtime. Генератор также не выдаёт «успешный» DOCX без графика: итоговый OOXML проверяется после сохранения.

## Запуск для разработки

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

## Работа в браузере

1. Добавить город, адрес, координаты или TXT/CSV/JSON.
2. Выбрать одну или несколько детерминированных моделей.
3. При необходимости выбрать один ансамбль.
4. Указать срок 1–7 суток и пороги осадков.
5. Оставить включённым пункт «Добавить метеограммы».
6. Убедиться, что в блоке «Система» указано `Метеограммы: готовы`.
7. Сформировать документ.

Метеограммы можно отключить. Тогда формируется только компактная двухстраничная сводка.

## Источники

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

## Часовые пояса

IANA timezone определяется локально по координатам. Для каждой точки сохраняется происхождение значения:

```text
explicit        — задано оператором
coordinates     — определено по координатам
geocoder        — получено при геокодировании
system_default  — резервное значение, требуется проверка
```

Все подписи времени и метеограммы используют локальное время точки.

## Telegram

Команды:

```text
/forecast  — справка
/cancel    — отменить активное задание
/sources   — модели
/settings  — настройки и состояние worker
/help      — помощь
```

Telegram и браузер используют одну SQLite-очередь. Одна точка возвращает DOCX, несколько — ZIP.

## Astra Linux без Интернета

Офлайн-комплект собирается на подключённой машине с совместимой архитектурой:

```bash
INCLUDE_GRIB=0 OUTPUT_DIR=dist/offline ./scripts/build-offline-bundle.sh
```

После переноса и распаковки:

```bash
sudo ./setup.sh
```

Подписанный комплект:

```bash
sudo ./setup.sh --keyring /root/weather-release-keyring.gpg
```

В wheelhouse входят Matplotlib, NumPy и их зависимости. SciPy не требуется. Worker запускает Matplotlib в headless-режиме:

```text
MPLBACKEND=Agg
MPLCONFIGDIR=/var/lib/weather-to-docx/cache/matplotlib
```

Полная инструкция: [`docs/OFFLINE_INSTALL.md`](docs/OFFLINE_INSTALL.md).

## Проверки проекта

```bash
ruff check .
pytest
python -m compileall -q src
node --check src/weather_to_docx/static/app.js
node --check src/weather_to_docx/static/reliability.js
node --check src/weather_to_docx/static/compact_report.js
weather-to-docx-verify --deep
```

CI проверяет Python 3.11–3.13, PCHIP, обработку пропусков, детерминированный и ансамблевый PNG, фактическое встраивание крупного графика в DOCX, LibreOffice, wheel и автономный комплект.

## Документация

- [`docs/METEOGRAMS.md`](docs/METEOGRAMS.md) — устройство и научная семантика графиков;
- [`docs/ENSEMBLES.md`](docs/ENSEMBLES.md) — ансамблевая методика;
- [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) — приёмка;
- [`docs/OFFLINE_INSTALL.md`](docs/OFFLINE_INSTALL.md) — Astra Linux;
- [`docs/TELEGRAM.md`](docs/TELEGRAM.md) — Telegram;
- [`docs/DADATA.md`](docs/DADATA.md) — геокодирование;
- [`docs/API.md`](docs/API.md) — HTTP API;
- [`CHANGELOG.md`](CHANGELOG.md) — история изменений.
