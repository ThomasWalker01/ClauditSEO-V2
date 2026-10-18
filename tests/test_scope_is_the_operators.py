"""Escalation may raise the tier. It may never widen the page set
(relay item 136a).

The operator chose **Page × Deep** on `https://www.13acme.com.au/` — the
cell that reads "One URL you name" — and got a 145-page crawl:

    Pulse (T1): 3 page(s) fetched
    adaptive: ONP → CRITICAL (score 0 → CRITICAL band)
    adaptive: escalating to T3
    Escalated crawl (T3): 145 page(s) fetched

**The cause is one line.** `_execute_run` holds the operator's `scope` and
hands it to the by-hand path; the adaptive path it never gets. So both of
`run_adaptive`'s crawls fall back to the tier's own budget, and a tier's
budget is a page count — T3's is the whole site. Scope and tier were
separated at `scanscope.py` precisely so that "look harder" and "look at
more pages" stopped being one control, and the adaptive path was left on
the old side of that line.

`crawl_kwargs` already produces the arguments; nothing new needs
inventing. What these clauses hold is that the adaptive path asks for
them, at both crawls, and that the escalation records what it did not do.
"""

from __future__ import annotations

import pytest

from clauditseo.crawler.types import Tier
from clauditseo.scanscope import SCOPES, crawl_kwargs


# --- the frontier -------------------------------------------------------

@pytest.mark.parametrize("scope,expect", [
    ("page", {"only_urls"}),
    ("nav", {"nav_only"}),
])
def test_a_scope_restricts_the_frontier_at_every_tier(scope, expect):
    """The property the escalation broke: what a scope restricts does not
    loosen as the tier rises.

    T3 is the tier whose budget is the whole site, so if a scope's
    restriction were expressed as a page count alone, escalating to T3
    would erase it. `page` restricts the frontier itself - fetch this and
    follow nothing - which no budget can widen.
    """
    for tier in (Tier.T1, Tier.T2, Tier.T3):
        kw = crawl_kwargs(scope, tier, "https://example.test/one")
        assert expect <= set(kw), (tier, scope, kw)
        if scope == "page":
            assert kw["only_urls"] == ["https://example.test/one"], kw
            # A page scope must not carry a page budget that implies a
            # crawl: the frontier is the restriction.
            assert kw.get("budget") is None or kw["budget"].max_pages == 1, kw


def test_the_page_scope_survives_the_tier_that_would_erase_a_budget():
    """T3's own budget is the whole site, which is why this is the tier
    the defect showed up at."""
    from clauditseo.crawler.types import TIER_BUDGETS

    assert TIER_BUDGETS[Tier.T3].max_pages > 100, TIER_BUDGETS[Tier.T3]
    kw = crawl_kwargs("page", Tier.T3, "https://example.test/one")
    assert kw["only_urls"] == ["https://example.test/one"], kw


# --- the adaptive path --------------------------------------------------

def _crawls(monkeypatch) -> list[dict]:
    """Record every crawl `run_adaptive` asks for, and answer with an empty
    result so nothing is fetched."""
    from clauditseo.crawler.types import CrawlResult

    seen: list[dict] = []

    def fake_crawl(start_url, tier, **kw):
        seen.append({"start_url": start_url, "tier": tier,
                     "only_urls": kw.get("only_urls"),
                     "nav_only": kw.get("nav_only"),
                     "max_pages": getattr(kw.get("budget"), "max_pages", None)})
        return CrawlResult(start_url=start_url, tier=tier)

    monkeypatch.setattr("clauditseo.adaptive.crawl", fake_crawl)
    return seen


def test_run_adaptive_takes_the_operators_scope():
    """The signature, because the defect is that the caller had it and the
    callee could not accept it."""
    import inspect

    from clauditseo.adaptive import run_adaptive

    params = inspect.signature(run_adaptive).parameters
    assert "scope" in params, sorted(params)
    assert params["scope"].default is None, (
        "an audit that names no scope must behave exactly as it did")


def test_the_worker_hands_the_adaptive_path_the_scope_it_was_given():
    """`_execute_run` chooses between two paths and only one of them was
    told what the operator asked for. Read from the source because the
    branch is one line and a run would cost a crawl to observe."""
    import inspect

    from clauditseo.api import app as _app

    src = inspect.getsource(_app._execute_run)
    call = src[src.index("run_adaptive("):]
    call = call[:call.index(")")]
    assert "scope=" in call, (
        "the adaptive path is called without the operator's scope, so both "
        f"its crawls fall back to the tier's page budget: {call}")


@pytest.mark.parametrize("scope,tier_name", [("page", "T3"), ("nav", "T2")])
def test_both_crawls_carry_the_scope_not_just_the_first(monkeypatch, scope, tier_name):
    """The pulse and the escalated crawl, because the run that cost 145
    pages escalated *after* a pulse that was itself unscoped."""
    from clauditseo.crawler.types import CrawlResult, Page, Tier

    seen = _crawls(monkeypatch)

    # A pulse that escalates: one page, and a CRITICAL finding on it.
    def fake_crawl(start_url, tier, **kw):
        seen.append({"start_url": start_url, "tier": tier,
                     "only_urls": kw.get("only_urls"),
                     "nav_only": kw.get("nav_only")})
        out = CrawlResult(start_url=start_url, tier=tier)
        out.pages.append(Page(url=start_url, requested_url=start_url, status=200,
                              content_type="text/html; charset=utf-8",
                              content="<html><body><main><h1>x</h1></main></body></html>"))
        return out

    monkeypatch.setattr("clauditseo.adaptive.crawl", fake_crawl)
    _drive_adaptive(monkeypatch, scope=scope, force_tier=tier_name)

    assert len(seen) == 2, [c["tier"] for c in seen]
    for call in seen:
        if scope == "page":
            assert call["only_urls"], (
                "a crawl went out without the page restriction, so the tier's "
                f"budget decided the page set: {call}")
        else:
            assert call["nav_only"], call
    assert seen[1]["tier"].value == tier_name, seen[1]


