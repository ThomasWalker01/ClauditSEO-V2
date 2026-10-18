"""Spend that outlives a delete (channel ruling 20261011-0746).

A delete removes a run's `cost_entries` with everything else it wrote, which
made the month's total, the per-client rows and the cap warning fall by money
already billed. Before any delete path removes cost rows it hands them here,
and their sums are added to `deleted_spend` under the operator-local month
each was spent in - never the month of the delete, and with no client, site
or run named.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def local_month(stamp: str | None) -> str | None:
    """The operator's calendar month (YYYY-MM) of a stored UTC stamp, in
    either shape the column holds: `now_iso()`'s ISO with an offset, or
    SQLite's own "YYYY-MM-DD HH:MM:SS", which is UTC. The rule
    `_local_month_utc` applies the other way round (item 248)."""
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(stamp.replace(" ", "T"))
    except ValueError:
        return stamp[:7]
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone().strftime("%Y-%m")


def keep_deleted_spend(conn: sqlite3.Connection, run_ids: list[str]) -> dict:
    """Add these runs' cost rows to `deleted_spend`, by month, before the
    caller deletes them. Inside the caller's transaction: if the delete rolls
    back, so does this. Returns what was kept, for the caller to say."""
    if not run_ids:
        return {"usd": 0.0, "tokens": 0.0, "entries": 0, "priced": 0}
    marks = ",".join("?" * len(run_ids))
    months: dict[str, dict] = {}
    for r in conn.execute(
            f"SELECT created_at, quantity, actual_cost FROM cost_entries WHERE run_id IN ({marks})",
            run_ids):
        m = months.setdefault(local_month(r["created_at"]) or "unknown",
                              {"tokens": 0.0, "usd": 0.0, "priced": 0, "unpriced": 0, "entries": 0})
        m["tokens"] += r["quantity"] or 0
        m["entries"] += 1
        if r["actual_cost"] is None:
            m["unpriced"] += 1
        else:
            m["usd"] += r["actual_cost"]
            m["priced"] += 1
    for month, m in months.items():
        conn.execute(
            "INSERT INTO deleted_spend (month, tokens, usd, priced, unpriced, entries)"
            " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(month) DO UPDATE SET"
            " tokens = tokens + excluded.tokens, usd = usd + excluded.usd,"
            " priced = priced + excluded.priced, unpriced = unpriced + excluded.unpriced,"
            " entries = entries + excluded.entries",
            (month, m["tokens"], m["usd"], m["priced"], m["unpriced"], m["entries"]))
    return {"usd": round(sum(m["usd"] for m in months.values()), 4),
            "tokens": sum(m["tokens"] for m in months.values()),
            "entries": sum(m["entries"] for m in months.values()),
            "priced": sum(m["priced"] for m in months.values())}


def deleted_in(conn: sqlite3.Connection, month: str) -> dict | None:
    """The tally for one month, or None where nothing was deleted in it."""
    row = conn.execute("SELECT * FROM deleted_spend WHERE month=?", (month,)).fetchone()
    return dict(row) if row else None
