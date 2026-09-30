"""The Reports screen's first control generates, deliverables come before the
analyses, identical renders fold into one row, and the intro says what is
free.

Brief v2 step G (`_plans/site-screen-brief-v2-2026-09-03.md`, UX-11). The
rail's step 6 said "generate" and landed on a screen whose first control
was a filter over twenty-seven analyses; every one of twenty-five
deliverables was stale with `regenerate` at equal weight; nine rows from one
day were byte-identical; and the intro said "nothing on this page runs
anything" beside twenty-five regenerate buttons.

**What is not here.** "Tidy duplicates" was to move copies to a trash; no
route trashes a document, so nothing is offered that would. Two rows fold
as one when template, audience, audits, size and renderer all agree and
neither is part of a replacement chain - the closest reading of "identical"
the wire allows, since no content hash is carried.
"""

from __future__ import annotations

import pytest

from tests.parts import ANATOMY_READY
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
  const content = document.getElementById('content');
  const firstControl = content.querySelector('button, select, input, a.tone');
  const cards = [...content.querySelectorAll('.card')].map((c) =>
    (c.querySelector('h3')?.textContent || c.className).trim());
  const deliv = [...document.querySelectorAll('table.findings')].find((t) =>
    (t.tHead?.innerText || '').toUpperCase().includes('STILL CURRENT?'));
  return {
    firstControl: firstControl ? firstControl.tagName.toLowerCase() + ':' + (firstControl.getAttribute('aria-label') || firstControl.textContent.trim()) : null,
    generateBefore: !!(content.querySelector('.report-gen') && deliv
      && (content.querySelector('.report-gen').compareDocumentPosition(deliv) & Node.DOCUMENT_POSITION_FOLLOWING)),
    delivBeforeAnalyses: !!(deliv && document.querySelector('.analyses-all')
      && (deliv.compareDocumentPosition(document.querySelector('.analyses-all')) & Node.DOCUMENT_POSITION_FOLLOWING)),
    analysesOpen: !!document.querySelector('.analyses-all[open]'),
    lede: (document.querySelector('.view-lede')?.textContent || '').trim(),
    rows: deliv ? [...deliv.tBodies[0].rows].map((r) => ({
      text: r.innerText, dup: (r.querySelector('.dup-note')?.textContent || '').trim() })) : [],
    foldNote: (document.querySelector('button[aria-pressed]')?.parentElement?.textContent || '').trim(),
  };
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


def _open(browser, base, site_id):
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    pg.goto(f"{base}/#/sites/{site_id}/reports", wait_until="load", timeout=30_000)
    pg.wait_for_selector(".report-gen", timeout=30_000)
    pg.wait_for_selector(".stats-row", timeout=30_000)
    pg.wait_for_timeout(400)
    return pg


def test_the_first_control_generates_and_deliverables_come_before_the_analyses(browser, served):
    base, ids = served
    pg = _open(browser, base, ids["site"])
    try:
        got = pg.evaluate(_JS)
        pg.click(".analyses-all > summary")
        opened = pg.evaluate(_JS)
    finally:
        pg.close()
    assert got["firstControl"] == "select:template", got["firstControl"]
    assert got["generateBefore"] and got["delivBeforeAnalyses"], got
    assert not got["analysesOpen"] and opened["analysesOpen"], (got, opened)
    # Item 178 (08-5): rendering is free; the run report's plan is not.
    assert "writes a client plan with a model" in got["lede"] and "runs anything" not in got["lede"], got["lede"]


def test_the_rails_generate_lands_on_this_screen(browser, served):
    base, ids = served
    pg = browser.new_page()
    try:
        pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load", timeout=30_000)
        pg.wait_for_selector(".seq-step", timeout=30_000)
        # The steps are drawn from the shell and the ACTION is drawn from the
        # payload, so waiting on `.seq-step` waits for the wrong half. With no
        # run in hand yet this step's action is the span "needs an audit"
        # (`anatomy.tsx`, the Client report step: held -> triage, else
        # latestRun -> Generate, else the span), and a span has no href - which
        # is how this clause read `None` under the full suite on 2026-09-19
        # while passing alone. `data-anatomy="loaded"` is the payload's own
        # mark, which is what the assertion is actually about.
        pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
        href = pg.evaluate("""() => {
          const li = [...document.querySelectorAll('.seq-step')].find((el) =>
            (el.querySelector('.seq-name')?.textContent || '').trim() === 'Client report');
          return li?.querySelector('.seq-action a')?.getAttribute('href') || null; }""")
    finally:
        pg.close()
    assert href == f"#/sites/{ids['site']}/reports", href


def test_identical_renders_fold_into_one_row(browser, served):
    import httpx

    base, ids = served
    body = {"template": "run", "audience": "internal", "run_ids": [ids["run"]]}
    made = [httpx.post(f"{base}/api/reports", json=body, timeout=120).status_code for _ in range(2)]
    assert all(c in (200, 201) for c in made), made
    listed = httpx.get(f"{base}/api/sites/{ids['site']}/client-reports", timeout=30).json()["reports"]
    twins = [d for d in listed if d["template"] == "run" and d["audience"] == "internal"
             and d["run_ids"] == [ids["run"]] and not d["supersedes"] and not d["superseded_by"]]
    assert len(twins) >= 2, "precondition: the two generations are not both listed"
    same = len({(d["bytes"], d["renderer_version"]) for d in twins}) == 1
    assert same, f"precondition: the two renders differ in size or renderer: {twins}"

    pg = _open(browser, base, ids["site"])
    try:
        got = pg.evaluate(_JS)
        pg.click("button[aria-pressed]")
        pg.wait_for_timeout(300)
        unfolded = pg.evaluate(_JS)
    finally:
        pg.close()
    folded = [r for r in got["rows"] if r["dup"]]
    assert len(folded) == 1 and folded[0]["dup"].startswith(f"{len(twins)} identical renders"), got["rows"]
    assert len(got["rows"]) == len(listed) - (len(twins) - 1), (len(got["rows"]), len(listed))
    assert len(unfolded["rows"]) == len(listed), (len(unfolded["rows"]), len(listed))
