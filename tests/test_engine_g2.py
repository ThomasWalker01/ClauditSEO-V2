"""Gate G2: TEC + ONP end to end against the planted-defect fixture site.

- every planted defect in the manifest is found;
- severities match the manifest;
- the score is deterministic across two identical runs;
- T1 (Pulse) completes within its page budget.
"""

from __future__ import annotations

import pytest

import clauditseo.modules  # noqa: F401  (registers TEC + ONP)
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from tests.fixtures.site_basic import MANIFEST, routes_with_base

FAST = TierBudget(max_pages=50, request_timeout_s=5, wall_clock_s=30, delay_s=0)


@pytest.fixture(scope="module")
def fixture_crawl():
    from tests.conftest import FixtureSite

    # Two-step start: routes need the server's port for absolute sitemap URLs.
    site = FixtureSite({})
    site.routes.update(routes_with_base(site.base_url))
    site.start()
    try:
        yield crawl(site.base_url + "/", Tier.T2, budget=FAST)
    finally:
        site.stop()


def _audit(fixture_crawl):
    return run_audit(Site(domain="fixture.local"), fixture_crawl,
                     ["TEC", "ONP"], Tier.T2)


def test_every_planted_defect_is_found_with_matching_severity(fixture_crawl):
    result = _audit(fixture_crawl)
    produced = {(f.dimension, f.check_id, f.subject, f.severity.value)
                for f in result.findings}
    missing = [m for m in MANIFEST if m not in produced]
    assert not missing, f"planted defects not found (or wrong severity): {missing}"


def test_no_findings_against_clean_subjects(fixture_crawl):
    result = _audit(fixture_crawl)
    clean_paths = {"/dup-a", "/dup-b"}  # only duplication findings expected there
    for f in result.findings:
        if f.subject in clean_paths:
            # `meta-desc-length` measures the fixture's short descriptions
            # since brief v10 step AG; the pages are clean of everything else.
            assert f.check_id in ("title-duplicate", "meta-desc-duplicate", "meta-desc-length"), (
                f"unexpected finding {f.check_id} on clean page {f.subject}")


def test_score_is_deterministic_across_identical_runs(fixture_crawl):
    a = _audit(fixture_crawl)
    b = _audit(fixture_crawl)
    assert a.composite_score == b.composite_score
    assert {d: s.score for d, s in a.subscores.items()} == \
           {d: s.score for d, s in b.subscores.items()}
    assert len(a.findings) == len(b.findings)


def test_weights_are_visible_and_renormalised(fixture_crawl):
    result = _audit(fixture_crawl)
    weights = {d: s.weight for d, s in result.subscores.items()}
    assert pytest.approx(sum(weights.values()), abs=1e-6) == 1.0
    # Renormalised over the two that ran: TEC 0.18 (0.22 until item 143 step BD
    # moved 0.04 to SEC) against ONP 0.22.
    assert weights["TEC"] == pytest.approx(0.18 / 0.40)
    assert weights["ONP"] == pytest.approx(0.22 / 0.40)


def test_t1_pulse_stays_within_budget(make_site):
    from clauditseo.crawler.types import TIER_BUDGETS
    from tests.fixtures.site_basic import routes_with_base
    from tests.conftest import FixtureSite

    site = FixtureSite({})
    site.routes.update(routes_with_base(site.base_url))
    site.start()
    try:
        t1 = TierBudget(max_pages=TIER_BUDGETS[Tier.T1].max_pages,
                        request_timeout_s=5, wall_clock_s=30, delay_s=0)
        crawl_result = crawl(site.base_url + "/", Tier.T1, budget=t1)
        assert len(crawl_result.pages) <= 3
        result = run_audit(Site(domain="fixture.local"), crawl_result,
                           ["TEC", "ONP"], Tier.T1)
        assert 0 <= result.composite_score <= 100
        assert result.subscores["TEC"].detail["finding_counts"]
    finally:
        site.stop()
