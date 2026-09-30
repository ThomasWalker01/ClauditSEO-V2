"""WF-58 — the comparability key could not see the dimension set.

Report 051, carried at High by every report from 051 to 097. `site_trend` is
the one function whose stated job is to say where a comparison stops being
one, and it keyed on `(engine_version, scope.basis, tier)` — three terms that
between them say which engine measured, whether breadth was applied, and how
deep the crawl went, and nothing at all about *which dimensions ran*.

The consequence report 051 reproduced against a throwaway migrated database:
a composite of 91.0 over eight dimensions and one of 62.0 over one, same
tier, same engine version, same basis, both came back `comparable: True`. The
launcher can produce that pair in one click from the anatomy screen (WF-59),
and the operator's stored history already shows the shape — `8fdeb042` ran
seven dimensions and `e4f998d1` eight, with only an engine-version change
separating them on the chart.

The term is the run's *measured* dimension set — applicable, with coverage —
which is the same predicate `_snapshot_metrics` already uses to decide which
per-dimension rows to write. Not the requested set: a dimension that was asked
for and read nothing contributes to neither the composite nor the chart, so
counting it would split a series on a difference no plotted number carries.

**Two counter-assertions here are as load-bearing as the defect clause**, and
they are why the term is scoped rather than added to every key:

  - two runs over the *same* set stay comparable, or the flag has simply been
    turned off;
  - a per-dimension series — `onp.subscore` — is **not** split by the other
    dimensions the run happened to measure. ONP's own score is computed from
    ONP's own checks; the set of dimensions beside it is not that number's
    frame. Marking those points incomparable would be a false alarm on eight
    series at once, and a flag that cries wolf is the state WF-48 describes:
    noise is what hides a real miss.
"""

from __future__ import annotations

import json

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from clauditseo.persistence import runs as runs_repo

#: The full set, as `tests/test_coverage.py` declares it. Both fixtures below
#: derive their dimension sets from this rather than from a literal, so a
#: dimension added to the product widens the wide run without an edit here.
DIMS = ["TEC", "ONP", "A11Y", "PRF", "CNT", "OFP", "LOC", "AIS"]

#: The narrow run. One dimension, chosen because the crawl fixture below gives
#: it real coverage — a dimension with `coverage == 0.0` writes no trend point
#: at all and the narrow run would have no composite to compare.
NARROW = ["ONP"]


def _crawl() -> CrawlResult:
    page = Page(
        url="https://x.test/", requested_url="https://x.test/", status=200,
        content_type="text/html",
        content="<html lang=en><head><title>A reasonable title for the page</title>"
                f"<meta name=description content='{'x' * 140}'></head><body><main>"
                f"<h1>Hi</h1><p>{'word ' * 400}</p></main></body></html>",
        headers={"cache-control": "max-age=3600"}, elapsed_ms=120)
    return CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[page])


def _site(tmp_path):
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo

    conn = connect(tmp_path / "trend.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Trend Co")
    return conn, repo.create_site(conn, client, "x.test")


def _audit(conn, site_id, dims):
    """One completed audit over `dims`, into a real database.

    No `store_evidence`, deliberately. Every run here then reaches
    `_snapshot_metrics` with `scope=None`, so `share_basis` returns
    `coverage` for all of them and the *basis* term of the key is held
    constant. Tier and engine version are constant by construction. That
    leaves the dimension set as the only term that differs between the two
    runs, which is what makes a `comparable` verdict attributable to it.
    """
    result = run_audit(Site(domain="https://x.test/"), _crawl(), dims, Tier.T2,
                       context={"providers": None})
    run_id = runs_repo.create_run(conn, site_id, dims, "T2")
    runs_repo.complete_run(conn, run_id, result)
    return result


def _frames(conn, site_id, metric_key="composite_score"):
    return [json.loads(r["scope"]) if r["scope"] else None
            for r in conn.execute(
                "SELECT scope FROM metric_snapshots"
                " WHERE site_id=? AND metric_key=? ORDER BY captured_at, rowid",
                (site_id, metric_key))]


