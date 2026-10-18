"""A part's re-check asks first where the press starts a whole-site audit.

Item 189, from channel ruling `20260918-1431`. The actions row's free control
is captioned "Re-check <part> · this part's checks · free". In page mode it
posts `/refresh`: one page, one dimension, named in the request, seconds. In
site mode it posted `/audits` with `tier: "auto"` — a fresh adaptive crawl of
the whole site, minutes of wall clock, a new run row, a new composite, and a
new set of finding states that move the standing position. On a 227-page site
that is what "re-check this part" performed, from rest, with no second step.

"Free" was true — no model tokens — and that is exactly why nothing caught it:
the confirmations in this product are for spends and deletes, and this is
neither. It is item 184's family, a control whose words describe a smaller act
than its press performs.

**The confirmation was not missing; the layout could not reach it.**
`SectionRefresh` is the confirmation for this exact POST, and it renders
nothing else — `if (!confirming) return null` — because its opener is the
re-audit drawer's primary. But `ReauditDrawer` renders only when
`!threeBlocks` and `PartPage` only when `threeBlocks`, so the identical act
has been confirmed on the parts with no renderer and unconfirmed on every part
that has one, since the three-block layout arrived. So the fix is not a new
dialog: the button became the opener, and the confirmation it opens is the
same component the drawer opens.

**Why the press must send nothing.** A confirmation that appears *after* the
request is a receipt, and the whole finding is that the request is larger than
the caption. The first clause below asserts the absence of the POST, which is
the half a rendered assertion about a dialog cannot see.

**Why not a `ConfirmAsk`.** `confirm.tsx` knows two kinds, `spend` and
`danger`. A spend dialog would print "Price: unpriced" for something that
costs no money, which reads as "price unknown" and is false; a danger dialog
would paint a free re-measure in the danger tone. Neither is honest, and a
third kind is a change to the shared confirmation for one caller.
"""

from __future__ import annotations

import pytest

from clauditseo import anatomy as an
from clauditseo import axe
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_heading_fault import browser_page  # noqa: F401  (reused fixture)
from tests.parts import open_part

#: A part that renders as three blocks, which is where the defect lived. Not
#: forced onto the layout of last resort: `tests/last_resort.py` exists to put
#: these parts on the OLD layout, and the old layout is the one that always
#: confirmed. Using it here would test the half that was never broken.
PART = "Indexability & canonicals"
KEY = "indexability"

DIM = an.refresh_for(KEY)["dimension"]
ALSO = an.refresh_for(KEY)["also"]


def live(fn):
    """The file's gate, in the form `test_section_refresh.py` states it."""
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


def _open(pg, base: str, site: str) -> None:
    pg.goto(f"{base}/#/sites/{site}?tab=findings", wait_until="load")
    pg.wait_for_selector(".anat-layout", timeout=15_000)
    open_part(pg, PART)
    pg.wait_for_selector(".part-actions .act-sweep", timeout=15_000)


@live
def test_the_press_starts_no_audit_until_it_is_confirmed(served, browser_page):
    """The clause the finding is about. Everything else here is the wording.

    Collected by URL and method rather than by watching for a run row: a run
    that has been asked for exists before it has produced anything, so the
    request is the earliest honest evidence and a count of runs is the latest.

    **The waits are in this order for a reason.** Waiting for the
    confirmation first and asserting the absence second reads better and
    proves less: against the old code the wait times out, so the clause fails
    on a missing dialog and the assertion about the POST never runs. A fixed
    pause, then the assertion, then the dialog — so the failure text on the
    defect is the finding ("started an audit before the operator confirmed
    it") rather than a Playwright timeout. Measured both ways against the
    reverted source before it was written this way round.
    """
    base, ids = served
    posted: list[str] = []
    browser_page.on("request", lambda r: posted.append(r.url)
                    if r.method == "POST" and "/audits" in r.url else None)
    _open(browser_page, base, ids["site"])

    browser_page.click(".part-actions .act-sweep")
    browser_page.wait_for_timeout(1_500)
    assert not posted, (
        "the press started an audit before the operator confirmed it, so the "
        f"confirmation is a receipt rather than a question: {posted}")
    browser_page.wait_for_selector(".part-actions .sec-refresh-confirm",
                                   timeout=15_000)


