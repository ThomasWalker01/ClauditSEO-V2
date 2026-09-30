"""Coverage: a dimension must not be scored on ground it never looked at.

The defect these guard against was quiet and one-directional. With no
provider keys, Performance and Off-page both returned 100/100 — a quarter of
the composite awarded for not having looked — and the fewer keys an operator
configured, the better the site scored.
"""

from __future__ import annotations

import json

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine import scoring
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, SubScore, Tier
from clauditseo.modules.ofp import SIGNALS, OffPageModule
from clauditseo.providers.base import BacklinkSnapshot, ProviderHub, SourcedValue

DIMS = ["TEC", "ONP", "A11Y", "PRF", "CNT", "OFP", "LOC", "AIS"]


#: 133 characters, 828px at Arial 14 — inside both the old character window
#: and the new pixel one, so the fixture says the same thing under either.
DESCRIPTION = ("Solar panels and battery storage for homes and businesses "
               "across regional Victoria, installed by an accredited local "
               "team since 2009.")


def _crawl() -> CrawlResult:
    page = Page(
        url="https://x.test/", requested_url="https://x.test/", status=200,
        content_type="text/html",
        content="<html lang=en><head><title>A reasonable title for the page</title>"
                # Real prose, not 140 identical 'x'. Since brief v16i the
                # length check measures PIXELS, and `x` is a wide glyph: 140
                # of them is 980px and over the 920px window, where the same
                # count of ordinary English is about 830. The fixture means
                # "a description inside the window", so it has to be a string
                # a real page could carry.
                f"<meta name=description content='{DESCRIPTION}'></head><body><main>"
                f"<h1>Hi</h1><p>{'word ' * 400}</p></main></body></html>",
        headers={"cache-control": "max-age=3600"}, elapsed_ms=120)
    return CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[page])


class _Hub(ProviderHub):
    """Subclasses the real hub rather than re-declaring its surface, so a
    method added to the contract arrives here instead of failing as a missing
    attribute. A double that has to be edited every time the thing it stands
    in for grows is a double that will eventually stand in for something
    else."""

    def __init__(self, snap=None, cwv=None):
        super().__init__()
        self._snap, self._cwv = snap, cwv

    def backlink_snapshot(self, domain):  # noqa: ARG002
        return self._snap

    def cwv_metrics(self, url):  # noqa: ARG002
        return self._cwv


OPR_ONLY = BacklinkSnapshot(
    domain="x.test", sources=["openpagerank"],
    domain_authority=SourcedValue(value=42.0, source="openpagerank",
                                  confidence="low"))
MOZ = BacklinkSnapshot(
    domain="x.test", sources=["moz"],
    referring_domains=SourcedValue(value=250, source="moz", confidence="high"),
    anchors={"brand": 120, "home": 60, "services": 70})


def _run(hub):
    return run_audit(Site(domain="https://x.test/"), _crawl(), DIMS, Tier.T2,
                     context={"providers": hub})


# --- the composite ---------------------------------------------------------

def test_unmeasured_offpage_carries_no_weight():
    """Not "scores badly" — carries nothing. A dimension with no data has no
    opinion, and the weight belongs to the dimensions that did measure."""
    ofp = _run(_Hub()).subscores["OFP"]
    assert ofp.coverage == 0.0
    assert ofp.weight == 0.0


def test_partly_measured_performance_carries_partial_weight():
    """Crawl-derived timing signals still stand without a key, so PRF does not
    drop out — it carries the share it actually covered."""
    prf = _run(_Hub()).subscores["PRF"]
    assert 0.0 < prf.coverage < 1.0
    full = _run(_Hub(cwv={"lcp_ms": SourcedValue(value=1800, source="crux",
                                                 confidence="high")}))
    assert prf.weight < full.subscores["PRF"].weight
    assert full.subscores["PRF"].coverage == 1.0


def test_weights_still_sum_to_one():
    """Redistribution, not deletion: the composite stays a weighted mean."""
    for hub in (_Hub(), _Hub(snap=MOZ)):
        total = sum(s.weight for s in _run(hub).subscores.values())
        assert abs(total - 1.0) < 1e-9


def test_measured_share_reports_what_was_covered():
    assert scoring.measured_share(_run(_Hub()).subscores) < 1.0
    assert scoring.measured_share(_run(_Hub(
        snap=MOZ,
        cwv={"lcp_ms": SourcedValue(value=1800, source="crux",
                                    confidence="high")})).subscores) == 1.0


