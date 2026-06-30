"""Shared formatting utilities used across layers."""

from __future__ import annotations

from datetime import UTC, date, datetime


def format_age(since: datetime | None, *, now: datetime | None = None) -> str:
    """Return a compact human-readable age, e.g. ``"just now"``, ``"14m"``,
    ``"2h 14m"``, ``"3d 2h"``.

    ``since`` is treated as UTC when it is naive. Returns ``"unknown"`` when the
    value is absent.
    """
    if since is None:
        return "unknown"
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)

    total_seconds = int((reference - since).total_seconds())
    if total_seconds < 60:
        return "just now"

    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes}m"

    hours, rem_minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {rem_minutes}m" if rem_minutes else f"{hours}h"

    days, rem_hours = divmod(hours, 24)
    return f"{days}d {rem_hours}h" if rem_hours else f"{days}d"


def renewal_proximity(renewal_date: date | str | None) -> str:
    """Return a human-readable string describing how close a renewal date is.

    Accepts a :class:`datetime.date` object, an ISO-format date string, or
    ``None``.  Returns ``"N/A"`` when the value is absent or unparseable.
    """
    if not renewal_date:
        return "N/A"
    try:
        if isinstance(renewal_date, date):
            renewal = renewal_date
        else:
            renewal = date.fromisoformat(renewal_date)
        days = (renewal - date.today()).days
        if days < 0:
            return f"OVERDUE ({abs(days)}d ago)"
        if days <= 30:
            return f":warning: {days}d away"
        return f"{days}d away"
    except Exception:
        return str(renewal_date)