@live
def test_the_caption_is_unchanged_and_the_press_spends_nothing(served, browser_page):
    """The opener is still the control the operator knows, and it is still
    free — F-10's two steps put the commitment on the button inside, and a
    caption that changed would make this a different control appearing."""
    base, ids = served
    _open(browser_page, base, ids["site"])
    text = browser_page.eval_on_selector(".part-actions .act-sweep",
                                         "el => el.innerText")
    assert text.startswith(f"Re-check {an.BY_KEY[KEY].label}"), text
    assert "free" in text, text
    # And no page scope claimed: in site mode there is no page set at press
    # time, which is the wording item 183 and audit F17 settled.
    assert "this part's checks" in text, text


@live
def test_the_confirmation_names_the_dimension_and_what_else_moves(served,
                                                                  browser_page):
    """What makes the second step worth taking: the breadth of the act, in the
    words the drawer already uses. Read off the rendered text, not the source,
    because the claim is what an operator sees."""
    base, ids = served
    _open(browser_page, base, ids["site"])
    browser_page.click(".part-actions .act-sweep")
    box = browser_page.wait_for_selector(".part-actions .sec-refresh-confirm",
                                         timeout=15_000)
    body = box.inner_text()

    assert DIM in body, (f"the confirmation does not name the dimension it "
                         f"runs ({DIM}): {body!r}")
    assert "crawls the site" in body, (
        "the confirmation does not say it crawls the site, which is the "
        f"whole difference from the page refresh: {body!r}")
    for part in ALSO:
        assert part in body, (
            f"{part} moves with this run and the confirmation does not name "
            f"it: {body!r}")


@live
def test_a_narrowed_page_still_commits_on_the_press(served, browser_page):
    """The other branch, unchanged and deliberately so.

    With a page in hand and a per-page part, `/refresh` is one page for one
    dimension: the page is in the request, the run scores nothing and may not
    clear a site-scoped finding, and it answers in seconds. The caption says
    what happens, so a confirmation there would stand between the operator and
    a thing they correctly expect. Asserted so that "asks first" is not
    quietly applied to both.
    """
    base, ids = served
    posted: list[str] = []
    browser_page.on("request", lambda r: posted.append(r.url)
                    if r.method == "POST" and "/refresh" in r.url else None)
    _open(browser_page, base, ids["site"])

    # An assertion rather than a skip, and the difference matters: this file
    # runs in `rendered-a11y`, which fails on any skip, so a conditional skip
    # here is a red job waiting for its condition. `per_page` is True for this
    # part, read from the anatomy table, which is the same table everywhere -
    # so the condition cannot arise, and if it ever does it is a change to the
    # part's checks that this clause should report rather than step around.
    offer = an.refresh_for(KEY)
    assert offer["per_page"], (
        f"{PART} is no longer measured page by page, so the page-mode branch "
        "this clause drives has gone - which is a change to what the control "
        "does, not a reason to skip")

    # Narrow to a page through the address, the way the screen does.
    url = browser_page.evaluate("""async () => {
      const m = location.hash.match(/#\\/sites\\/([^?/]+)/);
      const r = await fetch(`/api/sites/${m[1]}/anatomy`);
      const pages = (await r.json()).pages || [];
      if (!pages.length) return null;
      const [path, query = ''] = location.hash.split('?');
      const q = new URLSearchParams(query);
      q.set('page', pages[0].url || pages[0]);
      location.hash = path + '?' + q.toString();
      return pages[0].url || pages[0];
    }""")
    assert url, ("the fixture site has no pages to narrow to, so page mode "
                 "cannot be driven - the fixture has changed under this "
                 "clause rather than the clause being inapplicable")
    browser_page.wait_for_selector(".part-actions .act-sweep", timeout=15_000)

    browser_page.click(".part-actions .act-sweep")
    browser_page.wait_for_timeout(1_500)
    assert posted, (
        "a page-mode re-check sent no refresh: the press that used to commit "
        "one page now does nothing, which is a worse outcome than the one "
        "item 189 was about")
    assert not browser_page.query_selector(".part-actions .sec-refresh-confirm"), (
        "page mode opened the site-wide confirmation, which describes an act "
        "it is not performing")
