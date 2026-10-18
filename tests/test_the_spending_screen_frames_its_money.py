"""UX-75: the screen where money is actually spent frames its dollar figure.

**One screen, one root, and the frame is already on the wire.** The tools
screen reads `/api/runs/{id}/expert`, whose `budget` key is the whole of
`_budget_status` — `month_tokens`, `month_usd`, `usd_entries`, `usd_unpriced`,
`cap_tokens`, `cap_usd`, `warning`. `tools.tsx` narrows the fetched type to
`{ warning: string | null }` and throws the rest away, then paints `warning`
as the only money on a page whose every control spends. Round 079 gave Home
and Admin the frame beside their figures and left this screen as it was, so
it is now the one screen still showing an unframed dollar total.

**The report's proposed mechanism is not the one taken, and the reason is
read from the consumers rather than argued.** Report 079's remediation item 2
suggests appending the frame clause to `warning` server-side, "since every
consumer renders `warning` verbatim and only Admin already sits beside a
frame." There are three consumers, not two, and two of them already sit
beside a frame: `admin.tsx:898-905` paints the warning immediately above
`This month: ... (n of m entries priced)`, and `home.tsx:143-144` paints it
in the same card as a `Stat` whose `note` is the identical clause. Appending
server-side would print "n of m entries priced" twice in one card on both of
those screens. The frame belongs where the figure is drawn, which is the same
division round 079 chose: the server carries the counts, the screen decides
how to say them. Recorded here rather than only in a commit message, because
the next reader meeting item 2 will otherwise implement it as written.

**Rendered text, not a substring search over source** — CQ-166, raised
against round 079's own guard, is that `"usd_unpriced" in src` passes when
the visible half is deleted and only the `title` remains. So this drives a
real browser against a real server and reads what was painted.

**What is deliberately not guarded here, and why it is not an omission.**
The working-set sentence on the same screen — `24 brief(s) - ~4445k tokens -
~USD 1.53`, where `forecast()` computes a `priced` count and `say()`
discards it — is `BACKLOG.md` B-25, and that entry says in as many words that
the *shape* of its fix is the operator's: "whether the fix is disclosing the
two populations separately, scoping both totals to the priced subset alone,
or something else". The invariant settles that the scope must travel; it does
not settle which of those three the sentence should do, and inventing an
answer here would present a product decision as a derived one. It is the same
figure on the same screen and it is left standing on purpose.

The quotation above read `~$1.53 USD` until CQ-168 gave the two money owners
one spelling and moved the currency to the front of every figure the app
draws. Updated rather than left, because a docstring quoting a screen that no
longer says that is the register-goes-stale habit CQ-175, CQ-176, CQ-180 and
CQ-182 are four instances of. B-25 itself is untouched: the two populations
the sentence conflates are unaffected by how the dollar figure is spelled.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import pytest

from clauditseo import axe
from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST

NEEDS_BROWSER = pytest.mark.skipif(
    not axe.available() or not (DIST / "index.html").is_file(),
    reason="needs clauditseo[render], `playwright install chromium`, and a "
           "built dashboard (npm run build in dashboard/)")

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served_over_budget():
    """A real server, over its USD cap, on a month that is partly priced.

    Its own server rather than `test_a11y_rendered.py`'s `served`, on the
    precedent `test_unpriced_spend_is_named.py` set and for its reason: that
    fixture's seed is asserted on by several files for its run count and its
    findings, and a cap plus cost rows added to it to prove something about
    this screen is how a shared fixture stops being readable.

    The cap is set in the environment because `config.settings()` reads fresh
    on every call — "cheap; keeps tests honest" — so the server picks it up
    per request without a restart, and the teardown puts the environment back
    the way it found it.
    """
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app

    before = os.environ.get("CLAUDITSEO_MONTHLY_BUDGET_USD")
    os.environ["CLAUDITSEO_MONTHLY_BUDGET_USD"] = "2.50"

    tmp = Path(tempfile.mkdtemp(prefix="spendscreen"))
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
                            json={"name": "Over Budget Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "https://overbudget.fixture/"},
                          timeout=30).json()
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], ["TEC"], "T2")
        # Two priced entries over the 80% warn line, and two carrying no
        # price at all — the shape of the operator's own month reduced to its
        # smallest reproducing case. `2.20` against a `2.50` cap warns; the
        # two unpriced rows are what makes it a floor rather than a total.
        runs.log_cost(conn, run_id, "llm", "EXPERT:priced-a", "tokens",
                      100_000, actual_cost=1.10)
        runs.log_cost(conn, run_id, "llm", "EXPERT:priced-b", "tokens",
                      100_000, actual_cost=1.10)
        runs.log_cost(conn, run_id, "llm", "EXPERT:unpriced-a", "tokens",
                      200_000)
        runs.log_cost(conn, run_id, "llm", "EXPERT:unpriced-b", "tokens",
                      200_000)
        # The tools screen renders its working set only once the site has a
        # finished run — `!!runs.length` at `tools.tsx:647`. `scores=None` is
        # the imported-crawl shape and is all this screen needs: it asks what
        # has been analysed, not what was scored.
        with conn:
            runs.mark_complete(conn, run_id, runs.now_iso())
        conn.close()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        if before is None:
            os.environ.pop("CLAUDITSEO_MONTHLY_BUDGET_USD", None)
        else:
            os.environ["CLAUDITSEO_MONTHLY_BUDGET_USD"] = before


def test_the_endpoint_the_screen_reads_already_carries_the_frame(
        served_over_budget):
    """The premise, asserted rather than assumed.

    The whole cluster rests on the frame being on the wire already, so that
    the fix is a screen reading what it is given rather than a new field. If
    that ever stops being true the browser test below would fail for a reason
    that has nothing to do with the screen, and the failure would be read
    wrongly.
    """
    import httpx

    base, site_id = served_over_budget
    # `/api/sites/{id}` rather than a runs collection — there is no
    # `/api/sites/{id}/runs` route, and asking for one answers 200 with the
    # site detail because `{site_id}` swallows the trailing segment. That is
    # the dead end this line records: the first version indexed `[0]` into
    # that dict and raised `KeyError: 0`, which reads as an empty run list
    # and is not one.
    run_id = httpx.get(f"{base}/api/sites/{site_id}",
                       timeout=30).json()["runs"][0]["id"]
    budget = httpx.get(f"{base}/api/runs/{run_id}/expert",
                       timeout=30).json()["budget"]

    assert budget["warning"], "the fixture is not over its warn line"
    assert budget["usd_entries"] == 2
    assert budget["usd_unpriced"] == 2, (
        "the endpoint the tools screen reads does not carry the count that "
        "makes its dollar figure a floor, so the screen has nothing to render")


@NEEDS_BROWSER
def test_the_spending_screen_says_what_its_dollar_warning_covers(
        served_over_budget):
    """DISCIPLINE rule 12: the tree is not where a screen counts.

    Read from what the browser painted, against a server genuinely over its
    cap on a genuinely partly-priced month. The assertion is on the text of
    the warning paragraph itself rather than on a substring anywhere in the
    document, because a document-wide search would pass on somebody else's
    copy of the same clause.
    """
    from playwright.sync_api import sync_playwright

    base, site_id = served_over_budget
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            # Admin since item 188. UX-75's premise was that Tools was the
            # one screen still showing an unframed dollar total, Home and
            # Admin having been given the frame in round 079 - and neither of
            # them was ever driven. So this reads the screen that kept the
            # behaviour instead of the one that had the defect.
            pg.goto(f"{base}/#/admin", wait_until="load", timeout=30_000)
            pg.wait_for_selector("p.error", timeout=30_000)
            paragraphs = [pg.inner_text(f"p.error >> nth={i}")
                          for i in range(pg.locator("p.error").count())]
            # The frame is a sibling of the warning here, not appended inside
            # it: `admin.tsx` paints `<p class="error"><strong>{warning}</strong>`
            # and the `PricedFrame` beside "This month: ...". So the figure and
            # its frame are read from the card, not from the paragraph.
            card = pg.inner_text("body")
        finally:
            browser.close()

    warning = [t for t in paragraphs if "monthly budget used" in t]
    assert warning, (
        f"no budget warning painted on Admin: {paragraphs!r}")
    assert "2 of 4" in card, (
        "Admin paints a dollar total with nothing saying it covers 2 of the "
        "month's 4 cost entries")


# RETIRED with item 188 (test_the_frame_is_not_as_loud_as_the_warning_it_qualifies):
#   UI-19's arrangement: the caveat inside the same <strong> as the warning, which was Tools' shape. Admin paints the frame in its own element beside the figure, so there is no <strong> to be inside.


