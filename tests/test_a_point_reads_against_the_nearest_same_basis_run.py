"""A trend point reads against the nearest earlier run measured the same way.

Brief v16f, part A. Until this change a point "read against the point before"
and nothing else: `site_trend` compared each point's frame with its immediate
predecessor's, so a single run at a different tier - one click from the
anatomy screen - broke the line for every point after it, and two runs that
were identical on every axis were called non-comparable because something
unlike them happened in between.

The operator's own history is the case. Nine scored site-wide runs of
`www.acme.com.au` between 2026-08-15 and 2026-09-02 produced a chart with
**eight breaks in eight steps** - no pair on it read against any other - while
`2026-09-02 02:22` and `2026-09-02 02:37` were the same tier, the same engine,
the same share basis and the same measured dimension set. The only thing
between them was `02:26`, a T2 run. The rule this file guards is: a point's
partner is the nearest **earlier** point with the same basis key, and runs
between them that changed something do not break the pair.

**The basis key is `(tier, engine, share basis, sorted measured dimensions)`** -
the same four terms `comparable` already keyed on, named and exposed rather
than recomputed by each screen. `comparable` itself is untouched and still
answers the adjacent-step question, because that is the question the chart's
break rules ask: *this step* is where something changed. The two facts are
different and both are drawn.

## Where the fixture's numbers come from, and the one thing reconstructed

Every stamp, score, tier, engine version and share basis below is Acme's,
read off the Score trend table the operator approved the mockup from
(`_relay/attachments/brief-v16f/score_trend_visual_mockup.html`). The live
database no longer holds them - that site's history was rebuilt on 2026-09-06
and stands at one scored run - so they are planted here rather than read, and
this file is where they now survive.

**The measured dimension sets are reconstructed, and deliberately not copied
from the mockup's `dims` column.** That column and the mockup's own `why`
column contradict each other: `dims` lists the same eight codes for the first
two points while `why` records `dimensions added: OFP` between them, and the
same disagreement recurs at four more steps. `why` is the product's own
`frameMoved` output over the stored frames, so it is the record of the
*measured* sets; `dims` is the requested list a run stores on its row. The
sets below are what the `why` chain says they were, and the chain closes: it
reproduces all four figures the brief states independently - 02:37 partners
02:22, eight break rules over eight steps, two points in the current-basis
band, and 02:26 outside it.

**Five of the nine record no dimension set of their own**, which is Acme's
real shape (the trend's own note said "5 of 9"): they predate the frame term
WF-58 added, and `site_trend` recovers their population from the
`{dim}.subscore` rows written beside them. The recovery stays; what is new is
that the point says so in one field a renderer can draw a ring from, rather
than only inside its frame.
"""

from __future__ import annotations

import json

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs as runs_repo

#: Acme's nine scored site-wide runs. `dims` is the MEASURED set, derived as
#: the docstring explains; `recorded` says whether the run wrote it on its own
#: frame or leaves it to be recovered from the sibling subscore rows.
BASE = ["A11Y", "AIS", "CNT", "ONP", "PRF", "TEC"]
NINE: list[dict] = [
    {"at": "2026-08-15T03:55:10+00:00", "score": 89.9, "tier": "T2",
     "engine": "0.7.0", "basis": None, "dims": BASE, "recorded": False},
    {"at": "2026-08-15T06:01:36+00:00", "score": 94.2, "tier": "T2",
     "engine": "0.7.0", "basis": None, "dims": BASE + ["OFP"], "recorded": False},
    {"at": "2026-08-17T00:01:04+00:00", "score": 91.1, "tier": "T2",
     "engine": "0.8.0", "basis": None,
     "dims": [d for d in BASE if d != "A11Y"] + ["OFP"], "recorded": False},
    {"at": "2026-08-17T03:55:22+00:00", "score": 70.5, "tier": "T3",
     "engine": "0.8.0", "basis": None, "dims": BASE, "recorded": False},
    {"at": "2026-08-23T11:27:41+00:00", "score": 72.0, "tier": "T3",
     "engine": "0.9.0", "basis": "coverage+breadth", "dims": BASE + ["LOC"],
     "recorded": False},
    {"at": "2026-09-01T04:58:03+00:00", "score": 91.0, "tier": "T3",
     "engine": "0.10.0", "basis": "coverage+breadth", "dims": BASE + ["LOC"],
     "recorded": True},
    {"at": "2026-09-02T02:22:15+00:00", "score": 94.2, "tier": "T1",
     "engine": "0.10.0", "basis": "coverage+breadth", "dims": BASE + ["LOC"],
     "recorded": True},
    {"at": "2026-09-02T02:26:48+00:00", "score": 94.0, "tier": "T2",
     "engine": "0.10.0", "basis": "coverage+breadth",
     "dims": BASE + ["LOC", "OFP"], "recorded": True},
    {"at": "2026-09-02T02:37:09+00:00", "score": 94.2, "tier": "T1",
     "engine": "0.10.0", "basis": "coverage+breadth", "dims": BASE + ["LOC"],
     "recorded": True},
]

