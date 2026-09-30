"""redirect-to-404 and meta-robots-conflict (item 137, brief v18 step BA).

Two of BA's decision-free checks (channel 20260910-0830): a redirect that lands
on an error, and meta robots disagreeing with X-Robots-Tag on indexation. Both
are crawl-state facts read off one page, so they are tested against a
hand-built crawl whose shapes are known.

redirect-temporary joined them once FEATURES F-13 captured the per-hop status
(`redirect_statuses`, parallel to `redirect_chain`): a 302/303/307 hop is a
temporary redirect on what should be a permanent move. A run crawled before the
capture has no statuses and fires nothing, which is the deferral resolving
rather than a false clean.
"""

from __future__ import annotations

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.modules.tec import TechnicalModule

_HTML = "<html><head>{head}</head><body>a body with enough words to be real</body></html>"


def _page(path, status=200, redirect_from=None, meta_robots=None, x_robots=None,
          redirect_statuses=None):
    url = f"https://x.test{path}"
    head = f'<meta name="robots" content="{meta_robots}">' if meta_robots else ""
    headers = {"x-robots-tag": x_robots} if x_robots else {}
    return Page(url=url, requested_url=redirect_from or url, status=status,
                content=_HTML.format(head=head), content_type="text/html",
                headers=headers,
                redirect_chain=[redirect_from] if redirect_from else [],
                redirect_statuses=redirect_statuses or [])


def _checks(*pages):
    out = TechnicalModule()._page_checks(CrawlResult(start_url="https://x.test/",
                                                     tier=None, pages=list(pages)))
    return {f.check_id: f for f in out}


# ---- redirect-to-404 -------------------------------------------------------

def test_a_redirect_that_ends_at_an_error_fires_high():
    hits = _checks(_page("/gone", status=404, redirect_from="https://x.test/old"))
    assert "redirect-to-404" in hits, hits
    assert hits["redirect-to-404"].severity.value == "high"


def test_a_redirect_to_a_live_page_does_not_fire():
    assert "redirect-to-404" not in _checks(
        _page("/here", status=200, redirect_from="https://x.test/old"))


def test_a_plain_404_with_no_redirect_is_not_a_redirect_to_404():
    hits = _checks(_page("/missing", status=404))
    assert "redirect-to-404" not in hits
    assert "http-status-error" in hits   # it is a broken URL, just not a redirect


# ---- meta-robots-conflict --------------------------------------------------

def test_meta_and_x_robots_disagreeing_fires_medium():
    hits = _checks(_page("/p", meta_robots="index, follow", x_robots="noindex"))
    assert "meta-robots-conflict" in hits, hits
    assert hits["meta-robots-conflict"].severity.value == "medium"


def test_they_agree_no_conflict():
    assert "meta-robots-conflict" not in _checks(
        _page("/p", meta_robots="noindex", x_robots="noindex"))


def test_only_one_present_is_not_a_conflict():
    # X-Robots-Tag alone still noindexes the page; that is not a disagreement.
    assert "meta-robots-conflict" not in _checks(_page("/p", x_robots="noindex"))
    assert "meta-robots-conflict" not in _checks(_page("/p", meta_robots="noindex"))


# ---- redirect-temporary (F-13) ---------------------------------------------

def test_a_temporary_hop_fires_redirect_temporary_low():
    hits = _checks(_page("/new", redirect_from="https://x.test/old",
                         redirect_statuses=[302]))
    assert "redirect-temporary" in hits, hits
    assert hits["redirect-temporary"].severity.value == "low"


def test_a_permanent_redirect_is_not_temporary():
    assert "redirect-temporary" not in _checks(
        _page("/new", redirect_from="https://x.test/old", redirect_statuses=[301]))


def test_a_run_without_captured_statuses_fires_nothing():
    # A run crawled before F-13: redirect_chain present, redirect_statuses empty.
    assert "redirect-temporary" not in _checks(
        _page("/new", redirect_from="https://x.test/old"))
