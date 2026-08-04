# 🌦️ Weather to DOCX

`weather-to-docx` получает прогнозы по городам или координатам и формирует отдельный документ Microsoft Word для каждой точки.

- одна точка → `DOCX`;
- несколько точек → отдельные `DOCX` и общий `ZIP`;
- детерминированные модели выводятся первыми;
- ансамблевая неопределённость выводится одной отдельной таблицей в конце;
- веб-интерфейс, Telegram, API и CLI используют одну очередь и одно вычислительное ядро;
- приложение устанавливается на Astra Linux без обращения к Интернету.

Текущая версия: **0.3.1**.

## 📄 Что находится в документе

Для каждой детерминированной модели создаются две таблицы:

1. **Наглядный прогноз** — пиктограмма, температура, осадки, ветер, порывы, давление и облачность.
2. **Подробный отчёт** — почасовые или нативные сроки, влажность, точка росы, осадки, снег, видимость, конвекция, радиация, почва и другие доступные параметры.

После всех моделей добавляется один раздел:

> **Ансамблевая оценка неопределённости**

В нём системы GEFS, ECMWF ENS, AIFS ENS, ICON-EPS и GEPS сравниваются отдельно. Их члены не смешиваются в искусственный супер-ансамбль.

Ансамблевая таблица показывает:

- доступное и ожидаемое число членов;
- полноту ансамбля;
- среднее, медиану и стандартное отклонение;
- диапазон `q10–q90`;
- сырые вероятности превышения порогов осадков;
- минимальный шаг вероятности `100 / N`.

Методика: [`docs/ENSEMBLES.md`](docs/ENSEMBLES.md).

## 🚀 Быстрый запуск для разработки

Требуется Python 3.11 или новее.

```bash
git clone https://github.com/f2re/weather-to-docx.git
cd weather-to-docx

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Проверка без Интернета:

```bash
weather-to-docx init
weather-to-docx doctor --deep
weather-to-docx sample --output var/sample --hours 24
```

Запуск веб-интерфейса и worker:

```bash
weather-to-docx-api
```

Во втором терминале:

```bash
weather-to-docx worker --poll-interval 5
```

Открыть:

```text
http://127.0.0.1:8080/
```

## 📦 Установка на Astra Linux без Интернета

Офлайн-комплект собирается на машине с Интернетом в совместимой версии Astra Linux, затем переносится на целевой сервер.

После распаковки:

```bash
sudo ./setup.sh
```

Для подписанного комплекта:

```bash
sudo ./setup.sh \
  --keyring /root/weather-release-keyring.gpg
