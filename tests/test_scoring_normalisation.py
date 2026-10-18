"""P1-1 gate: sub-scores are rate-based and comparable across crawl sizes.

- a check affecting every page costs its ceiling once, not per page;
- no single check can floor a dimension;
- site-level findings still deduct flat;
- the same fixture crawled at T1 (3 pages) and T2 (all pages) scores within
  a stated tolerance.
"""

from __future__ import annotations

import pytest

import clauditseo.modules  # noqa: F401
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget
from clauditseo.engine.core import run_audit
from clauditseo.engine.scoring import CHECK_CEILING, subscore
from clauditseo.engine.types import Finding, Severity, Site, Tier
from tests.conftest import FixtureSite

FAST = TierBudget(max_pages=50, request_timeout_s=5, wall_clock_s=30, delay_s=0)


class _FakeCrawl:
    def __init__(self, page_count: int):
        class _P:
            status = 200
            content_type = "text/html"
        self.pages = [_P() for _ in range(page_count)]


def _page_finding(check: str, path: str, sev: Severity = Severity.MEDIUM) -> Finding:
    return Finding(dimension="CNT", check_id=check, severity=sev,
                   summary="x", subject=path)


def test_full_saturation_costs_the_ceiling_once():
    findings = [_page_finding("thin-content", f"/p{i}") for i in range(100)]
    sub = subscore("CNT", findings, 0.16, {"crawl": _FakeCrawl(100)})
    assert sub.score == 100 - CHECK_CEILING[Severity.MEDIUM]   # 88, not 0
    assert sub.detail["per_check"]["thin-content"]["rate"] == 1.0


def test_rate_scales_with_share_of_pages_affected():
    ten_of_100 = subscore("CNT", [_page_finding("thin-content", f"/p{i}")
                                  for i in range(10)], 0.16,
                          {"crawl": _FakeCrawl(100)})
    one_of_10 = subscore("CNT", [_page_finding("thin-content", "/p0")], 0.16,
                         {"crawl": _FakeCrawl(10)})
    assert ten_of_100.score == one_of_10.score                 # same share, same score


def test_no_single_check_can_zero_a_dimension():
    findings = [_page_finding("img-alt-missing", f"/p{i}") for i in range(500)]
    sub = subscore("ONP", findings, 0.22, {"crawl": _FakeCrawl(500)})
    assert sub.score >= 100 - CHECK_CEILING[Severity.MEDIUM]


def test_site_level_findings_deduct_flat():
    site = Finding(dimension="TEC", check_id="not-https", severity=Severity.HIGH,
                   summary="x", subject="site")
    sub = subscore("TEC", [site], 0.22, {"crawl": _FakeCrawl(100)})
    assert sub.score == 90.0


def _uniform_defect_routes(pages: int) -> dict:
    # Every page identically defective: no meta description, no canonical.
    routes = {"/robots.txt": (200, {"Content-Type": "text/plain"},
                              "User-agent: *\nAllow: /\n")}
    links = "".join(f'<a href="/p{i}">p{i}</a>' for i in range(1, pages))
    body = ("Genuinely useful advice about drains pipes and pumps repeated "
            "for realistic length. " * 10)
    def page(title, extra=""):
        return (f"<html><head><title>{title}</title>"
                '<meta name="viewport" content="width=device-width"></head>'
                f"<body><h1>{title}</h1><p>{body}</p>{extra}</body></html>")
    routes["/"] = (200, {}, page("Uniform Fixture Home Page", links))
    for i in range(1, pages):
        routes[f"/p{i}"] = (200, {}, page(f"Uniform Fixture Page {i}"))
    return routes