def _drive_adaptive(monkeypatch, scope: str, force_tier: str):
    """Run `run_adaptive` against stubs, forcing an escalation.

    The escalation decision is `staging.plan`'s and is tested on its own;
    what these clauses are about is which pages the escalated crawl asks
    for, so the decision is forced rather than provoked.
    """
    import tempfile
    from pathlib import Path

    from clauditseo.adaptive import run_adaptive
    from clauditseo.config import Settings
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.engine import staging
    from clauditseo.engine.types import Site
    from clauditseo.persistence import repo, runs

    monkeypatch.setattr(staging, "escalated_tier", lambda _e: force_tier)
    conn = connect(Path(tempfile.mkdtemp()) / "s.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "S"), "scope.test")
    run_id = runs.create_run(conn, site_id, ["ONP"], "T1", scan_scope=scope)
    try:
        run_adaptive(conn, run_id, Site(domain="scope.test"), site_id,
                     "https://scope.test/one", Settings(anthropic_api_key=""),
                     ["ONP"], analyst=False, scope=scope)
    finally:
        conn.close()


# --- what the record and the operator are told --------------------------

def test_a_scope_that_blocks_a_wider_look_is_recorded_rather_than_silently_obeyed():
    """The suggestion the brief asks for: a CRITICAL on a site-wide
    dimension while the scope is one page is worth saying, and is never
    worth acting on without being asked."""
    from clauditseo.adaptive import scope_note

    note = scope_note("page", "TEC")
    assert note is not None
    assert note.severity.value == "info", note.severity
    assert "not taken" in note.summary.lower(), note.summary
    assert "page" in note.summary.lower(), note.summary
    # A site or full scope has nothing to decline.
    assert scope_note("full", "TEC") is None
    assert scope_note(None, "TEC") is None


def test_the_progress_line_says_which_pages_the_escalation_is_for():
    """`Escalated crawl (T3)` said how hard and not how many, which is the
    whole confusion this item is about."""
    from clauditseo.adaptive import escalation_label

    assert escalation_label(Tier.T3, "page") == "Escalated crawl (T3, page scope)"
    assert escalation_label(Tier.T2, None) == "Escalated crawl (T2)"


def test_every_scope_the_matrix_offers_has_a_label_for_that_line():
    """Derived from the registry, so a seventh scope cannot be added
    without the progress line learning to say it."""
    from clauditseo.adaptive import escalation_label

    for key in SCOPES:
        line = escalation_label(Tier.T3, key)
        assert key in line or SCOPES[key].label.lower() in line.lower(), (key, line)


# --- an absence cannot buy a crawl that is not allowed to be bigger -----

def test_a_one_page_pulse_with_nothing_to_score_does_not_escalate():
    """Item 3 of the brief, and its premise needed correcting.

    The brief reads "a dimension whose pulse coverage is zero cannot
    trigger escalation on its score". It already could not: the uncovered
    path never looks at the score, and says so - *"no coverage: the
    dimension measured nothing at this tier, so its score is not
    evidence"*. What it does instead is escalate on the **absence**, to
    buy the deeper crawl that would obtain the coverage, and that is a
    good rule when a deeper crawl is possible.

    Under a page or nav scope it is not possible. The escalated crawl
    fetches the same set by construction, so the absence would commission
    a crawl that provably cannot change the input that triggered it -
    which is what this rule already refuses for a crawl-blind dimension
    and for a crawl that fetched nothing.
    """
    from clauditseo.engine import staging

    cfg = staging.StagingConfig.from_env()
    args = ({"ONP": 0.0}, set(), set(), {"ONP"}, set(), None, cfg)

    widen = staging.plan(*args, crawl_obtained_pages=True, can_widen=True)
    assert staging.escalated_tier(widen) == "T2", widen
    assert widen["ONP"].buys_depth is True

    fixed = staging.plan(*args, crawl_obtained_pages=True, can_widen=False)
    assert staging.escalated_tier(fixed) is None, fixed
    # Reported, never banded HEALTHY, and carrying the reason.
    assert fixed["ONP"].band.name == "WATCH", fixed["ONP"]
    assert fixed["ONP"].buys_depth is False
    assert any("scope fixes the page set" in r for r in fixed["ONP"].reasons), \
        fixed["ONP"].reasons


def test_a_measured_zero_still_escalates_because_it_is_evidence():
    """The counter-case, so the rule above cannot be read as "a low score
    under a page scope is ignored".

    ONP scoring 0 over pages it *did* read is a measurement and a reason
    to look harder; only an absence is refused. On 13acme the escalation
    came from a measured 0 over three pages, not from zero coverage -
    which is why part 1 of this item, and not this part, is what stopped
    the 145-page crawl.
    """
    from clauditseo.engine import staging

    cfg = staging.StagingConfig.from_env()
    esc = staging.plan({"ONP": 0.0}, set(), set(), set(), set(), None, cfg,
                       crawl_obtained_pages=True, can_widen=False)
    assert esc["ONP"].band.name == "CRITICAL", esc["ONP"]
    assert esc["ONP"].buys_depth is True
    assert staging.escalated_tier(esc) == "T3", esc
