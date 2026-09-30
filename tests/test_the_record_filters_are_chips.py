"""The record's state and severity filters are chips with their counts, and
one press reaches each set.

Brief v3 step L (`_plans/site-screen-brief-v3-2026-09-03.md`, UX-13). The
filters were two selects, and the sets the operator reaches for most -
what is open, what is fixed, what is on a page the latest crawl did not
fetch - were a dropdown away each. Every set is one press now, the press
says how many it reaches, and the chips are the address's `?state=`
values, so a stored link and a press mean the same.

**Not offered, and said.** "Seen once" - the findings one audit has seen -
needs a field the record does not carry, which audit first saw a finding;
the brief asks for it to be reported rather than guessed.
"""

from __future__ import annotations

import re

import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

COVERAGE = re.compile(r"(-not-assessed$|-coverage$|^third-party-scripts)")

_JS = """() => ({
  selects: document.querySelectorAll('.state-filters select, .severity-filters select').length,
  states: [...document.querySelectorAll('[aria-label="state filter"] [data-state]')].map((b) => ({
    value: b.dataset.state, pressed: b.getAttribute('aria-pressed') === 'true',
    n: parseInt(b.querySelector('.tone-count-info')?.textContent || '-1', 10) })),
  severities: [...document.querySelectorAll('[aria-label="severity filter"] [data-severity]')].map((b) => ({
    value: b.dataset.severity, pressed: b.getAttribute('aria-pressed') === 'true',
    n: parseInt(b.querySelector('.tone-count-info')?.textContent || '-1', 10) })),
  rows: document.querySelectorAll('tbody tr:has(code)').length,
  hash: window.location.hash,
})"""

SETS = {
    "outstanding": lambda s: s["state"] in ("open", "regressed"),
    "fixed": lambda s: s["state"] == "fixed",
    "accepted-risk": lambda s: s["state"] == "accepted-risk",
    "withdrawn": lambda s: s["state"] == "withdrawn",
    "candidate": lambda s: s["state"] == "candidate",
    "all": lambda s: True,
}


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def test_every_set_is_one_press_and_the_chip_counts_what_it_reaches(browser, served):
    import httpx

    base, ids = served
    states = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()["states"]
    findings = [s for s in states if not (s["severity"] == "info" and COVERAGE.search(s["check_id"]))]
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&group=none", wait_until="load", timeout=30_000)
        pg.wait_for_selector('[aria-label="state filter"] [data-state]', timeout=30_000)
        got = pg.evaluate(_JS)
        assert got["selects"] == 0, "a select still stands where the chips are"
        counts = {c["value"]: c["n"] for c in got["states"]}
        for value, test in SETS.items():
            assert counts[value] == sum(1 for s in findings if test(s)), (value, counts)
        assert "gone" in counts and "seen-once" not in counts, counts
        # One press each, and the rows follow.
        seen = {}
        for value in SETS:
            pg.click(f'[aria-label="state filter"] [data-state="{value}"]')
            pg.wait_for_timeout(200)
            after = pg.evaluate(_JS)
            assert [c["value"] for c in after["states"] if c["pressed"]] == [value], after["states"]
            seen[value] = after["rows"]
    finally:
        pg.close()
    for value, test in SETS.items():
        want = min(50, sum(1 for s in findings if test(s)))
        assert seen[value] == want, (value, seen[value], want)


def test_the_severity_chips_count_what_they_reach(browser, served):
    import httpx

    base, ids = served
    states = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()["states"]
    findings = [s for s in states if not (s["severity"] == "info" and COVERAGE.search(s["check_id"]))]
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&group=none&state=all", wait_until="load",
                timeout=30_000)
        pg.wait_for_selector('[aria-label="severity filter"] [data-severity]', timeout=30_000)
        got = pg.evaluate(_JS)
        sev = next(c for c in got["severities"] if c["value"] != "all" and c["n"] > 0)
        pg.click(f'[aria-label="severity filter"] [data-severity="{sev["value"]}"]')
        pg.wait_for_timeout(200)
        after = pg.evaluate(_JS)
    finally:
        pg.close()
    for c in got["severities"]:
        want = len(findings) if c["value"] == "all" else sum(1 for s in findings if s["severity"] == c["value"])
        assert c["n"] == want, (c, want)
    assert after["rows"] == min(50, sev["n"]), (after["rows"], sev)