def test_t1_and_t2_scores_are_comparable_on_a_uniform_site():
    site = FixtureSite(_uniform_defect_routes(20)).start()
    try:
        t1 = crawl(site.base_url + "/", Tier.T1,
                   budget=TierBudget(3, 5, 30, 0))
        t2 = crawl(site.base_url + "/", Tier.T2, budget=FAST)
    finally:
        site.stop()
    dims = ["TEC", "ONP", "CNT"]
    r1 = run_audit(Site(domain="uniform.fixture"), t1, dims, Tier.T1)
    r2 = run_audit(Site(domain="uniform.fixture"), t2, dims, Tier.T2)
    assert len(t1.pages) == 3 and len(t2.pages) == 20
    for dim in dims:
        assert abs(r1.subscores[dim].score - r2.subscores[dim].score) <= 10, (
            f"{dim}: T1 {r1.subscores[dim].score} vs T2 {r2.subscores[dim].score}")
    assert abs(r1.composite_score - r2.composite_score) <= 10

def test_a_check_reports_pages_and_findings_separately():
    """`duplicate-content` names both sides of a pair, so twenty pages can
    produce twenty-one findings and the Biggest gains table read "21 of 20
    pages". Both counts are recorded so the column can show the one its
    heading claims."""
    from clauditseo.engine.scoring import subscore
    from clauditseo.engine.types import Confidence, Finding, Severity

    def f(path):
        return Finding(dimension="CNT", check_id="duplicate-content",
                       severity=Severity.MEDIUM, summary="dupe", subject=path,
                       affected_urls=[], evidence={}, confidence=Confidence.HIGH,
                       recommendation="")

    # Three findings across two pages — one page named twice.
    sub = subscore("CNT", [f("/a"), f("/b"), f("/a")], 0.16)
    detail = sub.detail["per_check"]["duplicate-content"]
    assert detail["affected"] == 3      # findings
    assert detail["pages"] == 2         # distinct subjects


# --- what the "N of M pages" numerator counts -----------------------------
def test_pages_counts_pages_not_whatever_makes_a_finding_unique():
    """The "N of M pages" numerator, on the table whose whole job is
    defensible arithmetic.

    `duplicate-content` names both sides of a pair and its subject is the
    pair key `/a|/b`, so counting subjects counted pairs: 20 crawled pages
    produced 21 pairs and the table read "21 of 20 pages". Counting subjects
    was the first fix and it only hid the symptom — the next crawl was
    larger, so it read "24 of 81" and stayed wrong quietly, which is worse.
    """
    from clauditseo.engine.scoring import subscore
    from clauditseo.engine.types import Confidence, Finding, Severity

    def pair(a, b):
        return Finding(dimension="CNT", check_id="duplicate-content",
                       severity=Severity.MEDIUM, summary=f"{a} and {b} overlap",
                       subject=f"{a}|{b}",
                       affected_urls=[f"https://x.test{a}", f"https://x.test{b}"],
                       evidence={}, confidence=Confidence.HIGH, recommendation="")

    # Three pairs drawn from four pages: /a-/b, /b-/c, /c-/d.
    findings = [pair("/a", "/b"), pair("/b", "/c"), pair("/c", "/d")]

    class _Page:
        status = 200
        content_type = "text/html"

    class _Crawl:
        pages = [_Page()] * 4

    detail = subscore("CNT", findings, 0.16,
                      context={"crawl": _Crawl()}).detail["per_check"]
    dup = detail["duplicate-content"]

    assert dup["affected"] == 3, "three findings"
    assert dup["pages"] == 4, "four distinct pages, not three pairs"
    assert dup["pages"] <= dup["eligible"], (
        "the numerator must never exceed the pages that were eligible — that "
        "is the '21 of 20' the table shipped")


def test_a_trailing_slash_is_not_a_second_page():
    """`eligible` counts crawled pages and the crawler normalises the
    trailing slash, so counting raw URLs here would reintroduce the
    double-count it fixed."""
    from clauditseo.engine.scoring import _pages_touched
    from clauditseo.engine.types import Confidence, Finding, Severity

    def at(url):
        return Finding(dimension="ONP", check_id="x", severity=Severity.LOW,
                       summary="s", subject="/a", affected_urls=[url],
                       evidence={}, confidence=Confidence.HIGH, recommendation="")

    assert _pages_touched([at("https://x.test/a"), at("https://x.test/a")]) == 1


