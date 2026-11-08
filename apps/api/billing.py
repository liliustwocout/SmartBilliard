from datetime import datetime, timedelta, timezone


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def quote(start: datetime, end: datetime, hourly_rate: int) -> dict:
    elapsed_us = max(0, (utc(end) - utc(start)) // timedelta(microseconds=1))
    minutes = (elapsed_us + 60_000_000 - 1) // 60_000_000
    return {
        "elapsed_seconds": elapsed_us // 1_000_000,
        "billable_minutes": minutes,
        "amount_vnd": (minutes * hourly_rate + 59) // 60,
    }
