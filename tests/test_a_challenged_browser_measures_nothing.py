"""A firewall that refuses the browser stops the browser's passes (1 Nov).

The crawl's plain requests read 100 real pages while a Vercel checkpoint answered
the headless browser. The audit filed the checkpoint's own failure text as a
contrast fault on five pages and its paint timings as the site's speed.
"""
from __future__ import annotations

import pytest

from clauditseo import axe
from clauditseo.crawler import access
from clauditseo.crawler.types import (BrowserChallenged, CrawlResult, Page,
                                      refuse_challenge)
from clauditseo.engine.types import Tier
from clauditseo.modules.a11y import AccessibilityModule

URL = "https://shop.example.test/"


class Loaded:
    def __init__(self, title):
        self._title = title

    def title(self):
        return self._title


class Answer:
    def __init__(self, headers):
        self.headers = headers


def test_a_checkpoint_title_is_refused():
    with pytest.raises(BrowserChallenged) as got:
        refuse_challenge(Loaded("Vercel Security Checkpoint"), URL)
    assert got.value.vendor == "Vercel" and got.value.url == URL


def test_the_response_headers_name_it_whatever_the_title():
    with pytest.raises(BrowserChallenged):
        refuse_challenge(Loaded(""), URL, Answer({"x-vercel-mitigated": "challenge"}))


def test_an_ordinary_page_passes():
    refuse_challenge(Loaded("Shop"), URL, Answer({"server": "Vercel"}))
    refuse_challenge(Loaded(""), URL, None)


def test_a_page_whose_title_cannot_be_read_is_judged_by_its_headers():
    class Gone:
        def title(self):
            raise RuntimeError("closed")
    refuse_challenge(Gone(), URL, None)


def _refused(*a, **k):
    raise BrowserChallenged("Vercel", URL)


def test_a_pass_stops_at_the_first_checkpoint():
    seen = []
    got = access.each_page([URL, URL + "a"],
                           lambda url: seen.append(url) or _refused(), seen.append)
    assert got == {} and seen == [URL]


def test_any_other_failure_is_that_pages_own():
    failed = []

    def visit(url):
        if url == URL:
            raise RuntimeError("timed out")
        return "read"
    got = access.each_page([URL, URL + "a"], visit, lambda url, error: failed.append(url))
    assert got == {URL + "a": "read"} and failed == [URL]


def test_the_accessibility_pass_says_so_once_and_stops(monkeypatch):
    calls = []
    monkeypatch.setattr(axe, "available", lambda: True)
    monkeypatch.setattr(axe, "run_page", lambda url, **k: calls.append(url) or _refused())
    pages = [Page(url=URL + p, requested_url=URL + p, status=200, headers={},
                  content="<html><body><main>words</main></body></html>",
                  content_type="text/html") for p in ("", "a", "b")]
    crawl = CrawlResult(start_url=URL, tier=Tier.T3, pages=pages)
    found = AccessibilityModule().run(pages, Tier.T3, {"crawl": crawl, "site": None})
    failed = [f for f in found if f.check_id == "axe-render-failed"]
    assert len(calls) == 1 and len(failed) == 1
    assert "Vercel" in failed[0].summary
    assert not [f for f in found if f.check_id == "axe-color-contrast"]


def test_a_refused_image_pass_says_so(monkeypatch):
    from types import SimpleNamespace

    from clauditseo import imaging
    from clauditseo.persistence.runs import _images_measured
    monkeypatch.setattr(imaging, "available", lambda: True)
    monkeypatch.setattr(imaging, "measure", lambda urls, breakpoints: {})
    crawl = SimpleNamespace(pages=[])
    assert imaging.measure_for_run(crawl, {}) == ({}, True)
    token = access._run.set(None)
    try:
        run = access.open_run("site", "shop.example.test")
        run.refused = BrowserChallenged("Vercel", URL)
        assert access.refused_by() == "Vercel"
        assert imaging.measure_for_run(crawl, {}) == ({}, "refused")
    finally:
        access._run.reset(token)
    assert _images_measured({"images_measured": "refused"}, []) == "refused"
