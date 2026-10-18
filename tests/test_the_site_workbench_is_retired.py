"""The site Workbench is retired the way Tools was (item 264, the chat and
workbench audit's change 1).

Its own second paragraph said it was "not what has run here. For that, and to
run one, use the Analyses tab" - and then drew two `run TEC audit` spend
controls under phase 1. Nothing live linked to it: its only door was a button
in `ClientDetailView`, a view the router no longer serves. It also kept the
`#/tools` door item 188 closed everywhere else.
"""

from __future__ import annotations

from pathlib import Path

from tests.needs_build import needs_build
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)

UI = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_screen_is_gone_and_nothing_links_to_it():
    assert not (UI / "workbench.tsx").exists(), "the site Workbench screen is still in the bundle"
    for path in UI.glob("*.tsx"):
        src = path.read_text(encoding="utf-8")
        assert "/workbench`" not in src and "WorkbenchView" not in src, (
            f"{path.name} still links to or mounts the site Workbench")


@needs_build
def test_a_stored_address_lands_on_the_analyses_tab_with_its_site(served):
    from playwright.sync_api import sync_playwright
    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}/workbench", wait_until="load")
            pg.wait_for_function("() => location.hash.endsWith('?tab=findings')", timeout=30_000)
            got = pg.evaluate("() => ({ hash: location.hash, title: document.title })")
        finally:
            browser.close()
    assert got["hash"] == f"#/sites/{ids['site']}?tab=findings", got
    assert got["title"].startswith("Analyses"), got
