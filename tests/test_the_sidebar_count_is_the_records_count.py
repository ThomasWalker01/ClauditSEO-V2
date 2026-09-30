"""A part's count (the shop header's since brief v24 step BO) equals the record's "Open + regressed"
count under that part's filter, for every part; what a count counts is
one rule, the server's, and a coverage note is not a finding.

Brief v5 step S (`_plans/site-screen-brief-v5-2026-09-03.md`, UX-20). On
Birch, Accessibility read 14 in the sidebar against 13 on the record: the
part total counted the `axe-coverage` note the record had excluded since
brief v2 step F. The rule lives in `runs.is_coverage_note` now, travels as
`coverage_note` on every state row, and the part totals leave the notes
out. Candidates (seen once) are in neither count, so nothing is shown
beside the badge for them.
"""

from __future__ import annotations

import pytest

from clauditseo.anatomy import categorise
from clauditseo.persistence.runs import is_coverage_note
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]


def test_the_rule_is_the_servers():
    assert is_coverage_note("axe-coverage", "info")
    assert is_coverage_note("schema-not-assessed", "info")
    # `third-party-scripts` was the third clause of this rule until migration
    # 0054 retired the id. An Info row for it is now an id nothing emits, so
    # the rule correctly does not recognise it -- asserted in the negative so a
    # re-introduction has to decide deliberately rather than inherit.
    assert not is_coverage_note("third-party-scripts", "info")
    assert not is_coverage_note("axe-coverage", "high")
    assert not is_coverage_note("heading-skip", "info")


def test_the_wire_carries_the_rule_and_the_part_totals_leave_the_notes_out(served):
    import httpx

    base, ids = served
    states = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()["states"]
    assert all("coverage_note" in s for s in states)
    assert any(s["coverage_note"] for s in states), "the fixture holds no coverage note"
    for s in states:
        assert s["coverage_note"] == is_coverage_note(s["check_id"], s["severity"]), s["check_id"]
    anatomy = httpx.get(f"{base}/api/sites/{ids['site']}/anatomy", timeout=30).json()
    outstanding = [s for s in states if s["state"] in ("open", "regressed") and not s["coverage_note"]]
    for c in anatomy["categories"]:
        checks = {f["check_id"] for f in c["findings"]}
        mine = [s for s in outstanding if s["check_id"] in checks]
        # `["value"]`: the count carries its population since item 156, and
        # the RULE this clause is about - the badge counts the record, notes
        # excluded - is unchanged by the count carrying where it came from.
        assert c["total"]["value"] == len(mine), (c["key"], c["total"], len(mine))
        # Counted off the record, not off `findings`. That list is capped
        # at fifty by the payload and `notes` is a total over all of them,
        # so on a part with more than fifty rows the two are different
        # populations - which is how a note that sorts last (info, at the
        # end) can exist, be counted, and be invisible to this clause.
        # Found when `img-logo-not-assessed` landed on a fixture whose
        # Images part carries sixty-five rows.
        notes = [s for s in states
                 if categorise(s["check_id"], s["dimension"]) == c["key"]
                 and s["coverage_note"] and s["state"] in ("open", "regressed")]
        assert c["notes"] == len(notes), (c["key"], c["notes"], len(notes))


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def test_every_badge_equals_the_records_filtered_count(browser, served):
    base, ids = served
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        # The part's count stands on the shop's header since the sidebar's
        # retirement (brief v24 step BO); the record is filtered by its part
        # select, which writes the same `?part=`.
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".catalogue-shop .crow-part-open", timeout=30_000)
        badges = pg.evaluate("""() => [...document.querySelectorAll('.catalogue-shop .crow-part')].map((b) => ({
          part: b.querySelector('.crow-part-link')?.textContent.trim(),
          n: parseInt((b.querySelector('.crow-part-open')?.textContent || '').replace(/[^0-9]/g, '') || '-1', 10) }))""")
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&state=outstanding", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".part-select", timeout=30_000)
        keys = {o["label"]: o["value"] for o in pg.evaluate(
            "() => [...document.querySelectorAll('.part-select option')].map((o) => ({ label: o.textContent.split(' · ')[0], value: o.value }))")}
        seen = {}
        for b in badges:
            if b["n"] <= 0:
                continue
            pg.select_option(".part-select", keys[b["part"]])
            pg.wait_for_selector(".part-chip", timeout=15_000)
            pg.wait_for_timeout(200)
            seen[b["part"]] = pg.evaluate(
                "() => parseInt(document.querySelector('[aria-label=\"state filter\"] [data-state=\"outstanding\"] .tone-count-info')?.textContent || '-1', 10)")
            pg.click(".part-chip")
            pg.wait_for_function("() => !document.querySelector('.part-chip')", timeout=15_000)
    finally:
        pg.close()
    assert seen, "no part carries a count"
    for b in badges:
        if b["n"] > 0:
            assert seen[b["part"]] == b["n"], (b["part"], seen[b["part"]], b["n"])
