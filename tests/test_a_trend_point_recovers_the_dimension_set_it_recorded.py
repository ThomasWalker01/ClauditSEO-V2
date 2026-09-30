"""WF-58, the half round 097 did not reach: the operator's own history.

`c622af9` put the measured dimension set into the comparability key and was
recorded closed. Report 098 re-measured the finding on the operator's install
and it still reproduces on every point they hold:
`GET /api/sites/2537f69f.../trend` returns `2026-08-15T03:55:10` and
`2026-08-15T06:01:36` as `comparable: True` while the same table's own
per-dimension series show the first measured six dimensions and the second
seven - `ofp.subscore` exists at one stamp and not the other. The term reaches
rows written after it and nothing else, so a fix for a finding about stored
history left the stored history in the state the finding describes.

**The reason given for stopping there is false, and this file is the proof.**
Three statements in the tree said the set was unrecoverable - two comments in
`runs.py` and a docstring in
`test_a_trend_point_states_which_dimensions_it_measured.py` - on the grounds
that a backfill would invent a population nobody recorded. It would not.
`_snapshot_metrics` writes one `{dim}.subscore` row per measured dimension at
the same `site_id` and `captured_at` as the composite, in the same
transaction, filtered by the same `applicable and coverage` predicate the
frame's own term is built from. The population is written down; it was written
in eight rows instead of one.

So the recovery is a *read*, not a backfill, and the third clause below is
what makes that claim checkable: for a run that recorded its own set,
stripping the frame's term and recovering it from the siblings returns the
same set. A derivation whose answer can be checked against a stored one is not
a guess. The rung it came from - `recorded` or `derived` - travels beside the
value, because `_pages_fetched` already establishes that a derived figure
indistinguishable from a stored one is a provenance breach even when it is
right, and because CQ-205 is the standing finding about a rung stored and read
by nobody.

**The last clauses are a browser drive, deliberately.** CQ-218 is report 098's
finding that `c622af9` shipped six cases for the half the operator never sees
and none for the half they read - the sentence in the trend block was verified
by grepping the served bundle, which shows the code shipped and not that it
renders the right thing. This file does not close CQ-218, which asks for cases
across the whole of `frameMoved`; it declines to repeat its defect for the one
sentence this change adds.
"""

from __future__ import annotations

import json
import socket
import threading
import time

import httpx
import pytest

from clauditseo import axe
from clauditseo.persistence import runs as runs_repo
from tests.test_a11y_rendered import DIST
from tests.test_a_trend_point_states_which_dimensions_it_measured import (
    DIMS, NARROW, _audit, _site,
)


def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


#: The operator's own two points, used as the fixture's stamps rather than
#: whatever clock the test runs on. `captured_at` is second-resolution and two
#: audits driven back to back land on the same second - measured, both at
#: `2026-08-23T23:56:00+00:00` - which is a state `_recoverable_dimension_sets`
#: now *refuses* to read, and is therefore useless for demonstrating a
#: successful recovery. The real history is hours apart.
STAMP_A = "2026-08-15T03:55:10+00:00"
STAMP_B = "2026-08-15T06:01:36+00:00"


def _audit_at(conn, site_id, dims, stamp):
    """One audit, with its snapshot rows moved to `stamp`.

    The rows are the product's own - run, scored and stored by `_audit` - and
    only their timestamp is corrected, toward the shape the operator's install
    actually has and away from an artefact of how fast a test loop runs.
    """
    before = {r["id"] for r in conn.execute(
        "SELECT id FROM metric_snapshots WHERE site_id=?", (site_id,))}
    result = _audit(conn, site_id, dims)
    fresh = [r["id"] for r in conn.execute(
        "SELECT id FROM metric_snapshots WHERE site_id=?", (site_id,))
        if r["id"] not in before]
    assert fresh, "the audit stored no metric snapshots to re-stamp"
    with conn:
        conn.executemany("UPDATE metric_snapshots SET captured_at=? WHERE id=?",
                         [(stamp, i) for i in fresh])
    return result


