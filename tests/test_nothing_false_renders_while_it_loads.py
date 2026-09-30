"""Item 179, commit 5: no screen states an empty answer while the answer is in
flight (UI audit pattern C: 11-1, 02-1, 01-4, 04-6, 05-14, 08-6, 09-1, 09-2,
09-5, 10-2, 10-12).

The auditors found it by polling `innerText` every 100 ms on a server slowed by
other sessions: "No audit to describe yet" on ten of ten client routes of a
site with two audits, "no completed audit" in the picker, "0 of 7 on a cadence
· USD 0.00". A settled screen is the wrong place to look for it, so these
tests make the settle long and step through it.

**How.** Every `/api/` request is held as it is made and released one at a
time, with the page's text sampled between releases, so every partial state a
slow server can produce is on screen for at least one sample. A phrase from
`FALSE_EMPTY` seen in any sample and absent from the settled screen is a false
empty: something the screen said while loading that its own data does not
bear out. A phrase that is true once settled - a bare site really has no audit
- is not flagged, which is what keeps this about loading and not about copy.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from tests.test_fetch_state import served  # noqa: E402,F401  (module fixture)
from tests.needs_build import needs_build

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"


#: Things a screen says only when it has read an empty answer.
FALSE_EMPTY = (
    "No audit to describe yet",
    "at an unknown time",
    "no completed audit",
    "No completed audit yet",
    "has no completed audit",
    "no audit selected",
    "no analysis writes to this part",
    "Run the precheck",
    # The triage verb stood here until item 196 retired the word from the
    # registry. Not replaced by a literal: this list is read against the
    # registry precisely so a test cannot hold a second definition.
    "nothing is spent unattended",
    "Showing the stored result",
    "never run",
    "Nothing has run here yet",
    "Nothing has been checked yet",
)


def _walk(pg, url: str, *, step_ms: int = 120, quiet: int = 20) -> list[str]:
    """Load `url` with every API request held and released one per step;
    return the page text at every step, the last one settled."""
    held: list = []
    pg.route(re.compile(r"/api/"), lambda route: held.append(route))
    try:
        pg.goto(url, wait_until="commit")
        texts: list[str] = []
        idle = 0
        for _ in range(600):
            pg.wait_for_timeout(step_ms)
            texts.append(pg.evaluate("() => document.body ? document.body.innerText : ''"))
            if held:
                route = held.pop(0)
                try:
                    route.continue_()
                except Exception:
                    pass  # the page moved on and dropped the request
                idle = 0
            else:
                idle += 1
                if idle >= quiet:
                    break
        return texts
    finally:
        pg.unroute(re.compile(r"/api/"))
        for route in held:
            try:
                route.continue_()
            except Exception:
                pass


def _false_empties(texts: list[str]) -> dict[str, str]:
    settled = texts[-1]
    seen: dict[str, str] = {}
    for phrase in FALSE_EMPTY:
        if phrase in settled:
            continue
        for t in texts:
            if phrase in t:
                i = t.index(phrase)
                seen[phrase] = t[max(0, i - 120): i + 120].replace("\n", " | ")
                break
    return seen


# `?tab=triage` was here until item 196 retired the ranking pane. The alias
# still resolves to Audit, so the route would render - but a loading-state
# guard over a word that names no screen is a clause that cannot fail.
CLIENT_ROUTES = ("", "?tab=history", "?tab=findings", "?tab=all",
                 "?tab=pages", "?tab=notes", "?tab=precheck")
OTHER_ROUTES = ("#/admin?tab=cadence", "#/admin?tab=workbench")


@needs_build
def test_no_route_says_something_empty_that_its_own_data_does_not_bear_out(served):
    from playwright.sync_api import sync_playwright

    base, ids = served
    found: dict[str, dict[str, str]] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for tail in CLIENT_ROUTES:
                pg = browser.new_page(viewport={"width": 1440, "height": 1000})
                texts = _walk(pg, f"{base}/#/sites/{ids['alpha']}{tail}")
                assert "Loading" in " ".join(texts), (
                    f"{tail or 'landing'}: no sample caught the load, so this route proves nothing")
                got = _false_empties(texts)
                if got:
                    found[f"#/sites/alpha{tail}"] = got
                pg.close()
            for route in OTHER_ROUTES:
                pg = browser.new_page(viewport={"width": 1440, "height": 1000})
                # The selection is the audited site: remembered from its own page.
                pg.goto(f"{base}/#/sites/{ids['alpha']}", wait_until="networkidle")
                texts = _walk(pg, f"{base}/{route}")
                got = _false_empties(texts)
                if got:
                    found[route] = got
                pg.close()
        finally:
            browser.close()
    assert not found, "said while loading, not true once loaded:\n" + "\n".join(
        f"  {route}: {phrase!r} … {ctx}" for route, got in found.items()
        for phrase, ctx in got.items())


def test_the_held_report_button_is_never_a_live_link_before_the_guard_is_read(served):
    """08-6: the button was a live link to Reports for as long as the headline
    took. At every step of the load it is either absent or not a link."""
    from playwright.sync_api import sync_playwright

    base, ids = served
    live_before: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page(viewport={"width": 1440, "height": 1000})
        held: list = []
        pg.route(re.compile(r"/api/"), lambda route: held.append(route))
        try:
            pg.goto(f"{base}/#/sites/{ids['alpha']}", wait_until="commit")
            for _ in range(400):
                pg.wait_for_timeout(120)
                state = pg.evaluate("""() => {
                  const b = [...document.querySelectorAll('.bl-buttons .bl-secondary')]
                    .find((e) => /client report/i.test(e.textContent || ''));
                  const sentence = document.querySelector('.bl-sentence[data-run]');
                  return { tag: b ? b.tagName : null, headline: Boolean(sentence) };
                }""")
                if state["tag"] == "A" and not state["headline"]:
                    live_before.append(str(state))
                if held:
                    try:
                        held.pop(0).continue_()
                    except Exception:
                        pass
                elif state["headline"]:
                    break
        finally:
            pg.unroute(re.compile(r"/api/"))
            browser.close()
    assert not live_before, (
        "the client-report button was a live link while the guard that holds it "
        f"was unread: {live_before[:3]}")


# RETIRED with item 188 (test_tools_offers_no_spend_on_the_previous_sites_audit):
#   Tools carried its own site switcher, so a stale run id could outlive a
#   switch and price the previous site's audit. The client screen has no
#   such switcher: the site is in the route, and changing it remounts. The
#   defect cannot be expressed on the surviving surface.

def test_no_admin_tab_draws_nothing_while_it_loads():
    """10-12: four tabs returned null while loading and on a failed read, so a
    blank card area read as "nothing configured"."""
    src = (SRC / "admin.tsx").read_text(encoding="utf-8")
    assert "if (!data) return null;" not in src
    assert ".catch(() => undefined)" not in src
