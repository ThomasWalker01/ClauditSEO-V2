"""The smallest refresh a section can ask for, offered from the section.

The operator, reading a `heading-skip` finding in Headings: "I cannot run a
scan directly from that page... but I cannot do it here or just for that
page." Both halves were true. The only route to a re-run was the launcher on
another screen, and the launcher asks in **dimensions** while every other
screen groups by **section** — so standing in Headings there was nothing to
press, and nothing said what pressing anything would have cost.

This was `FEATURES.md` F-06's *present-capability fallback*, built while F-06
itself was open: the coarse unit, reachable from the section and labelled
honestly — ONP is the smallest run that refreshes Headings across the site,
and the control names the four other sections that move with it *before* the
click.

**F-06 has since landed** (`tests/test_page_refresh.py`), and this file
changed with it rather than around it. The engine can now be asked for one
page and one dimension, so the control narrows to that unit whenever a page
is selected, and two sentences written while the finer unit did not exist —
the confirmation's "the engine has no per-page unit to ask for" and the F-07
note's pointer to a site-wide sweep — now say what happens instead. The
coarse control is unchanged for what it is: the offer with no page selected.

**Ordinary tests, not guards**, per the rule `FEATURES.md` states for its
entries and `test_heading_fault.py` records for F-07: the behaviour did not
exist, so there was no prior failure to observe and DISCIPLINE rule 1 does
not apply. `refresh_for` appeared nowhere in the engine, on the wire, or in
the bundle. The one assertion here that *is* a guard is
`test_no_screen_promises_an_audit_of_one_page` — the F-07 sentence it
replaces was shipped, was wrong, and could have been read off the source at
any point since.

Five of these need a browser and reuse `test_a11y_rendered.py`'s `served`
fixture, on the same terms `test_heading_fault.py` reuses it: they gate in
the `rendered-a11y` CI job, which fails on any skip, and the static tests
gate in `python`.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import json
import re
from pathlib import Path

import pytest

from clauditseo import anatomy as an
from clauditseo import axe
from clauditseo.engine import registry
from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_heading_fault import (  # noqa: F401  (reused helpers)
    browser_page, restage, restore,
)


# --- what the engine can actually be asked for ------------------------------

def test_headings_offers_the_dimension_that_covers_it():
    """The operator's own case. ONP is the smallest run that refreshes
    Headings, and the answer names it rather than leaving the section with no
    control at all."""
    got = an.refresh_for("headings")
    assert got is not None, "the section the item was written from offers nothing"
    assert got["dimension"] == "ONP"


def test_the_other_sections_that_move_with_it_are_named_not_counted():
    """The cost of the coarse unit, and the whole reason the control can be
    offered honestly. Four names, not "four other sections" — a count is not
    something an operator can weigh."""
    got = an.refresh_for("headings")
    assert got["also"] == ["Title & description", "Images", "Structured data",
                           "Indexability & canonicals"], got["also"]


def test_the_cost_comes_from_the_dimension_table_not_a_second_list():
    """Built from `categories_for_dimension`, so a module gaining or losing a
    category changes what the control says it will touch in the same edit.

    Asserted as an identity against the published function rather than
    against a copied list, which is the difference between a derivation and a
    duplicate that agrees today.
    """
    for code, keys in an.DIMENSION_CATEGORIES.items():
        published = an.categories_for_dimension(code)
        for key in keys:
            got = an.refresh_for(key)
            if got["dimension"] != code:
                continue          # another dimension is the smaller cover
            rebuilt = got["also"] + [an.BY_KEY[key].label]
            assert sorted(rebuilt) == sorted(published), (
                f"{key} describes a cost {code}'s category list does not")


def test_a_module_gaining_a_category_changes_what_the_control_says(monkeypatch):
    """The claim the docstring makes, made falsifiable.

    A hardcoded map would pass every assertion above and still go stale the
    first time a module's categories moved — which is how the two
    vocabularies on this screen drifted apart to begin with.
    """
    monkeypatch.setitem(an.DIMENSION_CATEGORIES, "CNT", ("content", "headings"))
    got = an.refresh_for("content")
    assert "Headings" in got["also"], (
        "the control still describes the categories the module used to have")


def test_the_section_is_never_listed_among_what_else_moves():
    """"It also refreshes Headings", read from the Headings section, is noise
    that makes the real four harder to read."""
    for key in an.BY_KEY:
        got = an.refresh_for(key)
        if got:
            assert an.BY_KEY[key].label not in got["also"], key


def test_where_two_dimensions_cover_a_section_the_smaller_one_wins(monkeypatch):
    """Both would refresh the section; only one is the *smallest* thing that
    would, and being the smallest is the ground the control is offered on.

    The scenario is constructed rather than read off today's tables. It used
    to assert `indexability`, which ONP covered with five categories and TEC
    with four — and that was an accident of what the modules happened to
    raise, not the rule. TEC gained `urls` on 29 August 2026 with
    `internal-link-tracking-params`, the two became five each, and a guard
    written against the accident went red while the rule it was named for was
    untouched. Constructed the way the neighbouring monkeypatch test is, so it
    keeps failing for the rule and stops failing for the arithmetic.
    """
    monkeypatch.setitem(an.DIMENSION_CATEGORIES, "CNT", ("content", "a11y"))
    got = an.refresh_for("a11y")
    assert got["dimension"] == "A11Y", got
    assert len(got["also"]) == 0, got["also"]
    assert len(an.DIMENSION_CATEGORIES["A11Y"]) < len(an.DIMENSION_CATEGORIES["CNT"])


def test_a_tie_is_broken_by_the_code_so_the_answer_does_not_move_with_dict_order():
    """The other half of the same rule, and the live case at HEAD.

    `indexability` is the only section two dimensions cover, and since TEC
    gained `urls` they are the same size — ONP five, TEC five — so "smallest"
    no longer discriminates. `refresh_for` breaks the tie on the dimension
    code, which is why the answer is stable rather than dependent on the order
    `DIMENSION_CATEGORIES` happens to be written in.

    Asserted with its cost stated rather than as a bare identity: the offer
    moved from TEC to ONP, so the Indexability control now names four other
    sections it moves where it named three. That is real and it is honest —
    `also` is computed from the winning dimension — but it is the kind of
    change that should fail a test when it happens rather than be noticed on
    screen.
    """
    # No longer a tie at HEAD: item 143 step BD took `security` out of TEC, so
    # TEC covers four sections to ONP's five and the smaller one wins - the
    # neighbour's rule, on the live tables. The tie-break itself is held on a
    # constructed tie, so it keeps failing for the rule.
    covering = [c for c, cats in an.DIMENSION_CATEGORIES.items()
                if "indexability" in cats]
    assert sorted(covering) == ["ONP", "TEC"], covering
    got = an.refresh_for("indexability")
    assert got["dimension"] == "TEC", got
    assert len(got["also"]) == 3, got["also"]
    # And a real tie still falls to the code, not to dict order.
    import pytest as _pytest
    mp = _pytest.MonkeyPatch()
    try:
        mp.setitem(an.DIMENSION_CATEGORIES, "TEC",
                   ("indexability", "crawl", "mobile", "urls", "security"))
        assert an.refresh_for("indexability")["dimension"] == "ONP"
    finally:
        mp.undo()


def test_a_dimension_that_covers_one_section_says_nothing_else_moves():
    """The case where the coarse unit happens to be exact. A11Y covers
    Accessibility and nothing else, so the control has no cost to state — and
    an empty list is how that is said, not a missing key."""
    got = an.refresh_for("a11y")
    assert got["dimension"] == "A11Y"
    assert got["also"] == []


def test_a_section_no_sweep_populates_offers_nothing():
    """`ANALYSIS_ONLY` — Links on the page, URLs & parameters, International.
    No run refreshes them, so the section offers no control rather than one
    that starts a run which would not touch it. The rule `specialist_for`
    already follows: an offer that ran the wrong thing is worse than silence.
    """
    for key in an.ANALYSIS_ONLY:
        assert an.refresh_for(key) is None, key


def test_every_section_either_offers_a_refresh_or_is_one_nothing_sweeps():
    """Enumerated from the category list rather than from the three names
    above, so a category added later cannot quietly answer neither."""
    uncovered = {k for k in an.BY_KEY if an.refresh_for(k) is None}
    assert uncovered == set(an.ANALYSIS_ONLY) | {"workflow"}, uncovered


def test_the_dimension_offered_is_one_the_launch_endpoint_accepts():
    """`POST /api/sites/{id}/audits` rejects an unknown dimension with 422. A
    control offering a code the engine does not register is a button that can
    only fail, which is worse than the absence it replaced."""
    known = set(registry.all_modules())
    for key in an.BY_KEY:
        got = an.refresh_for(key)
        if got:
            assert got["dimension"] in known, f"{key} offers {got['dimension']}"


# --- the wire ---------------------------------------------------------------

def test_every_category_carries_its_refresh_onto_the_wire(tmp_path):
    """Present on every category, including the ones whose answer is null.

    Null is an answer here — "no sweep refreshes this section" — and a
    different one from "not measured", which is why the key is sent rather
    than omitted the way F-07 omits an unrecorded position. The screen states
    it; it does not fall silent.
    """
    from tests.test_stored_shape import _audited

    conn, _run, _ev = _audited(tmp_path)
    site = conn.execute("SELECT id FROM sites").fetchone()["id"]
    view = runs.anatomy_view(conn, site)

    for c in view["categories"]:
        assert "refresh" in c, f"{c['key']} sends no answer at all"
        assert c["refresh"] == an.refresh_for(c["key"]), c["key"]
    assert [c for c in view["categories"] if c["refresh"]], (
        "no section on the wire offers a refresh")


# --- the sentence F-07 shipped, which named an action nothing can take ------

def test_no_screen_promises_an_audit_of_one_page():
    """The guard, and the only one here.

    F-07's unplaced branch read "The next audit of this page will point at
    it". That promised *page* granularity — the one granularity the engine
    cannot be asked for — so it named an action the product cannot take and
    the operator cannot request. Asserted across every screen rather than the
    one that had it, because that phrasing is the kind that gets copied.

    Comments are exempt: the code records the defect by quoting it, and a
    rule that forbade the record would delete the reason.

    Stripped structurally rather than by line prefix. The first attempt
    exempted lines *starting* with a comment token, which is not how a JSX
    block comment is written in this codebase — `{/* … */}` opens with `{`
    and its continuation lines carry no marker at all — so the rule flagged
    the very comment that records the defect it forbids.

    **The stripper is two patterns, and the single one it replaces could not
    fail.** It was `re.compile(r"/\\*.*?\\*/|^\\s*//.*$", re.S | re.M)`, and
    `re.S` applies to the whole pattern: the `.` in the line-comment branch
    matched newlines, so that branch ate everything from the first `//` to
    the end of the file. Measured on `anatomy.tsx` while WF-59 was being
    fixed: 122,420 bytes in, 4,757 out. The phrase this test forbids is
    absent either way — verified across all 21 screens under the corrected
    stripper, still zero — so nothing about this file's verdict changes. What
    changes is that the verdict is now capable of being the other one, which
    is the whole of DISCIPLINE rule 5. Corrected here as well as in
    `tests/test_a_section_refresh_starts_what_it_says.py`, which copied it,
    because a rule with two implementations is how this repository's defects
    survive their own fixes (rule 3).
    """
    bad = re.compile(r"audit of th(is|e) page", re.I)
    block = re.compile(r"/\*.*?\*/", re.S)
    line = re.compile(r"^[ \t]*//.*$", re.M)
    checked = 0
    for tsx in sorted(Path("dashboard/src").glob("*.tsx")):
        code = line.sub("", block.sub("", tsx.read_text(encoding="utf-8")))
        checked += 1
        assert not bad.search(code), f"{tsx.name} promises an audit of one page"
    assert checked > 1, "the screen list resolved to nothing"


# --- on the screen, in a browser --------------------------------------------

def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


#: Images rather than Headings since brief v14 step AP: that part renders as
#: three blocks and its refresh is the actions row's own `Re-check ONP ·
#: this page`, which `test_the_headings_part_page.py` reads. Images keeps
#: the drawer these clauses are about, under the same dimension, so what
#: they assert about ONP's reach is unchanged.
#: Indexability & canonicals since brief v16 step AT. Structured data took
#: the three-block layout, whose actions row *is* the section refresh's
#: replacement, so a clause about the old control has to drive a part that
#: still has one - and these clauses are about ONP's own refresh, so it has
#: to be one of ONP's. Of the five ONP sections, four now render as three
#: blocks and this is the fifth.

# Which dimension refreshes Indexability & canonicals, read off the rule rather
# than written out. It was ONP by a tie broken on the code while ONP and TEC
# covered five sections each; item 143 step BD moved `security` out of TEC, so
# TEC covers four and is now the smallest run that refreshes the section.
from clauditseo import anatomy as _an_refresh  # noqa: E402
from tests.parts import open_part, open_page_filter

INDEX_DIM = _an_refresh.refresh_for("indexability")["dimension"]
INDEX_ALSO = len(_an_refresh.refresh_for("indexability")["also"])

SECTION = "Indexability & canonicals"


def open_section(pg, base: str, site: str, name: str) -> None:
    on_the_layout_of_last_resort(pg)
    pg.goto(f"{base}/#/sites/{site}?tab=findings", wait_until="load")
    pg.wait_for_selector(".anat-layout", timeout=15_000)
    open_part(pg, name)
    pg.wait_for_selector(".sec-refresh-open", timeout=15_000)


@live
def test_the_section_offers_a_refresh_and_names_its_dimension(served, browser_page):
    base, ids = served
    open_section(browser_page, base, ids["site"], SECTION)

    # The drawer's primary button is the control since brief v5 step U, and
    # its label carries the run it starts.
    text = browser_page.eval_on_selector(".sec-refresh-open", "el => el.innerText")
    # Item 183: the part's name, not the engine code.
    assert text.startswith("Re-check Indexability"), text


@live
def test_the_cost_is_readable_before_the_click_not_after(served, browser_page):
    """The clause that makes a coarse control honest. An operator who wanted
    only Headings must be able to see that four more sections move with it
    without starting anything to find out."""
    base, ids = served
    open_section(browser_page, base, ids["site"], SECTION)

    # The count, in the line that is on screen unprompted.
    # The sentence is inside the drawer's closed details (brief v5 step U):
    # textContent, since innerText is what is painted.
    assert f"{INDEX_ALSO} other sections" in browser_page.eval_on_selector(
        ".reaudit", "el => el.textContent")

    # The confirmation — still before anything is committed — names them.
    browser_page.click(".sec-refresh-open")
    browser_page.wait_for_selector(".sec-refresh-confirm", timeout=5_000)
    shown = browser_page.eval_on_selector(".sec-refresh-confirm",
                                          "el => el.innerText")
    # The section driven is Indexability & canonicals, so what moves with it is
    # that section's `also` - read off the rule, as INDEX_DIM is.
    for other in an.refresh_for("indexability")["also"]:
        assert other in shown, f"{other!r} is not named before the click: {shown!r}"
    # And nothing in it offers or implies one page — this run is site-wide.
    assert "not one page" in shown, (
        f"the confirmation does not rule out page scope: {shown!r}")
    # It used to add "the engine has no per-page unit to ask for", which F-06
    # made false. The clause it was there to serve — the operator knowing what
    # scope they are committing to — is kept by naming the route to the page
    # unit instead of denying that one exists.
    assert "narrow to it above" in shown, (
        f"the confirmation denies page scope without naming it: {shown!r}")
    # WF-59: scope was never the missing term. Depth was — the one that
    # decides what a press costs, on a control whose label is "refresh".
    # Read from rendered text rather than from the source, because a
    # paragraph that renders empty is exactly the failure this file exists
    # to catch and the static half in
    # `tests/test_a_section_refresh_starts_what_it_says.py` cannot see it.
    assert "T3" in shown, (
        f"the confirmation does not say how deep the run may go: {shown!r}")
    assert "No model is invoked" in shown, (
        f"the confirmation does not say the run invokes no model: {shown!r}")
    assert "records a score" in shown, (
        f"the confirmation does not say it writes to the score history: "
        f"{shown!r}")


@live
def test_neither_step_of_the_section_refresh_is_marked_as_spending(
        served, browser_page):
    """F-10, clause 2, and WF-59 moved which clause of it applies.

    This asserted `marks == (1 if analyst_available else 0)` on the
    committing button, which was right while the run enabled the analysts:
    the request sent `tier: "auto"`, the server read
    `body.analyst or body.tier == "auto"`, and a press really did spend model
    tokens on any instance with a key configured.

    Q-18 (operator, 2026-08-25) had the control send `analyst: false`
    alongside the tier, so it cannot invoke a model on any instance at all.
    `SpendMark`'s own words are "This spends model tokens", so a mark would
    now be the check that fires every time — the exact thing F-10 clause 2
    forbids and the reason `PageRefresh` below has never carried one.

    Asserted over both steps and over the whole control rather than the two
    selectors that used to be marked, because "unmarked" is now a property of
    the control and not a state one of its buttons happens to be in.
    """
    base, ids = served
    open_section(browser_page, base, ids["site"], SECTION)

    assert browser_page.eval_on_selector_all(
        ".sec-refresh .spend-mark", "els => els.length") == 0, (
        "the control that only opens the confirmation is marked as spending")

    browser_page.click(".sec-refresh-open")
    browser_page.wait_for_selector(".sec-refresh-confirm", timeout=5_000)
    marks = browser_page.eval_on_selector_all(
        ".sec-refresh-confirm .spend-mark", "els => els.length")
    assert marks == 0, (
        f"a refresh that asks for no analyst carries {marks} spend mark(s)")


@live
def test_the_run_it_starts_is_scoped_to_the_dimension_that_covers_the_section(
        served, browser_page):
    """What the control actually asks for, read from the request rather than
    from the label on the button.

    The request is intercepted rather than allowed through: letting it run
    would crawl the fixture site again for an assertion about one JSON body,
    and the reply is the only part the screen reads.
    """
    base, ids = served
    sent: list[dict] = []

    def capture(route, request):
        sent.append(json.loads(request.post_data or "{}"))
        route.fulfill(status=202, content_type="application/json",
                      body=json.dumps({"run_id": "stub-run", "status": "running"}))

    browser_page.route("**/api/sites/*/audits", capture)
    try:
        open_section(browser_page, base, ids["site"], SECTION)
        browser_page.click(".sec-refresh-open")
        browser_page.wait_for_selector(".sec-refresh-confirm", timeout=5_000)
        browser_page.click(".sec-refresh-confirm .tone-action-primary")
        browser_page.wait_for_selector(".sec-refresh-done", timeout=10_000)
    finally:
        browser_page.unroute("**/api/sites/*/audits")

    assert len(sent) == 1, f"expected exactly one launch, got {sent!r}"
    assert sent[0]["dims"] == [INDEX_DIM], (
        f"the section started something other than the run it named: {sent[0]!r}")
    # WF-59, on the wire. The dimension was always scoped; the spend was not,
    # and this is the body that used to leave it unsaid. `tier` is asserted
    # alongside because Q-18 decided to KEEP `auto` — a body that dropped it
    # would satisfy the analyst clause while answering the breadth question
    # the way the operator declined.
    assert sent[0]["tier"] == "auto", (
        f"the section stopped starting an adaptive run: {sent[0]!r}")
    assert sent[0]["analyst"] is False, (
        f"the section refresh asks for an analyst it does not name: {sent[0]!r}")
    # The operator is still standing in the section they started it from.
    assert "#/runs/" not in browser_page.url, (
        f"the refresh navigated away from the section: {browser_page.url}")
    done = browser_page.eval_on_selector(".sec-refresh-done", "el => el.innerText")
    assert f"{INDEX_DIM} is running" in done, done



# --- F-06: the fine unit, on the screen -------------------------------------
#
# The engine and API half is `tests/test_page_refresh.py`, which needs no
# browser. These two clauses cannot be read off the source: what the control
# claims with a page selected is rendered text, and what it asks for is a
# request body.

@live
def test_with_a_page_selected_the_control_narrows_to_that_page(served, browser_page):
    """F-06 landing changes what the section may offer. With a page in front
    of the operator the engine can be asked for less than a dimension-wide
    sweep, so the control asks for less — and says so, including the part
    that has not shrunk: the other sections still move, for this page."""
    base, ids = served
    on_the_layout_of_last_resort(browser_page)
    browser_page.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load")
    browser_page.wait_for_selector(".anat-layout", timeout=15_000)
    # Indexability & canonicals since brief v16 step AT: the page refresh
    # this reads is the drawer's, and four of ONP's five sections render as
    # three blocks now.
    open_part(browser_page, 'Indexability & canonicals')
    open_page_filter(browser_page)
    browser_page.fill(".page-find", "/deep")
    browser_page.wait_for_selector(".sec-refresh-page", timeout=15_000)

    text = browser_page.eval_on_selector(".sec-refresh-page", "el => el.innerText")
    assert "/deep" in text, f"the control does not name the page it reads: {text!r}"
    assert "Indexability" in text, f"the control does not name the part it re-checks: {text!r}"

    browser_page.click(".sec-refresh-page-open")
    browser_page.wait_for_selector(".sec-refresh-page-confirm", timeout=5_000)
    shown = browser_page.eval_on_selector(".sec-refresh-page-confirm",
                                          "el => el.innerText")
    # The section driven is Indexability & canonicals, so what moves with it is
    # that section's `also` - read off the rule, as INDEX_DIM is.
    for other in an.refresh_for("indexability")["also"]:
        assert other in shown, f"{other!r} is not named before the click: {shown!r}"
    assert "no score" in shown.lower(), (
        f"the confirmation does not say it writes no score: {shown!r}")
    # Unmarked, and F-10 clause 2 is why: no analyst is asked for, so no
    # model is invoked and a mark here would fire every time.
    assert browser_page.eval_on_selector_all(
        ".sec-refresh-page-confirm .spend-mark", "els => els.length") == 0, (
        "a refresh that invokes no model is marked as spending")


@live
def test_the_page_refresh_asks_for_the_page_and_the_section(served, browser_page):
    """What it actually requests, read from the request. Intercepted rather
    than allowed through: committing it would crawl the fixture site and
    write findings to the shared fixture database for an assertion about one
    JSON body."""
    base, ids = served
    sent: list[dict] = []

    def capture(route, request):
        sent.append(json.loads(request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"run_id": "stub-run", "url": "/deep",
                                       "dimension": "ONP", "tier": "T2",
                                       "also": [], "pages": 1,
                                       "pages_attempted": 1, "recorded": 0,
                                       "cleared": 0, "regressed": 0,
                                       "opened": 0, "scored": False}))

    browser_page.route("**/api/sites/*/refresh", capture)
    try:
        on_the_layout_of_last_resort(browser_page)
        browser_page.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load")
        browser_page.wait_for_selector(".anat-layout", timeout=15_000)
        # Indexability & canonicals since brief v16 step AT: same dimension
        # as the parts this clause has followed through three moves, and
        # the last of ONP's five still rendering the old page's controls.
        open_part(browser_page, 'Indexability & canonicals')
        open_page_filter(browser_page)
        browser_page.fill(".page-find", "/deep")
        browser_page.wait_for_selector(".sec-refresh-page", timeout=15_000)
        browser_page.click(".sec-refresh-page-open")
        browser_page.wait_for_selector(".sec-refresh-page-confirm", timeout=5_000)
        browser_page.click(".sec-refresh-page-confirm .tone-action-primary")
        browser_page.wait_for_selector(".sec-refresh-page-done", timeout=10_000)
    finally:
        browser_page.unroute("**/api/sites/*/refresh")

    assert len(sent) == 1, f"expected exactly one refresh, got {sent!r}"
    assert sent[0]["section"] == "indexability", sent[0]
    assert sent[0]["url"].endswith("/deep"), (
        f"the control asked for a page other than the one selected: {sent[0]!r}")
    # The operator is still standing where they were, and the answer is here.
    assert "#/runs/" not in browser_page.url, browser_page.url