#: The four figures the brief states, kept beside the fixture rather than
#: inside one assertion each: a fixture edited without them re-checked is the
#: shape DISCIPLINE rule 4 refuses.
LATEST = 8             # 2026-09-02 02:37
PARTNER_OF_LATEST = 6  # 2026-09-02 02:22, across 02:26
IN_THE_BAND = [6, 8]
BREAKS = 8             # one per step, all eight steps


def _site(tmp_path):
    conn = connect(tmp_path / "trend.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Acme")
    return conn, repo.create_site(conn, client, "www.acme.com.au")


def _plant(conn, site_id: str, point: dict, *, kind: str = "audit",
           scan_scope: str = "full", status: str = "complete") -> str:
    """One scored run and the snapshots it wrote, at a stamp of our choosing.

    Planted rather than audited. `run_audit` cannot be made to produce a
    composite of 89.9 at engine 0.7.0 in 2026, and the question here is not
    what the engine scores - `test_scoring_normalisation.py` asks that - but
    what the read path does with nine rows that already exist. The writer's
    own shape is copied exactly: one `composite_score` row and one
    `{dim}.subscore` row per measured dimension, at one `captured_at`, with
    the frame `_snapshot_metrics` builds.

    A run that is not a site-wide completed audit writes no snapshots at all,
    which is `complete_run`'s own gate rather than a second opinion about it.

    **`recorded` decides two things at once, and that is Acme's shape rather
    than a convenience.** The five points that predate WF-58's frame term also
    predate migration 0044's `run_id` column - they are the same five rows,
    written by the same older engine - so they are planted with neither, and
    the read path has to recover the population from their sibling rows and
    the run from their stamp. The four newer ones carry both, as the writer
    now writes them. Both rungs are exercised by one fixture because the live
    corpus holds both.
    """
    run_id = runs_repo.create_run(conn, site_id, point["dims"], point["tier"],
                                  kind=kind, scan_scope=scan_scope)
    with conn:
        conn.execute(
            "UPDATE audit_runs SET status=?, engine_version=?, composite_score=?,"
            " started_at=?, finished_at=?, scan_scope=? WHERE id=?",
            (status, point["engine"], point["score"], point["at"], point["at"],
             scan_scope, run_id))
        frame: dict = {"basis": point["basis"]}
        if point["recorded"]:
            frame["dimensions"] = sorted(point["dims"])
        blob = json.dumps(frame)
        stored_run = run_id if point["recorded"] else None
        if status == "complete" and scan_scope == "full" and kind == "audit":
            conn.execute(
                "INSERT INTO metric_snapshots (id, site_id, metric_key, value, source,"
                " confidence, captured_at, tier, engine_version, scope, run_id)"
                " VALUES (?, ?, 'composite_score', ?, 'engine', 'high', ?, ?, ?, ?, ?)",
                (repo.create_id(), site_id, point["score"], point["at"],
                 point["tier"], point["engine"], blob, stored_run))
            for dim in point["dims"]:
                conn.execute(
                    "INSERT INTO metric_snapshots (id, site_id, metric_key, value,"
                    " source, confidence, captured_at, tier, engine_version, scope,"
                    " run_id)"
                    " VALUES (?, ?, ?, ?, 'engine', 'high', ?, ?, ?, ?, ?)",
                    (repo.create_id(), site_id, f"{dim.lower()}.subscore", 80.0,
                     point["at"], point["tier"], point["engine"], blob, stored_run))
    return run_id


def _acme(tmp_path):
    conn, site_id = _site(tmp_path)
    ids = [_plant(conn, site_id, p) for p in NINE]
    return conn, site_id, ids


