"""Item 164: page mode shows the site's record under a page label.

`RecordPane` read `data.states` - the whole record - in page mode, so the Record
on twenty22 narrowed to `/` said "2 checks - 62 findings" under a chip reading
`narrowed to /`. The pane now narrows once, from the address, with the same
`narrowStates` the anatomy uses.

Driven against the accessibility sweep's fixture. The page chosen is the one
the fixture's record names on the most open rows (home excepted), and the test requires rows
off that page, so the site count and the page count differ and the old code
fails.
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlsplit

import pytest

pytest.importorskip("playwright")

from tests.test_a11y_rendered import served  # noqa: E402,F401  (module fixture)
from tests.needs_build import needs_build

_COUNT = """() => {
  const spans = [...document.querySelectorAll('span.muted')]
    .map((e) => e.textContent.trim())
    .filter((t) => /^\\d+ (findings?|of \\d+)/.test(t));
  return spans[0] || null;
}"""


def _path(u: str) -> str:
    return urlsplit(u).path or "/"


def _count(pg) -> int:
    got = pg.evaluate(_COUNT)
    assert got, "the record's count line is on screen"
    return int(re.match(r"(\d+)", got).group(1))


@needs_build
def test_page_mode_narrows_the_record_to_the_page(served):
    import httpx
    from playwright.sync_api import sync_playwright
    base, ids = served
    site = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()
    open_rows = [s for s in site["states"] if s["state"] in ("open", "regressed")
                 and not s.get("coverage_note") and not re.search(r"-(not-assessed|coverage)$", s["check_id"])]
    # Not the home page: the address drops a page scope naming the start URL,
    # which reads as the whole site.
    per_page = Counter(_path(u) for s in open_rows
                       for u in set(s["affected_urls"]) if u.startswith("http") and _path(u) != "/")
    page_path, _n = per_page.most_common(1)[0]
    page_url = next(u for s in open_rows for u in s["affected_urls"] if _path(u) == page_path)
    want = sum(1 for s in open_rows if any(_path(u) == page_path for u in s["affected_urls"]))
    assert want < len(open_rows), "the fixture must hold rows off the chosen page"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1400, "height": 900})
        try:
            counts = []
            pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&group=none", wait_until="load")
            pg.wait_for_selector(".state-filters", timeout=30_000)
            pg.wait_for_timeout(500)
            counts.append(_count(pg))
            # Into page mode in place, as the mode switch does: a hash change,
            # not a reload (Playwright's goto does not announce a hash-only move).
            pg.evaluate("(h) => { location.hash = h; }",
                        f"#/sites/{ids['site']}?tab=all&group=none&page={page_url}")
            pg.wait_for_timeout(800)
            counts.append(_count(pg))
        finally:
            browser.close()
    site_count, page_count = counts
    assert site_count == len(open_rows), (site_count, len(open_rows))
    assert page_count == want, (page_count, want, page_path)


def test_the_record_chip_and_the_record_rows_read_one_set():
    """One narrowing, before every read: no `data.states` read survives in the
    pane, so no count or row can come from the unnarrowed record."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src" / "pane_record.tsx").read_text(encoding="utf-8")
    assert "narrowStates(data?.states ?? [], page)" in src
    assert "data.states" not in src
