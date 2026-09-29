"""Deterministic clinical arithmetic. Models never do this math (DECISIONS.md: no LLM arithmetic)."""
from __future__ import annotations

from datetime import date

DAYS_PER_MONTH = 30.4375  # mean Gregorian month (365.25 / 12)


def bmi(weight_kg: float, height_cm: float) -> float:
    if weight_kg <= 0 or height_cm <= 0:
        raise ValueError("weight and height must be positive")
    return weight_kg / (height_cm / 100) ** 2


def age_on(birth: date, on: date) -> int:
    """Completed years of age on a given date."""
    if on < birth:
        raise ValueError("date precedes birth")
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def days_between(start: date, end: date) -> int:
    return (end - start).days


def whole_months_between(start: date, end: date) -> int:
    """Calendar months completed from start to end (e.g. 2026-02-18 -> 2026-08-18 == 6)."""
    if end < start:
        return -whole_months_between(end, start)
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months


def months_between(start: date, end: date) -> float:
    """Fractional months using the mean month length (reporting only; thresholds use whole_months_between)."""
    return days_between(start, end) / DAYS_PER_MONTH


def pct_change(before: float, after: float) -> float:
    if before == 0:
        raise ValueError("baseline cannot be zero")
    return (after - before) / before * 100