def _at(trend, i):
    return trend[i]["captured_at"]


def test_a_point_reads_against_the_nearest_same_basis_run(tmp_path):
    """The headline case, in the operator's own numbers.

    Watched failing against unmodified HEAD: `partner_run_id` did not exist,
    so the read path had no answer to give and every screen fell back to "the
    row above". The assertion names the two stamps rather than the indices so
    a failure reads as the history it is about.
    """
    conn, site_id, ids = _acme(tmp_path)
    trend = runs_repo.site_trend(conn, site_id)
    assert len(trend) == 9, f"expected Acme's nine points, got {len(trend)}"
    latest = trend[LATEST]
    assert latest["partner_run_id"] == ids[PARTNER_OF_LATEST], (
        f"{_at(trend, LATEST)} reads against "
        f"{latest['partner_run_id']!r}; the nearest earlier run on its own "
        f"basis is {_at(trend, PARTNER_OF_LATEST)} "
        f"({ids[PARTNER_OF_LATEST]}), and the run between them "
        f"({_at(trend, LATEST - 1)}) is a different tier")
    assert latest["partner_run_id"] != ids[LATEST - 1], (
        "the latest point still reads against the row above it")
    conn.close()


def test_runs_between_do_not_break_a_pair(tmp_path):
    """The rule stated as its own assertion, not inferred from the case above.

    The pair is what survives; the run between is what used to destroy it.
    Asserted on the key rather than on the partner alone, so a partner found
    by position rather than by basis would not satisfy it.
    """
    conn, site_id, ids = _acme(tmp_path)
    trend = runs_repo.site_trend(conn, site_id)
    a, between, b = trend[6], trend[7], trend[8]
    assert a["basis_key"] == b["basis_key"], (
        "the fixture's two 02:22/02:37 points do not share a basis key, so "
        f"there is no pair to preserve: {a['basis_key']!r} vs {b['basis_key']!r}")
    assert between["basis_key"] != a["basis_key"], (
        "the run between them measures the same way, so nothing is being "
        "reached across and this asserts nothing")
    assert b["partner_index"] == 6, (
        f"the pair was broken by the run between them: {_at(trend, 8)} reads "
        f"against index {b['partner_index']}")
    # And the run between keeps its own honest answer: nothing earlier
    # measured the way it did.
    assert between["partner_run_id"] is None, (
        f"{_at(trend, 7)} was given a partner it does not have: "
        f"{between['partner_run_id']!r}")
    assert ids[6] == a["run_id"] and ids[8] == b["run_id"], (
        "a point does not carry the id of the run that made it, so no screen "
        "can link the pair")
    conn.close()


def test_no_partner_when_no_earlier_run_shares_the_key(tmp_path):
    """Eight of Acme's nine points have no partner at all, and must say so.

    The failure mode this refuses is the tempting one: a "nearest" search that
    falls back to the previous point when nothing matches. That would restore
    exactly the defect, and would do it silently.
    """
    conn, site_id, _ = _acme(tmp_path)
    trend = runs_repo.site_trend(conn, site_id)
    partnered = [i for i, p in enumerate(trend) if p["partner_run_id"] is not None]
    assert partnered == [LATEST], (
        "only 2026-09-02 02:37 has an earlier run on its own basis; points "
        f"{partnered} were given one")
    assert trend[0]["partner_index"] is None, "the first point has nothing before it"
    conn.close()


def test_narrow_and_blocked_runs_are_neither_points_nor_partners(tmp_path):
    """The exclusion, which is the writer's and stays the writer's.

    Green on both trees, and written down for the reason WF-58's counter-
    assertions are: a partner search widened to "the nearest earlier run" -
    rather than the nearest earlier *point* - would pair a site's composite
    with an eight-page verification, which is the pairing WF-60 was measured
    on. This is the assertion that would catch it.
    """
    conn, site_id, ids = _acme(tmp_path)
    # Both planted between 02:22 and 02:37, where a partner search that
    # ignored the exclusion would find them first.
    _plant(conn, site_id, {**NINE[LATEST], "at": "2026-09-02T02:30:00+00:00"},
           kind="verify", scan_scope="page")
    _plant(conn, site_id, {**NINE[LATEST], "at": "2026-09-02T02:33:00+00:00"},
           status="blocked")
    trend = runs_repo.site_trend(conn, site_id)
    assert len(trend) == 9, (
        f"a narrow or blocked run became a trend point: {len(trend)} points")
    assert trend[LATEST]["partner_run_id"] == ids[PARTNER_OF_LATEST], (
        "the latest point was paired with a run that is not a point")
    conn.close()