def _strip_term(conn, site_id, *, stamps=None) -> list[str]:
    """Put the site-level frames back into the state the stored rows are in.

    The term is removed from the *frame* only; the `{dim}.subscore` rows keep
    their own scope and, more to the point, keep existing - which is exactly
    the state `2026-08-15T03:55:10` is in. Deliberately not simulated by
    hand-writing a frame: the rows are produced by the product and then edited
    down to what the product used to produce, so the population the recovery
    reads is the real one and not one this file invented for it.
    """
    rows = conn.execute(
        "SELECT id, captured_at, metric_key, scope FROM metric_snapshots"
        " WHERE site_id=?", (site_id,)).fetchall()
    touched = []
    for row in rows:
        if runs_repo.is_per_dimension_metric(row["metric_key"]) or not row["scope"]:
            continue
        if stamps is not None and row["captured_at"] not in stamps:
            continue
        frame = json.loads(row["scope"])
        if "dimensions" not in frame:
            continue
        frame.pop("dimensions")
        with conn:
            conn.execute("UPDATE metric_snapshots SET scope=? WHERE id=?",
                         (json.dumps(frame), row["id"]))
        touched.append(row["captured_at"])
    return touched


def _stamps(conn, site_id) -> list[str]:
    return [r["captured_at"] for r in conn.execute(
        "SELECT captured_at FROM metric_snapshots WHERE site_id=?"
        " AND metric_key='composite_score' ORDER BY captured_at, rowid",
        (site_id,))]


# --- the defect, as the operator holds it ----------------------------------

def test_two_legacy_points_over_different_dimension_sets_are_not_comparable(tmp_path):
    """Report 098's measurement, reproduced: both frames predate the term.

    Round 097's own guard strips the term from *one* point and asserts the
    pair is incomparable - which passes for the wrong reason, because unknown
    never equals a recorded set. The operator has no such pair. Every point
    they hold predates the term, so both sides read unknown, unknown equals
    unknown, and the line is asserted unbroken across a real population
    change. That is the state this clause puts the fixture in.

    Watched failing against unmodified HEAD product source:
    `trend[1]["comparable"]` was `True`.
    """
    conn, site_id = _site(tmp_path)
    wide = _audit_at(conn, site_id, DIMS, STAMP_A)
    narrow = _audit_at(conn, site_id, NARROW, STAMP_B)
    assert wide.composite_score is not None and narrow.composite_score is not None, (
        "precondition: a run with no composite writes no trend point")

    touched = _strip_term(conn, site_id)
    assert len(touched) >= 2, (
        "precondition: the fixture's frames did not carry the term, so "
        f"removing it changed nothing (touched={touched})")

    # The precondition comes from the runs, not from the recovery. Asking the
    # thing under test whether there is anything to detect is the weak
    # population the profile's guard invariant names: on unmodified HEAD the
    # recovery returns nothing, so a precondition read from it would make this
    # clause fail for "no population" rather than for the defect.
    wide_dims = {d for d, s in wide.subscores.items() if s.applicable and s.coverage}
    narrow_dims = {d for d, s in narrow.subscores.items()
                   if s.applicable and s.coverage}
    assert narrow_dims and wide_dims > narrow_dims, (
        "precondition: the two runs measured the same dimensions, so there is "
        f"no population change to detect (wide={sorted(wide_dims)}, "
        f"narrow={sorted(narrow_dims)})")

    trend = runs_repo.site_trend(conn, site_id)
    assert len(trend) == 2, f"expected one point per run, got {len(trend)}"
    assert trend[1]["comparable"] is False, (
        f"a composite over {sorted(narrow_dims)} is asserted comparable with "
        f"one over {sorted(wide_dims)} - neither frame recorded its set, so "
        "the key read unknown against unknown and called the largest "
        "population change the product can make a like-for-like step")
    assert [(p["scope"] or {}).get("dimensions") for p in trend] == [
        sorted(wide_dims), sorted(narrow_dims)], (
        "the break is right and the sets behind it are not what the runs "
        f"measured: {[(p['scope'] or {}).get('dimensions') for p in trend]}")


