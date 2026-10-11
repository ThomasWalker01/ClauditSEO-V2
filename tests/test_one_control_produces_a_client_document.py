"""One control in the product produces a client document, and its sentence
names the record rather than a picked audit (item 256, the Reports audit's
UX-02 and IP-01).

`#/reports/<run>` was an orphan route: nothing linked to it, and it offered an
enabled Generate for a run the Reports tab held, read no hold, wrote no plan,
carried no spend mark and printed the server's file path. Item 251 redirected
the address; this item deletes the screen behind it.

And the Reports tab's Generate card said "From the audit of ... - the one
selected on the client screen" and "Pick an audit in the header", after item
239 made a run report a copy of the site's record.
"""

from __future__ import annotations

from pathlib import Path

from tests.needs_build import needs_build
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)

UI = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_per_run_report_screen_is_gone_from_the_source():
    views = (UI / "views.tsx").read_text(encoding="utf-8")
    assert "export function ReportView" not in views, (
        "the unrouted per-run report screen is still in the bundle")
    # Nothing posts a document but the Reports tab's own controls and the
    # comparison screen, which makes the one template that needs a pair.
    posts = sorted(p.name for p in UI.glob("*.tsx")
                   if 'api.post' in p.read_text(encoding="utf-8")
                   and '"/api/reports"' in p.read_text(encoding="utf-8"))
    assert posts == ["reports.tsx", "views.tsx"], posts
    assert views.count('"/api/reports"') == 1, (
        "views.tsx posts a document from more than the comparison screen")
    app = (UI / "App.tsx").read_text(encoding="utf-8")
    assert "<ReportView" not in app and 'parts[0] === "reports"' in app


@needs_build
def test_the_old_address_lands_on_the_reports_tab_and_the_sentence_names_the_record(served):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1440, "height": 1100})
        try:
            pg.goto(f"{base}/#/reports/{ids['run']}", wait_until="load")
            pg.wait_for_selector(".report-gen-from", timeout=30_000)
            pg.wait_for_timeout(500)
            got = pg.evaluate("""() => ({
              hash: location.hash,
              text: document.querySelector('main, #root').innerText,
              sentence: document.querySelector('.report-gen-from').textContent.replace(/\\s+/g, ' ').trim(),
              generates: [...document.querySelectorAll('button')].filter((b) => /\\bGenerate\\b/.test(b.textContent)).length,
              buttons: [...document.querySelectorAll('button')].map((b) => b.textContent.trim()),
              link: document.querySelector('.report-gen-from a') })""")
            pg.select_option('select[aria-label="template"]', "run-free")
            pg.wait_for_timeout(200)
            free = pg.evaluate("() => document.querySelector('.report-gen-from').textContent.replace(/\\s+/g, ' ').trim()")
        finally:
            browser.close()
    assert got["hash"] == f"#/sites/{ids['site']}/reports", got["hash"]
    assert "selected on the client screen" not in got["text"], got["sentence"]
    assert "Pick an audit in the header" not in got["text"]
    assert got["sentence"].startswith("The run report is the site's record as of today: its score from the audit of "), got["sentence"]
    assert "findings dated by the audit that last measured them" in got["sentence"], got["sentence"]
    assert "analyses as last written" in got["sentence"], got["sentence"]
    assert got["link"] is None, "the sentence still links to the client screen's pick"
    assert got["generates"] == 1, (
        f"{got['generates']} Generate controls on the one screen that makes a document: {got['buttons']}")
    assert free.startswith("The audit report is the site's record as of today"), free
    assert "analyses as last written" not in free and free.endswith("Free: no model runs."), free
