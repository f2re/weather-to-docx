# 🗺️ Геокодирование DaData

## Зачем используется DaData

Система должна принимать не только координаты, но и понятные человеку названия:

```text
Псков
Санкт-Петербург, Невский проспект
Великий Новгород
```

DaData преобразует строку в координаты и нормализованное название. Результат всегда сохраняется в справочник как обычная `Location`, поэтому дальнейшая генерация не зависит от DaData.

## Два разных режима API

### Подсказки

Endpoint:

```text
https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address
```

Требуется:

```dotenv
WTD_DADATA_TOKEN="token"
```

Подсказки используются в веб-интерфейсе, где оператор видит несколько вариантов и выбирает нужный.

Официальная документация прямо указывает, что подсказки не предназначены для полностью автоматической обработки адресной базы: окончательное решение должен принимать человек.

### Стандартизация

Endpoint:

```text
https://cleaner.dadata.ru/api/v1/clean/address
```

Требуются:

```dotenv
WTD_DADATA_TOKEN="token"
WTD_DADATA_SECRET="secret"
```

Стандартизация применяется для автоматической обработки строк файла, когда secret настроен. Она возвращает координаты, нормализованный адрес и код качества.

DaData принимает один адрес за запрос, поэтому система обрабатывает список последовательно и ограничивает количество точек.

## Получение ключей

1. Зарегистрируйтесь на DaData.
2. Подтвердите электронную почту.
3. В личном кабинете скопируйте API token.
4. Для стандартизации скопируйте secret key.
5. Выполните:

```bash
sudo weather-to-docx-configure
```

6. Вставьте token и, при необходимости, secret.

Настройки хранятся в:

```text
/etc/weather-to-docx/weather-to-docx.env
```

## Безопасность

`secret` никогда не должен попадать:

- в JavaScript;
- в HTML;
- в HTTP-ответ диагностического API;
- в Telegram-сообщение;
- в журнал;
- в Git.

Все обращения к DaData выполняет серверная часть.

Рекомендуемые права:

```bash
sudo chown root:weatherdoc /etc/weather-to-docx/weather-to-docx.env
sudo chmod 0640 /etc/weather-to-docx/weather-to-docx.env
```

## HTTP API приложения

### Подсказки

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/geocoding/suggest \
  -H 'Content-Type: application/json' \
  -d '{"query":"Псков","count":5}'
```

### Выбрать один адрес

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/geocoding/resolve \
  -H 'Content-Type: application/json' \
  -d '{"query":"Псков","automatic":false}'
```

### Автоматическая стандартизация

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/geocoding/resolve \
  -H 'Content-Type: application/json' \
  -d '{"query":"пск обл псков","automatic":true}'
```

При `automatic=true` система использует стандартизацию, если secret задан. Без secret используется первая подсказка с явным ограничением достоверности.

### Обратное геокодирование

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/geocoding/reverse \
  -H 'Content-Type: application/json' \
  -d '{"latitude":57.8193,"longitude":28.3325,"count":1}'
```

Обратное геокодирование применяется, например, для геопозиции Telegram.

## Качество координат

DaData возвращает `qc_geo`. Код сохраняется в кандидате геокодирования:

| Код | Смысл |
|---:|---|
| 0 | точные координаты |
| 1 | ближайший дом |
| 2 | улица |
| 3 | населённый пункт |
| 4 | город |
| 5 | координаты не определены |

Для прогноза по городу код 4 допустим, но оператор должен понимать, что это координаты города, а не конкретного объекта.

## Работа без DaData

DaData необязательна. Если `WTD_DADATA_TOKEN` не задан, приложение автоматически
использует бесплатный геокодер [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org/).
Он поддерживает поиск города и адреса, импорт названий из TXT/CSV/JSON и обратное
геокодирование Telegram-геопозиции. Публичный endpoint ограничен одним запросом в
секунду; приложение соблюдает это ограничение. Для высокой нагрузки настройте
собственный Nominatim-совместимый endpoint:

```dotenv
WTD_NOMINATIM_URL="https://nominatim.openstreetmap.org"
WTD_NOMINATIM_TIMEOUT_SECONDS=20
```

Без исходящего HTTPS-доступа доступны:

- ручной ввод координат;
- TXT с координатами;
- CSV с координатами;
- JSON с координатами;
- геопозиция Telegram.

DaData имеет приоритет, если задан `WTD_DADATA_TOKEN`. Его `secret` по-прежнему
используется для пакетной стандартизации адресов; Nominatim для неё применяет
обычный поиск первого совпадения.

## Диагностика

```bash
curl -sS http://127.0.0.1:8080/api/v1/diagnostics | python3 -m json.tool
```

В ответе присутствуют только признаки:

```json
{
  "dadata_configured": true,
  "dadata_cleaner_configured": true
}
```

Сами ключи не возвращаются.

## Официальные источники

- DaData API: https://dadata.ru/api/
- Подсказки по адресам: https://dadata.ru/api/suggest/address/
- Стандартизация адресов: https://dadata.ru/api/clean/address/
- Обратное геокодирование: https://dadata.ru/api/geolocate/
