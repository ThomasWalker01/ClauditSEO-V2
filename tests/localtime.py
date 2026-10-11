"""What the dashboard prints for a stored instant (item 248).

Every date on screen goes through `dashboard/src/dates.ts`, which converts
to the reader's local time. A test that derives the expected text by slicing
the stored string agrees with the screen only where the machine's zone is
UTC, or the hour is late enough: between local midnight and the offset, the
UTC day is yesterday. These say what the screen says, on any machine.

The rendered tests' browser runs in the machine's zone, as this does.
"""

from __future__ import annotations

from datetime import datetime


def _local(iso: str) -> datetime:
    at = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if at.tzinfo is None:
        # `new Date("2026-09-03T11:33:00")` reads an offset-less stamp as
        # local time, and so does this.
        return at
    return at.astimezone()


def stamp(iso: str) -> str:
    """`dates.ts` `stamp()`: `2026-09-29 06:09`."""
    return _local(iso).strftime("%Y-%m-%d %H:%M")


def day(iso: str) -> str:
    """`dates.ts` `day()`: `2026-09-29`."""
    return _local(iso).strftime("%Y-%m-%d")


def clock(iso: str) -> str:
    """`dates.ts` `clock()`: `06:09`."""
    return _local(iso).strftime("%H:%M")



