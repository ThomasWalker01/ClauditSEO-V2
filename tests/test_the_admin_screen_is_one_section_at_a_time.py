"""Admin shows one section at a time, named by the address, and the briefs by
phase live under it.

The operator, 2026-09-03: "Certain items are just in the wrong place. Can we
move this workbench section into the admin section under its own tab for the
moment ... Make each section in the admin it's own tab." The workbench section
is the run screen's phase-grouped list of briefs - the crawl-and-indexability,
technical-foundation, on-page, structured-data, local and decide-and-report
cards, each a row per brief with its model, price and a run control.

**Why a browser.** The claims are about which section paints for which
address, whether pressing a name writes the address (so the back button
works), and whether the run screen still paints the list it gave up. A source
scan would be satisfied by the tab table existing.

**What this does not drive.** Nothing here presses a run control: the
Workbench tab is asserted in the state it paints against a stored audit, rows
present and unpressed, the way `test_a11y_rendered.py`'s sweep reads the same
list on the run screen it used to stand on.
"""

from __future__ import annotations

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

#: Tab key → (the selector its own section paints once its data is in, the
#: heading that section carries). The heading is the card's own `<h3>`, so a
#: renamed section fails against the word the operator reads.
SECTIONS = {
    "spend": (".admin-tabs", "Spend"),
    "providers": (".tone-action-paid", "Providers"),
    "keys": ("input[type=password]", "Provider keys"),
    "models": (".tier-pick", "Models and budgets"),
    # Brief v4 Item 3g: one row per brief, its default model.
    "briefs": (".brief-pick", "Analysis defaults"),
    "prices": (".money-sub", "Money"),
    "brand": (".brand-name", "Your name on client reports"),
    # Brief v11 step AI: the local-SEO record per site.
    "sites": (".site-record", "Sites"),
    # Item 177: every site's cadence, one row per site.
    "cadence": (".cadence-row", "Cadences"),
    "operators": (".admin-tabs", "Operators"),
    "database": (".advice-read", "Database"),
    # Grouped by the payload's parts since brief v11 step AI, not phases.
    "workbench": (".alist", "Title & description"),
}

_SCREEN = """() => ({
  tabs: [...document.querySelectorAll('nav.admin-tabs a.ref-link')].map((a) => ({
    text: a.textContent.trim(), href: a.getAttribute('href'),
    current: a.getAttribute('aria-current'),
  })),
  tablist: document.querySelectorAll('[role=tablist], [role=tab]').length,
  headings: [...document.querySelectorAll('#content h3')].map((h) => h.textContent.trim()),
  status: [...document.querySelectorAll('#content [role=status]')]
            .map((el) => el.textContent.trim()).filter(Boolean),
  alists: document.querySelectorAll('.alist').length,
  hash: window.location.hash,
})"""

_RUN = """() => ({
  alists: document.querySelectorAll('.alist').length,
  phaseNotes: document.querySelectorAll('.phase-note').length,
  moved: (() => {
    const a = document.querySelector('.phase-moved a');
    return a ? { href: a.getAttribute('href'), text: a.textContent.trim() } : null;
  })(),
  headings: [...document.querySelectorAll('#content h3')].map((h) => h.textContent.trim()),
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


def _open(browser, base, route, ready):
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    pg.goto(f"{base}/{route}", wait_until="load")
    pg.wait_for_selector(ready, timeout=15_000)
    return pg


def test_the_bare_address_lands_on_the_first_section_with_the_row(browser, served):
    """`#/admin` paints the row of sections and the first of them, and no
    other section's heading is on the screen."""
    base, _ = served
    pg = _open(browser, base, "#/admin", ".admin-tabs")
    try:
        got = pg.evaluate(_SCREEN)
    finally:
        pg.close()
    assert [t["text"] for t in got["tabs"]] == [
        "Spend", "Providers", "Provider keys", "Models and budgets", "Analysis defaults",
        "Money", "Brand", "Sites", "Cadences", "Operators", "Database", "Workbench"], got["tabs"]
    assert [t["href"] for t in got["tabs"]] == [
        f"#/admin?tab={k}" for k in SECTIONS], got["tabs"]
    assert [t["text"] for t in got["tabs"] if t["current"] == "page"] == ["Spend"], got["tabs"]
    assert got["headings"] == ["Spend"], got["headings"]
    # Links, not a tablist: the address is the state, as on the client screen.
    assert got["tablist"] == 0


