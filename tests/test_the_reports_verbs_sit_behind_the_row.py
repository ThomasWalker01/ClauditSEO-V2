"""`regenerate` stands inline on the newest deliverable of each template ×
audience and behind the row's overflow on every other.

Brief v3 step N (`_plans/site-screen-brief-v3-2026-09-03.md`, UI-11).
Twenty-five rows carried `regenerate` at equal weight; the older documents
are what a client was sent, not what to send next.

**Why the wire is rewritten here.** The sweep's fixture renders every
document with the current renderer, and the screen has withheld
`regenerate` from a current document since UX-39 - so no row there offers
the verb at all. The list is answered through the page's own route table
with every document marked as written by an older renderer, which is the
one state where every row offers the verb and the rule about which row
shows it inline can be read.
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

_JS = """() => {
  const deliv = [...document.querySelectorAll('table.findings')].find((t) =>
    (t.tHead?.innerText || '').toUpperCase().includes('STILL CURRENT?'));
  return deliv ? [...deliv.tBodies[0].rows].map((r) => ({
    day: r.cells[0].textContent.trim(),
    template: r.cells[1].childNodes[0]?.textContent.trim(),
    audience: r.cells[2].textContent.trim(),
    inline: [...r.cells[5].querySelectorAll(':scope > button')].map((b) => b.textContent.trim()),
    behind: [...r.cells[5].querySelectorAll('details.row-more button')].map((b) => b.textContent.trim()),
  })) : null;
}"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def test_only_the_newest_of_each_template_and_audience_regenerates_inline(browser, served):
    import httpx

    base, ids = served
    # Two documents of one template x audience, so there is an older one.
    body = {"template": "run", "audience": "internal", "run_ids": [ids["run"]]}
    for _ in range(2):
        assert httpx.post(f"{base}/api/reports", json=body, timeout=120).status_code in (200, 201)
    listed = httpx.get(f"{base}/api/sites/{ids['site']}/client-reports", timeout=30).json()["reports"]
    assert len([d for d in listed if d["template"] == "run" and d["audience"] == "internal"]) >= 2

    def older(route):
        data = route.fetch().json()
        for d in data["reports"]:
            d["renderer"], d["renderer_version"] = "superseded", "0.1"
        route.fulfill(status=200, content_type="application/json", body=json.dumps(data))

    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        pg.route(f"**/api/sites/{ids['site']}/client-reports", older)
        pg.goto(f"{base}/#/sites/{ids['site']}/reports", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".report-gen", timeout=30_000)
        pg.wait_for_selector("table.findings tbody tr", timeout=30_000)
        # Unfold identical renders so every document is a row.
        if pg.query_selector("button[aria-pressed]"):
            pg.click("button[aria-pressed]")
            pg.wait_for_timeout(300)
        rows = pg.evaluate(_JS)
    finally:
        pg.close()
    offered = [r for r in rows if not (r["inline"] == [] and r["behind"] == [])]
    assert len(offered) == len(listed), (len(offered), len(listed))
    inline = [r for r in rows if r["inline"]]
    assert all(r["inline"] == ["regenerate"] and r["behind"] == [] for r in inline), inline
    assert all(r["behind"] == ["regenerate"] for r in rows if not r["inline"]), rows
    # One inline per template x audience, and it is the newest of them.
    pairs = {(r["template"], r["audience"]) for r in rows}
    assert len(inline) == len(pairs), (inline, pairs)
    for r in inline:
        same = [x for x in rows if (x["template"], x["audience"]) == (r["template"], r["audience"])]
        assert r["day"] == max(x["day"] for x in same), (r, same)
    assert any(not r["inline"] for r in rows), "no older document stood behind the overflow"
