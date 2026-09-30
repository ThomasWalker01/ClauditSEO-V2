"""Run-all, in both scopes, opens one confirm panel in the drawer whose
total is the sum of the ticked rows at their default models; a page-scoped
brief is never in a batch; a read brief is unticked with a re-run tick;
the commit posts the ticked briefs and nothing else.

Brief v4 Item 3f (`_plans/site-screen-brief-v4-2026-09-03.md`). The live
catalogue's "USD 0.04 for all 23" was the cheapest-model floor - the median
of what past runs cost at whatever ran them - and must not appear as the
batch total. The estimate at the default is priced on the server
(`analyses.cost_at`) under one stated input share.

**Why the wire is rewritten here.** The sweep's fixture holds no brief
history, so every estimate there is "unpriced" and a total would be
vacuous; the lanes are answered through the page's route table with a
token estimate and a default-model price on every row, and a floor that
differs from the sum, so the rule can be read.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.analyses import INPUT_SHARE, cost_at
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_the_part_page_is_three_blocks import three_block_parts
from tests.parts import ANATOMY_READY, open_part

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]


def test_the_estimate_is_priced_at_the_model_under_the_stated_share():
    assert cost_at(None, (3, 15)) is None and cost_at(1000, None) is None
    assert cost_at(1_000_000, (3, 15)) == round(INPUT_SHARE * 3 + (1 - INPUT_SHARE) * 15, 4)
    assert INPUT_SHARE == 0.9


_JS = """() => {
  const panel = document.querySelector('.batch-confirm');
  return {
    panel: !!panel,
    heading: (panel?.querySelector('h4')?.textContent || '').trim(),
    rows: panel ? [...panel.querySelectorAll('tbody tr.batch-row')].map((tr) => ({
      tool: tr.querySelector('code')?.textContent.trim(),
      ticked: tr.querySelector('.batch-tick').checked,
      disabled: tr.querySelector('.batch-tick').disabled,
      est: tr.cells[3].textContent.trim(), note: tr.cells[4].textContent.trim() })) : [],
    total: (panel?.querySelector('.batch-total')?.textContent || '').trim(),
    runAll: (document.querySelector('.run-all')?.textContent || '').trim(),
    runPart: (document.querySelector('.run-part')?.textContent || '').trim(),
    live: [...document.querySelectorAll('.crow-part .cat-live')].length,
  };
}"""


def _stub(lanes: dict) -> dict:
    """Every row estimated: 100k tokens at a default priced 3/15, and a floor
    that is not the sum - the fixture's own `est_cost` medians would be."""
    floor = 0.0
    for i, row in enumerate(lanes["ready"] + lanes["available"]):
        row["est_tokens"] = 100_000 * (i + 1)
        row["est_seconds"] = 30 * (i + 1)
        row["est_cost"] = 0.01 * (i + 1)          # the cheapest-model floor
        row["est_cost_default"] = cost_at(row["est_tokens"], (3, 15))
        if row in lanes["available"]:
            floor += row["est_cost"]
    lanes["outstanding_cost"] = round(floor, 4)
    lanes["outstanding_cost_default"] = round(sum(
        r["est_cost_default"] for r in lanes["available"] if r["type"] != "page"), 4)
    lanes["input_share"] = INPUT_SHARE
    return lanes


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def test_run_all_opens_one_panel_whose_total_is_the_ticked_rows_at_their_defaults(browser, served):
    import httpx

    base, ids = served
    real = httpx.get(f"{base}/api/runs/{ids['run']}/analyses", timeout=30).json()
    stubbed = _stub(json.loads(json.dumps(real)))
    by_tool = {r["tool"]: r for r in stubbed["ready"] + stubbed["available"]}
    posted: list[str] = []
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.route("**/api/runs/*/analyses",
                 lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(stubbed)))
        pg.route("**/api/runs/*/expert/*",
                 lambda r: (posted.append(r.request.url.rsplit("/", 1)[1]),
                            r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True})))
                 if r.request.method == "POST" else r.continue_())
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load", timeout=30_000)
        # With no part open the shop is Analyses' own body (brief v24 step BO).
        pg.wait_for_selector(".catalogue-shop .catalogue-table", timeout=30_000)
        pg.wait_for_selector(".run-all", timeout=30_000)
        before = pg.evaluate(_JS)
        pg.click(".run-all")
        pg.wait_for_selector(".batch-confirm", timeout=15_000)
        got = pg.evaluate(_JS)
        # A page-scoped brief cannot be ticked; a read brief can, for a re-run.
        page_row = next((r for r in got["rows"] if by_tool[r["tool"]]["type"] == "page"), None)
        read_row = next((r for r in got["rows"] if by_tool[r["tool"]]["state"] == "ready"
                         and by_tool[r["tool"]]["type"] != "page"), None)
        if read_row:
            pg.check(f'.batch-row:has(code:text-is("{read_row["tool"]}")) .batch-tick')
        after_tick = pg.evaluate(_JS)
        pg.click(".batch-commit")
        pg.wait_for_timeout(600)
        landed = pg.evaluate(_JS)
    finally:
        pg.close()
    assert before["panel"] is False and before["runAll"].startswith("Run all"), before
    assert got["panel"] and got["heading"].startswith("Run "), got["heading"]
    ticked = [r for r in got["rows"] if r["ticked"]]
    assert ticked and all(by_tool[r["tool"]]["state"] == "not_run" and by_tool[r["tool"]]["type"] != "page"
                          for r in ticked), ticked
    want = round(sum(by_tool[r["tool"]]["est_cost_default"] for r in ticked), 2)
    assert f"USD {want:.2f}" in got["total"], (got["total"], want)
    assert f"USD {stubbed['outstanding_cost']:.2f}" not in got["total"], "the floor is the batch total"
    if page_row:
        assert not page_row["ticked"] and page_row["disabled"] and "not in this batch" in page_row["note"], page_row
    if read_row:
        assert not read_row["ticked"] and not read_row["disabled"] and "tick to re-run" in read_row["note"], read_row
        assert next(r for r in after_tick["rows"] if r["tool"] == read_row["tool"])["ticked"]
    expected = sorted(r["tool"] for r in after_tick["rows"] if r["ticked"])
    assert sorted(posted) == expected, (sorted(posted), expected)
    assert "content-brief" not in posted
    assert not landed["panel"], "the panel stands after the commit"


