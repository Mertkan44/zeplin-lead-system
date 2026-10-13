"""DeepSeek UTC peak windows and the verified Chinese public-holiday calendar.

Sources and review limits: docs/deepseek-pricing.md. No guessed future holidays.
"""
from datetime import datetime, timezone

HOLIDAY_RANGES = {
    2026: ((1, 1, 3), (2, 15, 23), (4, 4, 6), (5, 1, 5),
           (6, 19, 21), (9, 25, 27), (10, 1, 7)),
}


def billing_period(at: datetime) -> str | None:
    if at.tzinfo is None:
        raise ValueError("An aware provider-attempt timestamp is required")
    at = at.astimezone(timezone.utc)
    # Weekends and times outside the two windows are off-peak in every year.
    if at.weekday() >= 5 or not (1 <= at.hour < 4 or 6 <= at.hour < 10):
        return "off_peak"
    ranges = HOLIDAY_RANGES.get(at.year)
    if ranges is None:
        return None
    if any(at.month == month and first <= at.day <= last for month, first, last in ranges):
        return "off_peak"
    return "peak"