def test_measured_share_counts_the_pages_it_never_fetched():
    """The number exists to say how much of the intended audit was covered,
    and it was blind to the largest gap there is. A real T2 audit with the
    page cap lowered fetched 6 of the 272 URLs the sitemap declares and
    reported 0.796 — a figure that described the provider signals it was
    missing while saying nothing about the 98% of the site it never opened."""
    subs = {"ONP": SubScore(dimension="ONP", score=83.0, weight=0.276,
                            coverage=1.0, detail={"nominal_weight": 0.22}),
            "CNT": SubScore(dimension="CNT", score=100.0, weight=0.201,
                            coverage=1.0, detail={"nominal_weight": 0.16})}
    scope = {"pages_fetched": 6, "discovered": 272}

    blind = scoring.measured_share(subs)
    assert blind == 1.0, "every dimension claims full coverage on 6 of 272 pages"

    aware = scoring.measured_share(subs, scope)
    assert aware < blind
    assert aware == round(6 / 272, 4), aware


def test_measured_share_says_nothing_new_without_a_declared_total():
    """Same rule as the scope line: a crawl with no sitemap has no total, so
    there is no ratio to apply and the figure is what it always was."""
    subs = {"ONP": SubScore(dimension="ONP", score=83.0, weight=0.276,
                            coverage=1.0, detail={"nominal_weight": 0.22})}
    for scope in ({"pages_fetched": 6, "discovered": None},
                  {"pages_fetched": 6, "discovered": 0},
                  None):
        assert scoring.measured_share(subs, scope) == scoring.measured_share(subs)


def test_a_full_crawl_is_not_penalised():
    """Fetching everything declared is complete breadth, not 100% of a cap."""
    subs = {"ONP": SubScore(dimension="ONP", score=83.0, weight=0.276,
                            coverage=1.0, detail={"nominal_weight": 0.22})}
    assert scoring.measured_share(subs, {"pages_fetched": 12, "discovered": 12}) == 1.0
    # More fetched than the sitemap declares — link-following found pages the
    # sitemap omits, which is a finding about the sitemap, not over-coverage.
    assert scoring.measured_share(subs, {"pages_fetched": 20, "discovered": 12}) == 1.0


def test_runs_stored_before_coverage_existed_report_full():
    """A historical row has neither field. It is read at its face value rather
    than retroactively marked down — the same guarantee that let A11Y be added
    without moving any score already in the database."""
    old = {"ONP": SubScore(dimension="ONP", score=90.0, weight=0.5,
                           detail={"nominal_weight": 0.22})}
    assert scoring.measured_share(old) == 1.0


# --- per-signal honesty ----------------------------------------------------

def test_free_provider_does_not_silence_the_not_assessed_note():
    """The regression that prompted this: OpenPageRank returns a snapshot
    carrying only domain authority, which no check consumes. Treating "a
    provider answered" as "the dimension was measured" made configuring the
    free key *less* honest than configuring nothing."""
    findings = OffPageModule().run(
        [], Tier.T2, {"site": Site(domain="https://x.test/"),
                      "providers": _Hub(snap=OPR_ONLY)})
    ids = {f.check_id for f in findings}
    assert "backlinks-not-assessed" in ids
    note = next(f for f in findings if f.check_id == "backlinks-not-assessed")
    assert set(note.evidence["unmeasured"]) == set(SIGNALS)
    assert "openpagerank" in note.summary


def test_free_provider_buys_no_coverage():
    """Same measured ground as no key at all, so the same composite."""
    assert _run(_Hub()).composite_score == _run(_Hub(snap=OPR_ONLY)).composite_score


def test_domain_authority_is_reported_but_scores_nothing():
    """An operator paid for the number, so show it — labelled as a proxy that
    drives no check, rather than left to look like it was scored."""
    findings = OffPageModule().run(
        [], Tier.T2, {"site": Site(domain="https://x.test/"),
                      "providers": _Hub(snap=OPR_ONLY)})
    da = next(f for f in findings if f.check_id == "domain-authority-reported")
    assert da.severity.value == "info"
    assert scoring.CHECK_CEILING[da.severity] == 0.0


def test_a_provider_that_supplies_the_signals_reaches_full_coverage():
    ofp = _run(_Hub(snap=MOZ)).subscores["OFP"]
    assert ofp.coverage == 1.0
    assert ofp.unmeasured == ()


# --- what reaches the trend table ------------------------------------------

def _stored_run(tmp_path, hub):
    """One audit completed into a real database, so what `_snapshot_metrics`
    writes can be read back rather than inferred."""
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs

    conn = connect(tmp_path / "snapshots.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Snapshot Co")
    site_id = repo.create_site(conn, client, "x.test")
    result = _run(hub)
    run_id = runs.create_run(conn, site_id, DIMS, "T2")
    runs.complete_run(conn, run_id, result)
    return conn, site_id, result


