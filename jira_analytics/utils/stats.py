"""Statistical helpers for project-level metric aggregation."""

from __future__ import annotations

import math


def safe_mean(values: list[float]) -> float | None:
    """Return arithmetic mean or None for empty input."""
    if not values:
        return None
    return sum(values) / len(values)


def percentile(values: list[float], p: float) -> float | None:
    """
    Compute the p-th percentile using linear interpolation.

    Args:
        values: Non-empty list of numeric values.
        p: Percentile in [0, 100].
    """
    if not values:
        return None
    if len(values) == 1:
        return values[0]

    ordered = sorted(values)
    rank = (p / 100.0) * (len(ordered) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def is_finite(value: float | None) -> bool:
    """Return True if value is a finite number (not NaN or Infinity)."""
    if value is None:
        return True
    return math.isfinite(value)


def seconds_to_hours(seconds: float) -> float:
    return round(seconds / 3600, 4)


def seconds_to_days(seconds: float) -> float:
    return round(seconds / 86400, 4)
