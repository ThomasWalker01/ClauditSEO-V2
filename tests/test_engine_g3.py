"""Gate G3: the five remaining dimensions catch their planted fixture
defects, LOC redistributes when not applicable, and adding a toy EXT
dimension requires zero engine-core changes (everything EXT lives in this
file and uses only the public registry API)."""

from __future__ import annotations

import pytest

import clauditseo.modules  # noqa: F401  (registers all built-in dimensions)
from clauditseo.providers.base import ProviderHub
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget
from clauditseo.engine import registry
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Finding, Severity, Site, SubScore, Tier
from tests.conftest import FixtureSite
from tests.fixtures.site_full import MANIFEST, routes_with_base

ALL_DIMS = ["TEC", "ONP", "PRF", "CNT", "OFP", "LOC", "AIS"]
FAST = TierBudget(max_pages=50, request_timeout_s=10, wall_clock_s=60, delay_s=0)


@pytest.fixture(scope="module")
def fixture_crawl():
    site = FixtureSite({})
    site.routes.update(routes_with_base(site.base_url))
    site.start()
    try:
        yield crawl(site.base_url + "/", Tier.T2, budget=FAST)
    finally:
        site.stop()


@pytest.fixture(scope="module")
def audit(fixture_crawl):
    return run_audit(Site(domain="fixture.local", business_type="local-service"),
                     fixture_crawl, ALL_DIMS, Tier.T2)


def test_every_planted_defect_found_per_dimension(audit):
    produced = {(f.dimension, f.check_id, f.subject, f.severity.value)
                for f in audit.findings}
    missing = [m for m in MANIFEST if m not in produced]
    assert not missing, f"planted defects not found (or wrong severity): {missing}"


def test_all_seven_dimensions_scored_with_visible_weights(audit):
    assert set(audit.subscores) == set(ALL_DIMS)
    assert pytest.approx(sum(s.weight for s in audit.subscores.values()), abs=1e-6) == 1.0
    assert 0 <= audit.composite_score <= 100


def test_loc_redistributes_when_not_applicable(fixture_crawl):
    result = run_audit(Site(domain="fixture.local", business_type="saas"),
                       fixture_crawl, ALL_DIMS, Tier.T2)
    assert result.subscores["LOC"].applicable is False
    assert result.subscores["LOC"].weight == 0.0
    assert pytest.approx(sum(s.weight for s in result.subscores.values()), abs=1e-6) == 1.0


def test_t1_makes_no_provider_calls(fixture_crawl):
    # Subclasses the real hub so a method added to the contract arrives here
    # rather than failing as a missing attribute — the point of this double
    # is that it explodes on a provider call, not on an interface change.
    class ExplodingHub(ProviderHub):
        def backlink_snapshot(self, domain):
            raise AssertionError("T1 must not call providers")

        def cwv_metrics(self, url):
            raise AssertionError("T1 must not call providers")

    result = run_audit(Site(domain="fixture.local", business_type="local-service"),
                       fixture_crawl, ALL_DIMS, Tier.T1,
                       context={"providers": ExplodingHub()})
    assert result.composite_score >= 0


# --- EXT: the zero-engine-diff proof ---------------------------------------

class ExtModule:
    """A complete new dimension defined entirely outside the package."""

    code = "EXT"
    name = "Extension Example"
    default_weight = 0.10

    def applicable(self, site: Site) -> bool:
        return True

    def run(self, pages, tier, context) -> list[Finding]:
        return [Finding(dimension="EXT", check_id="ext-always", severity=Severity.INFO,
                        summary="EXT ran.", subject="ext")]

    def score(self, findings, context) -> SubScore:
        return SubScore(dimension="EXT", score=90.0, weight=self.default_weight)


def test_ext_module_composes_with_zero_engine_changes(fixture_crawl):
    registry.register(ExtModule())
    try:
        result = run_audit(Site(domain="fixture.local"), fixture_crawl,
                           ["TEC", "EXT"], Tier.T2)
        assert "EXT" in result.subscores
        assert any(f.dimension == "EXT" for f in result.findings)
        weights = {d: s.weight for d, s in result.subscores.items()}
        assert pytest.approx(sum(weights.values()), abs=1e-6) == 1.0
        # EXT's own default weight participates in renormalisation: 0.10 over
        # 0.10 + TEC's 0.18 (0.22 until item 143 step BD).
        assert weights["EXT"] == pytest.approx(0.10 / 0.28)
    finally:
        registry.unregister("EXT")
