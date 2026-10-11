"""The part switcher keeps to its two rows (item 185; the regression from
item 278, row 5).

Item 278 row 5 put "· N seen once" beside a part's count. On the landing
strip that is room enough; in the part view's sticky switcher, four such
pills wrapped the strip to a third row at 1440 px, and a list capped at two
rows (`--switch-rows`, item 185) scrolled seven pixels inside the pinned
header on every part. In the switcher the clause reads "+N", the words kept
for a screen reader.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.needs_build import needs_build
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)

pw = pytest.importorskip("playwright")
SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_markup_and_the_rule():
    lanes = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    assert '<span className="parts-seen-plus" aria-hidden="true">{" "}+</span>' in lanes
    assert '<span className="parts-seen-word"> seen once</span>' in lanes
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    assert ".part-switch .parts-seen-sep { display: none; }" in css
    assert ".part-switch .parts-seen-plus { display: inline; }" in css


@needs_build
def test_the_switcher_does_not_scroll_at_1440(served):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings&part=crawl", wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(".part-switch-list", timeout=30_000)
            pg.wait_for_timeout(300)
            got = pg.evaluate("""() => { const ul = document.querySelector('.part-switch-list');
              return { sh: ul.scrollHeight, ch: ul.clientHeight }; }""")
        finally:
            browser.close()
    assert got["sh"] <= got["ch"] + 1, got
