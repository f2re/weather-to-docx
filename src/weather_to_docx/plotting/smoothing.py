from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np


def smooth_segments(
    x: Iterable[float],
    y: Iterable[float],
    *,
    samples_per_interval: int = 5,
    max_gap_factor: float = 2.6,
    lower: float | None = None,
    upper: float | None = None,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Сгладить конечные непрерывные участки методом PCHIP.

    Пропуски и большие временные разрывы не соединяются. PCHIP сохраняет
    форму и не создаёт выбросов между соседними экстремумами, поэтому подходит
    для температуры, влажности, облачности, давления и ветра. Осадки этим
    методом не обрабатываются.
    """

    x_values = np.asarray(tuple(x), dtype=float)
    y_values = np.asarray(tuple(y), dtype=float)
    if x_values.shape != y_values.shape:
        raise ValueError("Координаты и значения должны иметь одинаковую длину")
    if x_values.ndim != 1:
        raise ValueError("Сглаживание поддерживает только одномерные ряды")
    if samples_per_interval < 1:
        raise ValueError("Число отсчётов на интервал должно быть положительным")

    finite = np.isfinite(x_values) & np.isfinite(y_values)
    indexes = np.flatnonzero(finite)
    if indexes.size == 0:
        return []

    finite_steps = np.diff(x_values[indexes])
    positive_steps = finite_steps[finite_steps > 0]
    reference_step = float(np.median(positive_steps)) if positive_steps.size else math.inf
    maximum_gap = reference_step * max_gap_factor

    groups: list[list[int]] = [[int(indexes[0])]]
    for previous, current in zip(indexes[:-1], indexes[1:], strict=False):
        gap = x_values[current] - x_values[previous]
        adjacent = current == previous + 1
        if adjacent and (not math.isfinite(maximum_gap) or gap <= maximum_gap):
            groups[-1].append(int(current))
        else:
            groups.append([int(current)])

    result: list[tuple[np.ndarray, np.ndarray]] = []
    for group in groups:
        group_x = x_values[group]
        group_y = y_values[group]
        unique_x, unique_indexes = np.unique(group_x, return_index=True)
        unique_y = group_y[unique_indexes]
        if unique_x.size == 1:
            smooth_x = unique_x
            smooth_y = unique_y
        else:
            count = max(unique_x.size, (unique_x.size - 1) * samples_per_interval + 1)
            smooth_x = np.linspace(unique_x[0], unique_x[-1], count)
            smooth_y = pchip_interpolate(unique_x, unique_y, smooth_x)
        if lower is not None or upper is not None:
            smooth_y = np.clip(
                smooth_y,
                -np.inf if lower is None else lower,
                np.inf if upper is None else upper,
            )
        result.append((smooth_x, smooth_y))
    return result


def pchip_interpolate(
    x: Iterable[float],
    y: Iterable[float],
    x_new: Iterable[float],
) -> np.ndarray:
    """Чистая NumPy-реализация монотонного кубического PCHIP.

    Производные вычисляются по схеме Fritsch–Carlson. Реализация не требует
    SciPy, что существенно упрощает автономную установку на Astra Linux.
    """

    x_values = np.asarray(tuple(x), dtype=float)
    y_values = np.asarray(tuple(y), dtype=float)
    target = np.asarray(tuple(x_new), dtype=float)
    if x_values.ndim != 1 or y_values.ndim != 1:
        raise ValueError("PCHIP поддерживает только одномерные ряды")
    if x_values.size != y_values.size:
        raise ValueError("Координаты и значения должны иметь одинаковую длину")
    if x_values.size == 0:
        raise ValueError("Нельзя интерполировать пустой ряд")
    if np.any(~np.isfinite(x_values)) or np.any(~np.isfinite(y_values)):
        raise ValueError("PCHIP принимает только конечные значения")
    if np.any(np.diff(x_values) <= 0):
        raise ValueError("Координаты PCHIP должны строго возрастать")
    if x_values.size == 1:
        return np.full_like(target, y_values[0], dtype=float)
    if x_values.size == 2:
        return np.interp(target, x_values, y_values)

    h = np.diff(x_values)
    delta = np.diff(y_values) / h
    derivatives = np.zeros_like(y_values)

    for index in range(1, x_values.size - 1):
        left = delta[index - 1]
        right = delta[index]
        if left == 0 or right == 0 or np.sign(left) != np.sign(right):
            derivatives[index] = 0.0
            continue
        weight_left = 2 * h[index] + h[index - 1]
        weight_right = h[index] + 2 * h[index - 1]
        derivatives[index] = (weight_left + weight_right) / (
            weight_left / left + weight_right / right
        )

    derivatives[0] = _endpoint_derivative(h[0], h[1], delta[0], delta[1])
    derivatives[-1] = _endpoint_derivative(
        h[-1],
        h[-2],
        delta[-1],
        delta[-2],
    )

    clipped_target = np.clip(target, x_values[0], x_values[-1])
    intervals = np.searchsorted(x_values, clipped_target, side="right") - 1
    intervals = np.clip(intervals, 0, x_values.size - 2)
    interval_h = h[intervals]
    fraction = (clipped_target - x_values[intervals]) / interval_h

    h00 = 2 * fraction**3 - 3 * fraction**2 + 1
    h10 = fraction**3 - 2 * fraction**2 + fraction
    h01 = -2 * fraction**3 + 3 * fraction**2
    h11 = fraction**3 - fraction**2

    return (
        h00 * y_values[intervals]
        + h10 * interval_h * derivatives[intervals]
        + h01 * y_values[intervals + 1]
        + h11 * interval_h * derivatives[intervals + 1]
    )


def _endpoint_derivative(
    first_h: float,
    second_h: float,
    first_delta: float,
    second_delta: float,
) -> float:
    derivative = (
        (2 * first_h + second_h) * first_delta - first_h * second_delta
    ) / (first_h + second_h)
    if np.sign(derivative) != np.sign(first_delta):
        return 0.0
    if np.sign(first_delta) != np.sign(second_delta) and abs(derivative) > abs(3 * first_delta):
        return 3 * first_delta
    return float(derivative)