def test_a_recovered_point_says_it_was_recovered(tmp_path):
    """The rung reaches the payload, on both sides of the distinction.

    Watched failing against unmodified HEAD: `dimensions_basis` was absent
    from every frame, so no consumer could tell a recovered set from a
    recorded one.
    """
    conn, site_id = _site(tmp_path)
    _audit_at(conn, site_id, DIMS, STAMP_A)
    _audit_at(conn, site_id, NARROW, STAMP_B)
    first = _stamps(conn, site_id)[0]
    # Two rows, not one: `composite_score` and `measured_share` are both
    # site-level and both carry the frame, so stripping one stamp touches the
    # pair. Asserted as a set with its size stated, rather than as a list that
    # happens to be in an order.
    stripped = _strip_term(conn, site_id, stamps={first})
    assert set(stripped) == {first} and len(stripped) == 2, (
        "precondition: the first point's frame was not put into the legacy "
        f"state, so this clause has one rung and not two: {stripped}")

    trend = runs_repo.site_trend(conn, site_id)
    bases = [(p["scope"] or {}).get("dimensions_basis") for p in trend]
    assert bases == ["derived", "recorded"], (
        "the two rungs are not distinguishable on the wire: the first point's "
        "set was read back off its own per-dimension rows and the second's "
        f"was stated by the run, and both read {bases!r}")


def test_the_recovered_set_is_the_set_the_run_recorded(tmp_path):
    """What makes the recovery a derivation rather than a guess.

    The run states its set on the frame; the same run writes one row per
    measured dimension beside it. Recovering from the second must return the
    first, or every point recovered at the moment the term was introduced
    would break its own series on a difference that is only bookkeeping.

    Watched failing against unmodified HEAD: the recovered set was `None`.
    """
    conn, site_id = _site(tmp_path)
    _audit_at(conn, site_id, DIMS, STAMP_A)
    _audit_at(conn, site_id, NARROW, STAMP_B)

    recorded = [(p["scope"] or {}).get("dimensions")
                for p in runs_repo.site_trend(conn, site_id)]
    assert all(r for r in recorded), (
        f"precondition: the runs recorded no sets to check against: {recorded}")

    _strip_term(conn, site_id)
    recovered = [(p["scope"] or {}).get("dimensions")
                 for p in runs_repo.site_trend(conn, site_id)]
    assert recovered == recorded, (
        "the set read back off a point's own rows is not the set the same "
        f"point recorded: recorded={recorded}, recovered={recovered}")


# --- the counter-assertions: true on both trees ----------------------------

def test_a_point_with_no_per_dimension_rows_stays_unknown(tmp_path):
    """The one case where the population really was not recorded.

    A frame with no term and no sibling rows has nothing to read, and the
    answer stays unknown - not a guess, and not an empty set, which would
    compare equal to another empty set and assert two blind points alike.

    The state is staged by deleting the sibling rows, and this is honest about
    what that models: at HEAD a composite is only written when some dimension
    had coverage, so the writer always leaves siblings behind. This is the
    defensive rung, asserted so that "unknown" survives as an answer the code
    can still give rather than one the recovery quietly abolished.
    """
    conn, site_id = _site(tmp_path)
    _audit_at(conn, site_id, DIMS, STAMP_A)
    _audit_at(conn, site_id, NARROW, STAMP_B)
    first = _stamps(conn, site_id)[0]
    _strip_term(conn, site_id, stamps={first})
    with conn:
        deleted = conn.execute(
            "DELETE FROM metric_snapshots WHERE site_id=? AND captured_at=?"
            " AND metric_key LIKE '%.subscore'", (site_id, first)).rowcount
    assert deleted, (
        "precondition: the fixture had no per-dimension rows to remove, so "
        "the unknown rung is reached here by an accident rather than by the "
        "state this clause names")

    trend = runs_repo.site_trend(conn, site_id)
    assert (trend[0]["scope"] or {}).get("dimensions") is None, (
        "a point with neither a recorded set nor a row to read one from was "
        f"given one anyway: {trend[0]['scope']}")
    assert (trend[0]["scope"] or {}).get("dimensions_basis") is None, (
        "the unknown rung is labelled as though it came from somewhere: "
        f"{trend[0]['scope']}")
    assert trend[1]["comparable"] is False, (
        "an unknown population was read as a match for a recorded one")


