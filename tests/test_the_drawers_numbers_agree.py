"""The catalogue drawer's numbers agree: the header's "can run now" is the
button's count and the rows run-all would tick; a row says "unpriced"
only when its model has no price on file, and then says where to set
one; the confirm total names how many rows contributed.

Brief v5 step Q (`_plans/site-screen-brief-v5-2026-09-03.md`, UX-16). Every
row said `unpriced` while the header said `USD 0.02 to run the rest` and
the button `USD 0.01`; the header said `23 not run` while the button said
`17`, and nothing said that six need a page.

**Why the wire is rewritten here.** The fixture holds no brief history and
prices no model; the lanes are answered with a token estimate on most
rows, a price list covering every model but one, and one row on the
unpriced model, so each of the three cases can be read.
"""

from __future__ import annotations

import json
import re

import pytest

from clauditseo.analyses import cost_at
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

_JS = """() => {
  const d = document.querySelector('.catalogue-shop');
  const head = (d?.querySelector('.catalogue-head small')?.textContent || '').replace(/\\s+/g, ' ').trim();
  return {
    head,
    button: (d?.querySelector('.run-all')?.textContent || '').replace(/\\s+/g, ' ').trim(),
    rows: [...(d?.querySelectorAll('.catalogue-table tbody tr.crow') || [])].map((tr) => ({
      tool: tr.querySelector('code')?.textContent.trim(),
      model: tr.cells[3].textContent.trim().split(' ')[0],
      est: tr.cells[4].textContent.replace(/\\s+/g, ' ').trim(),
      link: tr.cells[4].querySelector('a')?.getAttribute('href') || null })),
    total: (d?.querySelector('.batch-total')?.textContent || '').replace(/\\s+/g, ' ').trim(),
    ticked: d ? d.querySelectorAll('.batch-tick:checked').length : -1,
  };
}"""


def _stub(lanes: dict) -> dict:
    rows = lanes["ready"] + lanes["available"]
    models = sorted({r["model"] for r in rows if r.get("model")})
    assert len(models) >= 1
    unpriced_model = models[-1]
    lanes["models"] = [{"model": m, "price": None if m == unpriced_model else (3, 15)} for m in models]
    seen_unpriced = False
    for i, r in enumerate(rows):
        if r.get("model") == unpriced_model:
            r["est_tokens"] = None; r["est_cost_default"] = None; seen_unpriced = True
        elif i % 2 == 0:
            r["est_tokens"] = 100_000; r["est_cost_default"] = cost_at(100_000, (3, 15))
        else:
            r["est_tokens"] = None; r["est_cost_default"] = None
    batch = [r["est_cost_default"] for r in lanes["available"]
             if r.get("est_cost_default") is not None and r["type"] != "page"]
    lanes["outstanding_cost_default"] = round(sum(batch), 4) if batch else None
    lanes["input_share"] = 0.9
    return lanes, unpriced_model, seen_unpriced


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def test_header_button_rows_and_total_say_one_thing(browser, served):
    import httpx

    base, ids = served
    real = httpx.get(f"{base}/api/runs/{ids['run']}/analyses", timeout=30).json()
    stubbed, unpriced_model, seen_unpriced = _stub(json.loads(json.dumps(real)))
    # The catalogue holds every brief that writes to a sidebar part
    # (brief v10 step AD): not triage, which ranks the rest, and not the
    # client plan, which writes the document (brief v18 step AY).
    rows = [r for r in stubbed["ready"] + stubbed["available"]
            if r["type"] != "triage" and r.get("part") not in ("none", "report")]
    can_run = [r for r in rows if r["state"] == "not_run" and r["type"] != "page"]
    need_page = [r for r in rows if r["type"] == "page" and r["state"] != "ready"]
    priced = [r for r in can_run if r["est_cost_default"] is not None]
    pg = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        pg.route("**/api/runs/*/analyses",
                 lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(stubbed)))
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load", timeout=30_000)
        # With no part open the shop is Analyses' own body (brief v24 step BO).
        pg.wait_for_selector(".catalogue-shop .catalogue-table", timeout=30_000)
        pg.wait_for_selector(".run-all", timeout=30_000)
        got = pg.evaluate(_JS)
        pg.click(".run-all")
        pg.wait_for_selector(".batch-confirm", timeout=15_000)
        asked = pg.evaluate(_JS)
    finally:
        pg.close()
    assert f"· {len(rows)} · " in got["head"] and f"{len(can_run)} can run now" in got["head"], got["head"]
    if need_page:
        assert f"{len(need_page)} need a page" in got["head"], got["head"]
    assert got["button"].startswith(f"Run all {len(can_run)}"), got["button"]
    total = round(sum(r["est_cost_default"] for r in priced), 2)
    assert f"USD {total:.2f}" in got["button"], (got["button"], total)
    if len(priced) < len(can_run):
        assert f"({len(priced)} priced, {len(can_run) - len(priced)} unpriced)" in got["button"], got["button"]
    # A row says "unpriced" only when its model has no price on file, and
    # then says where to set one; a priced model with no history says so.
    # Every cell leads with the kind of cost since brief v17 step AV5
    # (`model · USD 0.02`); what these clauses are about is the figure
    # after it, so the prefix is taken off rather than asserted twice.
    for row in got["rows"]:
        assert row["est"].startswith("model · "), row
        est = row["est"][len("model · "):]
        if "unpriced" in est:
            assert est.startswith("unpriced — set on Admin") and row["link"] == "#/admin?tab=models", row
        elif est.startswith("no estimate yet"):
            assert row["link"] is None, row
        else:
            assert re.match(r"USD ", est), row
    if seen_unpriced:
        assert any("unpriced" in r["est"] for r in got["rows"]), got["rows"]
    assert any("no estimate yet" in r["est"] for r in got["rows"]), got["rows"]
    assert asked["ticked"] == len(can_run), (asked["ticked"], len(can_run))
    assert asked["total"].startswith(f"{len(can_run)} will run · USD {total:.2f} from {len(priced)} priced row"), asked["total"]
