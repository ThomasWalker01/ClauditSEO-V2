"""Adaptive staging gate: deterministic results decide what runs next.

Unit tests pin the policy (bands 95/80/60, overrides, hysteresis, task
selection). The integration test proves the flow end to end on a fixture
engineered so Content lands in the CONCERN band while On-Page stays
healthy: CNT gets its analyst, ONP does not, and every escalation records
its reasons.
"""

from __future__ import annotations

import dataclasses

import pytest

import clauditseo.modules  # noqa: F401
from clauditseo.adaptive import run_adaptive
from clauditseo.analysts.mock import MockAnalyst
from clauditseo.config import Settings
from clauditseo.crawler.types import TierBudget
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.staging import (Band, StagingConfig, analyst_tasks,
                                      band_for_score, escalated_tier,
                                      paid_provider_dims, plan)
from clauditseo.engine.types import Site, Tier
from clauditseo.persistence import repo, runs
from tests.conftest import FixtureSite

CFG = StagingConfig(healthy=95, watch=80, concern=60, hysteresis_delta=5)
FAST = {Tier.T1: TierBudget(3, 5, 30, 0), Tier.T2: TierBudget(30, 5, 30, 0),
        Tier.T3: TierBudget(30, 5, 30, 0)}


# --- policy units -----------------------------------------------------------

#: The pulse's parity probe fetches each probed page once per agent (item 151).
_PARITY_FETCHES = 3


def test_bands_match_operator_thresholds():
    assert band_for_score(95, CFG) is Band.NONE
    assert band_for_score(94.9, CFG) is Band.WATCH
    assert band_for_score(80, CFG) is Band.WATCH
    assert band_for_score(79.9, CFG) is Band.CONCERN
    assert band_for_score(60, CFG) is Band.CONCERN
    assert band_for_score(59.9, CFG) is Band.CRITICAL


def test_plan_escalates_only_unhealthy_dimensions():
    esc = plan({"TEC": 98, "CNT": 75, "ONP": 88, "OFP": 40},
               set(), set(), set(), set(), None, CFG,
               crawl_obtained_pages=True)
    assert set(esc) == {"CNT", "ONP", "OFP"}
    assert esc["CNT"].band is Band.CONCERN
    assert esc["ONP"].band is Band.WATCH
    assert esc["OFP"].band is Band.CRITICAL
    assert escalated_tier(esc) == "T3"
    assert paid_provider_dims(esc) == {"OFP"}
    assert "score 75" in esc["CNT"].reasons[0]


def test_regression_and_critical_overrides():
    esc = plan({"TEC": 99, "ONP": 90}, {"TEC"}, {"ONP"}, set(), set(), None, CFG,
               crawl_obtained_pages=True)
    assert esc["TEC"].band is Band.CONCERN          # regression lifts healthy dim
    assert "regression override" in " ".join(esc["TEC"].reasons)
    assert esc["ONP"].band is Band.CONCERN          # WATCH +1 for critical finding
    assert "critical-finding override" in " ".join(esc["ONP"].reasons)


def test_hysteresis_caps_reruns_after_a_deep_run():
    previous = {"tier": "T2", "subscores": {"CNT": {"score": 74}}}
    esc = plan({"CNT": 75}, set(), set(), set(), set(), previous, CFG,
               crawl_obtained_pages=True)
    assert esc["CNT"].band is Band.WATCH
    assert "hysteresis" in " ".join(esc["CNT"].reasons)
    # A regressed dimension is never dampened.
    esc = plan({"CNT": 75}, {"CNT"}, set(), set(), set(), previous, CFG,
               crawl_obtained_pages=True)
    assert esc["CNT"].band is Band.CONCERN
    # A big move re-escalates.
    esc = plan({"CNT": 62}, set(), set(), set(), set(),
               {"tier": "T2", "subscores": {"CNT": {"score": 80}}}, CFG,
               crawl_obtained_pages=True)
    assert esc["CNT"].band is Band.CONCERN


