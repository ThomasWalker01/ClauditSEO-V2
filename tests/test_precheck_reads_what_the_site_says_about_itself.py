"""The precheck: page counts per scope, and where the site contradicts itself.

Every case runs against a fake fetcher. The precheck's whole promise is that it
costs four to six requests and no model, so a test that reached the network
would be measuring somebody's uptime instead of this code.
"""

from __future__ import annotations

import pytest

from clauditseo.crawler.types import Page
from clauditseo.precheck import PrecheckError, run_precheck

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://ex.test/</loc></url>
  <url><loc>https://ex.test/about</loc></url>
  <url><loc>https://ex.test/contact</loc></url>
  <url><loc>https://ex.test/secret-orphan</loc></url>
</urlset>
"""

HOME = """<html><body>
  <header><a href="/">Home</a><a href="/about">About</a></header>
  <main><a href="/blog/post-1">A post nobody navigates to</a></main>
  <footer><a href="/about">About</a><a href="/contact">Contact</a>
          <a href="https://twitter.com/x">Twitter</a></footer>
  <aside><a href="/related">Related</a></aside>
</body></html>"""


class FakeFetcher:
    """Serves a fixed map of url -> (status, body, content_type)."""

    def __init__(self, pages: dict[str, tuple[int, str]]):
        self.pages = pages
        self.asked: list[str] = []

    def fetch(self, url: str) -> Page:
        self.asked.append(url)
        status, body = self.pages.get(url, (404, ""))
        ctype = "application/xml" if url.endswith(".xml") else "text/html"
        return Page(url=url, requested_url=url, status=status,
                    content=body, content_type=ctype)

    def close(self) -> None:
        pass


@pytest.fixture
def site():
    return {
        "https://ex.test/robots.txt": (200, "User-agent: *\nSitemap: https://ex.test/sitemap.xml\n"),
        "https://ex.test/sitemap.xml": (200, SITEMAP),
        "https://ex.test/": (200, HOME),
    }


def _run(monkeypatch, pages, **kw):
    fake = FakeFetcher(pages)
    monkeypatch.setattr("clauditseo.precheck.Fetcher", lambda **_: fake)
    return run_precheck("ex.test", **kw), fake


def test_it_counts_each_scope_from_what_the_site_published(monkeypatch, site):
    r, fake = _run(monkeypatch, site)

    assert r.sitemap_state == "ok"
    assert r.scopes()["full"]["pages"] == 4
    assert r.scopes()["page"]["pages"] == 1

    # /, /about, /contact — the Twitter link is off-domain and `/related` is in
    # an aside, which is not the site's statement about its own shape.
    assert r.scopes()["nav"]["pages"] == 3
    assert r.nav_count + r.footer_count == 3, "each URL counted once, by its best region"


def test_the_two_sources_are_diffed_and_the_claim_is_not_overstated(monkeypatch, site):
    r, _ = _run(monkeypatch, site)

    assert r.not_linked == ["https://ex.test/secret-orphan"], (
        "in the sitemap, in neither nav nor footer")
    assert r.not_in_sitemap == [], "everything navigable is published"

    # /blog/post-1 is a body link. It is neither navigation nor a sitemap
    # entry, and must appear in neither list — the precheck reads one page and
    # may not imply anything about pages it never looked for.
    assert "https://ex.test/blog/post-1" not in r.not_linked
    assert "https://ex.test/blog/post-1" not in r.not_in_sitemap


def test_a_nav_page_missing_from_the_sitemap_is_reported(monkeypatch, site):
    site["https://ex.test/sitemap.xml"] = (200, SITEMAP.replace(
        "  <url><loc>https://ex.test/contact</loc></url>\n", ""))
    r, _ = _run(monkeypatch, site)
    assert r.not_in_sitemap == ["https://ex.test/contact"]


@pytest.mark.parametrize("body,status,expected", [
    ("", 404, "absent"),
    ("", 500, "unreachable"),
    ("<urlset><this is not xml", 200, "malformed"),
])
def test_an_unreadable_sitemap_never_reports_zero_pages(
        monkeypatch, site, body, status, expected):
    """`None` and `0` are different claims and the difference matters.

    Zero says "this site has no pages". None says "nobody could tell us". The
    first sends the operator to fix a crawl that is not broken.
    """
    site["https://ex.test/sitemap.xml"] = (status, body)
    r, _ = _run(monkeypatch, site)

    assert r.sitemap_state == expected
    assert r.sitemap_urls is None
    assert r.scopes()["full"]["pages"] is None
    assert r.scopes()["full"]["basis"] != ""


def test_the_disagreement_is_suppressed_when_there_is_nothing_to_disagree_with(
        monkeypatch, site):
    """No sitemap means no finding, not "every nav page is missing"."""
    site["https://ex.test/sitemap.xml"] = (404, "")
    r, _ = _run(monkeypatch, site)

    assert r.findings_meaningful is False
    assert r.not_linked == [] and r.not_in_sitemap == []
    assert r.scopes()["nav"]["pages"] == 3, "the nav count still stands on its own"


def test_url_spellings_that_mean_one_page_do_not_read_as_a_disagreement(monkeypatch, site):
    """Written first, because it is the case that fails without normalisation.

    The sitemap and the markup rarely agree on trailing slashes, scheme case or
    campaign tags. Diffing the raw strings invents orphans that are not there.
    """
    site["https://ex.test/sitemap.xml"] = (200, """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://ex.test/</loc></url>
  <url><loc>HTTPS://EX.TEST/about/</loc></url>
  <url><loc>https://ex.test/contact?utm_source=newsletter</loc></url>
