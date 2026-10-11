"""The strip says "seen once" beside a part's count (item 278, row 5).

The catalogue says "1 · 1 seen once"; the strip said "1", so a part whose
second row waited to be confirmed read as if the count were its whole story.
"""

from __future__ import annotations

import json

import pytest

from clauditseo import axe
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_heading_fault import browser_page  # noqa: F401  (reused fixture)


@pytest.mark.skipif(not (DIST / "index.html").is_file() or not axe.available(),
                    reason="needs the built dashboard and playwright")
def test_a_parts_seen_once_rows_are_said_beside_its_count(served, browser_page):
    base, ids = served
    picked = {}

    def anatomy(route):
        data = route.fetch().json()
        c = next(c for c in data["categories"] if c.get("group") != "workflow")
        c["seen_once"] = {**c["total"], "value": 2}
        picked["key"] = c["key"]
        route.fulfill(status=200, content_type="application/json", body=json.dumps(data))

    browser_page.route("**/api/sites/*/anatomy*", anatomy)
    browser_page.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
    browser_page.wait_for_selector(".cl-landing .cl-parts .parts-link", timeout=15_000)
    got = browser_page.evaluate("""(key) => {
      const a = document.querySelector(`.cl-parts .cl-part-${key}`);
      return a && { said: (a.querySelector('.parts-seen-once')?.textContent || '').trim(),
                    label: a.getAttribute('aria-label') };
    }""", picked["key"])
    assert got, picked
    assert got["said"].replace("\\u00a0", " ").endswith("2 seen once"), got
    assert ", 2 seen once" in got["label"], got
