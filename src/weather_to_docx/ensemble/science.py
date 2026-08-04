from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable

# Переменные с выраженно асимметричными, ограниченными или неотрицательными
# распределениями получают устойчивый медианный центр. Для температуры и
# давления сохраняется среднее, чтобы стандартное отклонение имело обычный
# смысл ансамблевого spread относительно среднего.
ROBUST_CENTRE_PARAMETERS = frozenset(
    {
        "precipitation",
        "rain",
        "showers",
        "snowfall",
        "snow_depth",
        "wind_speed_10m",
        "wind_gusts_10m",
        "cape",
        "cin",
        "cloud_cover",
        "relative_humidity_2m",
    }
)
ANGULAR_PARAMETERS = frozenset({"wind_direction_10m"})
CATEGORICAL_PARAMETERS = frozenset({"weather_code"})


@dataclass(frozen=True, slots=True)
class EnsembleStatistics:
    count: int
    mean: float
    median: float
    standard_deviation: float
    p10: float
    p90: float
    minimum: float
    maximum: float

    @property
    def interdecile_range(self) -> float:
        return self.p90 - self.p10


def finite_values(values: Iterable[float]) -> list[float]:
    return [float(value) for value in values if math.isfinite(float(value))]


def ensemble_statistics(values: Iterable[float]) -> EnsembleStatistics:
    sample = finite_values(values)
    if not sample:
        raise ValueError("Ансамбль не содержит конечных числовых значений")
    return EnsembleStatistics(
        count=len(sample),
        mean=statistics.fmean(sample),
        median=quantile_type8(sample, 0.5),
        standard_deviation=statistics.pstdev(sample) if len(sample) >= 2 else 0.0,
        p10=quantile_type8(sample, 0.10),
        p90=quantile_type8(sample, 0.90),
        minimum=min(sample),
        maximum=max(sample),
    )


def primary_centre(parameter: str, stats: EnsembleStatistics) -> tuple[float, str]:
    if parameter in ROBUST_CENTRE_PARAMETERS:
        return stats.median, "median"
    return stats.mean, "mean"


def raw_probability(values: Iterable[float], threshold: float) -> tuple[float, int, int]:
    sample = finite_values(values)
    if not sample:
        raise ValueError("Нельзя вычислить вероятность без членов ансамбля")
    exceedances = sum(value >= threshold for value in sample)
    return 100.0 * exceedances / len(sample), exceedances, len(sample)


def probability_resolution(member_count: int) -> float:
    if member_count < 1:
        raise ValueError("Число членов должно быть положительным")
    return 100.0 / member_count


def circular_mean_degrees(values: Iterable[float]) -> float:
    sample = finite_values(values)
    if not sample:
        raise ValueError("Нельзя вычислить направление без членов ансамбля")
    radians = [math.radians(value % 360.0) for value in sample]
    sine = statistics.fmean(math.sin(value) for value in radians)
    cosine = statistics.fmean(math.cos(value) for value in radians)
    if abs(sine) < 1e-12 and abs(cosine) < 1e-12:
        return sample[0] % 360.0
    return math.degrees(math.atan2(sine, cosine)) % 360.0


def quantile_type8(values: Iterable[float], probability: float) -> float:
    """Выборочная квантиль Hyndman–Fan type 8.

    Type 8 приблизительно несмещён по медиане для произвольного непрерывного
    распределения. Краевое поведение соответствует определению, применяемому
    в R ``quantile(type=8)``.
    """

    if not 0.0 <= probability <= 1.0:
        raise ValueError("Вероятность квантили должна быть от 0 до 1")
    ordered = sorted(finite_values(values))
    if not ordered:
        raise ValueError("Нельзя вычислить квантиль пустого набора")
    if len(ordered) == 1 or probability <= 0.0:
        return ordered[0]
    if probability >= 1.0:
        return ordered[-1]

    n = len(ordered)
    h = (n + 1.0 / 3.0) * probability + 1.0 / 3.0
    if h <= 1:
        return ordered[0]
    if h >= n:
        return ordered[-1]
    lower_index = math.floor(h)
    fraction = h - lower_index
    lower = ordered[lower_index - 1]
    upper = ordered[lower_index]
    return lower + fraction * (upper - lower)