def test_an_uncovered_dimension_is_banded_on_its_absence_not_its_score():
    """A perfect score on no coverage escalates at WATCH and says why, and
    hysteresis cannot dampen it: there is no standing analysis to reuse, and
    two fabricated 100.0s always fall inside the delta."""
    esc = plan({"OFP": 100.0, "TEC": 98}, set(), set(), {"OFP"}, set(), None, CFG,
               crawl_obtained_pages=True)
    assert set(esc) == {"OFP"}
    assert esc["OFP"].band is Band.WATCH
    assert esc["OFP"].reasons == [
        "no coverage: the dimension measured nothing at this tier, "
        "so its score is not evidence"]
    assert analyst_tasks(esc) == []          # no judgement commissioned
    assert paid_provider_dims(esc) == set()  # no paid call authorised
    # A crawl can fill this one, so the deeper crawl is still bought.
    assert esc["OFP"].buys_depth
    assert escalated_tier(esc) == "T2"

    previous = {"tier": "T2", "subscores": {"OFP": {"score": 100.0}}}
    damp = plan({"OFP": 100.0}, {"OFP"}, set(), {"OFP"}, set(), previous, CFG,
                crawl_obtained_pages=True)
    assert damp["OFP"].band is Band.CONCERN  # regression override still applies
    assert not any("hysteresis" in r for r in damp["OFP"].reasons)


def test_an_absence_no_crawl_can_fill_is_reported_but_buys_no_depth():
    """The two claims separated. A dimension whose coverage no crawl can
    obtain still escalates — it is reported, and never banded HEALTHY — but
    it does not on its own decide the tier, because the crawl it would buy
    cannot change the input that triggered it.
    """
    esc = plan({"OFP": 100.0, "TEC": 98}, set(), set(), {"OFP"}, {"OFP"}, None, CFG,
               crawl_obtained_pages=True)
    assert set(esc) == {"OFP"}, "the absence must still be escalated"
    assert esc["OFP"].band is Band.WATCH, "and still never banded HEALTHY"
    assert not esc["OFP"].buys_depth
    assert any("no crawl can obtain it" in r for r in esc["OFP"].reasons)
    assert escalated_tier(esc) is None, "an absence alone bought a crawl"
    assert analyst_tasks(esc) == []
    assert paid_provider_dims(esc) == set()

    # One dimension that does buy depth is enough for the whole run.
    mixed = plan({"OFP": 100.0, "CNT": 75}, set(), set(), {"OFP"}, {"OFP"},
                 None, CFG, crawl_obtained_pages=True)
    assert escalated_tier(mixed) == "T2"

    # An override fires on evidence, so it lifts the band — and stops there.
    # WF-54: it used to restore the depth decision too, which bought the exact
    # crawl the line above had just refused, one path over on the same
    # dimension. Neither override can reach CRITICAL from WATCH, and CRITICAL
    # is the band that authorises the backlink provider, so the crawl each
    # would buy still reads no backlink signal.
    regressed = plan({"OFP": 100.0}, {"OFP"}, set(), {"OFP"}, {"OFP"}, None, CFG,
                     crawl_obtained_pages=True)
    assert regressed["OFP"].band is Band.CONCERN, "still escalated on evidence"
    assert not regressed["OFP"].buys_depth
    assert escalated_tier(regressed) is None

    critical = plan({"OFP": 100.0}, set(), {"OFP"}, {"OFP"}, {"OFP"}, None, CFG,
                    crawl_obtained_pages=True)
    assert critical["OFP"].band is Band.CONCERN
    assert not critical["OFP"].buys_depth
    assert escalated_tier(critical) is None


def test_analyst_task_selection():
    esc = plan({"CNT": 70, "ONP": 85, "AIS": 55, "TEC": 65}, set(), set(), set(), set(),
               None, CFG, crawl_obtained_pages=True)
    assert analyst_tasks(esc) == ["PRI-J", "CNT-J", "AIS-J"]  # priority order
    watch_only = plan({"CNT": 90}, set(), set(), set(), set(), None, CFG,
                      crawl_obtained_pages=True)
    assert analyst_tasks(watch_only) == []                    # WATCH spends nothing


# --- integration ------------------------------------------------------------