def test_a_check_that_names_no_page_still_reports_something():
    """Falling back to the subject count, so a bare zero never appears where
    a real count belongs."""
    from clauditseo.engine.scoring import _pages_touched
    from clauditseo.engine.types import Confidence, Finding, Severity

    f = Finding(dimension="TEC", check_id="x", severity=Severity.LOW,
                summary="s", subject="/only-a-subject", affected_urls=[],
                evidence={}, confidence=Confidence.HIGH, recommendation="")
    assert _pages_touched([f]) == 1


# --- duplicate content, once the furniture is discounted --------------------

def _dup(pages):
    """Run the duplicate check over {path: text}, or over a list of
    (path, text) pairs when the same path has to appear twice — which is
    what a crawl of /x and /x?y produces, and a dict cannot express."""
    from clauditseo.modules.cnt import ContentModule
    from clauditseo.modules.pagefacts import PageFacts

    items = pages.items() if isinstance(pages, dict) else pages
    facts = [PageFacts(url=f"https://x.test{p}", path=p, text=t,
                       word_count=len(t.split()))
             for p, t in items]
    return ContentModule()._duplicate_content(facts)


NAV = ("home about us services contact partner portal careers blog "
       "press releases awards best workplace in finance and insurance "
       "outstanding customer service line of credit apply now ")


def test_shared_navigation_is_not_duplicate_content():
    """The bug this closes, in the shape it was found in.

    `/contact-us` shared 314 of its 379 shingles with `/careers` — the menu,
    an award banner and blog teasers — and was reported as 83% duplicate. The
    text really is on both pages; it is just not content.
    """
    found = _dup({
        "/contact-us": NAV + "call us on this number or fill in the form",
        "/careers": NAV + "we are hiring engineers and analysts join the team",
        "/faqs": NAV + "answers to the questions we are asked most often",
        "/blog": NAV + "writing about lending and small business finance",
    })
    assert [f.check_id for f in found if f.check_id == "duplicate-content"] == [], (
        "pages that share only their chrome are not duplicates of each other")
    # What they ARE is template-only, and that is said instead of nothing —
    # the whole point of the change is to be more accurate, not quieter.
    assert {f.check_id for f in found} == {"template-only-page"}


def test_genuinely_duplicated_body_text_is_still_caught():
    """The check has to keep working, or the fix is just a mute button."""
    # Long enough to clear MIN_UNIQUE_SHINGLES, which is about 44 words of a
    # page's own text — the bar a page must pass before it is compared at all.
    # The real /contact-us had 65 shingles of its own and cleared it.
    body = ("short term business loans are unsecured and funded within one "
            "business day with repayments drawn weekly from your trading "
            "account and no property security required for approval up to "
            "five hundred thousand dollars with a decision usually returned "
            "the same afternoon and funds settled before the end of the week ")
    found = _dup({
        "/loans-a": NAV + body,
        "/loans-b": NAV + body,
        "/faqs": NAV + "answers to the questions we are asked most often here",
        "/blog": NAV + "writing about lending and small business finance today",
    })
    dup = [f for f in found if f.check_id == "duplicate-content"]
    assert [f.subject for f in dup] == ["/loans-a|/loans-b"]
    assert dup[0].evidence["metric"] == "jaccard on non-chrome shingles"
    assert dup[0].evidence["site_chrome_shingles"] > 0, "chrome was found"


def test_a_page_with_almost_no_text_of_its_own_is_not_compared():
    """It would compare a handful of shingles against a handful and call any
    coincidence a duplicate. The thin-content and low-text-ratio checks
    already speak to that page, and each fact should be stated once."""
    found = _dup({
        "/thin-a": NAV + "get in touch",
        "/thin-b": NAV + "get in touch",
        "/blog": NAV + "writing about lending and small business finance today",
        "/faqs": NAV + "answers to the questions we are asked most often here",
    })
    assert found == []


