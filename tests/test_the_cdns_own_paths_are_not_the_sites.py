"""The CDN's own paths are not the site's (item 275, row 10).

Cloudflare rewrites a mailto into `/cdn-cgi/l/email-protection#...`, which
a script decodes in a browser and a crawler fetches as a 404. The crawl
followed it, and `http-status-error` and `broken-internal` each raised it -
an instruction to fix a page the site does not have.
"""

from __future__ import annotations

from clauditseo.crawler.crawl import is_edge_path


def test_the_edge_path():
    assert is_edge_path("https://t.co/cdn-cgi/l/email-protection")
    assert not is_edge_path("https://t.co/contact-us/")
    assert not is_edge_path("https://t.co/blog/cdn-cgi-explained/")


def test_the_checks_and_the_frontier_leave_it_out():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "clauditseo"
    assert "if is_edge_path(link_url):" in (root / "crawler" / "crawl.py").read_text(encoding="utf-8")
    assert "not is_edge_path(page.url)" in (root / "modules" / "tec.py").read_text(encoding="utf-8")
    assert "not is_edge_path(target)" in (root / "modules" / "links.py").read_text(encoding="utf-8")