def _page(title: str, desc: str, body: str, path: str) -> str:
    # Within the description window the sweep measures since brief v10
    # step AG: these fixtures are meant to be clean on ONP.
    if len(desc) < 120:
        desc = (desc + " This page explains what it covers, who it is for, and "
                       "what to do next, in plain words for a first-time reader.")[:160]
    # And an entity block, because brief v16 step AS made "the home page
    # carries no Organization, LocalBusiness or WebSite block" a finding.
    # These fixtures exist to be clean on ONP so the clause below can say
    # that CNT escalated and ONP did not; without this they would be
    # testing the new check by accident.
    # `url` and `logo` alongside, because the existing schema validator
    # recommends both on an Organization and a block carrying only a name
    # trades one finding for another. Clean means clean.
    schema = ('<script type="application/ld+json">{"@context":'
              '"https://schema.org","@type":"Organization","@id":'
              '"https://adaptive.fixture/#organization","name":"Adaptive Co",'
              '"url":"https://adaptive.fixture/",'
              '"logo":"https://adaptive.fixture/logo.svg"}</script>')
    return (f"<html><head><title>{title}</title>"
            f'<meta name="description" content="{desc}">'
            # `initial-scale=1` as well as device-width, since item 147
            # (brief v20): `viewport-scale` reads a viewport with no
            # initial-scale as a defect, and it is right to — the page opens
            # zoomed on some devices. Without it this fixture raised a real
            # TEC finding, dropped to CONCERN and escalated, so a test named
            # "when all healthy" was running against a site that was not.
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"{schema}"
            f'<link rel="canonical" href="{path}"></head>'
            f"<body>{body}</body></html>")


def _routes() -> dict:
    words = ("Reliable local trades knowledge written plainly for homeowners who "
             "want honest answers about maintenance costs schedules and quality "
             "before booking anyone at all. ")
    home_body = ("<h1>Adaptive Fixture</h1><h2>Guides</h2><p>" + words * 12 + "</p>"
                 + "".join(f'<a href="/g{i}">guide {i}</a>' for i in range(1, 6)))
    routes = {
        "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nAllow: /\n"),
        "/": (200, {}, _page("Adaptive Fixture Home Guides", "Home of the adaptive fixture.",
                             home_body, "/")),
    }
    # Identical thin bodies: thin-content at 5/6 rate PLUS duplicate-content
    # pairs, landing CNT in the CONCERN band under rate-based scoring.
    shared = ("A very short note about home maintenance that repeats the same "
              "boilerplate paragraph on every guide page and stops well before "
              "saying anything genuinely useful about the topic at hand today. " * 2)
    for i in range(1, 6):
        body = f"<h1>Guide {i}</h1><p>{shared}</p>"
        routes[f"/g{i}"] = (200, {}, _page(f"Guide Number {i} For Homeowners",
                                           f"Short guide number {i} for homeowners.",
                                           body, f"/g{i}"))
    return routes


def test_adaptive_flow_escalates_content_not_onpage(tmp_path, monkeypatch):
    for var in ("CLAUDITSEO_BAND_HEALTHY", "CLAUDITSEO_BAND_WATCH",
                "CLAUDITSEO_BAND_CONCERN"):
        monkeypatch.delenv(var, raising=False)
    conn = connect(tmp_path / "adaptive.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Adaptive Co")
    site_id = repo.create_site(conn, client, "adaptive.fixture")
    run_id = runs.create_run(conn, site_id, ["TEC", "ONP", "CNT"], "T1",
                             analyst_enabled=True)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    server = FixtureSite(_routes()).start()
    notes: list[str] = []
    try:
        result, esc = run_adaptive(conn, run_id, Site(domain="adaptive.fixture"),
                                   site_id, server.base_url + "/", cfg,
                                   ["TEC", "ONP", "CNT"],
                                   announce=notes.append,
                                   provider=MockAnalyst(), budgets=FAST)
    finally:
        server.stop()

    # CNT: five thin guide pages -> 75 -> CONCERN; ONP is clean -> no escalation.
    assert esc["CNT"].band is Band.CONCERN
    assert "ONP" not in esc
    assert result.subscores["ONP"].score == 100.0

    stored = runs.get_run(conn, run_id)
    assert stored["tier"] == "T2"                      # executed tier stamped
    assert stored["status"] == "complete"

    analyst = [f for f in stored["findings"] if f["source"] == "model-judgement"]
    ran_tasks = {f["check_id"] for f in analyst}
    assert ran_tasks == {"cnt-j", "pri-j"}             # CNT's analyst + narrative only

    esc_notes = [f for f in stored["findings"]
                 if f["check_id"] == "adaptive-escalation"]
    assert any(f["dimension"] == "CNT" and "CONCERN" in f["summary"]
               for f in esc_notes)
    assert not any(f["dimension"] == "ONP" for f in esc_notes)
    assert any("escalating to T2" in n for n in notes)

    # Live progress steps were recorded through every stage.
    labels = [s["label"] for s in stored["progress"]]
    assert any(l.startswith("Pulse (T1)") for l in labels)
    assert any(l.startswith("Escalated crawl (T2)") for l in labels)
    assert any(l.startswith("Analyst CNT-J") for l in labels)
    assert labels[-1] == "Saving results and updating finding states"
    conn.close()