```

`setup.sh`:

1. проверяет SHA-256 и подпись;
2. устанавливает системные пакеты только из вложенного APT-репозитория;
3. устанавливает Python-пакеты только из `wheelhouse`;
4. сохраняет существующую SQLite-базу;
5. атомарно переключает релиз;
6. запускает диагностику;
7. открывает мастер настройки;
8. запускает API, worker и, при необходимости, Telegram.

Полная инструкция: [`docs/OFFLINE_INSTALL.md`](docs/OFFLINE_INSTALL.md).

## ⚙️ Первичная настройка

Мастер запускается автоматически после установки. Повторный запуск:

```bash
sudo weather-to-docx-configure
```

Он запрашивает:

- адрес и порт веб-интерфейса;
- резервный часовой пояс;
- горизонт прогноза;
- набор моделей;
- DaData token и secret;
- Telegram bot token;
- разрешённые Telegram user ID.

Настройки хранятся здесь:

```text
/etc/weather-to-docx/weather-to-docx.env
```

Ручное редактирование:

```bash
sudoedit /etc/weather-to-docx/weather-to-docx.env
sudo systemctl restart weather-to-docx-api weather-to-docx-worker
sudo systemctl restart weather-to-docx-telegram
```

## 🖥️ Работа через браузер

Основной сценарий состоит из трёх шагов.

### 1. Выбрать точки

Можно:

- найти город или адрес через DaData;
- ввести координаты;
- загрузить TXT, CSV или JSON;
- выбрать несколько сохранённых точек.

Для координат часовой пояс определяется локально по базе IANA. Доступ к внешнему сервису для этого не нужен.

Перед импортом файла система показывает:

- распознанные названия;
- координаты;
- часовой пояс;
- предупреждения по отдельным строкам.

Точки записываются в справочник только после подтверждения.

### 2. Выбрать источники

Детерминированные модели и ансамбли показаны раздельно. Интерфейс сообщает, если выбранный источник имеет меньший горизонт, чем запросил оператор.

### 3. Сформировать документы

Доступны:

- горизонт от 1 до 35 суток;
- пороги ансамблевой вероятности осадков;
- оперативный, расширенный и полный профиль;
- A3 и A4.

Расширенный и полный профиль следует формировать в A3. Интерфейс не позволяет отправить заведомо нечитаемую комбинацию A4 с расширенной таблицей.

## 🧭 Часовые пояса

Каждая точка хранит не только IANA timezone, но и происхождение значения:

- `explicit` — введён оператором;
- `coordinates` — определён локально по координатам;
- `geocoder` — получен от геокодера;
- `system_default` — использована резервная настройка, значение нужно проверить.

Точки, сохранённые версией 0.3.0 без признака происхождения, не считаются автоматически подтверждёнными. Перед новым заданием их timezone перепроверяется по координатам.

## ⏱️ Очередь и восстановление

API, веб-интерфейс и Telegram создают задания в общей SQLite-очереди.

Worker использует:

- ограниченную по времени аренду задания;
- heartbeat;
- идентификатор worker;
- число попыток;
- прогресс по комбинациям `точка × источник`.

Если worker аварийно завершился, просроченное задание автоматически возвращается в очередь. Старый worker не может перезаписать результат нового выполнения.

Состояние:

```bash
systemctl status weather-to-docx-api
systemctl status weather-to-docx-worker
```

Журнал:

```bash
journalctl -u weather-to-docx-worker -f
```

## 🤖 Telegram-бот

Боту можно отправить:

```text
Псков
```

```text
57.8193, 28.3325
```

```text
Псков
Великий Новгород
59.9386, 30.3141
```

Также поддерживаются TXT, CSV, JSON и Telegram-геопозиция.

Ответ:

- одна точка → DOCX;
- несколько точек → ZIP;
- большой архив → отдельные DOCX.

Команды:

```text
/forecast  — как отправить точку или файл
/cancel    — отменить последнее активное задание
/sources   — используемые модели
/settings  — текущие настройки и worker
/help      — краткая справка
```

Telegram использует общую очередь. Перезапуск процесса бота не удаляет поставленное задание.

Ограничить доступ:

```dotenv
WTD_TELEGRAM_ALLOWED_USER_IDS="123456789,987654321"
```

Подробнее: [`docs/TELEGRAM.md`](docs/TELEGRAM.md).

## 🗺️ DaData

Для поиска города или адреса:

```dotenv
WTD_DADATA_TOKEN="ваш-token"
```

Для автоматической стандартизации пакетных адресов:

```dotenv
WTD_DADATA_SECRET="ваш-secret"
```

DaData используется только для преобразования названия или адреса в координаты. Часовой пояс после этого определяется локально по координатам.

Без DaData можно работать с координатами и файлами, содержащими широту и долготу.

Подробнее: [`docs/DADATA.md`](docs/DADATA.md).

## 🛰️ Источники прогноза

### Детерминированные

| `source_id` | Исходная модель | Канал |
|---|---|---|
| `open_meteo_gfs` | NOAA GFS | Open-Meteo JSON |
| `open_meteo_ecmwf_ifs` | ECMWF IFS Open Data | Open-Meteo JSON |
| `open_meteo_ecmwf_aifs` | ECMWF AIFS | Open-Meteo JSON |
| `open_meteo_dwd_icon_global` | DWD ICON Global | Open-Meteo JSON |
| `open_meteo_gem_gdps` | ECCC GDPS | Open-Meteo JSON |
| `noaa_gfs_0p25` | NOAA GFS 0.25° | прямой NOMADS GRIB2 |

### Ансамблевые

| `source_id` | Система |
|---|---|
| `open_meteo_gefs_0p25` | NOAA GEFS 0.25° |
| `open_meteo_gefs_0p5` | NOAA GEFS 0.5° |
| `open_meteo_ecmwf_ifs_ensemble` | ECMWF IFS ENS |
| `open_meteo_ecmwf_aifs_ensemble` | ECMWF AIFS ENS |
| `open_meteo_dwd_icon_eps` | DWD ICON-EPS |
| `open_meteo_gem_geps` | ECCC GEPS |

Open-Meteo используется как транспорт явно выбранной модели. Режимы автоматического смешивания моделей не применяются.

Прямой `noaa_gfs_0p25` сохраняет точный цикл и требует ecCodes. Для большого числа точек этот источник создаёт значительную сетевую нагрузку; используйте его осознанно.

Подробнее: [`docs/SOURCES.md`](docs/SOURCES.md).

## 🔒 Полностью закрытый контур

Сервер без исходящего доступа не может сам загрузить свежий прогноз. Данные собираются на шлюзе и переносятся подписанным пакетом.

На шлюзе:

```bash
weather-to-docx keys generate \
  --private-key keys/forecast-private.pem \
  --public-key keys/forecast-public.pem

weather-to-docx collect-bundle \
  --config examples/locations.yml \
  --output forecast-bundle.tar.zst \
  --private-key keys/forecast-private.pem
```

В закрытом контуре:

```bash
weather-to-docx generate-bundle \
  --bundle forecast-bundle.tar.zst \
  --public-key /etc/weather-to-docx/keys/forecast-public.pem \
  --require-signature \
  --output /var/lib/weather-to-docx/documents
```

## 🧪 Проверка проекта

```bash
ruff check .
pytest
node --check src/weather_to_docx/static/app.js
node --check src/weather_to_docx/static/reliability.js
weather-to-docx sample --output var/sample --hours 24
```

CI проверяет Python 3.11, 3.12 и 3.13, wheel, автономный DOCX и офлайн-комплект.

## 📚 Документация

- [`docs/REMEDIATION_PLAN.md`](docs/REMEDIATION_PLAN.md) — план устранения оставшихся узких мест;
- [`docs/ENSEMBLES.md`](docs/ENSEMBLES.md) — научная методика ансамблей;
- [`docs/TELEGRAM.md`](docs/TELEGRAM.md) — Telegram-бот;
- [`docs/DADATA.md`](docs/DADATA.md) — геокодирование;
- [`docs/OFFLINE_INSTALL.md`](docs/OFFLINE_INSTALL.md) — Astra Linux и закрытый контур;
- [`docs/API.md`](docs/API.md) — HTTP API;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — архитектура;
- [`docs/SOURCES.md`](docs/SOURCES.md) — модели и происхождение данных;
- [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) — приёмка.

## ⚠️ Ограничения

- прогноз не заменяет официальные штормовые предупреждения;
- сырая ансамблевая вероятность не является локально калиброванной;
- серверный API по умолчанию слушает только `127.0.0.1`;
- для сетевого доступа требуется reverse proxy с TLS и аутентификацией;
- производственный офлайн-комплект нужно собирать в совместимой версии Astra Linux;
- построчное редактирование неоднозначных адресов и отдельная компактная компоновка A4 развиваются по [`плану`](docs/REMEDIATION_PLAN.md).
