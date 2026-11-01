"""A CDN's bot protection answering for a site stops the crawl and the spend
(31 Oct).

A Vercel checkpoint answered every request of an audit with a 403, ten minutes
after the same crawl had read 42 pages. The run reported robots.txt and the
sitemap as missing and the home page as broken, swept 27 sensitive paths at the
firewall, spent 24,639 tokens on four analysts with no page to read, and its
card named neither the firewall nor a way forward.
"""
from __future__ import annotations

from types import SimpleNamespace

from clauditseo.analysts.layer import run_analyst_layer
from clauditseo.crawler import crawl as crawl_module
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import Page, challenge_vendor, edge_challenge
from clauditseo.engine.types import Tier
from clauditseo.persistence.runs import _scope

HOME = "https://shop.example.test/"
CHECKPOINT = "<html><head><title>Vercel Security Checkpoint</title></head></html>"
ORDINARY = "<html><head><title>Shop</title></head><body><a href='/a'>a</a></body></html>"


def _page(url, status, body, headers=None):
    return Page(url=url, requested_url=url, status=status, content=body,
                content_type="text/html", headers=headers or {})


class Scripted:
    """Answers every URL from `answer`, and records what was asked."""

    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def fetch(self, url, *a, **k):
        self.asked.append(url)
        return self.answer(url)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _crawl(monkeypatch, answer, **kw):
    fetcher = Scripted(answer)
    monkeypatch.setattr(crawl_module, "Fetcher", lambda *a, **k: fetcher)
    monkeypatch.setattr(crawl_module.time, "sleep", lambda *_: None)
    swept = []
    import clauditseo.crawler.transport as transport
    import clauditseo.crawler.wellknown as wellknown
    import clauditseo.crawler.dnsq as dnsq
    monkeypatch.setattr(transport, "probe", lambda *_: None)
    monkeypatch.setattr(wellknown, "sweep", lambda url: swept.append(url) or {"fetched": []})
    monkeypatch.setattr(dnsq, "collect", lambda *_: None)
    return crawl(HOME, Tier.T2, security_paths=True, **kw), fetcher, swept


def test_a_challenge_is_told_by_its_exact_title_or_its_header():
    assert challenge_vendor("Vercel Security Checkpoint") == "Vercel"
    assert challenge_vendor(" Just a moment... ") == "Cloudflare"
    assert challenge_vendor("Shop", {"X-Vercel-Mitigated": "challenge"}) == "Vercel"
    assert challenge_vendor("Just a moment with our founder") is None
    assert edge_challenge(_page(HOME, 403, "<html><title>Forbidden</title>"), "page") is None


def test_a_refused_robots_request_stops_everything_after_it(monkeypatch):
    got, fetcher, swept = _crawl(monkeypatch, lambda u: _page(u, 403, CHECKPOINT))
    assert got.edge_challenge["vendor"] == "Vercel" and got.edge_challenge["at"] == "robots"
    assert len(fetcher.asked) == 1 and got.pages == [] and swept == []


def test_a_challenge_mid_crawl_keeps_what_was_read(monkeypatch):
    def answer(url):
        if url.endswith("/robots.txt"):
            return _page(url, 200, "User-agent: *\nAllow: /\n")
        return _page(url, 200, ORDINARY) if url == HOME else _page(url, 403, CHECKPOINT)

    got, _, swept = _crawl(monkeypatch, answer)
    assert [p.url for p in got.pages] == [HOME]
    assert got.truncated_by == "edge_challenge" and got.edge_challenge["at"] == "page"
    assert swept == []


def test_no_analyst_runs_on_a_crawl_that_read_nothing():
    result = SimpleNamespace(tier=Tier.T2, stats={"pages_eligible": 0})

    def refuse(*a, **k):
        raise AssertionError("a provider was reached")

    outcome = run_analyst_layer(None, "r", "shop.example.test", result, None,
                                SimpleNamespace(), provider=SimpleNamespace(analyse=refuse))
    assert outcome.ran is False and "no tokens" in outcome.reason_not_run


def test_the_scope_names_the_firewall_also_on_a_run_stored_before_it_was_recorded():
    recorded = {"vendor": "Vercel", "title": "t", "status": 403, "url": HOME, "at": "robots"}
    assert _scope({"edge_challenge": recorded})["edge_challenge"] == recorded
    old = {"pages": [{"url": HOME, "status": 403, "title": "Vercel Security Checkpoint",
                      "headers": {}}]}
    assert _scope(old)["edge_challenge"]["vendor"] == "Vercel"
    assert _scope({"pages": [{"url": HOME, "status": 200, "title": "Shop"}]})[
        "edge_challenge"] is None