def _healthy_routes(base: str) -> dict:
    """A fixture site every page-derived dimension scores well on, so the only
    thing that can escalate a run over it is the policy under test.

    The sitemap must declare the one page it serves. An empty sitemap is not
    healthy on TEC since item 137 (brief v18 step AZ): `sitemap-coverage` reads
    a reached indexable page absent from the sitemap as an incomplete sitemap,
    which is exactly what an empty one is. `base` is the running server's origin
    because the coverage check matches the sitemap's absolute <loc> by host."""
    words = ("Genuinely useful long form advice covering budgets timelines "
             "permits materials and tradesperson selection in plain English. ")
    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nAllow: /\n"),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"},
                         '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/'
                         f'schemas/sitemap/0.9"><url><loc>{base}/</loc></url></urlset>'),
        "/": (200, {}, _page("Healthy Fixture Home Page", "A healthy little site.",
                             "<h1>Healthy</h1><h2>Advice</h2><p>" + words * 10 + "</p>",
                             "/")),
    }


def test_adaptive_stops_at_pulse_when_all_healthy(tmp_path, monkeypatch):
    # Local fixtures can never reach 95 on TEC over http, so loosen the band
    # for this test only — the point is the stop-at-pulse path.
    monkeypatch.setenv("CLAUDITSEO_BAND_HEALTHY", "85")
    conn = connect(tmp_path / "healthy.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Healthy Co")
    site_id = repo.create_site(conn, client, "healthy.fixture")
    run_id = runs.create_run(conn, site_id, ["TEC", "ONP", "CNT"], "T1")
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")

    server = FixtureSite({})
    server.routes.update(_healthy_routes(server.base_url))
    server.start()
    try:
        result, esc = run_adaptive(conn, run_id, Site(domain="healthy.fixture"),
                                   site_id, server.base_url + "/", cfg,
                                   ["TEC", "ONP", "CNT"],
                                   provider=MockAnalyst(), budgets=FAST)
        page_hits = server.request_log.count("/")
    finally:
        server.stop()

    assert esc == {}
    stored = runs.get_run(conn, run_id)
    assert stored["tier"] == "T1"                       # never escalated
    # Plus the pulse's parity probe (item 151): the home page once more under
    # each of its three user agents, which is not a second crawl.
    assert page_hits == 1 + _PARITY_FETCHES, "no second crawl when everything is healthy"
    assert not [f for f in stored["findings"] if f["source"] == "model-judgement"]
    assert any(f["check_id"] == "adaptive-no-escalation" for f in stored["findings"])
    conn.close()


def test_an_absence_is_reported_without_buying_a_deeper_crawl(tmp_path,
                                                              monkeypatch):
    """OFP is in the product's default dimension list and reads no backlink
    data at T1 by contract, so round 046's rule bands it WATCH on every
    default run. `escalated_tier` returned "T2" for any escalation at all,
    which made the free stop-at-pulse path unreachable and bought a 100-page
    crawl that cannot obtain what it escalated for: OFP's coverage comes from
    a backlink provider, and `run_adaptive` clears those below CRITICAL.

    The two states are separate. The dimension must still be reported, still
    never be banded HEALTHY, and still not decide the tier on its own.
    """
    monkeypatch.setenv("CLAUDITSEO_BAND_HEALTHY", "85")
    conn = connect(tmp_path / "absence.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Absence Co")
    site_id = repo.create_site(conn, client, "healthy.fixture")
    dims = ["TEC", "ONP", "CNT", "OFP"]
    run_id = runs.create_run(conn, site_id, dims, "T1")
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")

    server = FixtureSite({})
    server.routes.update(_healthy_routes(server.base_url))
    server.start()
    try:
        result, esc = run_adaptive(conn, run_id, Site(domain="healthy.fixture"),
                                   site_id, server.base_url + "/", cfg, dims,
                                   provider=MockAnalyst(), budgets=FAST)
        page_hits = server.request_log.count("/")
    finally:
        server.stop()

    # The premise: OFP is applicable, measured nothing, and carries a 100.0.
    assert result.subscores["OFP"].applicable
    assert result.subscores["OFP"].coverage == 0.0
    assert result.subscores["OFP"].score == 100.0

    # The claim: no second crawl was bought.
    stored = runs.get_run(conn, run_id)
    assert stored["tier"] == "T1"
    # Plus the pulse's parity probe (item 151): the home page once more under
    # each of its three user agents, which is not a second crawl.
    assert page_hits == 1 + _PARITY_FETCHES, "an absence no crawl can fill still bought a crawl"

    # WF-06 does not regress: the absence is still escalated and still said.
    assert "OFP" in esc, "a dimension with no coverage was banded HEALTHY"
    assert esc["OFP"].band is Band.WATCH
    assert any("no coverage" in r for r in esc["OFP"].reasons)
    assert not [f for f in stored["findings"]
                if f["check_id"] == "adaptive-no-escalation"]
    assert [f for f in stored["findings"]
            if f["check_id"] == "adaptive-escalation"
            and f["dimension"] == "OFP"], "the absence was not reported"

    # And nothing was spent on it.
    assert not [f for f in stored["findings"] if f["source"] == "model-judgement"]
    conn.close()