def test_the_parts_own_button_scopes_the_panel_to_the_part(browser, served):
    import httpx

    base, ids = served
    real = httpx.get(f"{base}/api/runs/{ids['run']}/analyses", timeout=30).json()
    stubbed = _stub(json.loads(json.dumps(real)))
    anatomy = httpx.get(f"{base}/api/sites/{ids['site']}/anatomy", timeout=30).json()
    not_run = {r["tool"] for r in stubbed["available"] if r["state"] == "not_run" and r["type"] != "page"}
    # Not a part that renders as three blocks (brief v13 step AO): its
    # briefs are run from the actions row, and `Run the N not run` is the
    # old page's control. Read from the registry rather than listed here,
    # because this list was written twice and only one copy was kept.
    three_blocks = three_block_parts()
    part = next(c for c in anatomy["categories"]
                if c["group"] != "workflow" and c["key"] not in three_blocks
                and set(c["tools"]) & not_run)
    mine = [t for t in part["tools"] if t in not_run]
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.route("**/api/runs/*/analyses",
                 lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(stubbed)))
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        open_part(pg, part["label"])
        pg.wait_for_selector(".run-part", timeout=30_000)
        got = pg.evaluate(_JS)
        pg.click(".run-part")
        pg.wait_for_selector(".batch-confirm", timeout=15_000)
        panel = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["runPart"].startswith(f"Run the {len(mine)} not run"), got["runPart"]
    assert panel["heading"].startswith(f"Run {len(mine)} analys"), panel["heading"]
    assert {r["tool"] for r in panel["rows"] if r["ticked"]} == set(mine), panel["rows"]
    assert all(r["tool"] in part["tools"] for r in panel["rows"]), panel["rows"]