def test_a_recovered_dimension_set_is_marked_on_the_point(tmp_path):
    """Five of nine, and the point says which five.

    `scope.dimensions_basis` already carried the rung; nothing outside the
    frame could be drawn from it without a screen deciding what `derived`
    means. `basis_recovered` is that decision made once, by the reader that
    performed the recovery.
    """
    conn, site_id, _ = _acme(tmp_path)
    trend = runs_repo.site_trend(conn, site_id)
    recovered = [i for i, p in enumerate(trend) if p["basis_recovered"]]
    assert recovered == [0, 1, 2, 3, 4], (
        f"the recovered points are {recovered}; Acme's first five predate "
        "the frame term and have their population read back off the "
        "per-dimension rows stored beside them")
    for i in recovered:
        assert (trend[i]["scope"] or {}).get("dimensions_basis") == "derived", (
            f"point {i} is marked recovered but its frame does not say so")
        assert trend[i]["basis_key"], (
            f"point {i} was recovered and still has no basis key, so the "
            "recovery bought nothing")
    conn.close()


def test_the_break_rules_fall_where_the_key_changes(tmp_path):
    """Eight steps, eight breaks - and this is the fact `comparable` keeps.

    The chart draws two different relations and they are not the same
    question. `comparable` is the adjacent step: *here* something changed.
    The partner is the pair: *this* is what it reads against. Acme has eight
    of the first and one of the second, and a change that collapsed the two
    would draw either no rules or no lines.
    """
    conn, site_id, _ = _acme(tmp_path)
    trend = runs_repo.site_trend(conn, site_id)
    steps = [i for i in range(1, len(trend)) if not trend[i]["comparable"]]
    assert len(steps) == BREAKS and steps == list(range(1, 9)), (
        f"expected a break at every one of Acme's eight steps, got {steps}")
    changed = [i for i in range(1, len(trend))
               if trend[i]["basis_key"] != trend[i - 1]["basis_key"]]
    assert changed == steps, (
        "the break flag and the basis key disagree about where the frame "
        f"moved: flag {steps}, key {changed}")
    conn.close()


def test_the_current_basis_band_covers_only_matching_points(tmp_path):
    """Which points are directly comparable to the latest - 02:22 and 02:37.

    Read off `basis_key` rather than from a second rule, which is the whole
    reason the key is on the payload: the band, the line and the sentence are
    three drawings of one fact.
    """
    conn, site_id, _ = _acme(tmp_path)
    trend = runs_repo.site_trend(conn, site_id)
    latest = trend[LATEST]["basis_key"]
    inside = [i for i, p in enumerate(trend) if p["basis_key"] == latest]
    assert inside == IN_THE_BAND, (
        f"the current basis covers points {inside}; on Acme it is 02:22 and "
        "02:37, and 02:26 between them is a T2 run")
    conn.close()


def test_the_basis_key_names_all_four_terms(tmp_path):
    """One key, and it moves when any of the four moves.

    Written as four one-term perturbations of one point rather than as a
    string comparison, so the guard cannot be satisfied by a key that happens
    to be unique per point - an id would pass that.
    """
    conn, site_id = _site(tmp_path)
    base = NINE[LATEST]
    _plant(conn, site_id, {**base, "at": "2026-09-03T00:00:00+00:00"})
    moved = [
        ("tier", {"tier": "T3"}),
        ("engine", {"engine": "0.11.0"}),
        ("share basis", {"basis": "coverage"}),
        ("dimension set", {"dims": base["dims"] + ["OFP"]}),
    ]
    for n, (term, change) in enumerate(moved, start=1):
        _plant(conn, site_id,
               {**base, "at": f"2026-09-03T0{n}:00:00+00:00", **change})
    trend = runs_repo.site_trend(conn, site_id)
    first = trend[0]["basis_key"]
    for point, (term, _) in zip(trend[1:], moved):
        assert point["basis_key"] != first, (
            f"two runs differing only in {term} share a basis key, so the "
            f"chart would read them as one series: {point['basis_key']!r}")
        assert point["partner_run_id"] is None, (
            f"a run differing in {term} was paired with one that does not")
    conn.close()
