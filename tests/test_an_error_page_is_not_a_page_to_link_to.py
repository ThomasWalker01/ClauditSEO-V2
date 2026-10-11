"""Item 227 (Links on the page, change 1): an error page is not a page to
link to.

`links.py` computed orphans, under-linked pages and deep pages over every
HTML page the crawl stored, 404s included. So on twenty22 T3 `LNK/inlinks-low`
and `LNK/depth-deep` named `/on-page-seo/` and `/cdn-cgi/l/email-protection` -
the product's one instruction to add links to a page that does not exist. An
error page stays a TARGET, so `broken-internal` still reports the links to it.
"""

from __future__ import annotations

from tests.test_links_on_the_page import BASE, _by_check, _page, _run


def test_a_404_nothing_links_to_is_not_an_orphan():
    home = _page("/", '<a href="/reachable">Our travel team</a>')
    got = _by_check(_run(home, _page("/reachable", "<p>x</p>"),
                         _page("/gone", "<p>Not found</p>", status=404)))
    urls = {u for f in got.get("orphan", []) for u in f.affected_urls}
    assert BASE + "/gone" not in urls, urls


def test_a_404_with_one_inlink_is_not_under_linked_and_is_still_broken():
    home = _page("/", '<p><a href="/gone">the old page</a></p>')
    got = _by_check(_run(home, _page("/gone", "<p>Not found</p>", status=404)))
    thin = {u for f in got.get("inlinks-low", []) for u in f.affected_urls}
    assert BASE + "/gone" not in thin, thin
    broken = {u for f in got.get("broken-internal", []) for u in f.affected_urls}
    assert broken == {BASE + "/gone"}, sorted(got)


def test_a_deep_404_is_not_deep():
    chain = [_page("/", '<a href="/a">a</a>'), _page("/a", '<a href="/b">b</a>'),
             _page("/b", '<a href="/c">c</a>'), _page("/c", '<a href="/d">d</a>'),
             _page("/d", '<a href="/e">e</a>'),
             _page("/e", "<p>Not found</p>", status=404)]
    deep = {u for f in _by_check(_run(*chain)).get("depth-deep", []) for u in f.affected_urls}
    assert BASE + "/d" in deep, deep
    assert BASE + "/e" not in deep, deep


def test_a_link_on_an_error_page_counts_for_nothing():
    """Item 271, change 1. Item 227 took error pages out of the population
    but the link graph was still built from every HTML page, so a 404's own
    navigation was an inlink: a page only a 404 links to read as linked."""
    home = _page("/", '<a href="/linked">Linked</a>')
    got = _by_check(_run(home, _page("/linked", "<p>x</p>"),
                         _page("/only-from-404", "<p>y</p>"),
                         _page("/gone", '<p><a href="/only-from-404">a link</a></p>', status=404)))
    urls = {u for f in got.get("orphan", []) for u in f.affected_urls}
    assert BASE + "/only-from-404" in urls, urls
    assert BASE + "/linked" not in urls, urls
