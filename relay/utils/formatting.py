"""Shared formatting utilities used across layers."""

from __future__ import annotations

from datetime import date


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