def test_a_dimension_that_measured_nothing_writes_no_trend_point(tmp_path):
    """`applicable` says the dimension was in scope; `coverage` says whether
    any of it was obtained. The loop filtered on the first, so an ordinary
    keyless run wrote `ofp.subscore = 100.0` at `confidence: high` for a
    dimension that read no backlink data at all — a perfect score on zero
    evidence, at the highest confidence the product can state, into the table
    the trend chart and the analyst prompt both read."""
    conn, site_id, result = _stored_run(tmp_path, _Hub())
    assert result.subscores["OFP"].coverage == 0.0, "fixture must have a dark OFP"

    rows = {r["metric_key"]: r["value"] for r in conn.execute(
        "SELECT metric_key, value FROM metric_snapshots WHERE site_id=?", (site_id,))}
    assert "ofp.subscore" not in rows, (
        f"a dimension with coverage 0.0 wrote {rows.get('ofp.subscore')} to the trend")
    # The dimensions that did measure still record theirs.
    assert "onp.subscore" in rows and "composite_score" in rows
    conn.close()


def test_the_trend_records_how_much_of_the_audit_was_covered(tmp_path):
    """`measured_share` existed for two rounds with no caller, so a T1 pulse
    and a full T3 entered a site's history indistinguishable. Stored beside
    the composite, at the moment both are known."""
    conn, site_id, result = _stored_run(tmp_path, _Hub())
    rows = {r["metric_key"]: r["value"] for r in conn.execute(
        "SELECT metric_key, value FROM metric_snapshots WHERE site_id=?", (site_id,))}

    assert "measured_share" in rows, "the composite is stored with no coverage beside it"
    assert 0.0 < rows["measured_share"] < 1.0, rows["measured_share"]
    assert rows["measured_share"] == scoring.measured_share(result.subscores)
    conn.close()


def test_a_fully_measured_run_records_a_full_share(tmp_path):
    """The control: the row is about coverage, not a penalty every run pays."""
    conn, site_id, _ = _stored_run(tmp_path, _Hub(
        snap=MOZ, cwv={"lcp_ms": SourcedValue(value=1800, source="crux",
                                              confidence="high")}))
    rows = {r["metric_key"]: r["value"] for r in conn.execute(
        "SELECT metric_key, value FROM metric_snapshots WHERE site_id=?", (site_id,))}
    assert rows["measured_share"] == 1.0
    assert "ofp.subscore" in rows, "a measured dimension still records its point"
    conn.close()


def test_a_stored_share_records_the_scope_it_was_computed_under(tmp_path):
    """One key held two incompatible quantities, both at `confidence: high`.

    `measured_share` returns dimension coverage alone when the site declared
    no total, and coverage scaled by crawl breadth when it did. Five rows for
    one site stood at 0.2879 (T2), 0.0487 (T1), 0.9362 (T2), 0.6765 (T3) and
    0.783 (T3) — two of them sharing a tier and not describing the same
    quantity, in a table with no column that could say so. The operator's
    answer, recorded in `audits/DISPOSITIONS.md`: one key, with the scope it
    was computed under stored alongside the value.
    """
    conn, site_id, _ = _stored_run(tmp_path, _Hub())
    row = conn.execute(
        "SELECT scope FROM metric_snapshots WHERE site_id=? AND metric_key='measured_share'",
        (site_id,)).fetchone()
    assert row["scope"], "the share is stored with nothing saying what it means"
    assert json.loads(row["scope"])["basis"] == "coverage", (
        "no evidence was stored, so no declared total was available and breadth "
        "cannot have been applied")
    conn.close()


def test_a_breadth_scaled_share_is_not_comparable_with_a_coverage_only_one(tmp_path):
    """The read path is where the two quantities were indistinguishable.

    `site_trend` already refuses to call two points comparable across an
    engine change, for the same reason and by the same mechanism. A share
    computed against a declared site total and one computed without one are
    not the same measurement, and one engine version does not make them one.
    """
    from clauditseo.persistence import runs as runs_repo

    conn, site_id, _ = _stored_run(tmp_path, _Hub())
    # A second run on the same site, this one with a crawl that knows the
    # site's declared size — so `measured_share` scales by breadth.
    result = _run(_Hub())
    run_id = runs_repo.create_run(conn, site_id, DIMS, "T2")
    runs_repo.store_evidence(conn, run_id, {
        "stats": {"eligible": 6, "fetched": 6, "blocked_by_robots": 0},
        "sitemap_entry_total": 272, "pages": [], "robots_blocked": []})
    runs_repo.complete_run(conn, run_id, result)

    trend = runs_repo.site_trend(conn, site_id, "measured_share")
    assert len(trend) == 2, f"expected two stored shares, got {len(trend)}"
    assert trend[0]["scope"]["basis"] == "coverage"
    assert trend[1]["scope"]["basis"] == "coverage+breadth"
    assert trend[1]["value"] < trend[0]["value"], (
        "6 of 272 declared pages must scale the figure down")
    assert trend[0]["comparable"] is True, "the first point has nothing before it"
    assert trend[1]["comparable"] is False, (
        "a breadth-scaled share and a coverage-only one are not one series")
    conn.close()