</urlset>""")
    r, _ = _run(monkeypatch, site)

    assert r.not_linked == [], f"spelling differences invented orphans: {r.not_linked}"
    assert r.not_in_sitemap == [], f"spelling differences invented gaps: {r.not_in_sitemap}"


def test_a_failed_entry_page_is_an_error_not_a_nav_count_of_zero(monkeypatch, site):
    """A count of zero is a claim about the site; a dead fetch is not."""
    site["https://ex.test/"] = (503, "")
    with pytest.raises(PrecheckError, match="could not be read"):
        _run(monkeypatch, site)


def test_a_menu_the_fetcher_cannot_see_is_flagged_rather_than_asserted(monkeypatch, site):
    """A JS-rendered menu yields no links. Say so instead of reporting a fact."""
    site["https://ex.test/"] = (200, "<html><body><div id='root'></div></body></html>")
    r, _ = _run(monkeypatch, site)

    assert r.nav_unique == 0
    assert any("JavaScript" in w for w in r.warnings)


def test_it_reads_one_page_and_stops(monkeypatch, site):
    """The cost promise, asserted rather than described.

    robots + sitemap + entry page. Any growth here is the precheck quietly
    becoming a crawl, which is the one thing it must not do.
    """
    r, fake = _run(monkeypatch, site)
    assert len(fake.asked) == 3, fake.asked
    html_fetches = [u for u in fake.asked if not u.endswith((".txt", ".xml"))]
    assert html_fetches == ["https://ex.test/"]


# --- the endpoint -----------------------------------------------------------


def _api(tmp_path, monkeypatch, name="pc.db"):
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    client = TestClient(create_app(db_path=tmp_path / name))
    cid = client.post("/api/clients", json={"name": "C"}).json()["id"]
    site = client.post(f"/api/clients/{cid}/sites",
                       json={"domain": "ex.test"}).json()["id"]
    return client, site


def test_the_screen_can_tell_never_run_from_ran_and_found_nothing(
        tmp_path, monkeypatch, site):
    """`null` before, a payload after. The empty state must stay reachable.

    A scan screen that could not distinguish these two would have to guess a
    page count, which is the estimate this whole feature exists to replace.
    """
    client, site_id = _api(tmp_path, monkeypatch)
    assert client.get(f"/api/sites/{site_id}/precheck").json() is None

    monkeypatch.setattr("clauditseo.precheck.Fetcher",
                        lambda **_: FakeFetcher(site))
    posted = client.post(f"/api/sites/{site_id}/precheck", json={})
    assert posted.status_code == 200
    assert posted.json()["scopes"]["full"]["pages"] == 4

    stored = client.get(f"/api/sites/{site_id}/precheck").json()
    assert stored["scopes"]["full"]["pages"] == 4
    assert stored["checked_at"] == posted.json()["checked_at"]


def test_the_newest_row_wins_and_the_older_one_is_kept(tmp_path, monkeypatch, site):
    """History is retained: navigation churn between prechecks is a signal.

    Also pins the tie-break. `checked_at` is stamped to the second, so two
    prechecks in the same second are indistinguishable by it and the newest
    row is decided by insertion order. Without that, this case returns the
    older payload.
    """
    client, site_id = _api(tmp_path, monkeypatch, "hist.db")
    monkeypatch.setattr("clauditseo.precheck.Fetcher",
                        lambda **_: FakeFetcher(site))
    client.post(f"/api/sites/{site_id}/precheck", json={})

    thinner = dict(site)
    thinner["https://ex.test/"] = (200, "<html><footer><a href='/contact'>C</a>"
                                        "</footer></html>")
    monkeypatch.setattr("clauditseo.precheck.Fetcher",
                        lambda **_: FakeFetcher(thinner))
    client.post(f"/api/sites/{site_id}/precheck", json={})

    latest = client.get(f"/api/sites/{site_id}/precheck").json()
    assert latest["nav_unique"] == 1, "the newest row wins"
    assert latest["scopes"]["nav"]["pages"] == 1


def test_a_dead_target_is_502_not_500(tmp_path, monkeypatch, site):
    """The failure is the target site's, and the operator must be able to see
    that it was not their own install that broke."""
    client, site_id = _api(tmp_path, monkeypatch, "dead.db")
    site["https://ex.test/"] = (503, "")
    monkeypatch.setattr("clauditseo.precheck.Fetcher",
                        lambda **_: FakeFetcher(site))
    r = client.post(f"/api/sites/{site_id}/precheck", json={})
    assert r.status_code == 502
    assert "could not be read" in r.json()["detail"]


def test_a_start_url_off_the_site_is_refused(tmp_path, monkeypatch):
    client, site_id = _api(tmp_path, monkeypatch, "off.db")
    r = client.post(f"/api/sites/{site_id}/precheck",
                    json={"start_url": "https://somewhere-else.test/"})
    assert r.status_code == 422