def test_a_per_dimension_series_is_given_no_recovered_set(tmp_path):
    """`onp.subscore` is ONP's own score and the run's other dimensions are
    not its frame. `is_per_dimension_metric` scopes the term out of the key,
    and the recovery must not reach around that by writing the set onto the
    point anyway - it would put a value on the wire that the verdict beside it
    deliberately ignores, which is two opinions about one fact.
    """
    conn, site_id = _site(tmp_path)
    _audit_at(conn, site_id, DIMS, STAMP_A)
    _audit_at(conn, site_id, NARROW, STAMP_B)
    _strip_term(conn, site_id)

    series = runs_repo.site_trend(conn, site_id, "onp.subscore")
    assert len(series) == 2, (
        f"precondition: ONP was not measured by both runs ({len(series)} "
        "points), so the scoping rule is untested here")
    assert all((p["scope"] or {}).get("dimensions_basis") is None
               for p in series), (
        "a per-dimension series carries a recovered run-level set: "
        f"{[p['scope'] for p in series]}")
    assert series[1]["comparable"] is True, (
        "ONP's own score was marked incomparable with ONP's own score because "
        "the runs beside it measured different dimensions")


def test_two_runs_at_one_stamp_are_refused_rather_than_merged(tmp_path):
    """The risk this change introduces, guarded rather than documented.

    `metric_snapshots` carries no run reference, so `(site_id, captured_at)`
    is the only handle a recovery has - and `captured_at` is second
    resolution. Two audits driven back to back land on the same second: that
    is not hypothetical, it is what this file's own fixture did before
    `_audit_at` existed, both stamping `2026-08-23T23:56:00+00:00`.

    Merging them would hand the operator a dimension set no run measured,
    labelled `derived`, as provenance. That is the defect this whole finding
    is made of, one rung down, so the ambiguous stamp reads unknown instead.

    Passes on both trees, which is what a counter-assertion is for: before the
    change there was no recovery to be wrong, and after it there is one that
    must decline.

    **The collision is manufactured, not waited for.** This clause used to
    call `_audit` twice on the real clock and assert as a precondition that
    the two landed on the same second. They usually do and sometimes do not:
    under `-n auto` on a loaded machine the pair straddles a second boundary,
    the precondition fails, and the pinned gate goes red on the wall clock
    rather than on the product - filed as KI-58, reproduced from two
    independent sessions, and the reason Q-31 was asked. Writing one
    `captured_at` over the other is what `_audit_at` already does for every
    other clause in this file, and it makes the case the clause names happen
    on every run instead of most runs. It strengthens the guard: the rows are
    still the product's own, scored and stored by `_audit`, and only their
    timestamp is moved to the state the finding is about.
    """
    conn, site_id = _site(tmp_path)
    _audit_at(conn, site_id, DIMS, STAMP_A)
    _audit_at(conn, site_id, NARROW, STAMP_A)
    collided = _stamps(conn, site_id)
    assert len(collided) == 2 and collided[0] == collided[1], (
        "precondition: the two runs did not collide on one stamp, so this "
        f"clause is not testing the case it names ({collided})")
    _strip_term(conn, site_id)

    trend = runs_repo.site_trend(conn, site_id)
    sets = [(p["scope"] or {}).get("dimensions") for p in trend]
    assert sets == [None, None], (
        "two runs' rows at one timestamp were merged into a set neither of "
        f"them measured, and handed over as a recovered population: {sets}")
    bases = [(p["scope"] or {}).get("dimensions_basis") for p in trend]
    assert bases == [None, None], (
        f"an unrecoverable stamp was labelled with a rung: {bases}")


