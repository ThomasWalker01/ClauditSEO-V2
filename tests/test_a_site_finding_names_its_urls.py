"""A finding about several URLs names them (item 275, row 10).

Crawl's site-subject cards ("8 sitemap URLs not reached") said a count and
showed no URL, though the finding stores them (`affected_urls`, with
`affected_total` where the check capped its list). The card lists them
behind a disclosure, with the total where it kept fewer.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_list():
    src = SRC.read_text(encoding="utf-8")
    body = src.split("function SiteBriefFixBody", 1)[1].split("\n}\n", 1)[0]
    assert '<details className="fix-urls">' in body
    assert "` of ${fix.affectedTotal} found`" in body