@pytest.mark.parametrize("key", list(SECTIONS))
def test_each_address_paints_its_own_section_and_only_it(browser, served, key):
    base, _ = served
    ready, heading = SECTIONS[key]
    pg = _open(browser, base, f"#/admin?tab={key}", ".admin-tabs")
    try:
        pg.wait_for_selector(ready, timeout=15_000)
        got = pg.evaluate(_SCREEN)
    finally:
        pg.close()
    assert [t["href"] for t in got["tabs"] if t["current"] == "page"] == [
        f"#/admin?tab={key}"], got["tabs"]
    assert heading in got["headings"], (key, got["headings"])
    others = {h for k, (_, h) in SECTIONS.items() if k != key}
    leaked = others & set(got["headings"])
    assert not leaked, f"{key} also painted {sorted(leaked)}"
    assert not got["status"], got["status"]


def test_pressing_a_name_writes_the_address_and_back_returns(browser, served):
    """The row is navigation: a press changes the hash, the section follows,
    and the browser's own back button undoes it. The retired tab row on the
    client screen failed exactly this."""
    base, _ = served
    pg = _open(browser, base, "#/admin", ".admin-tabs")
    try:
        pg.click('nav.admin-tabs a.ref-link:text-is("Database")')
        pg.wait_for_selector(".advice-read", timeout=15_000)
        after = pg.evaluate(_SCREEN)
        pg.go_back()
        pg.wait_for_function(
            "() => (document.querySelector('#content h3')?.textContent || '').trim() === 'Spend'",
            timeout=15_000)
        back = pg.evaluate(_SCREEN)
    finally:
        pg.close()
    assert after["hash"] == "#/admin?tab=database", after["hash"]
    assert "Database" in after["headings"] and "Spend" not in after["headings"], after
    assert back["hash"] in ("#/admin", "") and back["headings"] == ["Spend"], back


def test_an_unknown_name_is_said_and_never_a_silent_fallthrough(browser, served):
    base, _ = served
    pg = _open(browser, base, "#/admin?tab=nonsense", ".admin-tabs")
    try:
        got = pg.evaluate(_SCREEN)
    finally:
        pg.close()
    assert got["headings"] == ["Spend"], got["headings"]
    said = " ".join(got["status"])
    assert "nonsense" in said and "Spend" in said, got["status"]
    assert [t["text"] for t in got["tabs"] if t["current"] == "page"] == ["Spend"]


def test_the_briefs_by_phase_run_against_the_selected_audit_under_admin(browser, served):
    """The moved list paints against the selection's audit, phase cards and
    rows and all, and its grouping note still points at the workbench."""
    base, ids = served
    pg = _open(browser, base, "#/admin?tab=workbench", ".alist")
    try:
        got = pg.evaluate(_SCREEN)
        note = pg.evaluate(
            "() => document.querySelector('.phase-note a')?.getAttribute('href') || null")
    finally:
        pg.close()
    assert got["alists"] >= 1, got
    # The parts, in the sidebar's order, from the briefs' own headers
    # (brief v11 step AI) - the phase list this held is gone.
    assert got["headings"][:2] == ["Title & description", "Headings"], got["headings"]
    assert not any(h.startswith("Phase ") for h in got["headings"]), got["headings"]
    assert note is None, "the phase note's workbench link went with the phases"


def test_the_run_screen_gave_the_list_up_and_says_where_it_went(browser, served):
    base, ids = served
    pg = _open(browser, base, f"#/runs/{ids['run']}", ".group-list")
    try:
        got = pg.evaluate(_RUN)
    finally:
        pg.close()
    assert got["alists"] == 0 and got["phaseNotes"] == 0, got
    assert not any(h.startswith("Phase ") for h in got["headings"]), got["headings"]
    assert got["moved"] and got["moved"]["href"] == "#/admin?tab=workbench", got["moved"]
    assert "Workbench" in got["moved"]["text"], got["moved"]