def test_two_composites_over_different_dimension_sets_are_not_comparable(tmp_path):
    """The defect, reproduced the way report 051 reproduced it.

    Watched failing against unmodified HEAD: both points came back
    `comparable: True`, which is the function that exists to deny like-for-like
    asserting it across the largest population change the product can make.
    """
    conn, site_id = _site(tmp_path)
    wide = _audit(conn, site_id, DIMS)
    narrow = _audit(conn, site_id, NARROW)

    # The fixture has to have produced the pair before the assertion means
    # anything — a run with no composite writes no trend point, and a trend of
    # one point is comparable by definition.
    assert wide.composite_score is not None and narrow.composite_score is not None, (
        "precondition: a run with no composite writes no trend point, so this "
        f"asserts nothing (wide={wide.composite_score}, "
        f"narrow={narrow.composite_score})")
    wide_dims = {d for d, s in wide.subscores.items() if s.applicable and s.coverage}
    narrow_dims = {d for d, s in narrow.subscores.items()
                   if s.applicable and s.coverage}
    assert narrow_dims and wide_dims > narrow_dims, (
        "precondition: the two runs measured the same dimensions, so there is "
        f"no population change to detect (wide={sorted(wide_dims)}, "
        f"narrow={sorted(narrow_dims)})")

    trend = runs_repo.site_trend(conn, site_id)
    assert len(trend) == 2, f"expected one point per run, got {len(trend)}"
    assert trend[0]["comparable"] is True, "the first point has nothing before it"
    assert trend[1]["comparable"] is False, (
        f"a composite over {sorted(narrow_dims)} is asserted comparable with one "
        f"over {sorted(wide_dims)} — same tier {trend[0]['tier']}, same engine "
        f"version {trend[0]['engine_version']}, same basis "
        f"{(trend[0]['scope'] or {}).get('basis')!r}, and the only thing that "
        "changed is the population the number was computed over")
    conn.close()


def test_two_composites_over_the_same_dimension_set_stay_comparable(tmp_path):
    """The counter-assertion, and it must pass on both trees.

    Adding a term to the key can only ever make more pairs incomparable, so a
    guard that asserted the defect clause alone would be satisfied by a
    `comparable` that is always `False`. This is the assertion that says the
    flag still carries information.
    """
    conn, site_id = _site(tmp_path)
    _audit(conn, site_id, DIMS)
    _audit(conn, site_id, DIMS)

    trend = runs_repo.site_trend(conn, site_id)
    assert len(trend) == 2, f"expected one point per run, got {len(trend)}"
    assert trend[1]["comparable"] is True, (
        "two audits over the same dimension set, at one tier and one engine "
        "version, are the like-for-like pair this flag exists to affirm")
    conn.close()


def test_a_per_dimension_series_is_not_split_by_the_runs_other_dimensions(tmp_path):
    """The second counter-assertion, also green on both trees.

    `onp.subscore` is ONP's own score from ONP's own checks. Whether the run
    beside it also measured A11Y changes nothing about that number, so the
    dimension set is not its frame and must not enter its key. Written down
    because the cheaper fix — put the term in every key — is over-strict in a
    way that reads as extra rigour and would mark eight series incomparable at
    every narrow run.
    """
    conn, site_id = _site(tmp_path)
    wide = _audit(conn, site_id, DIMS)
    narrow = _audit(conn, site_id, NARROW)
    for label, result in (("wide", wide), ("narrow", narrow)):
        sub = result.subscores.get("ONP")
        assert sub is not None and sub.applicable and sub.coverage, (
            f"precondition: the {label} run wrote no `onp.subscore` row, so "
            "this series has nothing to compare")

    trend = runs_repo.site_trend(conn, site_id, "onp.subscore")
    assert len(trend) == 2, f"expected one ONP point per run, got {len(trend)}"
    assert trend[1]["comparable"] is True, (
        "ONP's own subscore was marked incomparable because the run beside it "
        "measured different *other* dimensions — a false alarm on a series "
        "whose value the dimension set does not enter")
    conn.close()


def test_every_stored_trend_point_carries_the_dimension_set_it_measured(tmp_path):
    """The frame half: the term has to be *stored*, not derived at read time.

    `metric_snapshots` has no dimensions column and `site_trend` joins nothing,
    so the only place the set can come from is the frame `_snapshot_metrics`
    writes. Watched failing against unmodified HEAD: every frame held
    `basis` alone and no row anywhere carried the population.

    The population is derived from the rows the run actually wrote rather than
    from a literal list of metric keys, so a metric added to `_snapshot_metrics`
    is covered here on the day it is added.
    """
    conn, site_id = _site(tmp_path)
    result = _audit(conn, site_id, DIMS)
    measured = sorted(d for d, s in result.subscores.items()
                      if s.applicable and s.coverage)
    assert measured, "precondition: the fixture measured no dimension at all"

    rows = conn.execute(
        "SELECT metric_key, scope FROM metric_snapshots WHERE site_id=?",
        (site_id,)).fetchall()
    assert rows, "precondition: the run stored no trend point, so this asserts nothing"

    frameless = []
    for row in rows:
        frame = json.loads(row["scope"]) if row["scope"] else {}
        if frame.get("dimensions") != measured:
            frameless.append(f"{row['metric_key']}: {frame.get('dimensions')!r}")
    assert not frameless, (
        f"{len(frameless)} of {len(rows)} stored points do not say which "
        f"dimensions they were measured over (expected {measured}):\n  "
        + "\n  ".join(frameless))
    conn.close()