def test_two_pages_alone_are_not_enough_to_know_what_chrome_is():
    """With two samples everything shared is on 100% of pages, so subtracting
    'what most pages have' would subtract the entire comparison."""
    from clauditseo.modules.cnt import _site_chrome

    assert _site_chrome([{"a b c d e"}, {"a b c d e"}]) == set()
    assert _site_chrome([{"a b c d e"}] * 3) == {"a b c d e"}


def test_accessibility_is_reported_but_never_scored():
    """The operator's call: A11Y findings are real and still raised, but a
    weak ranking signal must not move an SEO composite by 10.9%."""
    from clauditseo.engine.scoring import DEFAULT_WEIGHTS, composite
    from clauditseo.engine.types import SubScore

    assert DEFAULT_WEIGHTS["A11Y"] == 0.0

    subs = {
        "ONP": SubScore("ONP", 80.0, 0.22, detail={"nominal_weight": 0.22}),
        "A11Y": SubScore("A11Y", 10.0, DEFAULT_WEIGHTS["A11Y"],
                         detail={"nominal_weight": 0.0}),
    }
    score, out = composite(subs)
    assert score == 80.0, "a zero-weight dimension cannot move the composite"
    assert out["A11Y"].weight == 0.0
    assert out["A11Y"].score == 10.0, "and its own score is still reported"


def test_one_page_at_two_urls_is_not_a_duplicate_of_itself():
    """`/apply` and `/apply?product_type=loc` reduce to one path, and the
    check reported "/apply and /apply share 100% of their body text" on the
    real site. The underlying fact — one page at two URLs — is real, and is
    parameter duplication for the URL checks to raise, not content
    duplication between two pages."""
    # Long enough to clear MIN_UNIQUE_SHINGLES after chrome is removed, or
    # the pair is skipped for thinness and the test proves nothing about the
    # same-path guard it exists to cover.
    body = ("apply online in a few minutes with your business details and "
            "bank statements and we will come back to you the same day with "
            "an indicative offer and the documents needed to settle it, "
            "including the direct debit authority and the guarantor forms "
            "where a guarantee is required for the amount you have asked for ")
    # A list, not a dict: the path really is identical on both, which is the
    # whole bug and something a dict literal silently cannot represent.
    found = _dup([
        ("/apply", NAV + body),
        ("/apply", NAV + body),
        ("/faqs", NAV + "answers to the questions we are asked most often here"),
        ("/blog", NAV + "writing about lending and small business finance today"),
    ])
    assert [f for f in found if f.check_id == "duplicate-content"] == [], (
        "a page cannot be a duplicate of itself")


# --- a crawl that fetched nothing measured nothing ---------------------------

PAGE_CONTENT_DIMENSIONS = ("ONP", "CNT", "AIS")

#: Every dimension that draws on fetched pages, and the coverage each must
#: report when none were fetched. ONP, CNT, AIS and LOC are wholly
#: page-derived, so they measured nothing. TEC keeps the share of itself that
#: robots.txt and the sitemap answer without a page. PRF keeps nothing here
#: because its field half needs a provider and its lab half needs a page, and
#: on this crawl it has neither. A11Y runs axe over rendered pages.
BLOCKED_CRAWL_COVERAGE = {
    "ONP": 0.0, "CNT": 0.0, "AIS": 0.0, "LOC": 0.0, "A11Y": 0.0,
    "PRF": 0.0, "TEC": 0.35,
}


