"""What the catalogue costs, and what the Analyse tile says (brief v17
step AV5).

AV5 asks the drawer's Est. column for `free` or `model · USD n`, and asks
run-all's confirm never to list a free item. **No row of that drawer can
be free**, and the reason is worth stating where it can go stale: the
lanes are built from the whole playbook, so five rows carry `kind:
sweep` - and those five are the *briefs* that accompany those sweeps.
`crawl` is in `EXPERT_TOOLS`, has a prompt and spends a model. The
sweep itself runs inside the audit and is not a row here at all.

So the Est. column states the kind and then the figure, and run-all
already lists nothing free. The clause below fails the day a row without
a brief reaches the lanes, which is the day the `free` case AV5 asks for
has something to render.

What is real in AV5 is the tile: the Analyse step should say what the
audit answered for nothing before it says what is left to pay for.
"""

from __future__ import annotations

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from clauditseo.persistence.repo import now_iso
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

BASE = "https://sweeps.fixture"
HOME = BASE + "/"


def test_every_row_the_catalogue_can_show_is_a_brief():
    """Why AV5's `free` Est. cell has nothing to render.

    Stated as a clause rather than as a comment, because it is a claim
    about the product that could stop being true without anyone touching
    the drawer - and the moment it does, the Est. column needs the branch
    this test is the reason for not writing.
    """
    from clauditseo import analyses as an
    from clauditseo.analysts.expert import EXPERT_TOOLS

    catalogue = an._catalogue()
    # The playbook's sweeps do reach the lanes' index - under the id of the
    # brief that accompanies them, which is what `expert` in the playbook
    # means and why `kind` is not the question to ask about cost.
    assert {r["kind"] for r in catalogue.values()} >= {"sweep", "site"}
    lanes = an.lanes({}, {}, set(),
                     {t: {"scope": s["scope"], "tier": s.get("tier", "standard"),
                          "inputs": s.get("inputs", [])}
                      for t, s in EXPERT_TOOLS.items()})
    listed = [r["tool"] for r in (*lanes["ready"], *lanes["available"])]
    assert listed, lanes
    briefless = [t for t in listed if t not in EXPERT_TOOLS]
    assert not briefless, (
        f"{briefless} reach the catalogue without a brief behind them, so "
        "they cost nothing to run. AV5's `free` case in the Est. column now "
        "has rows to render, and run-all must stop listing them.")


def _plant(db, site_id):
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["ONP", "TEC"], "T2")
    runs.store_evidence(conn, run_id, {"pages": [
        {"url": HOME, "status": 200, "title": "Sweeps", "canonical": HOME}]})
    runs.mark_complete(conn, run_id, now_iso())
    # Committed here rather than left to a later `with conn:` block: with
    # no findings to plant there is no such block, and the run was rolled
    # back on close - which reads on screen as "needs an audit".
    conn.commit()
    conn.close()
    return run_id


@pytest.fixture(scope="module")
def served():
    server, thread, db, base = _serve("sweeps")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Sweeps Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "sweeps.fixture"}, timeout=30).json()
        run_id = _plant(db, site["id"])
        yield base, site["id"], run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_the_lanes_carry_what_the_free_half_of_the_engine_answers(served):
    """The tile's first figure comes from the server, not from the screen.

    99 checks the engine answers without a model. A screen counting them
    would be a second derivation of `check_costs()` and would disagree
    with the part pages the first time a check changed hands.
    """
    base, _site_id, run_id = served
    lanes = httpx.get(f"{base}/api/runs/{run_id}/analyses", timeout=30).json()
    from clauditseo.checks import check_costs
    free = sum(1 for v in check_costs().values() if v == "free")
    assert lanes["free_checks"] == free > 50, lanes.get("free_checks")


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


_JS = """() => {
  const cell = (tr, sel) => (tr.querySelector(sel)?.textContent || '').trim();
  return {
    rows: [...document.querySelectorAll('.catalogue-table .crow')].map((tr) => ({
      tool: cell(tr, 'code'),
      est: cell(tr, '.crow-est'),
    })),
    runAll: (document.querySelector('.run-all')?.textContent || '').trim(),
    confirm: [...document.querySelectorAll('.batch-table tbody tr code')]
      .map((c) => c.textContent.trim()),
    tiles: [...document.querySelectorAll('.seq-step')].map(
      (s) => `${(s.querySelector('.seq-name')?.textContent || '').trim()}`
             + `|${(s.querySelector('.seq-state')?.textContent || '').trim()}`),
  };
}"""


def _open(pg, base, site_id):
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
    # With no part open the shop is Analyses' own body (brief v24 step BO).
    pg.wait_for_selector(".catalogue-shop .catalogue-table .crow", timeout=30_000)


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_est_column_says_what_kind_of_cost_it_is(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    by = {r["tool"]: r["est"] for r in got["rows"]}
    assert by, got["rows"]
    # Never run here and no price on file: the remedy, with the word that
    # says why there is a price to set at all.
    assert all(e.startswith("model") for e in by.values()), by
    assert by.get("title-desc", "").startswith("model · "), by
    # And run-all lists nothing free, because there is nothing free here.
    assert not [r for r in got["rows"] if r["est"] == "free"], got["rows"]


@NEEDS_BROWSER
@pytest.mark.skipif(not (DIST / "index.html").is_file(), reason="dashboard not built")
def test_the_analyse_tile_says_what_was_free_before_what_is_owed(browser, served):
    base, site_id, _ = served
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".seq-step", timeout=30_000)
        pg.wait_for_function(
            "() => [...document.querySelectorAll('.seq-state')]"
            ".some((s) => s.textContent.includes('analysis not run'))", timeout=20_000)
        got = pg.evaluate(_JS)
    finally:
        pg.close()
    tile = [t for t in got["tiles"] if t.startswith("Analyses|")]
    assert tile, got["tiles"]
    state = tile[0].split("|", 1)[1]
    assert " free · " in state and state.endswith("analysis not run"), state
    from clauditseo.checks import check_costs
    free = sum(1 for v in check_costs().values() if v == "free")
    assert state.startswith(f"{free} free · "), state
