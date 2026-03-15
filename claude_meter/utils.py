"""Shared utility functions."""

from datetime import datetime, timezone


def format_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def format_duration(minutes: float) -> str:
    if minutes <= 0:
        return "now"
    hours = int(minutes) // 60
    mins = int(minutes) % 60
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def ms_to_datetime(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