def test_every_stored_trend_point_records_the_scope_it_was_computed_under(tmp_path):
    """The frame clause was applied at one of the three writes in
    `_snapshot_metrics`, and the reader's key was built as though all three
    carried it.

    `site_trend` keyed comparability then on `(engine_version, scope.basis,
    tier)` — `scope.dimensions` joined them at WF-58, round 097 — and
    `components.tsx` renders the basis term as its own "Share basis"
    column. Only the `measured_share` INSERT names `scope`; the
    `composite_score` INSERT beside it and the per-dimension `<dim>.subscore`
    INSERT below it do not — so on the composite, which is the only series
    the trend table draws, a third of the comparability key is NULL on every
    row that has ever been written and the column reads `unknown` forever.
    That is CQ-96 and CQ-94, and it is the promoted frame invariant: a
    number's frame travels with the value.

    **Derived from the rows written, not from a list of metric keys.** A
    hard-coded list is how the previous guard could assert the property for
    `measured_share` and be silent about the two writes beside it — the
    defect this test exists for. A fourth metric key is covered on the day it
    is added.

    **The live database cannot answer this and was not asked.** Every one of
    the thirteen rows in `data/clauditseo.db` predates `d59b14a`, the commit
    that first wrote `scope` at all; the newest is `2026-08-17T13:57:33` and
    no run has completed since. So `scope IS NULL` there on every key
    including `measured_share`, for a reason that has nothing to do with this
    finding. The evidence has to be a run completed here.
    """
    from clauditseo.persistence import runs as runs_repo

    conn, site_id, _ = _stored_run(tmp_path, _Hub())
    # A run that stored its crawl evidence, so the scope dict is non-empty
    # and a bare `{"basis": ...}` cannot pass for carrying the frame.
    result = _run(_Hub())
    run_id = runs_repo.create_run(conn, site_id, DIMS, "T2")
    runs_repo.store_evidence(conn, run_id, {
        "stats": {"eligible": 6, "fetched": 6, "blocked_by_robots": 0},
        "sitemap_entry_total": 272, "pages": [], "robots_blocked": []})
    runs_repo.complete_run(conn, run_id, result)

    rows = conn.execute(
        "SELECT metric_key, captured_at, scope FROM metric_snapshots"
        " WHERE site_id=? ORDER BY captured_at, metric_key", (site_id,)).fetchall()
    assert rows, "the fixture stored no trend points, so this asserts nothing"

    frameless = [f"{r['metric_key']} @ {r['captured_at']}"
                 for r in rows if not r["scope"]]
    assert not frameless, (
        "a trend point stored with no frame — `site_trend` reads "
        "`scope.basis` as a third of its comparability key, so these points "
        "are asserted comparable with anything sharing their tier and "
        "engine version:\n  " + "\n  ".join(frameless))

    # The frame is the whole scope, not a bare basis label — otherwise a
    # point could carry `{"basis": "coverage"}` and still not say what
    # population it was computed over.
    #
    # **The dead end this replaces, recorded because it went red in the file
    # run and green on its own.** The first version grouped rows by
    # `rows[-1]["captured_at"]` and asserted that group's bases were exactly
    # `{"coverage+breadth"}`. `metric_snapshots` has no run column — the
    # stamp *is* the run key, which is why `delete_run` deletes by it — and
    # `now_iso()` is second-resolution. Run alone the two `complete_run`
    # calls straddle a second boundary and the group is one run; run inside
    # the file they land in the same second and the group is both runs, so
    # the set is `{"coverage", "coverage+breadth"}`. Asserting on the frames
    # present rather than on a timestamp slice tests more and does not
    # depend on how fast the machine is.
    frames = {r["scope"] for r in rows}
    bases = {json.loads(f)["basis"] for f in frames}
    assert bases == {"coverage", "coverage+breadth"}, (
        f"the two runs did not record two different bases: {bases}")
    breadth = json.loads(next(f for f in frames
                              if json.loads(f)["basis"] == "coverage+breadth"))
    assert breadth["discovered"] == 272 and breadth["pages_fetched"] == 6, (
        f"the frame names a basis without the counts it was derived from: {breadth}")
    conn.close()
