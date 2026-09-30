"""The breadth figure every audit stores, given the reader it never had.

`audits/DISPOSITIONS.md`'s engineering cohort, oldest live row at twelve
rounds: **`measured_share` has a writer and no reader.** Report 064 carries it
as CQ-23 and re-established it mechanically — "`measured_share` returns zero
hits under `dashboard/src`".

**What is stored.** `_snapshot_metrics` writes one `measured_share` row into
`metric_snapshots` beside every audit's composite, at `confidence: high`, with
the frame it was computed under in the `scope` column
(`clauditseo/persistence/runs.py:626-631`). It answers the question the
composite cannot: *how much of the intended audit does this number rest on.*
A T1 pulse over a tenth of the weight and a full T3 both print a two-digit
score, and only this figure separates them.

**What read it.** Nothing. `GET /api/sites/{id}/trend` takes a `metric`
parameter and would serve it (`clauditseo/api/app.py:1210-1214`), and no
caller anywhere passes `measured_share` — the dashboard asks for the default
`composite_score`, `analysts/tools.py:234` asks for the default, `chat.py:43`
asks for the default. So the figure has been computed, framed, stored at high
confidence and served on request, for twelve rounds, to nobody.

**Why the run screen and not the trend chart.** The headline on
`#/runs/<id>` is the one surface whose job is to decompose the composite —
it already prints the dimension table under "weighted over the dimensions
below", and already carries a card saying what a narrow run read. The trend
chart draws a series over time and would need a second axis to say the same
thing; that is a bigger change than this figure is worth, and the figure's
whole point is to qualify *a* score rather than to be a series.

**The frame travels with the value, which is why `basis` is not decoration.**
`scoring.share_basis` returns `coverage` or `coverage+breadth`, and the two
are not one quantity — `test_coverage.py` records five real rows for one site
where 0.2879 and 0.9362 shared a tier and meant different things. A screen
printing "28.8%" without saying which is the defect this figure was framed to
prevent, re-committed at the reader. So the screen branches on the stored
`basis`, and the branch set is derived here from `share_basis` itself rather
than written down, per DISCIPLINE rule 3.

**Absence is not zero.** A verify run, a refresh run and a blocked run all
store no snapshot — `complete_run` calls `_snapshot_metrics` only for a
site-reading kind, and `_snapshot_metrics` returns early on `blocked`. The
payload therefore carries `null`, and the screen must print nothing at all.
Rendering "0.0% of the intended audit" for a run that never wrote the figure
would be the `page_coverage` mistake in a new place: an unmeasured thing made
to look measured.

**Split across the two CI legs**, for the reason `test_spend_mark.py` and
`test_missing_composite_on_screen.py` both record. The payload half and the
static-source half run everywhere; the half about what the browser painted
drives a real server with a real browser and runs in `rendered-a11y`, where a
skip fails the job.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from pathlib import Path

import pytest

from clauditseo import axe
from clauditseo.engine.scoring import share_basis
from tests.test_a11y_rendered import DIST

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"
VIEWS = SRC / "views.tsx"

#: JSX/TS comments, blanked rather than deleted so line numbers survive into a
#: failure message — `test_missing_composite_on_screen.py`'s convention, and
#: its reason: a guard reading prose *about* the code passes on a comment
#: describing the fix somebody meant to make.
COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)

#: Every value `share_basis` can return, obtained by calling it rather than by
#: reading its source or restating its two strings. The scope shapes are the
#: two the function distinguishes: a declared total with a fetched count, and
#: anything short of that.
BASES = sorted({
    share_basis(None),
    share_basis({}),
    share_basis({"discovered": 272}),
    share_basis({"pages_fetched": 6}),
    share_basis({"pages_fetched": 6, "discovered": 272}),
})

NEEDS_BROWSER = pytest.mark.skipif(
    not axe.available() or not (DIST / "index.html").is_file(),
    reason="needs clauditseo[render], `playwright install chromium`, and a "
           "built dashboard (npm run build in dashboard/)")


def _source(path: Path) -> str:
    return COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"),
                       path.read_text(encoding="utf-8"))


def test_share_basis_still_returns_the_two_values_this_file_branches_on():
    """A precondition, so the assertions below cannot go vacuous.

    Every check here enumerates `BASES`. If `share_basis` were reduced to one
    value, or grew a third, the branch assertions would quietly compare
    against the wrong set. This fails first and names the function rather than
    the screen.
    """
    assert BASES == ["coverage", "coverage+breadth"], (
        f"`share_basis` now returns {BASES!r}. That is not a failure of the "
        "screen — it is a change to what the stored figure can mean, and the "
        "screen's branch set is derived from this function on purpose.")


# --- the payload -----------------------------------------------------------

def _completed(tmp_path, *, evidence=None, kind="audit"):
    """One run completed through the real `create_run`/`complete_run` path.

    The stored figure has to come out of `_snapshot_metrics`, not out of a
    value this test wrote into a column — the whole finding is about what the
    writer already produces.
    """
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    from tests.test_coverage import DIMS, _Hub, _run

    conn = connect(tmp_path / "share.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Share Co")
    site_id = repo.create_site(conn, client, "x.test")
    result = _run(_Hub())
    run_id = runs.create_run(conn, site_id, DIMS, "T2", kind=kind)
    if evidence is not None:
        runs.store_evidence(conn, run_id, evidence)
    runs.complete_run(conn, run_id, result)
    return conn, site_id, run_id


def test_a_run_carries_the_breadth_figure_the_audit_stored(tmp_path):
    """The reader, at the layer that serves the run screen.

    Read back from `metric_snapshots` rather than recomputed: recomputing
    would give the *figure* a reader and leave the stored row exactly as
    unread as it was, and the two can disagree — a run completed under an
    older engine keeps the value that engine wrote.
    """
    import json

    from clauditseo.persistence import runs as runs_repo

    conn, site_id, run_id = _completed(tmp_path, evidence={
        "stats": {"eligible": 6, "fetched": 6, "blocked_by_robots": 0},
        "sitemap_entry_total": 272, "pages": [], "robots_blocked": []})
    stored = conn.execute(
        "SELECT value, scope FROM metric_snapshots"
        " WHERE site_id=? AND metric_key='measured_share'", (site_id,)).fetchone()
    assert stored, "precondition: the audit stored no share to read"

    share = runs_repo.run_measured_share(conn, runs_repo.get_run(conn, run_id))
    assert share is not None, (
        "a completed audit's run payload carries no `measured_share`, so the "
        "figure the engine stored still has no reader")
    assert share["value"] == stored["value"], (
        f"the payload reports {share['value']} where the stored row holds "
        f"{stored['value']}")
    assert share["basis"] == json.loads(stored["scope"])["basis"]
    assert share["basis"] == "coverage+breadth", (
        "this run declared a total and a fetched count, so breadth applies")
    assert share["pages_fetched"] == 6 and share["discovered"] == 272, (
        "the counts the figure was derived from travel with it, so the screen "
        "can state the frame rather than assert it")
    conn.close()


def test_a_run_with_no_declared_total_says_so_rather_than_implying_breadth(tmp_path):
    """The other basis, and the reason the label is not decoration.

    Same key, same confidence, different quantity. A payload that reported
    only the number would leave the two indistinguishable, which is the defect
    the `scope` column was added to close.
    """
    from clauditseo.persistence import runs as runs_repo

    conn, _, run_id = _completed(tmp_path)
    share = runs_repo.run_measured_share(conn, runs_repo.get_run(conn, run_id))
    assert share is not None
    assert share["basis"] == "coverage"
    assert share["discovered"] is None, (
        "no total was declared, so there is no total to state; a zero here "
        "would read as a site with no pages")
    conn.close()


def test_a_run_that_stored_no_share_reports_none_rather_than_zero(tmp_path):
    """Absence is not zero — the distinction the whole coverage model turns on.

    A verification is not a reading of the site, so `complete_run` writes it
    no trend point at all. The payload must say "not recorded", because 0.0
    would say "we measured, and it was none of it".
    """
    from clauditseo.persistence import runs as runs_repo

    conn, site_id, run_id = _completed(tmp_path, kind="verify")
    assert not conn.execute(
        "SELECT 1 FROM metric_snapshots WHERE site_id=? AND metric_key='measured_share'",
        (site_id,)).fetchall(), "precondition: a verify run must store no share"

    assert runs_repo.run_measured_share(
        conn, runs_repo.get_run(conn, run_id)) is None, (
        "a run with no stored share reports something other than None, so the "
        "screen cannot tell an unmeasured breadth from a measured zero")
    conn.close()


def test_the_api_serves_the_figure_on_the_run_the_screen_asks_for(tmp_path):
    """Through the route, not only through the repository.

    `run_detail` builds its own dict on top of `get_run`, so a field added to
    the repository and dropped by the route would satisfy every test above and
    reach no screen.
    """
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    conn, _, run_id = _completed(tmp_path, evidence={
        "stats": {"eligible": 6, "fetched": 6, "blocked_by_robots": 0},
        "sitemap_entry_total": 272, "pages": [], "robots_blocked": []})
    conn.close()

    with TestClient(create_app(db_path=tmp_path / "share.db")) as client:
        body = client.get(f"/api/runs/{run_id}").json()
    assert body.get("measured_share"), (
        "GET /api/runs/{id} does not serve the stored breadth figure")
    assert body["measured_share"]["basis"] == "coverage+breadth"


def test_a_run_that_recorded_no_page_count_says_so_rather_than_naming_the_site(tmp_path):
    """UX-55's discriminator, at the layer that hands it to the screen.

    `share_basis` returns `coverage` for two situations and its own docstring
    says so - "the site declared no total, **or** the crawl recorded no fetched
    count". Only the first is a fact about the client's site. The reader can
    already tell them apart and has never been asserted to: `pages_fetched` is
    `None` when nothing about the crawl was recorded, and a number when the
    site simply declared no total.

    The neighbour above is named `..._with_no_declared_total_...` and passes no
    evidence, which is *this* case rather than that one. Its two assertions are
    true either way, so it is left as it stands; the distinction is asserted
    here instead, where a reader meeting the two together can see which is
    which.
    """
    from clauditseo.persistence import runs as runs_repo

    conn, _, unscoped = _completed(tmp_path)
    share = runs_repo.run_measured_share(
        conn, runs_repo.get_run(conn, unscoped))
    assert share is not None and share["basis"] == "coverage"
    assert share["pages_fetched"] is None, (
        f"a run that stored no crawl evidence reports "
        f"{share['pages_fetched']!r} pages fetched. `None` here is the only "
        "thing that separates 'we recorded nothing about this crawl' from "
        "'this site declared no page total', and the screen states one of "
        "those two as a fact about the client.")
    conn.close()


# --- the screen, as source -------------------------------------------------

def test_the_run_screen_reads_the_figure(tmp_path=None):
    """The finding itself, as source: zero hits under `dashboard/src`."""
    hits = [p.name for p in sorted(SRC.rglob("*.ts*"))
            if "measured_share" in _source(p)]
    assert hits, (
        "no file under dashboard/src mentions `measured_share`. The engine "
        "computes it, frames it and stores it at high confidence on every "
        "audit, and the API serves it on request — and no screen has ever "
        "shown it.")
    assert VIEWS.name in hits, (
        f"`measured_share` is read somewhere ({hits!r}) but not by the run "
        "screen, which is the surface that decomposes the composite")


def test_the_screen_states_which_of_the_two_quantities_it_is_printing():
    """One branch per value `share_basis` can return, enumerated from it.

    A hard-coded pair here would be the exact economy DISCIPLINE rule 3 names:
    a third basis would be printed under one of the other two's labels, and
    every test in this file would still pass.
    """
    src = _source(VIEWS)
    missing = [b for b in BASES if f'"{b}"' not in src and f"'{b}'" not in src]
    assert not missing, (
        f"the run screen prints the stored share without distinguishing "
        f"{missing!r} from the basis it does name. The two are not one "
        "measurement — the `scope` column exists because five rows for one "
        "site held both under one key.")


def test_the_screen_does_not_print_a_share_it_was_not_given():
    """No `?? 0` on the way to the screen.

    The payload says `null` for a run that stored nothing, and the one thing
    the screen may not do with that is coalesce it to a number.
    """
    src = _source(VIEWS)
    bad = re.findall(r"measured_share[^\n]{0,60}\?\?\s*0", src)
    assert not bad, (
        f"the run screen falls back to a numeric zero for an unrecorded "
        f"share: {bad!r}. A run that never measured its breadth has not "
        "measured it as none.")


#: A null test on the count the screen must branch on. Accepted in either
#: order and with either equality operator, because the property is "the
#: component asks whether it was given the count", not one spelling of it.
PAGES_FETCHED_NULL_TEST = re.compile(
    r"share\.pages_fetched\s*[!=]==?\s*(null|undefined)"
    r"|(null|undefined)\s*[!=]==?\s*share\.pages_fetched")


def test_the_screen_does_not_state_a_reason_it_was_not_given():
    """UX-55, as a tripwire for the CI leg that has no browser.

    The component printed *"this site declared no page total"* for both of the
    situations `share_basis` collapses into `coverage`, including the one where
    nothing about the crawl was recorded at all - a claim about the client's
    site made where the product simply stored nothing. A stated frame that is
    false is worse than an absent one, which is the provenance invariant read
    at the screen.

    **This is the tripwire, not the evidence.** What the browser painted is
    asserted by `test_the_run_screen_does_not_claim_a_total_the_site_never_declared`
    below, and that is where this finding is actually settled - a source match
    proves a branch exists, never that it renders. This one earns its place by
    running on the leg where no browser does, so the branch cannot be deleted
    silently between rendered runs.

    Deliberately not asserted here: the wording. Both sentences are pinned in
    the rendered test, against text a browser produced.
    """
    src = _source(VIEWS)
    assert PAGES_FETCHED_NULL_TEST.search(src), (
        "the run screen never asks whether it was given a fetched count, so "
        "its `coverage` sentence names one of the two situations `share_basis` "
        "collapses and asserts it for both. The count is already on the wire - "
        "`api.ts` types `pages_fetched: number | null` - so this is the screen "
        "declining to read what it was handed, not a missing field.")


# --- the screen, as painted ------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def narrow_audit():
    """A real server holding one audit that read 6 of 272 declared pages.

    Its own server rather than `test_a11y_rendered.py`'s `served`, for the
    reason `test_missing_composite_on_screen.py` gives: that fixture's seed is
    asserted on by several files for its run count and its trend, and adding a
    run to it to prove something about another screen is how a shared fixture
    stops being readable.

    The breadth is written as crawl evidence — the same shape `_scope` reads
    off a real crawl — so the figure on the screen is `_snapshot_metrics`'
    own arithmetic and not a number this fixture chose.
    """
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from clauditseo.db.connection import connect
    from clauditseo.persistence import runs
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="measuredshare"))
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
                            json={"name": "Narrow Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "narrow.fixture"}, timeout=30).json()

        result = _run(_Hub())
        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.store_evidence(conn, run_id, {
            "stats": {"eligible": 6, "fetched": 6, "blocked_by_robots": 0},
            "sitemap_entry_total": 272, "pages": [], "robots_blocked": []})
        runs.complete_run(conn, run_id, result)
        conn.close()

        yield base, run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@NEEDS_BROWSER
def test_the_run_screen_paints_how_much_of_the_audit_the_score_rests_on(narrow_audit):
    """DISCIPLINE rule 12: the tree is not where a screen counts.

    Asserted on the text the browser painted, for a run whose share came out
    of `_snapshot_metrics` — the figure, and the frame that says which of the
    two quantities it is.
    """
    import httpx
    from playwright.sync_api import sync_playwright

    base, run_id = narrow_audit
    served = httpx.get(f"{base}/api/runs/{run_id}", timeout=30).json()
    share = served["measured_share"]
    assert share and share["basis"] == "coverage+breadth", (
        f"precondition: the fixture run stored {share!r}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/runs/{run_id}", wait_until="load", timeout=30_000)
            pg.wait_for_selector(".headline", timeout=30_000)
            headline = pg.inner_text(".headline")
        finally:
            browser.close()

    assert f"{share['value'] * 100:.1f}%" in headline, (
        f"the rendered headline does not print the stored share "
        f"{share['value']} anywhere; it says {headline!r}")
    for count in ("6", "272"):
        assert count in headline, (
            f"the headline states a breadth-scaled share without the counts "
            f"it was scaled by ({count} missing): {headline!r}")


@pytest.fixture(scope="module")
def unscoped_audit():
    """A real server holding one completed audit that stored no crawl evidence.

    `narrow_audit` above, minus the one call that matters: no `store_evidence`,
    so `_snapshot_metrics` writes the frame `{"basis": "coverage"}` with no
    counts beside it and the reader answers `pages_fetched: None`. That is the
    state UX-55 is about, and it is not exotic - `cli.py`'s fixed-tier branch
    never calls `store_evidence` at all (CQ-05), and live run `8fdeb042` is an
    API run in the same state.

    Its own server rather than a second run inside `narrow_audit`, for that
    fixture's own stated reason: a fixture asserted on for what it holds stops
    being readable the moment another screen's proof is added to it.
    """
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from clauditseo.db.connection import connect
    from clauditseo.persistence import runs
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="unscopedshare"))
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
                            json={"name": "Unscoped Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "unscoped.fixture"}, timeout=30).json()

        conn = connect(db)
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        # No `store_evidence`. That absence is the fixture.
        runs.complete_run(conn, run_id, _run(_Hub()))
        conn.close()

        yield base, run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@NEEDS_BROWSER
def test_the_run_screen_does_not_claim_a_total_the_site_never_declared(unscoped_audit):
    """UX-55, settled where the operator meets it: the painted sentence.

    DISCIPLINE rule 12 - the tree is not where a screen counts - and rule 4:
    the source guard above proves a branch exists and can say nothing about
    what it renders. This drives the built bundle the operator is served,
    against a run whose frame came out of `_snapshot_metrics`.

    **Why this cannot be read off the live database instead.** Every
    `measured_share` row on the machine predates migration 0022 and carries
    `scope` NULL (CQ-136), so every live run paints the *third* arm - "the
    frame this figure was computed under was not recorded" - and the false
    sentence has not yet been shown to anybody. It would be, on the next run
    that stores one. A fixture is the only way to see it before then, and
    manufacturing a live run to watch it would leave a row this product cannot
    delete (WF-81).

    **Left to the writer, deliberately.** `share_basis` still returns two
    values and this test does not ask it to return three. Whether the writer
    records which of the two, or the frame gains a separate "was any scope
    recorded" key, is report 065's OPEN QUESTION 1 and it decides whether
    `site_trend`'s grouping key moves. Both answers leave `pages_fetched` on
    the wire, so this branch is correct under either and does not prejudge it.
    """
    import httpx
    from playwright.sync_api import sync_playwright

    base, run_id = unscoped_audit
    served = httpx.get(f"{base}/api/runs/{run_id}", timeout=30).json()
    share = served["measured_share"]
    assert share and share["basis"] == "coverage", (
        f"precondition: the fixture run stored {share!r}")
    assert share["pages_fetched"] is None, (
        f"precondition: this fixture exists for the no-count case and stored "
        f"{share['pages_fetched']!r}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/runs/{run_id}", wait_until="load", timeout=30_000)
            pg.wait_for_selector(".headline", timeout=30_000)
            headline = pg.inner_text(".headline")
        finally:
            browser.close()

    assert f"{share['value'] * 100:.1f}%" in headline, (
        f"the rendered headline does not print the stored share "
        f"{share['value']} anywhere; it says {headline!r}")
    assert "declared no page total" not in headline, (
        f"the headline tells the operator the client's site declared no page "
        f"total, on a run where nothing about the crawl was recorded. That is "
        f"a fact asserted about somebody else's website on no evidence: "
        f"{headline!r}")
    assert "this audit recorded no crawl page count" in headline, (
        f"the false sentence is gone and nothing replaced it. The subject has "
        f"to move from the site to the run - the reader knows the count is "
        f"missing and the operator needs to be told which of the two "
        f"situations they are looking at: {headline!r}")
