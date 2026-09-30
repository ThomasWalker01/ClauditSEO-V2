"""The Speed free checks read the performance trace (item 141, brief v19 step
BC): the thirteen sweep checks the browser-trace pass feeds, judged here in the
PRF module. The trace itself is `clauditseo.perf`'s; these tests pin the
judgement — each check fires on a defect trace, stays silent on a clean one,
reads the site's budgets where set, and emits nothing where no trace was taken
(so a rendererless run says the trace was not taken rather than inventing a
value). The capture is exercised by `test_the_perf_capture` beside this."""

from __future__ import annotations

from collections import Counter

from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Tier
from clauditseo.modules.prf import PerformanceModule

MOD = PerformanceModule()


def _page(url="https://x.test/"):
    return Page(url=url, requested_url=url, status=200,
                content_type="text/html", content="<html></html>")


def _run(trace, site=None, url="https://x.test/"):
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[_page(url)])
    ctx = {"crawl": crawl, "perf_traces": {url: trace} if trace else {}, "site": site}
    return MOD._trace_checks(crawl, ctx)


def _fired(trace, **kw):
    return {f.check_id for f in _run(trace, **kw)}


DEFECT = {
    "device_profile": "d", "ttfb_ms": 1200, "fcp_ms": 900,
    "lcp": {"ms": 4200, "element": "img.hero", "url": "https://x.test/hero.avif",
            "is_image": True, "sub_parts": {"ttfb": 1200, "load_delay": 500,
                                            "load_time": 800, "render_delay": 1700}},
    "cls": {"value": 0.30, "shifts": [{"value": 0.3, "sources": ["div#banner"]}]},
    "tbt_ms": 650,
    "long_tasks": [{"start_ms": 1000, "duration_ms": 200,
                    "scripts": [{"url": "https://cdn.ads.com/t.js", "ms": 180}]}],
    "resources": [
        {"url": "https://x.test/theme.css", "type": "css", "bytes": 180000,
         "transfer": 190000, "blocking": True, "compression": "none",
         "cache_control": None, "whitespace_ratio": 0.35,
         "coverage": {"used": 20000, "total": 180000}},
        {"url": "https://cdn.ads.com/t.js", "type": "script", "bytes": 400000,
         "transfer": 412000, "blocking": False, "compression": "br",
         "cache_control": "max-age=60", "whitespace_ratio": 0.02,
         "coverage": "unavailable"},
    ],
    "fonts": [{"family": "Inter", "display": None, "preloaded": False,
               "swap_observed": "unavailable"}],
    "head_rendered": "<head></head>", "frames": "unavailable",
}

CLEAN = {
    "device_profile": "d", "ttfb_ms": 200, "fcp_ms": 700,
    "lcp": {"ms": 1800, "element": "h1", "url": None, "is_image": False,
            "sub_parts": {"ttfb": 200, "load_delay": 0, "load_time": 0, "render_delay": 1600}},
    "cls": {"value": 0.02, "shifts": []},
    "tbt_ms": 40, "long_tasks": [],
    "resources": [
        {"url": "https://x.test/app.css", "type": "css", "bytes": 8000,
         "transfer": 3000, "blocking": False, "compression": "br",
         "cache_control": "max-age=31536000, immutable", "whitespace_ratio": 0.03,
         "coverage": {"used": 7000, "total": 8000}},
    ],
    "fonts": [{"family": "Inter", "display": "swap", "preloaded": True,
               "swap_observed": True}],
    "head_rendered": "<head></head>", "frames": "unavailable",
}


def test_every_free_trace_check_fires_on_a_defect_trace():
    fired = _fired(DEFECT)
    for check in ("lcp-slow", "cls-high", "inp-long-tasks", "ttfb-slow",
                  "render-blocking", "unused-css-js", "uncompressed",
                  "no-cache-headers", "unminified", "third-party-weight",
                  "font-blocking"):
        assert check in fired, check


def test_third_party_weight_attributes_main_thread_ms_by_host():
    """The ledger's second axis (item 141 #3): a long task's per-script
    attribution (Long Animation Frames) charges its ms to the script's host.
    cdn.ads.com ships 412 KB and runs 180 ms on the main thread."""
    row = next(f for f in _run(DEFECT) if f.check_id == "third-party-weight")
    host = next(h for h in row.evidence["hosts"] if h["host"] == "cdn.ads.com")
    assert host["bytes"] == 412000 and host["main_thread_ms"] == 180
    # A host with only main-thread ms and no bytes still surfaces.
    ms_only = {**CLEAN, "long_tasks": [
        {"start_ms": 500, "duration_ms": 120,
         "scripts": [{"url": "https://tag.example/t.js", "ms": 90}]}]}
    hosts = {h["host"] for f in _run(ms_only) if f.check_id == "third-party-weight"
             for h in f.evidence["hosts"]}
    assert "tag.example" in hosts


def test_the_bad_vitals_take_the_poor_band_severity():
    by = {(f.check_id): f.severity.value for f in _run(DEFECT)}
    # LCP 4200 > 4000 and CLS 0.30 > 0.25 are both in the poor band → HIGH.
    assert by["lcp-slow"] == "high" and by["cls-high"] == "high"
    # A needs-improvement LCP (2500 < 3200 < 4000) is MEDIUM, not HIGH.
    ni = {**DEFECT, "lcp": {**DEFECT["lcp"], "ms": 3200}}
    ni_by = {f.check_id: f.severity.value for f in _run(ni)}
    assert ni_by["lcp-slow"] == "medium"


def test_a_clean_trace_fires_nothing():
    assert _fired(CLEAN) == set()


def test_no_trace_is_silent_not_zero():
    # A page whose record says the trace was not taken emits nothing here.
    assert _fired({"traced": False}) == set()
    assert _fired(None) == set()


def test_page_weight_reads_total_transfer_from_the_trace():
    heavy = {**CLEAN, "resources": [
        {"url": "https://x.test/big.js", "type": "script", "bytes": 2_000_000,
         "transfer": 1_200_000, "blocking": False, "compression": "br",
         "cache_control": "max-age=60", "whitespace_ratio": 0.02, "coverage": "unavailable"}]}
    assert "page-weight" in _fired(heavy)
    # Under budget → silent.
    assert "page-weight" not in _fired(CLEAN)


def test_a_variant_with_unavailable_fields_does_not_crash_or_false_fire():
    # Item 154: an unavailable field degrades rather than reading as a defect.
    tr = {**CLEAN, "resources": [
        {"url": "https://x.test/a.css", "type": "css", "bytes": 5000,
         "transfer": 2000, "blocking": "unavailable", "compression": "unavailable",
         "cache_control": "unavailable", "whitespace_ratio": "unavailable",
         "coverage": "unavailable"}]}
    fired = _fired(tr)
    for check in ("render-blocking", "uncompressed", "no-cache-headers",
                  "unminified", "unused-css-js"):
        assert check not in fired, check


def test_the_site_budgets_override_the_defaults():
    class _Tight:
        ttfb_good = "100"
    # TTFB 200 passes the default 800 but fails a tight 100.
    ok = {**CLEAN}
    assert "ttfb-slow" not in _fired(ok)
    assert "ttfb-slow" in _fired(ok, site=_Tight())
