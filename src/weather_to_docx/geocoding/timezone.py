from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@lru_cache(maxsize=1)
def _finder():
    try:
        from timezonefinder import TimezoneFinder
    except ImportError as exc:  # pragma: no cover - проверяется диагностикой установки
        raise RuntimeError(
            "Локальный справочник часовых поясов не установлен. "
            "Установите зависимость timezonefinder."
        ) from exc
    return TimezoneFinder(in_memory=True)


@lru_cache(maxsize=10000)
def timezone_at(latitude: float, longitude: float) -> str | None:
    """Определить IANA timezone локально, без сетевого запроса.

    Координаты округляются вызывающей стороной только для ключа кэша. Сам поиск
    выполняется по переданным значениям и сохраняет пограничную точность
    используемого справочника.
    """

    if not -90 <= latitude <= 90:
        raise ValueError("Широта должна находиться от -90 до 90")
    if not -180 <= longitude <= 180:
        raise ValueError("Долгота должна находиться от -180 до 180")
    value = _finder().timezone_at(lat=latitude, lng=longitude)
    if value is None:
        value = _finder().certain_timezone_at(lat=latitude, lng=longitude)
    if not value:
        return None
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return None
    return value


def resolve_timezone(
    latitude: float,
    longitude: float,
    *,
    fallback: str,
) -> tuple[str, str]:
    """Вернуть timezone и происхождение значения.

    `coordinates` означает локальное определение по полигонам часовых поясов.
    `system_default` используется только как явный резерв и должен быть показан
    оператору в документе или интерфейсе.
    """

    resolved = timezone_at(float(latitude), float(longitude))
    if resolved:
        return resolved, "coordinates"
    try:
        ZoneInfo(fallback)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Неизвестный резервный часовой пояс: {fallback}") from exc
    return fallback, "system_default"