# --- the sentence the operator actually reads ------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def legacy_trend_server(tmp_path_factory):
    """A site whose whole history predates the dimension term.

    Which is the operator's install, not an invented shape: five stored points
    on `www.acme.com.au`, every one of them `scope.dimensions: null`, with
    their per-dimension rows intact beside them.
    """
    import uvicorn

    from clauditseo.api.app import create_app

    tmp = tmp_path_factory.mktemp("legacy-trend")
    conn, site_id = _site(tmp)
    _audit_at(conn, site_id, DIMS, STAMP_A)
    _audit_at(conn, site_id, NARROW, STAMP_B)
    stripped = _strip_term(conn, site_id)
    assert len(stripped) >= 2, "the fixture is not in the legacy state"
    conn.close()

    app = create_app(db_path=tmp / "trend.db")
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
    try:
        yield f"http://127.0.0.1:{port}", site_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_route_serves_the_legacy_state_this_screen_is_about(legacy_trend_server):
    """The floor. Every browser clause below asserts about text the client can
    only paint from this payload, so if the shape ever stops arriving they
    would all fail for a reason that is not the finding.
    """
    base, site_id = legacy_trend_server
    trend = httpx.get(f"{base}/api/sites/{site_id}/trend", timeout=30).json()
    assert len(trend) == 2, f"the site served {len(trend)} trend points"
    bases = [(p["scope"] or {}).get("dimensions_basis") for p in trend]
    assert bases == ["derived", "derived"], (
        f"neither point is in the legacy state this file is about: {bases!r}")
    assert trend[1]["comparable"] is False, (
        "the server did not break the line, so the sentence the clause below "
        "reads has no break to describe")


#: Everything the Score trend block and the Runs table beneath it say, as
#: one string.
#:
#: It was `p.trend-frame` alone — the paragraph that listed every break in
#: prose, which brief v16f dropped. The two facts these clauses are about did
#: not go with it: the break is drawn as a rule and named in the table's
#: "reads against" column, and the recovery is its own note under the chart.
#: Read as one string rather than as two selectors because the finding is
#: about what the operator is told on this screen, not about which element
#: tells them.
TREND_FRAME = """() => {
  const block = document.querySelector('.st-root');
  const table = document.querySelector('.runs-table');
  if (!block) return null;
  return [block.innerText, table ? table.innerText : ''].join(' ').trim();
}"""


@pytest.fixture()
def history_frame(legacy_trend_server):
    from playwright.sync_api import sync_playwright

    base, site_id = legacy_trend_server
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load",
                    timeout=30_000)
            # The strip, where the step names are: it left its card at item 173.
            pg.wait_for_selector("nav.seq-chapters a.seq-name", timeout=15_000)
            # By accessible name: the step names are the navigation, and
            # step 2's pane is where the trend lives.
            pg.click('a.seq-name:text-is("Record")')
            pg.click('.record-view a:text-is("Audits")')
            pg.wait_for_selector(".st-root", timeout=15_000)
            pg.wait_for_selector(".runs-table tbody tr", timeout=15_000)
            said = pg.evaluate(TREND_FRAME)
            assert said, "the Audit pane painted no Score trend block"
            yield said
        finally:
            browser.close()


@live
def test_the_history_screen_names_the_dimension_break(history_frame):
    """The break itself, on the screen. Watched failing against the unfixed
    bundle and server: the paragraph read *"All 2 points share one engine
    version, share basis, tier and dimension set, so they read as one
    series."* - which is the assertion the finding says is false.

    Since brief v16f the words are in the Runs table's last column rather
    than in a paragraph: the second point has no earlier run that measured
    its way, so its row reads `nothing - dimensions dropped: ...`. The full
    change list is what that column carries where there is no partner to
    name, which is the item's own rule and is why this clause still has
    something to read.
    """
    assert "dimensions dropped" in history_frame, (
        "the trend states no dimension movement, so the break the operator's "
        f"history actually contains is not on the screen: {history_frame!r}")


@live
def test_the_history_screen_says_the_set_was_recovered(history_frame):
    """The rung, rendered. A recovered set that reads exactly like a recorded
    one is the provenance breach; CQ-205 is the open finding about the same
    rung computed and rendered by nobody, one table over.

    Watched failing against the unfixed bundle: the paragraph carried no such
    sentence at all.
    """
    assert "recovered from the per-dimension scores" in history_frame, (
        "the screen states a dimension set for points that never recorded "
        f"one and does not say where it came from: {history_frame!r}")
    assert "2 of 2" in history_frame, (
        "the sentence does not count the points it covers, so a single legacy "
        f"row reads the same as a whole history of them: {history_frame!r}")