@pytest.mark.parametrize("dimension", sorted(BLOCKED_CRAWL_COVERAGE))
def test_a_blocked_crawl_reports_the_coverage_each_dimension_actually_had(dimension):
    """The rule is one rule — no page fetched, no page-derived claim — and it
    has to reach every module that depends on a page, not the three a probe
    happened to name. Four dimensions carrying 82% of the effective weight
    inherited `coverage=1.0` and reported full marks from an empty crawl."""
    from clauditseo.crawler.types import CrawlResult

    blocked = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[],
                          robots_blocked=["https://x.test/"])
    # A local business type, or LOC is not applicable and run_audit never
    # reaches its score() at all — the dimension would be in the parametrise
    # list and untested by it.
    result = run_audit(Site(domain="x.test", business_type="local-service"),
                       blocked, sorted(BLOCKED_CRAWL_COVERAGE), Tier.T2)

    sub = result.subscores[dimension]
    assert sub.applicable, f"{dimension} must be applicable or this proves nothing"
    expected = BLOCKED_CRAWL_COVERAGE[dimension]
    assert sub.coverage == expected, (
        f"{dimension} claims coverage {sub.coverage} where {expected} was "
        f"measurable without a page (it scored {sub.score})")
    if not expected:
        assert sub.weight == 0.0, (
            f"{dimension} carries weight {sub.weight} in the composite on no "
            f"measured evidence")


@pytest.mark.parametrize("dimension", PAGE_CONTENT_DIMENSIONS)
def test_a_blocked_crawl_scores_no_coverage_for_a_page_content_dimension(dimension):
    """A T2 run whose crawl fetched nothing still scores the dimensions that
    measure page content, because `_eligible_pages` floors the denominator at
    `max(count, 1)`: every page-rate deduction divides by a page that does not
    exist, collapses to zero, and the dimension reports full marks at full
    weight from no evidence at all.

    A blanket `Disallow: /` produces exactly this crawl, and it is routine on
    staging — the misconfiguration an SEO audit exists to catch is the one
    that makes the audit read perfect.

    Coverage and weight are the assertions, not the composite: the composite
    is a consequence, and a test that pins its value would pass again the
    moment the weights changed for some unrelated reason.
    """
    from clauditseo.crawler.types import CrawlResult

    blocked = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[],
                          robots_blocked=["https://x.test/"])
    result = run_audit(Site(domain="x.test"), blocked,
                       list(PAGE_CONTENT_DIMENSIONS), Tier.T2)

    assert result.stats["pages_crawled"] == 0
    assert result.stats["robots_blocked"] == 1

    sub = result.subscores[dimension]
    assert sub.coverage == 0.0, (
        f"{dimension} claims coverage {sub.coverage} of a site where no page "
        f"was fetched (it scored {sub.score})")
    assert sub.weight == 0.0, (
        f"{dimension} carries weight {sub.weight} in the composite on no "
        f"measured evidence")


def test_a_run_with_no_measurable_share_has_no_composite():
    """`or 1.0` made a zero denominator behave like a whole one, so a run
    where every dimension contributed nothing divided by a weight that was
    not there and returned 0.00 — a number, in the position the product uses
    for its headline score, meaning "we measured everything and it is
    perfectly bad" when the truth is that nothing was measurable.

    There is no composite in that state, and None is the only honest value:
    it cannot be averaged, plotted or compared by accident, which 0.0 can.
    """
    from clauditseo.engine.scoring import composite
    from clauditseo.engine.types import SubScore

    # Every share is zero, by each of the routes that can produce one:
    # coverage 0, weight 0, and not applicable.
    subs = {
        "ONP": SubScore("ONP", 100.0, 0.22, coverage=0.0,
                        detail={"nominal_weight": 0.22}),
        "A11Y": SubScore("A11Y", 10.0, 0.0, detail={"nominal_weight": 0.0}),
        "LOC": SubScore("LOC", 0.0, 0.13, applicable=False,
                        detail={"nominal_weight": 0.13}),
    }
    score, out = composite(subs)

    assert score is None, f"no measurable share can have no composite, got {score!r}"
    assert all(s.weight == 0.0 for s in out.values()), \
        "and nothing may carry weight in a composite that does not exist"
    # The sub-scores themselves survive: what each dimension saw is still
    # reported, which is the distinction between "not scored" and "not run".
    assert out["ONP"].score == 100.0
    assert out["ONP"].coverage == 0.0