def test_a_dimension_that_measured_nothing_is_not_banded_healthy(tmp_path,
                                                                 monkeypatch):
    """OFP is applicable on this fixture and reads no backlink data at any
    tier, so its score is 100.0 at coverage 0.0 — a perfect mark on nothing.
    Filtering the planner's input on `applicable` alone hands that 100.0 to
    `band_for_score`, which bands it HEALTHY and declines to escalate, so the
    one dimension the audit is blind to is the one it never looks harder at.
    `runs._snapshot_metrics` has required `applicable and coverage` since
    round 025; this is the same rule at the other consumer.
    """
    for var in ("CLAUDITSEO_BAND_HEALTHY", "CLAUDITSEO_BAND_WATCH",
                "CLAUDITSEO_BAND_CONCERN"):
        monkeypatch.delenv(var, raising=False)
    conn = connect(tmp_path / "uncovered.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Uncovered Co")
    site_id = repo.create_site(conn, client, "adaptive.fixture")
    dims = ["TEC", "ONP", "CNT", "OFP"]
    run_id = runs.create_run(conn, site_id, dims, "T1")
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    server = FixtureSite(_routes()).start()
    try:
        result, esc = run_adaptive(conn, run_id, Site(domain="adaptive.fixture"),
                                   site_id, server.base_url + "/", cfg, dims,
                                   provider=MockAnalyst(), budgets=FAST)
    finally:
        server.stop()

    # The premise: OFP really is applicable and really measured nothing.
    assert result.subscores["OFP"].applicable
    assert result.subscores["OFP"].coverage == 0.0
    assert result.subscores["OFP"].score == 100.0

    # The claim: a score that is not a measurement cannot buy a HEALTHY verdict.
    assert "OFP" in esc, "a dimension with no coverage was banded HEALTHY"
    assert esc["OFP"].band is Band.WATCH
    assert any("no coverage" in r for r in esc["OFP"].reasons)

    # ...and the run must not tell the operator every dimension was healthy.
    stored = runs.get_run(conn, run_id)
    assert not [f for f in stored["findings"]
                if f["check_id"] == "adaptive-no-escalation"]
    conn.close()


def _refusing_routes() -> dict:
    """A site that answers, and answers 500. Every page-derived dimension is
    uncovered because a 500 is not eligible, and TEC raises a CRITICAL
    finding for the same status — one pulse producing a dimension that is
    every page-derived dimension uncovered, which is the state the depth
    guard exists for and the one no test drove end to end.

    TEC is deliberately absent from the dimension list this fixture is run
    with: it derives 0.35 of its coverage from robots and sitemap checks that
    need no page, so it is a real measurement even here and buys depth on its
    own merits. Run `93bdd2b2`'s stored dimensions — AIS, CNT, LOC, ONP, PRF
    — carry no TEC either, which is why this shape is the stored one.
    """
    body = "<html><head><title>Down</title></head><body>Service down</body></html>"
    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nAllow: /\n"),
        "/": (500, {}, body),
    }


