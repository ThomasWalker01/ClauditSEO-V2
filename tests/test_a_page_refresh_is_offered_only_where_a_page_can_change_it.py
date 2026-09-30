"""UX-39: the page refresh is offered where re-reading a page cannot help.

First raised in report 051 and carried by every report since — 43 of them —
and reproduced at the running product before this guard was written, on
`www.13acme.com.au` with the page filter set to `/`:

    Refresh Backlinks for this page
    Re-reads / and re-measures OFP against it. Every other page keeps its
    findings and its timestamps.

Every clause of that is false. `OffPageModule` declares
``measured_per_page = False``: all five of its checks read the domain's
backlink profile and every one of them builds its `Finding` with a literal
`affected_urls=[]`, so re-reading `/` cannot change what OFP measures however
many times it is pressed. All ten OFP
findings ever stored carry ``affected_urls=[]``, and `_apply_states` skips
every finding with no page on a narrow run — ``if narrow and not pages:
continue`` (`clauditseo/persistence/runs.py:634`), whose own comment already
names the residual this guard is about. So the control spends a crawl and a
provider call to change nothing, and says the opposite.

**The predicate is `registry.page_blind_dims()`, and picking it was the
work.** Report 051 proposed `Category.group`, on the reading that the seven
sections outside "on the page" are all incapable. Measured against the engine
rather than the grouping, that is wrong in both directions and would have
broken working controls:

  * `ais.py:95,110` and `loc.py:99,162` attribute findings to `page.url`, so
    AI surface and Local & citations *can* be cleared by a page refresh —
    both are `beyond the site` and both would have lost a working offer;
  * TEC emits `noindex-linked`, `http-status-error` and `not-https` against
    pages, so Crawl and Security would have lost theirs too;
  * counted over every finding this install has ever stored, OFP is the only
    dimension with no page-attributed finding at all — 0 of 10, against
    AIS 0 of 6 by data but page-capable by construction, and LOC 1 of 9.

`page_blind_dims` is the engine's own answer to "can re-reading one page move
any of this dimension's findings", declared per module as `measured_per_page`
and guarded by `tests/test_page_scope_is_declared.py` against each module's
own source.

**This read `crawl_blind_dims` until `QUESTIONS.md` Q-17.** That was the
neighbouring fact — "can fetching more pages raise this dimension's coverage"
— standing in for this one, and it gave the right answer for the wrong reason:
OFP is the only member of either set, so the proxy could not be caught being
wrong until a dimension was crawl-blind but page-capable, or the reverse. Q-17
split the two and the modules now declare each separately. Every assertion
below is unchanged in outcome and now derives from the fact it is about.

**Not a filter on "sections with no finding for this page".** Seven sections
offered the control on `/` and only one is a defect: Title & description and
Mobile hold nothing on that page *today*, and a refresh there can legitimately
find something or confirm there is nothing. Incapable-by-construction is the
claim, and only OFP meets it.
"""

from __future__ import annotations

import pytest

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo import anatomy as an
from clauditseo import axe
from clauditseo.engine import registry
from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_heading_fault import browser_page  # noqa: F401  (reused fixture)
from tests.test_page_refresh import _client_and_site, _fixture
from tests.parts import open_part, open_page_filter

#: The crawl-blind dimensions at HEAD, and the sections they cover. Named so
#: the assertions below read, but never used as the rule — every clause
#: derives its expectation from `page_blind_dims()` so that a second
#: page-blind dimension inherits this fix instead of the defect. **It has
#: one now**: LNK landed at brief v17 step AW, and every one of its checks
#: is a statement about the graph — how many pages link at this one, how far
#: it is from home, whether one anchor serves two targets. Re-reading a
#: single page cannot move any of them, because the answer lives in the
#: other pages. `BLIND_SECTION` is the one the wire clauses drive, and it
#: stays `backlinks` so those clauses keep testing the route they were
#: written against.
BLIND_SECTION = "backlinks"
BLIND_SECTIONS = {"backlinks", "links"}


def _blind_sections() -> set[str]:
    """Sections whose smallest covering run is a dimension no page can move."""
    blind = registry.page_blind_dims()
    return {c.key for c in an.CATEGORIES
            if (o := an.refresh_for(c.key)) and o["dimension"] in blind}


# --- the predicate ----------------------------------------------------------

