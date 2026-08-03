from __future__ import annotations

import math


RUMBS = (
    "С",
    "ССВ",
    "СВ",
    "ВСВ",
    "В",
    "ВЮВ",
    "ЮВ",
    "ЮЮВ",
    "Ю",
    "ЮЮЗ",
    "ЮЗ",
    "ЗЮЗ",
    "З",
    "ЗСЗ",
    "СЗ",
    "ССЗ",
)

ARROWS = ("↓", "↙", "←", "↖", "↑", "↗", "→", "↘")


def wind_speed_direction_from_uv(u: float, v: float) -> tuple[float, float]:
    """Return meteorological wind speed and direction from U/V components."""
    speed = math.hypot(u, v)
    if speed < 1e-9:
        return 0.0, 0.0
    direction = (270.0 - math.degrees(math.atan2(v, u))) % 360.0
    return speed, direction


def wind_rumb(direction: float | None, speed: float | None = None) -> str:
    if direction is None:
        return "—"
    if speed is not None and speed < 0.3:
        return "штиль"
    return RUMBS[int((direction + 11.25) // 22.5) % 16]


def wind_arrow(direction: float | None, speed: float | None = None) -> str:
    """Arrow shows where the air flow is moving, opposite to meteorological direction."""
    if direction is None:
        return ""
    if speed is not None and speed < 0.3:
        return "○"
    to_direction = (direction + 180.0) % 360.0
    return ARROWS[int((to_direction + 22.5) // 45.0) % 8]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
