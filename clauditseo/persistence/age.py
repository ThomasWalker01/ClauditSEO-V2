"""When a measurement is old enough to say so (item 239 step 6).

Two thresholds in days, the operator's, kept in `app_prefs` and set in
Admin. The tone itself is decided where the date is drawn - the dashboard's
`age.ts` - from these two numbers, so every date on a screen is judged by
one rule; the server only owns what the numbers are.
"""

from __future__ import annotations

import sqlite3

#: Item 239's defaults: under 30 days a date is muted, 30 to 90 it may be
#: out of date, over 90 it is.
WARN_DAYS = 30
STALE_DAYS = 90
#: Ten years: a threshold past this is a typing slip, not a policy.
MAX_DAYS = 3650


def thresholds(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT age_warn_days, age_stale_days FROM app_prefs WHERE id=1").fetchone()
    warn = row["age_warn_days"] if row and row["age_warn_days"] else WARN_DAYS
    stale = row["age_stale_days"] if row and row["age_stale_days"] else STALE_DAYS
    return {"warn_days": warn, "stale_days": stale,
            "defaults": {"warn_days": WARN_DAYS, "stale_days": STALE_DAYS}}


def set_thresholds(conn: sqlite3.Connection, warn_days: int, stale_days: int) -> dict:
    """Refused unless 1 <= warn < stale <= ten years: a warning that comes
    after staleness would never be seen."""
    if not (1 <= warn_days < stale_days <= MAX_DAYS):
        raise ValueError("the warning age must be at least 1 day and less than the "
                         f"out-of-date age, which must be at most {MAX_DAYS} days")
    from .repo import now_iso
    with conn:
        conn.execute("UPDATE app_prefs SET age_warn_days=?, age_stale_days=?, updated_at=?"
                     " WHERE id=1", (warn_days, stale_days, now_iso()))
    return thresholds(conn)