def test_the_offer_says_whether_a_page_is_a_unit_it_can_be_asked_for():
    """`refresh_for` answers the question the page control has to ask.

    Derived from the registry, not listed here: a hard-coded set of one is
    how the next provider-derived dimension inherits the defect silently,
    which is the reason `page_blind_dims` exists rather than a literal in
    `refresh_for`.
    """
    blind = registry.page_blind_dims()
    assert blind, "no dimension declares measured_per_page = False any more"

    seen = 0
    for c in an.CATEGORIES:
        offer = an.refresh_for(c.key)
        if offer is None:
            continue
        seen += 1
        assert "per_page" in offer, (
            f"{c.key} offers a refresh without saying whether a page is a "
            f"unit it can be asked for: {offer}")
        assert offer["per_page"] is (offer["dimension"] not in blind), (
            f"{c.key} covers {offer['dimension']}, which is "
            f"{'crawl-blind' if offer['dimension'] in blind else 'crawl-derived'}"
            f", and its per_page reads {offer['per_page']}")
    assert seen > 1, "the section list resolved to nothing"


def test_exactly_the_off_page_section_is_the_one_a_page_cannot_move():
    """The measurement that chose the predicate, kept as an assertion.

    If a later change makes this fail, the fix is not to widen the rule to
    `Category.group` — that was measured and is wrong — it is to re-read the
    module that changed its declaration.
    """
    assert _blind_sections() == BLIND_SECTIONS, (
        "the set of sections no page refresh can move has changed; re-read "
        "each module's measured_per_page before touching this guard")

    # The counter-assertion that rules out the grouping the report proposed:
    # both of these sit outside "on the page" and both attribute findings to
    # a page, so both keep their page control.
    for key in ("ai-surface", "local"):
        assert an.refresh_for(key)["per_page"] is True, (
            f"{key} lost its page refresh — it is beyond the site, but its "
            f"module emits findings against page URLs")


# --- on the wire ------------------------------------------------------------

def test_the_screen_is_told_which_sections_a_page_refresh_can_move(tmp_path):
    """The screen may not decide this for itself.

    Same rule as `names_a_page`, one control along: the server owns the
    question because the answer is a property of the engine's modules, which
    the browser cannot see.
    """
    from tests.test_stored_shape import _audited

    conn, _run, _ev = _audited(tmp_path)
    site = conn.execute("SELECT id FROM sites").fetchone()["id"]
    view = runs.anatomy_view(conn, site)

    by_key = {c["key"]: c for c in view["categories"]}
    assert by_key[BLIND_SECTION]["refresh"]["per_page"] is False, (
        "the wire does not tell the screen that a page refresh of "
        f"{BLIND_SECTION} cannot move anything")
    assert by_key["headings"]["refresh"]["per_page"] is True, (
        "a page-capable section lost its page refresh on the wire")


# --- the endpoint -----------------------------------------------------------

def test_the_route_refuses_a_page_refresh_it_cannot_carry_out(tmp_path):
    """Refused at the server, not only unoffered by the screen.

    The screen is one caller. A route that bills for a crawl and a provider
    call it knows cannot change anything is the defect itself, and hiding the
    button leaves it payable by anything that posts.
    """
    site = _fixture().start()
    try:
        client, _conn, site_id = _client_and_site(tmp_path, site)
        resp = client.post(f"/api/sites/{site_id}/refresh",
                           json={"url": site.base_url + "/",
                                 "section": BLIND_SECTION})
        assert resp.status_code == 422, (
            f"the route accepted a page refresh of {BLIND_SECTION}: "
            f"{resp.status_code} {resp.text[:400]}")
        detail = resp.json()["detail"]
        assert "OFP" in detail or "backlink" in detail.lower(), detail
        assert "page" in detail.lower(), (
            f"the refusal does not say what it is about: {detail!r}")

        # Counter-assertion, and it passes on both trees: the refusal is
        # about the dimension, not about the route.
        ok = client.post(f"/api/sites/{site_id}/refresh",
                         json={"url": site.base_url + "/",
                               "section": "headings"})
        assert ok.status_code == 200, (
            f"a page-capable section was refused too: {ok.text[:400]}")
    finally:
        site.stop()


# --- on the screen, in a browser --------------------------------------------

def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


