# 🛠️ Разработка и проверка

## Среда

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Для прямого GFS:

```bash
sudo apt install libeccodes0 libeccodes-data
python -m pip install -e '.[dev,grib]'
```

## Проверки

```bash
make test
make lint
make sample
make check
```

Эквивалентно:

```bash
ruff check .
pytest
python -m compileall -q src
weather-to-docx sample --output var/sample --hours 24
```

Интеграционные тесты используют локальные фикстуры и не обращаются к Интернету.

## Структура тестов

- `test_open_meteo.py` — нормализация JSON и метаданные;
- `test_gfs_nomads.py` — выбор цикла, параметры подмножества и преобразования;
- `test_weather_rules.py` — приоритеты погодных явлений;
- `test_document.py` — создание валидного DOCX с двумя таблицами;
- `test_batch_and_jobs.py` — пакетная генерация и SQLite-очередь;
- `test_bundle.py` — подпись, контрольные суммы и безопасный импорт.

## Добавление параметра

1. Добавьте описание в `domain/parameters.py`.
2. Нормализуйте поле в нужном адаптере.
3. Укажите единицу и исходное имя.
4. Для расчётного поля установите `QualityFlag.CALCULATED`.
5. Добавьте колонку только в соответствующий профиль документа.
6. Добавьте тест отсутствующего и корректного значения.

## Добавление источника

1. Создайте `sources/<source>.py`.
2. Реализуйте `ForecastSource.fetch`.
3. Заполните `SourceDescriptor` и `SourceMetadata`.
4. Зарегистрируйте источник в `SourceRegistry`.
5. Сохраните компактную официальную фикстуру.
6. Добавьте тест без сетевых обращений.
7. Обновите `README.md` и `docs/SOURCES.md`.

## Правила коммитов

Коммиты должны быть небольшими и описывать законченный результат, например:

```text
Добавлен адаптер ECMWF IFS Open Data
Исправлен расчёт интервальных осадков GFS
Добавлена автономная установка Astra Linux
```

Секреты, закрытые ключи, реальные `.env`, прогнозные GRIB и сгенерированные документы в репозиторий не добавляются.