def test_the_two_kinds_of_metric_key_are_both_present_in_a_real_run(tmp_path):
    """The population guard for the scoping rule itself.

    `site_trend` decides whether the dimension term belongs in the key by
    asking `is_per_dimension_metric`. A predicate that answered one way for
    every key the product writes would make the two counter-assertions above
    vacuous without either of them going red — so the split is checked against
    the keys a real completed run stores, derived from the database rather
    than from a list written here.
    """
    conn, site_id = _site(tmp_path)
    _audit(conn, site_id, DIMS)

    keys = {r["metric_key"] for r in conn.execute(
        "SELECT DISTINCT metric_key FROM metric_snapshots WHERE site_id=?",
        (site_id,))}
    assert keys, "precondition: the run stored no metric keys to classify"

    per_dimension = {k for k in keys if runs_repo.is_per_dimension_metric(k)}
    site_level = keys - per_dimension
    assert per_dimension and site_level, (
        "the predicate puts every key the product writes on one side, so the "
        f"scoping rule is untested by construction: keys={sorted(keys)}, "
        f"per_dimension={sorted(per_dimension)}")
    assert "composite_score" in site_level and "measured_share" in site_level, (
        f"the two aggregates over the dimension set are not site-level: "
        f"{sorted(site_level)}")
    conn.close()


def test_a_point_stored_before_the_term_existed_reads_unknown(tmp_path):
    """A point with no recorded set is not comparable with one that has one.

    The assertion is unchanged and is still the right one. What changed under
    it is the fixture, and the claim this docstring used to make.

    It used to say a backfill would invent a population nobody recorded, and
    that stripping the frame's term was therefore enough to produce an unknown
    population. Both are false, and report 098 named this docstring as one of
    three statements in the tree carrying the error. `_snapshot_metrics`
    writes one `{dim}.subscore` row per measured dimension at the same
    `captured_at`, so a frame with no term still has its set written down
    beside it, and `site_trend` recovers it there — see
    `test_a_trend_point_recovers_the_dimension_set_it_recorded.py`, and the
    operator's own history, where every stored point was in exactly that state
    and every pair was asserted comparable across a real dimension change.

    So the unknown case now needs the rows removed as well as the term, and
    that is the only case that is genuinely unknown: a point with nothing
    anywhere that recorded its population.
    """
    conn, site_id = _site(tmp_path)
    _audit(conn, site_id, DIMS)
    _audit(conn, site_id, DIMS)

    # Strip the term from the first point only, which is what a pre-change row
    # looks like from the read side.
    first = conn.execute(
        "SELECT id, scope, captured_at FROM metric_snapshots WHERE site_id=?"
        " AND metric_key='composite_score' ORDER BY captured_at, rowid",
        (site_id,)).fetchone()
    legacy = json.loads(first["scope"])
    assert "dimensions" in legacy, (
        "precondition: the fixture stored no dimension term, so removing it "
        "changes nothing")
    legacy.pop("dimensions")
    with conn:
        conn.execute("UPDATE metric_snapshots SET scope=? WHERE id=?",
                     (json.dumps(legacy), first["id"]))
        # And the rows the set is recoverable from, or this point is not
        # unknown at all — it is derived, and the assertion below would be
        # testing the recovery rather than the unknown rung.
        removed = conn.execute(
            "DELETE FROM metric_snapshots WHERE site_id=? AND captured_at=?"
            " AND metric_key LIKE '%.subscore'",
            (site_id, first["captured_at"])).rowcount
    assert removed, (
        "precondition: the point had no per-dimension rows to remove, so it "
        "was already unknown for a reason this fixture did not create")

    trend = runs_repo.site_trend(conn, site_id)
    assert trend[1]["comparable"] is False, (
        "a point that never recorded its population was called comparable with "
        "one that did — the unknown was read as a match rather than as an "
        "unknown")
    conn.close()