def _filtered_to_a_page(pg, base: str, site: str) -> str:
    """The screen with a page filter committed, as the operator sets one.

    Typed into the picker rather than pushed into the URL: `page` is state on
    this screen and not a route, so a hash carrying a page query renders the
    unfiltered screen — which is how this reproduction was first run, and it
    read as "not reproducible" for one attempt.
    """
    pg.goto(f"{base}/#/sites/{site}?tab=findings", wait_until="load")
    pg.wait_for_selector(".anat-layout", timeout=20_000)
    path = pg.eval_on_selector("#anat-pages option", "el => el.value")
    open_page_filter(pg)
    pg.fill(".page-find", path)
    pg.wait_for_timeout(2_000)
    return path


def _open(pg, name: str) -> str:
    open_part(pg, name)
    # The control is the re-audit drawer's primary since brief v5 step U,
    # and the sentence that says why a page does not narrow a part is in
    # the drawer's closed details - hence textContent.
    pg.wait_for_selector(".reaudit-primary", timeout=15_000)
    pg.wait_for_timeout(300)
    return pg.eval_on_selector(".reaudit", "el => el.textContent")


@live
def test_the_page_control_is_not_offered_where_a_page_cannot_move_it(
        served, browser_page):  # noqa: F811
    """The sentence the operator reads, and the one they must not.

    `sec-refresh-page` is the class the page control renders under, so this
    asks the screen the same question the payload was asked above rather than
    matching on prose that can be reworded.
    """
    base, ids = served
    path = _filtered_to_a_page(browser_page, base, ids["site"])
    assert path, "the fixture served no page to filter to"

    text = _open(browser_page, "Backlinks")
    assert not browser_page.query_selector(".sec-refresh-page"), (
        "with a page filter set, Backlinks still offers a page refresh: "
        f"{text!r}")
    assert "for this page" not in text, (
        f"Backlinks still claims a page scope it cannot act on: {text!r}")


@live
def test_the_screen_says_why_the_page_filter_does_not_narrow_this_section(
        served, browser_page):  # noqa: F811
    """Withdrawing the control silently would leave the operator to work out
    why one section behaves differently from its neighbours.

    The provenance invariant applies to the limitation as much as to a
    figure: it has to be in rendered text, not in a title attribute.
    """
    base, ids = served
    _filtered_to_a_page(browser_page, base, ids["site"])
    text = _open(browser_page, "Backlinks")

    assert "OFP" in text, f"the limit does not name the dimension: {text!r}"
    assert "not measured page by page" in text.lower(), (
        f"the section does not say why the page filter does not apply: {text!r}")


@live
def test_a_page_capable_section_keeps_its_page_refresh(served, browser_page):  # noqa: F811
    """The counter-assertion, and it passes on both trees.

    Without it, deleting the page control outright would satisfy every clause
    above.
    """
    base, ids = served
    path = _filtered_to_a_page(browser_page, base, ids["site"])
    # Images rather than Headings: that part renders as three blocks since
    # brief v14 step AP, where the page refresh is the actions row's own
    # `Re-check ONP · this page` and the drawer this clause reads is gone.
    # `test_the_headings_part_page.py` asserts the same offer there.
    # Accessibility since brief v16 step AT: Structured data took the
    # three-block layout. Indexability & canonicals since brief v16e (relay
    # 136f). **Local & citations since item 137 (brief v18 step BA)**, because
    # Indexability took the AO layout in its turn — it gained a PART_RENDERERS
    # entry, so it now offers the page refresh through the actions row, not the
    # drawer. This clause has now moved four times for one reason, and the
    # moves are the useful record: each names the part that had just gained a
    # part page. What it asserts is unchanged — a page-capable part offers a
    # page refresh — and the part it asserts it on is simply one that still
    # renders the drawer.
    #
    # `local` is page-capable (`refresh.per_page`, dimension LOC) and has no
    # entry in `PART_RENDERERS`, which are the two conditions. When it gains
    # one, move this again rather than weakening it: the property holds on a
    # part page too, but through a different control, and a clause that
    # accepted either would stop noticing which it found.
    text = _open(browser_page, "Local")

    assert browser_page.query_selector(".sec-refresh-page"), (
        f"Local & citations lost its page refresh on {path}: {text!r}")
    assert "for this page" in text, text
