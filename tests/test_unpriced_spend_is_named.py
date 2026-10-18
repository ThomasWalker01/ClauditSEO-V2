"""UX-04: a dollar total says how many of the entries under it carry a price.

**Measured, not inferred.** Against the operator's live database on 22 August
2026, `cost_entries` for the current month holds **48 rows, 34 of them with a
NULL `actual_cost`**, and `SUM(actual_cost)` over them is `2.178569`. Reports
076, 077 and 078 each re-measured it and each recommended the same remedy;
none of the three rounds took it. The Home screen renders that sum as
`USD 2.18` under the label "spent this month", which is a floor covering 14
of 48 entries and reads as a measurement of all 48. It was `$2.18` when this
was written; CQ-168 moved the currency to the front of every figure the app
draws, and the quotation is updated rather than left as a description of a
screen that no longer says that.

**Two aggregations of one column, opposite null policies — and both are
wrong in the same way.** `_budget_status` coerces with `float(row["usd"] or 0)`,
so a month where nothing at all is priced reports `0`, which is a *claim of
zero spend*. `monthly_spend` does not coerce, so the same month reports
`None` and the admin table draws an em dash — honest about "no figure" and
silent about the fact that a figure *is* drawn for a month that is only
partly priced. Neither states what the number covers, which is the frame
clause of the provenance invariant applied to money.

**Why the fix is forward-looking only, said here rather than discovered
later.** `cost_entries` stores a provider and an operation and no model id
(`clauditseo/db/migrations/0001_initial.sql:56-66`), so an entry written
before its model was priced cannot be joined to a price afterwards. Report
078's open question 3 puts that to the operator. This guard is about the
*frame* — it holds the product to saying what the figure covers — and is
true whether or not the back-fill ever becomes possible.

**Split across the two CI legs, for the reason `test_spend_mark.py` records.**
The server half is arithmetic and runs everywhere. The static half reads the
two screens' source. The rendered half is about what the browser paints, which
cannot be read off source, so it drives a real server and runs in
`rendered-a11y`, where a skip fails the job.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from pathlib import Path

import pytest

from clauditseo import axe
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from tests.test_a11y_rendered import DIST

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"
HOME = SRC / "home.tsx"
ADMIN = SRC / "admin.tsx"

#: JSX/TS comments, blanked rather than deleted so line numbers survive into
#: any failure message — `test_missing_composite_on_screen.py`'s convention,
#: and for its reason: a guard that reads prose *about* the code passes on a
#: comment describing the fix somebody meant to make.
COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)

NEEDS_BROWSER = pytest.mark.skipif(
    not axe.available() or not (DIST / "index.html").is_file(),
    reason="needs clauditseo[render], `playwright install chromium`, and a "
           "built dashboard (npm run build in dashboard/)")


def _source(path: Path) -> str:
    return COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"),
                       path.read_text(encoding="utf-8"))


@pytest.fixture
def partly_priced(tmp_path):
    """One month, three entries, one of them priced.

    The shape of the operator's own data reduced to its smallest reproducing
    case: a month whose dollar sum is real and covers a minority of the rows
    that contributed tokens to it.
    """
    conn = connect(tmp_path / "spend.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Unpriced Co")
    site = repo.create_site(conn, client, "unpriced.test")
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    runs.log_cost(conn, run_id, "llm", "EXPERT:priced", "tokens", 1000,
                  actual_cost=0.25)
    runs.log_cost(conn, run_id, "llm", "EXPERT:unpriced-a", "tokens", 2000)
    runs.log_cost(conn, run_id, "llm", "EXPERT:unpriced-b", "tokens", 4000)
    yield conn
    conn.close()


@pytest.fixture
def wholly_unpriced(tmp_path):
    """The same month with nothing priced at all — the zero-coercion case."""
    conn = connect(tmp_path / "unpriced.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Nothing Priced Co")
    site = repo.create_site(conn, client, "nothing.test")
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    runs.log_cost(conn, run_id, "llm", "EXPERT:a", "tokens", 1000)
    runs.log_cost(conn, run_id, "llm", "EXPERT:b", "tokens", 2000)
    yield conn
    conn.close()


class _NoCaps:
    monthly_budget_tokens = None
    monthly_budget_usd = None


def test_the_budget_summary_says_how_many_entries_its_dollar_figure_covers(
        partly_priced):
    """The frame, as data, before any screen can render it.

    `month_usd` alone cannot be read: `0.25` is the same value whether it
    covers one entry of three or three of three, and the difference is the
    whole finding.
    """
    from clauditseo.api.app import _budget_status

    status = _budget_status(partly_priced, _NoCaps())

    assert status["month_tokens"] == 7000
    assert status["month_usd"] == 0.25
    assert status["usd_entries"] == 1, (
        "the budget summary does not say how many cost entries its dollar "
        "figure covers, so a floor is indistinguishable from a total")
    assert status["usd_unpriced"] == 2, (
        "the budget summary does not say how many cost entries carry no "
        "price, which is the count that makes the figure a floor")


def test_a_month_with_no_price_at_all_reports_no_figure_rather_than_zero(
        wholly_unpriced):
    """The zero coercion turns "not priced" into "spent nothing".

    Those are different claims, and the second one is false: the month in the
    fixture spent 3000 tokens. A null is the honest answer and the screens
    already have a branch for it.
    """
    from clauditseo.api.app import _budget_status

    status = _budget_status(wholly_unpriced, _NoCaps())

    assert status["month_tokens"] == 3000
    assert status["month_usd"] is None, (
        "a month in which nothing is priced reports USD 0.00, which claims "
        "zero spend on 3000 tokens of it")
    assert status["usd_entries"] == 0
    assert status["usd_unpriced"] == 2


def test_a_month_with_no_entries_at_all_still_reports_a_genuine_zero(tmp_path):
    """The opposite error, guarded against on the way past.

    "Nothing is priced" and "nothing was spent" are both real states and the
    null belongs to the first only. A fresh install has no cost entries, and
    reporting *that* as unknown would put "not priced" on the Home tile of
    every new operator — the same confusion this change removes, pointed the
    other way.
    """
    from clauditseo.api.app import _budget_status

    conn = connect(tmp_path / "empty.db")
    migrate(conn)
    try:
        status = _budget_status(conn, _NoCaps())
    finally:
        conn.close()

    assert status["month_tokens"] == 0
    assert status["month_usd"] == 0.0, (
        "a month with no cost entries reports its dollar total as unknown, "
        "when it is a measured zero")
    assert status["usd_entries"] == 0 and status["usd_unpriced"] == 0


def test_the_per_client_ledger_says_what_each_row_s_dollar_figure_covers(
        partly_priced):
    """The other aggregation of the same column, held to the same frame.

    `monthly_spend` feeds the admin per-client table. It lets the NULL
    through, so a wholly-unpriced month draws an em dash — but a partly
    priced one draws a number with nothing saying what it omits, which is the
    identical defect one row along.
    """
    ledger = runs.monthly_spend(partly_priced)

    assert len(ledger) == 1
    row = ledger[0]
    assert row["tokens"] == 7000 and row["usd"] == 0.25
    assert row["priced"] == 1, (
        "the per-client ledger does not say how many entries its USD column "
        "covers")
    assert row["unpriced"] == 2, (
        "the per-client ledger does not say how many entries carry no price")


def test_home_renders_the_frame_beside_the_spend_figure():
    """Visible text on the screen, not a `title` and not a tooltip.

    `Stat`'s `note` prop exists for exactly this — "a row of stats where
    three respond to a filter and one does not needs to say which is which"
    — and it renders inline, which a `title` does not.
    """
    src = _source(HOME)
    assert "usd_unpriced" in src, (
        "home.tsx renders the month's dollar sum under 'spent this month' "
        "without reading the count of entries that figure does not cover, so "
        "the tile states a floor as a total")


def test_the_admin_screen_renders_the_frame_on_both_of_its_figures():
    """Two figures on one card, from two different aggregations.

    The Spend card's summary line comes from `_budget_status` and its table
    comes from `monthly_spend`; both draw dollars over partly-priced months,
    so both carry the frame or the card contradicts itself.
    """
    src = _source(ADMIN)
    assert "usd_unpriced" in src, (
        "the admin Spend card's summary line states a dollar figure without "
        "saying how many entries it covers")
    assert "unpriced" in src.split("data.spend")[-1], (
        "the admin per-client spend table states a USD figure per month "
        "without saying how many of that month's entries carry no price")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served_partly_priced():
    """A real server whose only month of spend is partly priced.

    Its own server rather than `test_a11y_rendered.py`'s `served`: that
    fixture's seed is asserted on by several files for its run count and its
    findings, and adding cost rows to it to prove something about a fifth
    screen is how a shared fixture stops being readable.
    """
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app

    tmp = Path(tempfile.mkdtemp(prefix="unpricedspend"))
    db = tmp / "clauditseo.db"
    app = create_app(db_path=db)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("server did not start")

    base = f"http://127.0.0.1:{port}"
    try:
        client = httpx.post(f"{base}/api/clients",
                            json={"name": "Unpriced Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "https://unpriced.fixture/"},
                          timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], ["TEC"], "T2")
        runs.log_cost(conn, run_id, "llm", "EXPERT:priced", "tokens", 1000,
                      actual_cost=0.25)
        runs.log_cost(conn, run_id, "llm", "EXPERT:a", "tokens", 2000)
        runs.log_cost(conn, run_id, "llm", "EXPERT:b", "tokens", 4000)
        conn.close()
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@NEEDS_BROWSER
def test_the_home_tile_paints_the_frame_the_operator_reads(
        served_partly_priced):
    """DISCIPLINE rule 12: the tree is not where a screen counts.

    Asserts on what the browser painted, against a server whose dollar sum
    genuinely covers a minority of its own cost entries.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{served_partly_priced}/#/", wait_until="load",
                    timeout=30_000)
            # Item 176: the tile is the head's spend line.
            pg.wait_for_selector(".home-spend", timeout=30_000)
            tiles = [pg.inner_text(".home-spend")]
        finally:
            browser.close()

    # Lower-cased before matching: `.stat span` is upper-cased in CSS, so
    # `inner_text` returns "SPENT THIS MONTH". Matching the source casing
    # made this fail with "no spend tile", which is a true failure for a
    # false reason — the tile was there, painting `$0.25 USD` with no frame.
    spend = [t for t in tiles if "spent this month" in t.lower()]
    assert spend, f"no spend tile on the home screen: {tiles!r}"
    text = spend[0]
    assert "1 of 3" in text, (
        "the home spend tile paints a dollar figure with nothing saying it "
        f"covers 1 of the month's 3 cost entries: {text!r}")
