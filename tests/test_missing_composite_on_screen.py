"""UX-15: the run-detail headline says a missing composite the way every
other surface says it.

**The state is reachable today, not hypothetical.** `composite()` returns
`None` — not `0.0` — when no dimension contributed a measurable share, and an
A11Y-only audit is exactly that: `DEFAULT_WEIGHTS["A11Y"]` is `0.0` by the
operator's own decision, and A11Y is selectable from the API and the CLI.
`tests/test_reporting_g7.py::db_with_an_unscorable_run` has staged that run
since round 003 to prove the *documents* handle it. Nothing had ever asked
what the screen does.

**What it did.** `{data.composite_score?.toFixed(1) ?? "—"}` over a
`composite / 100` label, with no accessible text and no reason. A sighted
operator reads an em dash under "composite / 100" — which says a composite
was measured and is being withheld — and a screen-reader user hears "dash,
composite slash one hundred". Report 036 drove that against a real run at
`#/runs/f80bc200…`; it has been carried as UX-15 for thirteen rounds and sits
in `audits/DISPOSITIONS.md`'s engineering cohort as "run-detail headline
renders a bare em dash for no composite".

**Why the sentence is derived here rather than written here.**
`clauditseo/reporting/render.py` owns `NO_COMPOSITE`, and
`test_reporting_g7.py::test_every_template_says_a_missing_composite_the_same_way`
already holds four surfaces to it — both document templates, both audiences,
chat and the CLI. The dashboard was the fifth surface and the only one saying
something else. This file takes the two clauses out of that constant rather
than restating them, so the day the wording moves, the screen is held to the
new wording and not to a copy of the old one. That is DISCIPLINE rule 3's
"enumerate from a registry, never from a hard-coded list", applied across the
Python/TSX boundary where an import cannot reach.

**Two consumers are deliberately not changed, and are named rather than
missed.** `ScoreBadge`'s null branch (`components.tsx`) renders `—` with an
`sr-only` "not scored" and is reached from six table cells; a table cell has
no room for a reason, and its null has several distinct causes — no run yet,
an unscorable run, a field the payload omits — so stamping `NO_COMPOSITE`'s
one reason on it is the wrong economy `render.py:165-167` warns against in
its own words. `views.tsx`'s delete-confirmation string names a run for
identification rather than stating its score. Neither is the accessibility
defect UX-15 names: the headline had no alternative text at all.

**Split across the two CI legs, for the reason `test_spend_mark.py` records.**
The static half reads the source and runs everywhere. The rendered half is
about what the screen *draws* in a state, which cannot be read off source, so
it drives a real server with a real browser and is run in `rendered-a11y`,
where a skip fails the job.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from pathlib import Path

import pytest

from clauditseo import axe
from clauditseo.reporting.render import NO_COMPOSITE
from tests.test_a11y_rendered import DIST

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"
VIEWS = SRC / "views.tsx"

#: JSX/TS comments, blanked rather than deleted so line numbers survive into
#: any failure message — `test_accessibility_headline.py`'s convention, and
#: the reason for it: a guard that reads prose *about* the code passes on a
#: comment that describes the fix somebody meant to make.
COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)

#: The two clauses `test_reporting_g7.py` holds every other surface to, taken
#: out of the constant itself. `NO_COMPOSITE` is
#: `[TO CONFIRM: Not assessed: <what>. Reason: <reason>.]`.
_PARTS = re.match(r"\[TO CONFIRM: (?P<what>Not assessed: [^.]+)\. "
                  r"Reason: (?P<reason>.+)\.\]$", NO_COMPOSITE)

NEEDS_BROWSER = pytest.mark.skipif(
    not axe.available() or not (DIST / "index.html").is_file(),
    reason="needs clauditseo[render], `playwright install chromium`, and a "
           "built dashboard (npm run build in dashboard/)")


def _source(path: Path) -> str:
    return COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"),
                       path.read_text(encoding="utf-8"))


def test_the_shared_sentence_still_has_the_two_clauses_this_file_reads():
    """A precondition, so the assertions below cannot go vacuous.

    Every other test here matches against `_PARTS`. If `NO_COMPOSITE` were
    reworded into a shape this regex does not match, `_PARTS` would be `None`
    and the substring checks would silently compare against nothing. This
    fails first and names the constant rather than the screen.
    """
    assert _PARTS is not None, (
        f"NO_COMPOSITE no longer has the `[TO CONFIRM: <what>. Reason: "
        f"<reason>.]` shape this file reads its clauses out of: "
        f"{NO_COMPOSITE!r}")
    assert _PARTS.group("what") == "Not assessed: composite score"
    assert _PARTS.group("reason").strip()


def test_the_headline_has_no_bare_fallback_for_a_missing_composite():
    """The defect itself, as source: a null coalescing straight to a dash.

    Matched on the composite specifically rather than on `?? "—"` anywhere,
    because a dash is the right answer in a table cell and the wrong one under
    a `composite / 100` label.
    """
    src = _source(VIEWS)
    bare = re.findall(r"composite_score[^\n]{0,40}\?\?\s*\"—\"", src)
    assert not bare, (
        "the run-detail headline still falls back to a bare em dash for a "
        f"composite that was never computed: {bare!r}. A missing composite is "
        "not a withheld one, and the product already has a sentence for it — "
        f"{NO_COMPOSITE!r}")


def test_the_screen_carries_the_same_clauses_as_every_other_surface():
    """Rendered text, not a `title`, and not this file's own words.

    The clauses come out of `NO_COMPOSITE`, so a rewording in `render.py`
    fails here rather than leaving the screen quoting a retired sentence —
    the failure mode UX-10 was, at eight occurrences in a client document.
    """
    assert _PARTS is not None
    src = _source(VIEWS)
    for clause in (_PARTS.group("what"), _PARTS.group("reason")):
        assert clause in src, (
            f"the run-detail headline does not say {clause!r}. Four surfaces "
            "already do — both document templates, chat and the CLI — and the "
            "screen is the fifth.")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def unscorable_run():
    """A real server holding one complete run with no composite.

    Its own server rather than `test_a11y_rendered.py`'s `served`: that
    fixture's seed is asserted on by several files for its run count, its
    trend and its findings, and adding a third run to it to prove something
    about a fourth screen is how a shared fixture stops being readable. The
    recipe is `test_reporting_g7.py::db_with_an_unscorable_run`'s — an
    A11Y-only audit — driven through the same `create_run`/`complete_run`
    path a real audit takes, so the null in the payload is the scoring
    layer's own verdict and not a value this test wrote into a column.
    """
    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from clauditseo.crawler.crawl import crawl
    from clauditseo.crawler.types import TierBudget
    from clauditseo.db.connection import connect
    from clauditseo.engine.core import run_audit
    from clauditseo.engine.types import Site, Tier
    from clauditseo.persistence import runs
    from tests.conftest import FixtureSite
    from tests.test_history_g4 import GOOD_PROMO, _routes

    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="nocomposite"))
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
                            json={"name": "Unscorable Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "https://unscorable.fixture/"},
                          timeout=30).json()

        fixture = FixtureSite(_routes(GOOD_PROMO)).start()
        try:
            crawled = crawl(fixture.base_url + "/", Tier.T2,
                            budget=TierBudget(max_pages=10,
                                              request_timeout_s=5,
                                              wall_clock_s=30, delay_s=0))
        finally:
            fixture.stop()

        result = run_audit(Site(domain="https://unscorable.fixture/"),
                           crawled, ["A11Y"], Tier.T2)
        assert result.composite_score is None, \
            "fixture must produce no composite, or it proves nothing"

        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], ["A11Y"], "T2")
        runs.complete_run(conn, run_id, result)
        conn.close()

        yield base, run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@NEEDS_BROWSER
def test_the_run_screen_states_why_there_is_no_composite(unscorable_run):
    """The clause that matters, read where the operator reads it.

    DISCIPLINE rule 12: the tree is not where a screen counts. This asserts
    on the text the browser actually painted, on a run whose null came out of
    `composite()`.
    """
    from playwright.sync_api import sync_playwright

    assert _PARTS is not None
    base, run_id = unscorable_run
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/runs/{run_id}", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(".headline", timeout=30_000)
            headline = pg.inner_text(".headline")
        finally:
            browser.close()

    for clause in (_PARTS.group("what"), _PARTS.group("reason")):
        assert clause in headline, (
            f"the rendered headline does not say {clause!r}; it says "
            f"{headline!r}")
    assert "composite / 100" not in headline, (
        "a run with no composite still labels its headline `composite / 100`, "
        "which says a number was measured and is being withheld: "
        f"{headline!r}")
