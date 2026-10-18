"""One clock: every date on screen is local time, through one function (item 248).

Round-2 screen audits, cross-cutting item 1 of 5. The same audit carried two
dates one click apart: the Record's Audits tab printed "2026-09-29 06:09"
(`stamp()`, local) and Reports printed "2026-09-28" for the same run
(`iso.slice(0, 10)`, the UTC day). The dossier, the run page, the landing's
Waiting lane and the delete confirm each sliced their own. On the server a
cadence fell due ten hours early on a UTC+10 machine, and "this month" was
UTC's month.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

#: A date cut out of a string by position. `slice(0, 10)` is the day of
#: whatever offset the string happens to carry, and `slice(11, 16)` its time.
SLICED = re.compile(r"\.(?:slice|substring|substr)\(\s*(?:0\s*,\s*1[06]|11\s*,\s*16)\s*\)")

#: Not our instants, and each says why. A date the PAGE declares is the
#: page's own text: converting it would move a day the page wrote. The
#: certificate's expiry is OpenSSL's text, not an ISO stamp.
NOT_AN_INSTANT = {
    ("dossier.tsx", "`${k}: ${String(v).slice(0, 10)}`"),
    ("part_page.tsx", "{updated ? updated.slice(0, 10) :"),
}


def _hits() -> list[str]:
    out = []
    for path in sorted(SRC.glob("*.ts*")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not SLICED.search(line):
                continue
            text = line.strip()
            if text.startswith(("*", "//", "/*")):
                continue
            if any(path.name == f and frag in line for f, frag in NOT_AN_INSTANT):
                continue
            out.append(f"{path.name}:{n}: {text[:120]}")
    return out


def test_no_date_is_sliced_out_of_a_string():
    hits = _hits()
    assert not hits, ("a date is cut out of a string by position; print it with "
                      "`stamp()`, `day()` or `clock()` from dates.ts:\n  " + "\n  ".join(hits))


def test_the_exemptions_are_still_in_the_tree():
    """An exemption for a line that has gone excuses whatever replaces it."""
    for name, frag in NOT_AN_INSTANT:
        assert frag in (SRC / name).read_text(encoding="utf-8"), (name, frag)


def test_the_three_printers_are_the_only_ones():
    """`toLocaleDateString` and `toLocaleString()` on a Date are a second
    format for the same thing. Home's next-pass line is the one place that
    names a weekday, and it is local already."""
    allowed = {("home.tsx", "toLocaleDateString(undefined,")}
    bad = []
    for path in sorted(SRC.glob("*.ts*")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith(("*", "//", "/*")):
                continue
            if re.search(r"toLocale(Date|Time)String|new Date\([^)]*\)\.toLocaleString\(", line) \
                    and not any(path.name == f and frag in line for f, frag in allowed):
                bad.append(f"{path.name}:{n}: {line.strip()[:120]}")
    assert not bad, "\n".join(bad)


# ---- the server's clocks -----------------------------------------------------

def test_a_stamp_and_a_clock_reading_are_compared_as_moments():
    from clauditseo.scheduler import instant
    utc = instant("2026-09-29T20:00:00+00:00")
    assert utc.tzinfo is not None
    # A naive value is the machine's local time, so it survives a round trip.
    here = datetime(2026, 9, 30, 6, 0, 0)
    assert instant(here).replace(tzinfo=None) == here
    assert instant("not a date") is None and instant(None) is None


def test_a_cadence_is_not_due_before_its_interval_has_passed():
    """A run that started 6 days 20 hours ago is not due on a weekly cadence,
    whatever the machine's offset. Stripped of its offset and compared with
    the local clock, it read as 7 days 6 hours on a UTC+10 machine."""
    from clauditseo.api.app import _next_pass
    from clauditseo.scheduler import INTERVALS

    now = datetime.now().astimezone()
    started = (now - timedelta(days=6, hours=20)).astimezone(timezone.utc)
    got = _next_pass("weekly", started.isoformat(), datetime.now(), INTERVALS, timedelta)
    assert got["schedule_state"] == "scheduled", got
    due = datetime.fromisoformat(got["next_pass_at"])
    assert due.tzinfo is not None, "the next pass is printed without saying whose clock"
    assert abs((due - (started + timedelta(days=7))).total_seconds()) < 60

    late = (now - timedelta(days=7, hours=2)).astimezone(timezone.utc)
    assert _next_pass("weekly", late.isoformat(), datetime.now(), INTERVALS,
                      timedelta)["schedule_state"] == "overdue"


def test_due_sites_asks_the_same_question(tmp_path):
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    from clauditseo.scheduler import due_sites

    conn = connect(tmp_path / "due.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "Due Co"), "due.fixture")
    conn.execute("UPDATE sites SET schedule='weekly' WHERE id=?", (site,))
    run_id = runs.create_run(conn, site, ["TEC"], "T2", scan_scope="site")
    started = datetime.now(timezone.utc) - timedelta(days=6, hours=20)
    conn.execute("UPDATE audit_runs SET status='complete', started_at=? WHERE id=?",
                 (started.isoformat(), run_id))
    conn.commit()
    assert due_sites(conn, datetime.now()) == []
    assert [s["id"] for s in due_sites(conn, datetime.now() + timedelta(hours=5))] == [site]
    conn.close()


def test_this_month_is_the_machines_month():
    from clauditseo.api.app import _local_month_utc

    first, nxt = _local_month_utc(datetime(2026, 10, 1, 3, 0, 0))
    start = datetime.strptime(first, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    end = datetime.strptime(nxt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    # Local midnight on the 1st, whatever that is in UTC.
    assert start.astimezone().strftime("%Y-%m-%d %H:%M") == "2026-10-01 00:00"
    assert end.astimezone().strftime("%Y-%m-%d %H:%M") == "2026-11-01 00:00"
    assert _local_month_utc(datetime(2026, 12, 31, 23, 0, 0))[1] == \
        datetime(2027, 1, 1).astimezone().astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def test_spend_in_the_first_hours_of_a_local_month_is_this_months(tmp_path):
    from clauditseo.api.app import _budget_status
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs

    class Caps:
        monthly_budget_tokens = None
        monthly_budget_usd = None

    conn = connect(tmp_path / "month.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "Month Co"), "m.fixture")
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    here = datetime.now()
    first_local = datetime(here.year, here.month, 1).astimezone()
    inside = (first_local + timedelta(minutes=5)).astimezone(timezone.utc)
    before = (first_local - timedelta(minutes=5)).astimezone(timezone.utc)
    for at, tokens in ((inside, 100), (before, 7000)):
        conn.execute("INSERT INTO cost_entries (id, run_id, provider, operation, units,"
                     " quantity, est_cost, actual_cost, created_at)"
                     " VALUES (?, ?, 'p', 'o', 'tokens', ?, 0, NULL, ?)",
                     (repo.create_id(), run_id, tokens, at.isoformat()))
    conn.commit()
    try:
        status = _budget_status(conn, Caps())
    finally:
        conn.close()
    assert status["month_tokens"] == 100, status


# ---- the screen ----------------------------------------------------------------

from tests.test_a11y_rendered import DIST, served  # noqa: E402,F401  (reused fixture)

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")
BUILT = pytest.mark.skipif(not (DIST / "index.html").is_file(),
                           reason="dashboard not built (npm run build in dashboard/)")


@NEEDS_BROWSER
@BUILT
def test_one_run_is_one_date_on_every_screen(served):
    """Driven in a zone where the run's local day is not its UTC day, which
    is where a sliced date and a converted one disagree."""
    import httpx
    from playwright.sync_api import sync_playwright

    base, ids = served
    run = httpx.get(f"{base}/api/runs/{ids['run']}", timeout=30).json()
    run = run.get("run", run)
    started = datetime.fromisoformat(run["started_at"])
    # Fixed-offset zones on the far side of midnight from this moment.
    zone, hours = (("Pacific/Kiritimati", 14) if started.astimezone(timezone.utc).hour >= 10
                   else ("Pacific/Honolulu", -10))
    local = started.astimezone(timezone(timedelta(hours=hours)))
    utc_day = started.astimezone(timezone.utc).strftime("%Y-%m-%d")
    local_day = local.strftime("%Y-%m-%d")
    assert local_day != utc_day, "the zone was chosen so the two days differ"
    local_stamp = local.strftime("%Y-%m-%d %H:%M")

    screens = {
        "the run page": f"#/runs/{ids['run']}",
        "the Audits tab": f"#/sites/{ids['site']}?tab=history",
        "the Record": f"#/sites/{ids['site']}?tab=all",
        "the landing": f"#/sites/{ids['site']}",
        "Reports": "#/reports",
    }
    seen = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(timezone_id=zone, viewport={"width": 1440, "height": 1000})
        pg = ctx.new_page()
        try:
            for name, route in screens.items():
                pg.goto(f"{base}/{route}", wait_until="load", timeout=30_000)
                pg.wait_for_timeout(2500)
                seen[name] = pg.inner_text("body")
            # The delete confirm names the audit by its date.
            pg.goto(f"{base}/#/sites/{ids['site']}?tab=history", wait_until="load", timeout=30_000)
            pg.wait_for_timeout(2500)
            seen["the delete confirms"] = " ".join(pg.evaluate(
                "() => [...document.querySelectorAll('[aria-label*=\"elete\"], [title*=\"elete\"]')]"
                ".map(e => (e.getAttribute('aria-label') || '') + ' ' + (e.getAttribute('title') || ''))"))
        finally:
            browser.close()

    wrong = {name: utc_day for name, text in seen.items() if utc_day in text}
    assert not wrong, f"the UTC day {utc_day} is printed (local is {local_day}) on: {sorted(wrong)}"
    for name in ("the run page", "the Audits tab", "the landing"):
        assert local_day in seen[name], f"{name} does not print the run's local day {local_day}"
    assert local_stamp in seen["the Audits tab"], (
        f"the Audits tab does not print {local_stamp}")
