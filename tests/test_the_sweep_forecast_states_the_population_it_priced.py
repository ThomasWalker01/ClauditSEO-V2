"""CQ-214 and CQ-215: the screen's largest money figure states what it priced.

**The rendered half of CQ-198, and the reason it needs its own file.**
`tests/test_a_brief_price_says_which_site_it_was_drawn_from.py` is pure source
reading by a decision its own docstring argues - nothing there loads
`dashboard/dist`, so `scripts/prove_fail.py` can answer for it. That decision
is still right and is not overturned here. What it cannot do is see a render
site wrapped in a branch, and that is exactly what CQ-215 found: every clause
there passes against a screen showing a money figure and no scope, because
`PriceScopeNote` sat inside `tools.tsx`'s `{!tool || !brief ? (` else-branch
and the assertions were `OWNER in source` plus a regex count over source. A
file was in the population; a *render site* was not. So the rendered clause
lives here, in the CI sweep at `.github/workflows/ci.yml`, and the two files
cite each other.

**Two payloads, one question - which is the root CQ-214 names.** The tools
screen paints two prices from two different sources. The per-brief price comes
from `/api/playbook`'s `experts` map, whose `scoped_to_site` the screen has
read since CQ-198. The sweep forecast - the largest figure on the workbench,
beside the control that runs every brief - is `fig.cost`, summed by `forecast`
out of `/api/runs/{id}/expert`'s `estimates`, and `type Estimate` dropped
`scoped_to_site` on the floor. Same key, same question, one payload over, in
the file CQ-198 had just been fixed in.

**The frame is derived from the entries that were summed, never from the
screen's own site id.** DISCIPLINE rule 5: a check drawing its evidence from
the thing it checks can only ever pass. The screen holds the id it issued the
fetch with, and rendering that would be cheaper and could never disagree with
the figure it describes. `scoped_to_site` is what the estimator recorded the
median was computed over, which is a different fact from what the caller asked
for, and it is the only one of the two that can contradict the screen.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from pathlib import Path
from urllib.parse import quote

import pytest

from clauditseo import axe
from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST

NEEDS_BROWSER = pytest.mark.skipif(
    not axe.available() or not (DIST / "index.html").is_file(),
    reason="needs clauditseo[render], `playwright install chromium`, and a "
           "built dashboard (npm run build in dashboard/)")

#: The class the one owner paints, named rather than discovered so a shortfall
#: says what is missing. Same component as the source guard's `PriceScopeNote`.
SCOPE_CLASS = "price-scope"

#: A real brief id from `clauditseo/playbook.py`, not an invented one.
#: `expert_estimates` keys on `expert_reports.tool_id` and the screen's working
#: set is built from the playbook, so a fixture using a made-up id produces
#: estimates the screen never looks at - a fixture that cannot express the case
#: its guard was written against, which is the promoted guard's-population
#: invariant in its fixture spelling.
PRICED_TOOL = "indexability"

#: The fixture's own host, asserted on below. A frame that named some other
#: site would satisfy a bare "something was painted" check.
FIXTURE_HOST = "sweepscope.fixture"

#: A page URL for the dossier route. `PageDetailView` filters the run's
#: findings by it and mounts `ExpertPanel` either way, so it does not have to
#: be a page the fixture crawled - which is what lets the third render site be
#: reached without adding a crawl to this fixture for that alone.
FIXTURE_PAGE = f"https://{FIXTURE_HOST}/"

#: The screens that draw a brief price, the route each is reached at, and a
#: selector each paints whether or not the note is there.
#:
#: **CQ-215.** `tests/test_a_brief_price_says_which_site_it_was_drawn_from.py`
#: used to decide both of the questions below from its own source text - which
#: screens are in the population, by `"typical_cost" in p.read_text()`, and how
#: many notes each renders, by `len(re.findall(rf"<{OWNER}\b", source))`. Both
#: are satisfiable by a comment and breakable by a rename, and `tools.tsx`
#: carries a note recording that someone broke the count by naming the
#: component in prose. Both questions are settled here instead, from what the
#: browser painted.
#:
#: The `ready` selector is deliberately **not** `p.price-scope`: a clause that
#: waited for the note could never observe zero of them, and zero is the value
#: it exists to catch - CQ-214, which is exactly the case the source count sat
#: through. The route is a routing fact read from `dashboard/src/App.tsx`,
#: which is the part a source read may still own; nothing here reads a `.tsx`
#: to decide what was rendered.
PRICE_SCREENS = {
    "schedule": (lambda site, run: f"#/sites/{site}?schedule",
                 "section.sched-block"),
    "page-experts": (lambda site, run:
                     f"#/runs/{run}/page/{quote(FIXTURE_PAGE, safe='')}",
                     "h3"),
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served_with_a_priced_brief():
    """A real server with one site whose history prices one real brief.

    Its own server rather than `test_a11y_rendered.py`'s `served`, on the
    precedent `test_the_spending_screen_frames_its_money.py` set and for its
    reason: that fixture's seed is asserted on by several files for its run
    count and its findings, and an `expert_reports` row added to it to prove
    something about this screen is how a shared fixture stops being readable.
    """
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app

    tmp = Path(tempfile.mkdtemp(prefix="sweepscope"))
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
                            json={"name": "Scope Fixture Co"},
                            timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "https://sweepscope.fixture/"},
                          timeout=30).json()
        conn = connect(db)
        # An older, finished run carries the priced history.
        # `expert_estimates` takes its medians over *this site's* stored
        # briefs, so the price has to exist on a run of this site rather than
        # on the run being looked at.
        priced_run = runs.create_run(conn, site["id"], ["TEC"], "T2")
        runs.store_expert_report(
            conn, priced_run, PRICED_TOOL,
            {"model": "fixture", "report": "", "findings": [],
             "tokens": 120_000, "cost": 0.42},
            elapsed_ms=90_000)
        with conn:
            runs.mark_complete(conn, priced_run, runs.now_iso())
        # The run the screen reads. The tools screen renders its working set
        # only once the site has a finished run. `scores=None` is the
        # imported-crawl shape and is all this screen needs: it asks what has
        # been analysed, not what was scored.
        run_id = runs.create_run(conn, site["id"], ["TEC"], "T2")
        with conn:
            runs.mark_complete(conn, run_id, runs.now_iso())
        conn.close()
        yield base, site["id"], run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_payload_the_sweep_sums_already_carries_the_frame(
        served_with_a_priced_brief):
    """The premise, asserted rather than assumed - and non-vacuously.

    If this fails, the rendered clause below is measuring the absence of
    something that was never on the wire, and its failure would say the wrong
    thing. The assertions are separate on purpose: a payload with no priced
    entry at all would satisfy "every entry carries the key" trivially, which
    is the empty-population defect the promoted invariant names.
    """
    import httpx

    base, site_id, run_id = served_with_a_priced_brief
    payload = httpx.get(f"{base}/api/runs/{run_id}/expert", timeout=30).json()
    estimates = payload.get("estimates") or {}
    assert estimates, (
        "the run carries no estimates at all, so the screen has no sweep "
        "figure to frame and this file proves nothing")

    priced = {k: v for k, v in estimates.items() if v.get("cost") is not None}
    assert priced, (
        "no estimate carries a cost, so `fig.cost` is 0 and the screen paints "
        f"no money: {sorted(estimates)}")

    unframed = [k for k, v in priced.items() if "scoped_to_site" not in v]
    assert not unframed, (
        f"{unframed} carry a cost with no `scoped_to_site` beside it; the "
        "estimator is meant to record which population each median was taken "
        "over - `expert_estimates` in `clauditseo/persistence/runs.py`")
    assert all(v["scoped_to_site"] == site_id for v in priced.values()), (
        "the route resolved the run's own site and the estimates say they "
        "were measured over a different population")


# RETIRED with item 188: `test_the_sweep_forecast_is_framed_before_a_tool_is
# _opened` drove the Tools screen's sweep forecast - the figure summed out of
# `/api/runs/{id}/expert`'s `estimates` beside the control that ran every
# brief. Tools is gone and no other screen sums that payload, so the clause
# had nothing to drive. The surviving large money figure, the catalogue's
# batch total, states its own population inline and is held there by
# `test_run_all_confirms_at_the_defaults.py`, `test_the_drawers_numbers
# _agree.py` and `test_a_brief_price_says_what_it_covers.py` - checked before
# deleting this, because "nothing asserts it now" is the thing to be sure of.

@NEEDS_BROWSER
@pytest.mark.parametrize("screen", sorted(PRICE_SCREENS))
def test_every_screen_that_draws_a_brief_price_paints_one_scope_note(
        screen, served_with_a_priced_brief):
    """CQ-215's count, taken from the DOM instead of from a source regex.

    The source guard counted `<PriceScopeNote` in a file. That count sees a
    render site sitting inside a branch that never runs, and it sees a mention
    in a comment - both of which it counts as a painted note, which is how
    CQ-214 passed every clause in that file while the workbench showed the
    largest money figure in the product with no population beside it.

    Counted per screen rather than document-wide on purpose: a search for the
    sentence anywhere would pass on a screen that happened to paint it
    somewhere else, which is CQ-166's shape.
    """
    from playwright.sync_api import sync_playwright

    base, site_id, run_id = served_with_a_priced_brief
    route, ready = PRICE_SCREENS[screen]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/{route(site_id, run_id)}",
                    wait_until="networkidle", timeout=30_000)
            # Non-vacuity: the screen is on, and this selector is one it
            # paints whether or not the note is beside it.
            pg.wait_for_selector(ready, timeout=30_000)
            # The payloads these frames describe land after the first paint,
            # so settle before counting. Waiting for the note itself would
            # make zero unobservable, which is the count under test.
            pg.wait_for_timeout(2_000)
            notes = pg.locator(f"p.{SCOPE_CLASS}")
            painted = [notes.nth(i).inner_text() for i in range(notes.count())]
        finally:
            browser.close()

    assert len(painted) == 1, (
        f"the {screen} screen painted the scope note {len(painted)} times. "
        "0 leaves a brief price on screen with no population stated - the "
        "defect CQ-214 found on the workbench, which the source count sat "
        "through - and more than one is UI-19's repeated static explanation "
        "inside one scroll")
    assert FIXTURE_HOST in painted[0], (
        f"the {screen} screen's frame does not name the site whose history "
        f"the medians were taken over: {painted[0]!r}")


def test_the_driven_screens_are_still_the_ones_wired_to_the_note():
    """A drift alarm on `PRICE_SCREENS`, and deliberately not the membership
    decision.

    Membership is decided by the browser, above. What a hand-kept list cannot
    do is notice a *fourth* screen starting to draw a brief price, and dropping
    that alarm entirely was the one real cost of moving the population off a
    source scan - so it is kept, here, stated as what it is: a check that the
    list this file drives still matches the screens the tree wires the note
    into. It makes no claim about what any of them rendered.

    Imports rather than a bare substring, because that is the wiring fact: a
    screen that renders the note has to import it, and a comment naming it
    does not.
    """
    src = Path(__file__).resolve().parents[1] / "dashboard" / "src"
    wired = set()
    for path in src.glob("*.tsx"):
        text = path.read_text(encoding="utf-8")
        # `\s*` between the brace and `from`, because these imports wrap:
        # `expert.tsx` breaks the line there, and a contiguous pattern found
        # it not at all - which is round 111's CQ-229 mistake and the same one
        # CQ-216's own clause records.
        for block in re.findall(
                r"import \{([^}]*)\}\s*from \"\./components\"", text):
            if "PriceScopeNote" in block:
                wired.add(path.name)
    assert wired, (
        "no screen imports PriceScopeNote from ./components any more; the "
        "population is empty and this file's premise has gone")
    # Two since item 188 retired Tools, which was the third. The alarm is
    # the point of this clause - a screen that STARTS drawing a brief price
    # needs a route adding above - so the set shrank rather than the
    # comparison loosening.
    assert wired == {"schedule.tsx", "expert.tsx"}, (
        f"the screens wired to the scope note are {sorted(wired)}, which is "
        "not the set PRICE_SCREENS drives above. A screen that started "
        "drawing a brief price needs a route adding there, or it paints a "
        "price with nothing checking that it says which site it came from")
