# 🛰️ Источники прогнозов

Документ фиксирует происхождение данных, модель, способ доставки, горизонт, правила расчёта ансамблевых продуктов и ограничения, которые должны быть видны оператору и в DOCX.

## 1. Принцип разделения моделей

Система не использует автоматические режимы `best_match`, `seamless` или незаметное объединение нескольких моделей. Каждый адаптер передаёт внешний идентификатор модели явно и создаёт самостоятельный `ForecastSeries`.

```text
поставщик данных  →  служба доставки  →  адаптер  →  ForecastSeries  →  секция DOCX
```

Пример:

```text
ECMWF             →  Open-Meteo       →  open_meteo_ecmwf_ifs
исходная модель      доставка JSON       отдельная секция ECMWF IFS
```

В метаданных сохраняются:

- `source_id` адаптера;
- организация-поставщик;
- название исходной модели;
- внешний идентификатор модели;
- служба доставки;
- цикл, если он достоверно известен;
- время получения;
- горизонт и шаг выдачи;
- сетка и расстояние до выбранного узла;
- лицензия и атрибуция;
- число членов ансамбля и порог вероятности осадков.

## 2. Реализованные детерминированные источники

| `source_id` | Поставщик / модель | Внешний идентификатор | Доставка | Горизонт | Точный цикл |
|---|---|---|---|---:|---|
| `open_meteo_gfs` | NOAA GFS 0.25° | `gfs025` | Open-Meteo GFS JSON | 16 суток | нет в стандартном ответе |
| `open_meteo_ecmwf_ifs` | ECMWF IFS 0.25° Open Data | `ecmwf_ifs025` | Open-Meteo ECMWF JSON | 15 суток | нет в стандартном ответе |
| `open_meteo_ecmwf_aifs` | ECMWF AIFS 0.25° Single | `ecmwf_aifs025_single` | Open-Meteo ECMWF JSON | 15 суток | нет в стандартном ответе |
| `open_meteo_dwd_icon_global` | DWD ICON Global | `dwd_icon_global` | Open-Meteo DWD ICON JSON | 8 суток | нет в стандартном ответе |
| `open_meteo_gem_gdps` | ECCC GEM Global / GDPS | `cmc_gem_gdps` | Open-Meteo GEM JSON | 10 суток | нет в стандартном ответе |
| `noaa_gfs_0p25` | NOAA/NCEP GFS 0.25° | GRIB product inventory | прямой NOAA NOMADS GRIB2 | 384 часа | да |
| `demo` | синтетический тестовый ряд | локальный генератор | без сети | задаётся параметром | не применимо |

### 2.1. Адаптеры Open-Meteo

Базовый запрос содержит конкретный параметр `models`, поэтому разные прогностические системы не смешиваются. По умолчанию запрашивается совместимый набор приземных полей. Через `options.hourly` можно явно задать расширенный список, если выбранная модель его предоставляет.

Пример:

```yaml
sources:
  - source_id: open_meteo_ecmwf_ifs
    forecast_days: 10
    options:
      cell_selection: nearest
      hourly:
        - temperature_2m
        - relative_humidity_2m
        - dew_point_2m
        - pressure_msl
        - precipitation
        - cloud_cover
        - wind_speed_10m
        - wind_direction_10m
```

Преимущества:

- единый документированный JSON;
- не требуется локальный декодер GRIB;
- можно быстро подключить несколько независимых моделей;
- удобно использовать на сетевом шлюзе для закрытого контура.

Ограничения:

- Open-Meteo является службой доставки и обработки, а не исходным владельцем модели;
- стандартный ответ обычно не содержит достоверного времени исходного цикла;
- временная сетка может быть приведена к почасовой;
- доступность публичного API и его лимиты находятся вне контроля установки;
- для производственной нагрузки следует использовать собственный шлюз, разрешённый тариф либо прямые источники.

В DOCX одновременно указываются исходная модель и доставка через Open-Meteo.

### 2.2. NOAA GFS 0.25° через NOMADS

Endpoint фильтра:

```text
https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl
```

Шаблон продукта:

```text
gfs.YYYYMMDD/CC/atmos/gfs.tCCz.pgrb2.0p25.fFFF
```

где:

- `CC` — цикл `00`, `06`, `12` или `18 UTC`;
- `FFF` — заблаговременность;
- `pgrb2.0p25` — регулярная сетка 0.25°.

Адаптер получает только выбранные параметры, уровни и небольшой прямоугольник вокруг координаты. Полный глобальный GRIB2 не скачивается.

Основные сообщения:

```text
TMP RH DPT PRMSL PRES UGRD VGRD GUST
APCP ACPCP TCDC LCDC MCDC HCDC
VIS CAPE CIN DSWRF PWAT HPBL WEASD SNOD
```

Внутренние расчёты:

- скорость и направление ветра из `UGRD/VGRD`;
- интервальные осадки из накопленного `APCP`;
- погодный код по локальным правилам приоритетов;
- точный цикл и срок из GRIB-метаданных.

Требуется ecCodes:

```bash
sudo apt install libeccodes0 libeccodes-data
python -m pip install 'weather-to-docx[grib]'
```

Для Astra Linux эти пакеты должны войти в локальный APT-репозиторий и wheelhouse автономного комплекта.

## 3. Реализованные ансамблевые источники

