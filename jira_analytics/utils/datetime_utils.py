"""Datetime parsing utilities for Jira timestamps."""

from __future__ import annotations

from datetime import datetime, timezone


def parse_jira_datetime(value: str | int | float | None) -> datetime | None:
    """
    Parse a Jira timestamp into a timezone-aware UTC datetime.

    Supports ISO-8601 strings and Unix epoch seconds/milliseconds.
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        # Jira bulk changelog may use epoch seconds
        if value > 1_000_000_000_000:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        return datetime.fromtimestamp(value, tz=timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    # Normalize timezone offsets like +0000 → +00:00
    if len(text) > 5 and text[-5] in "+-" and text[-4:].isdigit():
        if ":" not in text[-6:]:
            text = f"{text[:-5]}{text[-5:-2]}:{text[-2:]}"

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


def duration_seconds(start: datetime, end: datetime) -> float:
    """Compute non-negative duration in seconds between two datetimes."""
    return max(0.0, (end - start).total_seconds())
