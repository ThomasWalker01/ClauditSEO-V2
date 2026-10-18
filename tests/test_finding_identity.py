"""A run cannot hold two findings with one fingerprint.

`fingerprint = sha256(dimension:check_id:subject)` and `finding_states` is
keyed on it, so the fingerprint IS the identity. Two findings sharing one
inside a single run is the engine contradicting its own definition.

It happened wherever a page was reachable at two URLs. `/apply` and
`/apply?product_type=loc` reduce to one path, so every per-page check produced
two identical findings — same check, same summary, same fingerprint. One real
run held 469 findings against 462 fingerprints, the client report listed 469,
and the app's own headline said 462. The same root cause produced
"/apply and /apply share 100% of their body text" in the duplicate-content
check, which was fixed there and only there.
"""

from __future__ import annotations

from clauditseo.engine.core import _merge_by_identity
from clauditseo.engine.types import Finding, Severity


def _f(check_id: str, subject: str, urls: list[str], summary: str = "x"):
    return Finding(dimension="ONP", check_id=check_id, severity=Severity.MEDIUM,
                   summary=summary, subject=subject, affected_urls=urls)


def test_one_page_at_two_urls_produces_one_finding():
    got = _merge_by_identity([
        _f("h1-missing", "/apply", ["https://x.test/apply"]),
        _f("h1-missing", "/apply", ["https://x.test/apply?product_type=loc"]),
    ])
    assert len(got) == 1


def test_both_urls_survive_the_merge():
    """Merged, not dropped. Both are real and the operator has to fix the
    page at both, so discarding one answers "which URLs are affected" with
    less than was measured."""
    got = _merge_by_identity([
        _f("h1-missing", "/apply", ["https://x.test/apply"]),
        _f("h1-missing", "/apply", ["https://x.test/apply?product_type=loc"]),
    ])
    assert got[0].affected_urls == ["https://x.test/apply",
                                    "https://x.test/apply?product_type=loc"]


def test_a_repeated_url_is_not_listed_twice():
    got = _merge_by_identity([
        _f("h1-missing", "/apply", ["https://x.test/apply"]),
        _f("h1-missing", "/apply", ["https://x.test/apply"]),
    ])
    assert got[0].affected_urls == ["https://x.test/apply"]


def test_different_checks_on_one_page_stay_separate():
    """Only identity merges. Two different defects on the same page are two
    findings, and collapsing them would hide one."""
    got = _merge_by_identity([
        _f("h1-missing", "/apply", ["https://x.test/apply"]),
        _f("img-alt-missing", "/apply", ["https://x.test/apply"]),
    ])
    assert len(got) == 2


def test_the_same_check_on_different_pages_stays_separate():
    got = _merge_by_identity([
        _f("h1-missing", "/apply", ["https://x.test/apply"]),
        _f("h1-missing", "/contact", ["https://x.test/contact"]),
    ])
    assert len(got) == 2


def test_order_is_preserved_so_a_report_does_not_reshuffle():
    got = _merge_by_identity([
        _f("a", "/one", []), _f("b", "/two", []), _f("a", "/one", []),
        _f("c", "/three", []),
    ])
    assert [f.check_id for f in got] == ["a", "b", "c"]


def test_the_stored_count_matches_the_fingerprint_count(tmp_path):
    """The end-to-end property. The app's headline counts fingerprints and the
    report counted rows; they must be the same number."""
    import clauditseo.modules  # noqa: F401
    from clauditseo.crawler.crawl import crawl
    from clauditseo.crawler.types import TierBudget
    from clauditseo.engine.core import run_audit
    from clauditseo.engine.types import Site, Tier
    from tests.conftest import FixtureSite

    # One page, two URLs — the shape that caused it.
    bad = ("<html lang=en><head><title>t</title></head><body>"
           "<h2>no h1 here</h2><img src=/i.png>"
           "<a href='/apply?product_type=loc'>loc</a></body></html>")
    routes = {"/robots.txt": (200, {"Content-Type": "text/plain"},
                              "User-agent: *\nAllow: /\n"),
              "/": (200, {}, "<html lang=en><head><title>t</title></head>"
                             "<body><a href='/apply'>a</a></body></html>"),
              "/apply": (200, {}, bad),
              "/apply?product_type=loc": (200, {}, bad)}
    site = FixtureSite(routes).start()
    try:
        crawled = crawl(site.base_url + "/", Tier.T2, budget=TierBudget(
            max_pages=10, request_timeout_s=5, wall_clock_s=30, delay_s=0))
        result = run_audit(Site(domain=site.base_url + "/"), crawled,
                           ["ONP"], Tier.T2)
    finally:
        site.stop()

    prints = [f.fingerprint for f in result.findings]
    assert len(prints) == len(set(prints)), (
        "the run holds two findings with one fingerprint; the app would "
        "count them once and the report would list them twice")