| `source_id` | Ансамбль | Внешний идентификатор | Горизонт |
|---|---|---|---:|
| `open_meteo_gefs_0p25` | NOAA GEFS 0.25° | `ncep_gefs025` | 10 суток |
| `open_meteo_gefs_0p5` | NOAA GEFS 0.5° | `ncep_gefs05` | 35 суток |
| `open_meteo_ecmwf_ifs_ensemble` | ECMWF IFS ENS 0.25° | `ecmwf_ifs025_ensemble` | 15 суток |
| `open_meteo_ecmwf_aifs_ensemble` | ECMWF AIFS ENS 0.25° | `ecmwf_aifs025_ensemble` | 15 суток |
| `open_meteo_dwd_icon_eps` | DWD ICON Global EPS | `dwd_icon_global_eps` | 8 суток |
| `open_meteo_gem_geps` | ECCC GEPS | `cmc_gem_geps` | 16 суток |

Endpoint:

```text
https://ensemble-api.open-meteo.com/v1/ensemble
```

### 3.1. Статистики

Для каждого доступного числового параметра рассчитываются:

- среднее ансамбля;
- стандартное отклонение `σ`;
- 10-й процентиль `p10`;
- 90-й процентиль `p90`;
- фактическое число доступных членов.

Направление ветра усредняется как круговая величина. Обычное арифметическое среднее направлений запрещено: например, `350°` и `10°` должны дать направление около `0°`, а не `180°`.

Категориальный код погоды выбирается по моде доступных членов.

### 3.2. Вероятность осадков

```text
PoP = N(осадки ≥ порога) / N(доступные члены) × 100 %
```

Пример настройки:

```yaml
- source_id: open_meteo_gefs_0p25
  forecast_days: 10
  options:
    precipitation_threshold_mm: 0.1
```

Порог не может быть отрицательным. В примечании значения сохраняются порог и число использованных членов. При неполном наборе членов расчёт продолжается по фактически доступным данным.

### 3.3. Интерпретация дальнего GEFS

`open_meteo_gefs_0p5` предназначен прежде всего для тенденции и вероятностной оценки на дальнем горизонте. Почасовые строки после 10–16 суток нельзя интерпретировать как точный сценарий погоды для конкретного объекта.

## 4. Параметры YAML

### Детерминированная модель через Open-Meteo

```yaml
- source_id: open_meteo_dwd_icon_global
  forecast_days: 8
  options:
    cell_selection: nearest
```

### Внутреннее зеркало или шлюз

```yaml
- source_id: open_meteo_gfs
  forecast_days: 10
  options:
    endpoint: https://weather-gateway.example.test/v1/gfs
```

### Ансамбль

```yaml
- source_id: open_meteo_ecmwf_ifs_ensemble
  forecast_days: 15
  options:
    precipitation_threshold_mm: 0.5
```

### Прямой GFS

```yaml
- source_id: noaa_gfs_0p25
  forecast_days: 7
  options:
    hourly_to_120: true
    max_concurrency: 4
    box_degrees: 0.5
    # cycle: 2026-08-03T12:00:00Z
```

`hourly_to_120: true` означает шаг 1 час до +120 ч и 3 часа далее. При `false` используется шаг 3 часа.

## 5. Отображение в DOCX

Для каждой модели создаётся самостоятельная секция. Перед таблицами выводятся:

- поставщик и модель;
- `source_id`;
- внешний идентификатор модели;
- цикл либо отметка об отсутствии точного цикла;
- время получения;
- горизонт и шаг;
- сетка;
- продукт;
- число членов ансамбля.

Вторая таблица содержит оперативные группы параметров и, при `include_all_parameters: true`, дополнительный столбец со всеми остальными полями:

- `*_spread`;
- `*_p10`;
- `*_p90`;
- изобарические уровни;
- поля конкретного поставщика, которые не имеют отдельного стандартного столбца.

## 6. Запрещённые упрощения

- нельзя выдавать детерминированные осадки за вероятность;
- нельзя считать цикл известным, если источник его не сообщил;
- нельзя заменять пропущенный параметр нулём;
- нельзя смешивать сроки из разных циклов;
- нельзя скрывать службу доставки данных;
- нельзя незаметно подменять одну модель другой;
- нельзя арифметически усреднять направление ветра;
- нельзя линейно интерполировать категориальные явления, тип осадков или экстремальные порывы;
- нельзя использовать синтетический `demo` как реальный прогноз.

## 7. Официальная документация

- Open-Meteo Forecast API: <https://open-meteo.com/en/docs>
- Open-Meteo Ensemble API: <https://open-meteo.com/en/docs/ensemble-api>
- Open-Meteo ECMWF API: <https://open-meteo.com/en/docs/ecmwf-api>
- Open-Meteo DWD ICON API: <https://open-meteo.com/en/docs/dwd-api>
- Open-Meteo GEM API: <https://open-meteo.com/en/docs/gem-api>
- NOAA GFS inventory: <https://www.nco.ncep.noaa.gov/pmb/products/gfs/>
- NOAA GEFS inventory: <https://www.nco.ncep.noaa.gov/pmb/products/gens/>
- NOAA NOMADS: <https://nomads.ncep.noaa.gov/>
- ECMWF Open Data: <https://www.ecmwf.int/en/forecasts/datasets/open-data>
- ECMWF ecCodes: <https://github.com/ecmwf/eccodes>
- DWD Open Data: <https://opendata.dwd.de/>
- ECCC Open Data: <https://eccc-msc.github.io/open-data/>
