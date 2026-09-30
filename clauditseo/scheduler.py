"""Recurring audits: a small loop that launches due runs.

The decision function is pure and tested; the thread around it is a timer.
Deliberately conservative in every ambiguous case: a site with a run already
in progress is skipped, a site that has never been crawled is NOT auto-crawled
(the first run sizes the site and belongs to the operator), and a failure to
launch one site's audit must not stop the others.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta

from clauditseo.persistence import runs

INTERVALS = {"weekly": timedelta(days=7), "monthly": timedelta(days=30)}
CHECK_EVERY_S = 30 * 60


def due_sites(conn: sqlite3.Connection, now: datetime) -> list[dict]:
    """Sites whose schedule says another audit is owed."""
    out = []
    for site in conn.execute(
            "SELECT id, domain, schedule FROM sites"
            " WHERE schedule IS NOT NULL AND archived_at IS NULL"):
        interval = INTERVALS.get(site["schedule"])
        if not interval:
            continue
        # guard-exempt(site-reading): "is anything already running for this
        # site" must span every kind - starting an audit while a verification
        # is in flight is the case it exists to prevent.
        running = conn.execute(
            "SELECT 1 FROM audit_runs WHERE site_id=? AND status='running'",
            (site["id"],)).fetchone()
        if running:
            continue
        # 'blocked' counts as a crawl having happened. It is a site that
        # refused us, and the interval is the whole point: without this the
        # site never shows a completed run, so every tick re-triggers and the
        # schedule turns into a retry loop against a host already saying no.
        #
        # `kind='audit'`, because this clock measures "when was this site
        # last audited" and a narrow run is not an audit of it. Without the
        # filter, re-reading one page (F-06's refresh) or verifying two
        # (`verify`) postponed the next unattended audit by a whole interval
        # — an operator's small check quietly cancelling the large one,
        # leaving no trace beyond a site that stopped being due.
        last = conn.execute(
            "SELECT started_at FROM audit_runs WHERE site_id=?"
            f" AND {runs.status_in(runs.AUDITED_STATUSES)}"
            f" AND {runs.kind_is_site_reading()}"
            " ORDER BY started_at DESC, rowid DESC LIMIT 1",
            (site["id"],)).fetchone()
        if not last:
            continue        # never crawled: the first run is the operator's call
        started = datetime.fromisoformat(last["started_at"].replace("Z", "+00:00"))
        if now - started.replace(tzinfo=None) >= interval:
            out.append(dict(site))
    return out


def start_scheduler(connect, launch, log=print,
                    launch_tool=None) -> threading.Event:
    """Run the check on a timer. `connect` opens a fresh connection per tick
    (SQLite connections are not thread-safe to share); `launch(site_row)`
    starts an audit and `launch_tool(job)` runs one scheduled brief.
    Returns the stop event."""
    stop = threading.Event()

    def tick() -> None:
        while not stop.wait(CHECK_EVERY_S):
            try:
                conn = connect()
                try:
                    _refresh_rates(conn, log)
                    _collect_sf(conn, log)
                    for site in due_sites(conn, datetime.now()):
                        try:
                            launch(site)
                            log(f"scheduler: launched audit for {site['domain']}")
                        except Exception as exc:   # noqa: BLE001 - one site must not stop the rest
                            log(f"scheduler: {site['domain']} failed to launch: {exc}")
                    # Briefs after audits: a brief reads a completed run, so
                    # firing one first would read yesterday's crawl when a
                    # fresh one is minutes away.
                    if launch_tool:
                        for job in due_tools(conn, datetime.now()):
                            try:
                                launch_tool(job)
                                mark_tool_ran(conn, job["site_id"], job["tool_id"],
                                              datetime.now().isoformat(timespec="seconds"))
                                log(f"scheduler: ran {job['tool_id']} for {job['domain']}")
                            except Exception as exc:   # noqa: BLE001
                                log(f"scheduler: {job['tool_id']} on {job['domain']}"
                                    f" failed: {exc}")
                finally:
                    conn.close()
            except Exception as exc:               # noqa: BLE001 - the loop survives anything
                log(f"scheduler: tick failed: {exc}")

    threading.Thread(target=tick, daemon=True, name="clauditseo-scheduler").start()
    return stop


#: The ECB publishes once a working day, so asking more often than daily is
#: traffic for nothing.
RATE_REFRESH_HOURS = 20


def _refresh_rates(conn, log) -> None:
    """Keep the exchange rate current, quietly.

    Failure is logged and dropped: a rate that could not be fetched leaves the
    one already stored, which the interface will show with its age. Falling
    back to a stale rate the reader can see beats interrupting an audit
    schedule over a currency conversion.
    """
    from clauditseo.providers import fx

    try:
        want = fx.display_currency(conn)
        if want == "USD":
            return                       # nothing to convert, nothing to fetch
        current = fx.rate_for(conn, want)
        if current and (current.get("age_days") or 0) * 24 < RATE_REFRESH_HOURS:
            return
        out = fx.refresh(conn)
        log(f"scheduler: exchange rates "
            + (f"refreshed ({out['stored']} currencies)" if out["ok"]
               else f"not refreshed: {out['error']}"))
    except Exception as exc:              # noqa: BLE001 - never stop the tick
        log(f"scheduler: rate refresh skipped: {exc}")


def _collect_sf(conn, log) -> None:
    """Sweep the Screaming Frog drop folder, when one is configured. The SF
    CLI crawls on the operator's schedule; this is the other half of that
    autonomy — exports become evidence runs with nobody clicking."""
    from clauditseo.config import settings

    folder = settings().sf_import_dir
    if not folder:
        return
    from clauditseo.importers import collect_drop_folder
    for outcome in collect_drop_folder(conn, folder):
        log(f"sf-collector: {outcome['file']} -> {outcome['status']}"
            + (f" ({outcome.get('pages')} pages)" if outcome.get("pages") else "")
            + (f": {outcome.get('reason')}" if outcome.get("reason") else ""))


# Cadences a tool schedule can use. Wider than the site-level set because the
# expert briefs cost money per run: an operator wants the cheap dispatcher
# often and an expensive site-wide brief rarely, and "weekly or monthly" does
# not express that.
TOOL_INTERVALS = {
    "weekly": timedelta(days=7),
    "fortnightly": timedelta(days=14),
    "monthly": timedelta(days=30),
    "quarterly": timedelta(days=91),
}


def due_tools(conn: sqlite3.Connection, now: datetime) -> list[dict]:
    """Scheduled briefs owed a run, with the audit they would read.

    Conservative in the same way `due_sites` is. A brief reads a completed
    run's stored crawl evidence, so a site with no completed run is skipped
    rather than crawled — deciding to spend money on a site nobody has audited
    yet is not a scheduler's call to make.
    """
    out: list[dict] = []
    for row in conn.execute(
            "SELECT ts.site_id, ts.tool_id, ts.cadence, ts.last_run_at, s.domain"
            " FROM tool_schedules ts JOIN sites s ON s.id = ts.site_id"
            " WHERE s.archived_at IS NULL"):
        interval = TOOL_INTERVALS.get(row["cadence"])
        if not interval:
            continue
        # A brief reads the run's stored crawl evidence. A blocked run stored
        # evidence too — the robots response that explains the block — so it
        # is a run a tool may read rather than a reason to skip the site.
        #
        # A narrow run's evidence is a different matter and is excluded by
        # kind: a brief handed a one-page refresh would describe that page as
        # though it were the site, at full price, unattended.
        run = conn.execute(
            "SELECT id, started_at FROM audit_runs WHERE site_id=?"
            f" AND {runs.status_in(runs.AUDITED_STATUSES)}"
            f" AND {runs.kind_is_site_reading()}"
            " ORDER BY started_at DESC, rowid DESC LIMIT 1",
            (row["site_id"],)).fetchone()
        if not run:
            continue
        if row["last_run_at"]:
            last = _parse(row["last_run_at"])
            if last and now - last < interval:
                continue
        out.append({"site_id": row["site_id"], "domain": row["domain"],
                    "tool_id": row["tool_id"], "cadence": row["cadence"],
                    "run_id": run["id"]})
    return out


def _parse(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def mark_tool_ran(conn: sqlite3.Connection, site_id: str, tool_id: str,
                  when: str) -> None:
    with conn:
        conn.execute("UPDATE tool_schedules SET last_run_at=?"
                     " WHERE site_id=? AND tool_id=?", (when, site_id, tool_id))
