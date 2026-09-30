"""The record opens grouped by check, instances beneath on expand, verbs at
the group level with a second press, and the flat shape one choice away.

Brief step 6 (`_plans/site-screen-reorg-brief-2026-09-03.md`, UX-01, UI-04
and the part of WF-04 the dashboard can do). The record was one row per
finding with two buttons each - 1,060 rows on the operator's own site, where
`A11Y/link-name-missing` on 41 pages read as 41 problems. A row is now a
check: its worst severity, how many findings on how many pages, and the
verbs that apply to what is under it; the instances open beneath; and
"every finding" is the flat shape behind it, remembered per site and named
on the address as `?group=none`.

**Why a browser.** The claims are about how many rows paint, what one
press paints, and what a group verb sends - and the group verb is
intercepted at the route so its requests can be counted without a real
state change bleeding into the sweep's shared fixture.

**What is not here, and why.** The brief's two new filters, "seen once"
and "on pages gone", need a server join - which audit last saw a finding,
and whether its page was in the audit in scope - that `runs.py` does not
have (`crawl_diff` compares two crawls at the page level and knows no
finding). The brief says to stop and report rather than compute either
client-side from the crawl diff, and that is what was done; the row marker
for a page not in the latest crawl waits on the same join.
"""

from __future__ import annotations

import json

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

_JS = """() => ({
  groupBy: document.querySelector('select[aria-label="group by"]')?.value || null,
  groups: [...document.querySelectorAll('tbody tr.group-row')].map((tr) => ({
    key: (tr.querySelector('code')?.textContent || '').trim(),
    expanded: tr.querySelector('.group-toggle')?.getAttribute('aria-expanded'),
    verbs: [...tr.querySelectorAll('td:last-child button')].map((b) => b.textContent.trim()),
    n: (tr.querySelector('.group-n')?.textContent || '').trim(),
  })),
  instances: document.querySelectorAll('tbody tr:not(.group-row):not(.group-confirm):has(code)').length,
  confirms: document.querySelectorAll('tbody tr.group-confirm').length,
  confirmText: (document.querySelector('tbody tr.group-confirm')?.textContent || '').trim(),
  count: (document.querySelector('.record-shape .muted')?.textContent || '').trim(),
  hash: window.location.hash,
})"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def _open(browser, base, site_id, tail=""):
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    pg.goto(f"{base}/#/sites/{site_id}?tab=all{tail}", wait_until="load", timeout=30_000)
    pg.wait_for_selector(".state-filters", timeout=30_000)
    pg.click('[aria-label="state filter"] [data-state="all"]')
    pg.wait_for_selector("tbody tr:has(code)", timeout=30_000)
    return pg


def test_the_record_opens_on_one_row_per_check_and_none_of_the_instances(browser, served):
    import httpx

    base, ids = served
    import re
    states = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()["states"]
    # Coverage notes are a strip of their own since brief v2 step F, not
    # groups: what the audit could not measure is not a finding.
    note = re.compile(r"(-not-assessed$|-coverage$|^third-party-scripts)")
    states = [s for s in states if not (s["severity"] == "info" and note.search(s["check_id"]))]
    checks = {f"{s['dimension']}/{s['check_id']}" for s in states}
    pg = _open(browser, base, ids["site"])
    try:
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["groupBy"] == "check", got
    assert len(got["groups"]) == len(checks), (
        f"{len(got['groups'])} group rows for {len(checks)} distinct checks: {got['groups']}")
    assert {g["key"] for g in got["groups"]} == checks
    assert got["instances"] == 0, "instances paint before a group is expanded"
    assert all(g["expanded"] == "false" for g in got["groups"]), got["groups"]
    assert got["count"].startswith(f"{len(checks)} check"), got["count"]
    assert len(states) > len(checks), (
        "precondition: the fixture holds no check with more than one finding, "
        "so grouping saves nothing here")


def test_a_group_opens_to_its_instances_and_the_flat_shape_is_one_choice_away(browser, served):
    base, ids = served
    pg = _open(browser, base, ids["site"])
    try:
        before = pg.evaluate(_JS)
        biggest = max(before["groups"], key=lambda g: int(g["n"].split()[0]))
        pg.click(f'tbody tr.group-row:has(code:text-is("{biggest["key"]}")) .group-toggle')
        pg.wait_for_selector("tbody tr:not(.group-row):has(code)", timeout=15_000)
        opened = pg.evaluate(_JS)
        pg.select_option('select[aria-label="group by"]', "none")
        pg.wait_for_function(
            "() => document.querySelectorAll('tbody tr.group-row').length === 0", timeout=15_000)
        flat = pg.evaluate(_JS)
    finally:
        pg.close()
    n = int(biggest["n"].split()[0])
    assert opened["instances"] == n, (biggest, opened["instances"])
    assert [g["expanded"] for g in opened["groups"] if g["key"] == biggest["key"]] == ["true"]
    assert flat["groups"] == [] and flat["instances"] > n, flat


def test_the_address_can_name_the_flat_shape(browser, served):
    base, ids = served
    pg = _open(browser, base, ids["site"], "&group=none")
    try:
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["groupBy"] == "none" and got["groups"] == [] and got["instances"] > 0, got


def test_a_group_verb_asks_before_it_moves_anything_and_then_sends_one_request_per_finding(browser, served):
    base, ids = served
    posted: list[str] = []

    def answer(route):
        posted.append(route.request.url)
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True}))

    pg = _open(browser, base, ids["site"])
    try:
        pg.route("**/api/sites/*/states/*", answer)
        got = pg.evaluate(_JS)
        target = next(g for g in got["groups"] if any(v.startswith("accept risk") for v in g["verbs"]))
        verb = next(v for v in target["verbs"] if v.startswith("accept risk"))
        n = int(verb.split("×")[1])
        # The verbs sit behind the row's overflow since brief v2 step F.
        pg.click(f'tbody tr.group-row:has(code:text-is("{target["key"]}")) details.row-more summary')
        pg.click(f'tbody tr.group-row:has(code:text-is("{target["key"]}")) button:text-is("{verb}")')
        pg.wait_for_selector("tbody tr.group-confirm", timeout=15_000)
        asked = pg.evaluate(_JS)
        assert posted == [], "a group verb moved findings before its second press"
        pg.click('tbody tr.group-confirm button:has-text("yes, accept risk")')
        # The confirmation closes once every request has been answered.
        pg.wait_for_function(
            "() => document.querySelectorAll('tbody tr.group-confirm').length === 0",
            timeout=15_000)
    finally:
        pg.close()
    assert asked["confirms"] == 1 and f"on {n} finding" in asked["confirmText"], asked
    assert len(posted) == n, (n, posted)
    assert all("/states/" in u for u in posted), posted
