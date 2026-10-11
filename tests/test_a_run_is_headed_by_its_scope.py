"""A run is headed by its own scope, not by the first scope that shares its
tier (item 262, run-views IP-01; item 258, record IP-02).

`scope-nav` and `scope-site` both carry the engine word T2, and the run
heading looked its word up by tier: `ENTRIES.find((e) => e.engine ===
data.tier)`. Every T2 site sample was headed "Nav (T2)" over its own banner,
"A sample of the site". The heading reads the run's stored scope now.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.db.connection import connect
from tests.needs_build import needs_build
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)

UI = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_no_screen_looks_a_word_up_by_tier():
    for path in UI.glob("*.tsx"):
        src = path.read_text(encoding="utf-8")
        assert "e.engine === " not in src, (
            f"{path.name} looks a glossary word up by its engine tier, which two "
            "scope entries share")


@needs_build
def test_a_site_sample_is_headed_site_on_the_run_and_the_history_view(served):
    from playwright.sync_api import sync_playwright
    base, ids = served
    conn = connect(Path(ids["db"]))
    try:
        before = conn.execute("SELECT scan_scope, tier FROM audit_runs WHERE id=?",
                              (ids["run"],)).fetchone()
        with conn:
            conn.execute("UPDATE audit_runs SET scan_scope='site', tier='T2' WHERE id=?", (ids["run"],))
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            pg = browser.new_page(viewport={"width": 1440, "height": 1000})
            try:
                pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&view=audits&run={ids['run']}",
                        wait_until="load")
                pg.wait_for_selector(".history-banner", timeout=30_000)
                pg.wait_for_function(
                    "() => [...document.querySelectorAll('h2')].some((h) => /^Audit of /.test(h.textContent))",
                    timeout=30_000)
                head = pg.evaluate("""() => [...document.querySelectorAll('h2')]
                  .map((h) => h.textContent.replace(/\\s+/g, ' ').trim()).find((t) => /^Audit of /.test(t))""")
            finally:
                browser.close()
    finally:
        with conn:
            conn.execute("UPDATE audit_runs SET scan_scope=?, tier=? WHERE id=?",
                         (before[0], before[1], ids["run"]))
        conn.close()
    assert " · Site (T2" in head, head
    assert "Nav" not in head, head