def test_a_run_whose_crawl_obtained_nothing_stops_at_the_pulse(tmp_path,
                                                               monkeypatch):
    """CQ-93. `crawl_obtained_pages` is computed at `adaptive.py` from the real
    crawl, and the rule it feeds was tested only by calling `staging.plan`
    directly — so the wiring that supplies it was asserted by nothing, on the
    one input that can refuse a spend.

    Three of eleven stored runs are `blocked`, so this is the shape of a real
    run rather than an invented one: the crawl reaches the site, obtains no
    eligible page, and every dimension comes back with a fabricated 100.0 at
    coverage 0.0.

    The claim is that such a run buys nothing: no second crawl, no analyst,
    no paid provider — while still reporting every absence.
    """
    for var in ("CLAUDITSEO_BAND_HEALTHY", "CLAUDITSEO_BAND_WATCH",
                "CLAUDITSEO_BAND_CONCERN"):
        monkeypatch.delenv(var, raising=False)
    conn = connect(tmp_path / "refused.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Refused Co")
    site_id = repo.create_site(conn, client, "refused.fixture")
    dims = ["ONP", "CNT"]
    run_id = runs.create_run(conn, site_id, dims, "T1", analyst_enabled=True)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")

    server = FixtureSite(_refusing_routes()).start()
    try:
        result, esc = run_adaptive(conn, run_id, Site(domain="refused.fixture"),
                                   site_id, server.base_url + "/", cfg, dims,
                                   provider=MockAnalyst(), budgets=FAST)
        page_hits = server.request_log.count("/")
    finally:
        server.stop()

    # The premise: the crawl reached the site and obtained no eligible page.
    assert page_hits >= 1, "the fixture was never asked for the page"
    assert all(not s.coverage for s in result.subscores.values() if s.applicable)

    # The claim: nothing was bought.
    stored = runs.get_run(conn, run_id)
    assert stored["tier"] == "T1", "a crawl that obtained nothing bought a deeper one"
    assert page_hits == 1, "a second crawl was issued against a site that refused the first"
    assert not [f for f in stored["findings"] if f["source"] == "model-judgement"]

    # And every absence is still reported, with the refusal written down.
    assert esc, "a run that measured nothing escalated nothing"
    assert all(not e.buys_depth for e in esc.values())
    assert not [f for f in stored["findings"]
                if f["check_id"] == "adaptive-no-escalation"], (
        "the operator was told every dimension was healthy")

    # CQ-92. The stored note is the operator's only record of a spend
    # decision, so it must carry the variable that took it: two escalations
    # at the same band spend differently, and `band` alone cannot say which.
    notes = [f for f in stored["findings"]
             if f["check_id"] == "adaptive-escalation"]
    assert notes, "the absences were not recorded"
    assert all(f["evidence"].get("buys_depth") is False for f in notes), (
        "a stored escalation cannot be audited for cost after the fact")


@pytest.mark.parametrize("dims,wanted", [(["TEC", "ONP"], True), (["ONP", "CNT"], False)])
def test_an_adaptive_run_takes_the_trace_when_a_dimension_reads_it(tmp_path, monkeypatch, dims, wanted):
    """Every free Re-check posts `tier: "auto"`, and until 2026-09-14 no
    adaptive run carried a trace. The pass is taken when a dimension reads it,
    and the traces reach the checks and the stored evidence."""
    from clauditseo import perf
    monkeypatch.setenv("CLAUDITSEO_BAND_HEALTHY", "85")
    calls = []

    def fake(crawl_result, run_id):
        url = crawl_result.pages[0].url
        calls.append(url)
        return {url: {"traced": True, "ttfb_ms": 5000, "resources": []}}, "every page of the pulse"
    monkeypatch.setattr(perf, "trace_for_run", fake)
    conn = connect(tmp_path / "trace.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Trace Co"), "healthy.fixture")
    run_id = runs.create_run(conn, site_id, dims, "T1")
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    server = FixtureSite({})
    server.routes.update(_healthy_routes(server.base_url))
    server.start()
    try:
        run_adaptive(conn, run_id, Site(domain="healthy.fixture"), site_id, server.base_url + "/",
                     cfg, dims, analyst=False, budgets=FAST)
    finally:
        server.stop()
    assert bool(calls) is wanted
    import json
    ev = json.loads(conn.execute("SELECT crawl_evidence FROM audit_runs WHERE id=?", (run_id,)).fetchone()[0])
    assert (ev.get("perf_sample") == "every page of the pulse") is wanted
    conn.close()
