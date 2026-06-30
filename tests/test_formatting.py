from __future__ import annotations

from datetime import UTC, datetime, timedelta

from relay.utils.formatting import format_age


def _ago(now: datetime, **kwargs) -> datetime:
    return now - timedelta(**kwargs)


def test_format_age_just_now():
    now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)
    assert format_age(_ago(now, seconds=30), now=now) == "just now"


def test_format_age_minutes():
    now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)
    assert format_age(_ago(now, minutes=14), now=now) == "14m"


def test_format_age_hours_and_minutes():
    now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)
    assert format_age(_ago(now, hours=2, minutes=14), now=now) == "2h 14m"


def test_format_age_whole_hours():
    now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)
    assert format_age(_ago(now, hours=3), now=now) == "3h"


def test_format_age_days_and_hours():
    now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)
    assert format_age(_ago(now, days=3, hours=2), now=now) == "3d 2h"


def test_format_age_naive_datetime_treated_as_utc():
    now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)
    naive = datetime(2026, 6, 29, 11, 0, 0)  # no tzinfo
    assert format_age(naive, now=now) == "1h"


def test_format_age_none():
    assert format_age(None) == "unknown"
