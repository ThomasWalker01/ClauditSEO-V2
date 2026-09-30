"""FEATURES.md F-11: a finding that states a count shows what it counted.

**These are ordinary tests for a feature, not guards, and none of them was
seen to fail against the old code in the sense DISCIPLINE rule 1 means.**
`FEATURES.md` says so in its own words — *"there is no failing behaviour to
observe first: the behaviour does not exist, so a 'guard' for it would assert
something the code has never attempted"*. They were written with the feature
and run against the old bundle before it was built, which is the nearest
thing to rule 1 that applies here — **measured, 5 failed and 3 passed**, and
which three passed is the useful half:

  * the four rendered clauses and the source rule failed, each on a missing
    `.pages-btn`, against the cell as it was: ``<td className="num">{f.pages}
    </td>`` and nothing else;
  * `test_the_count_and_the_list_behind_it_agree_on_the_wire` and
    `test_the_fixture_can_express_all_three_cases` passed, and were expected
    to. They assert the server contract this feature *relies* on rather than
    anything it changed — nothing on the wire moved — and they are here so
    that the day `pages` and `urls` drift apart, the disclosure's premise
    fails loudly instead of the disclosure opening onto nothing;
  * `test_a_finding_that_names_no_page_offers_no_control` **also passed on
    the old bundle, and cannot distinguish on its own**: a screen with no
    control anywhere trivially offers none on a page-less row. Said out loud
    rather than left for a reader to notice. It binds only in the pair — the
    clause that fails without the feature is
    `test_a_count_above_zero_opens_the_pages_it_counted`, and together they
    say *a control here and not there* rather than *no control anywhere*.

**What the entry asks for, stated wider than the one screen.** Wherever the
product states a quantity of affected things, the operator can reach those
things in one action from where the quantity is stated. The instance is the
section findings table: *"3 pages share the title 'Acme: Australia's Most
Open Minded Lender' — they compete for the same query"*, `PAGES 3`, and no way
to reach those three.

**The three cases, and the fixture expresses all three** — which is DISCIPLINE
rule 5 and is asserted below rather than assumed, because a fixture that
cannot express the failure is how a clause passes without ever being read:

  ``meta-desc-duplicate``   12 pages, 10 URLs on the wire. The truncated case.
                            `SHARED_DESC` sits on twelve fixture pages for a
                            different reason and this is the one finding on
                            the fixture site that crosses the payload's cap.
  ``axe-coverage``          0 pages, no URLs. The no-control case. A
                            site-scoped finding legitimately names no page,
                            and `QUESTIONS.md` Q-20 is open on precisely
                            which briefs those are — nothing here assumes
                            that answer, only that the empty case exists.
  everything else           1 or 2 pages, complete. The ordinary case.

**The residual is filed, not hidden.** Where the count is above the cap the
screen reaches ten of twelve and says so; the other two are stored and are
reachable from no screen. That is `BACKLOG.md` **B-30**, and the entry's own
acceptance signal permits it in as many words — *"Truncation is stated where
it happens … so a screen showing three of eleven says so rather than implying
eleven were three"*.
"""

from __future__ import annotations

from tests.last_resort import on_the_layout_of_last_resort
import pytest

from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_heading_fault import browser_page  # noqa: F401  (reused fixture)
from tests.parts import open_part

#: The section the truncated finding sits in, and the section the two
#: page-less findings sit in. Named so the assertions read; never used as the
#: rule — each test locates its own row from the payload the screen was sent,
#: so a fixture change moves the test rather than silently emptying it.
#: The part these clauses drive, chosen from the payload rather than named.
#:
#: Held by hand until brief v17 step AX and moved three times - away from
#: Title & description, then Headings, then Content - each time a part
#: gained a renderer of its own and lost the count that opens a list,
#: because every page such a part counted is already a card. The list of
#: parts that render as three blocks is derived, and so is "a part with a
#: row whose count opens a list", so a constant has nothing left to add
#: except a fourth move.
def cut_section(view: dict, need: str = "whole") -> str:
    """A part that keeps the old page and has the row these clauses need.

    `whole` wants a row carrying every page it counted; `truncated` wants
    one the emitter cut, which is a different question and a different
    row - the fixture plants exactly one of the second kind.
    """
    from tests.test_the_part_page_is_three_blocks import three_block_parts

    # Less the harness's parts, which `_section` draws on the old page (brief
    # v25 step BP, `tests/last_resort.py`).
    from tests.last_resort import PARTS as LAST_RESORT
    migrated = three_block_parts() - set(LAST_RESORT)
    for cat in view["categories"]:
        if cat["key"] in migrated:
            continue
        for f in cat["findings"]:
            whole = 0 < f["pages"] == len(f["urls"])
            cut = f["pages"] > len(f["urls"]) > 0
            if (whole if need == "whole" else cut):
                return cat["label"]
    raise AssertionError(
        f"no part on this fixture keeps the old page and has a {need} list; "
        "these clauses have nothing to drive")
def no_page_section(view: dict) -> tuple[str, bool]:
    """(label, is_three_block) of a part holding a finding that names no page.

    **Both layouts, because the subject moved.** This was a constant reading
    "Accessibility", re-pointed at whichever part had not yet gained a
    renderer. At brief v16e Accessibility took one too - and on this fixture
    the ONLY page-less findings are the A11Y scope statements (`axe-sampled`
    and the coverage note), so there was no part left to move to. That is
    structural rather than a fixture accident: a site-scoped finding is what
    names no page, and A11Y is where this fixture's are.

    So the clause learned the second layout instead of moving a fourth time.
    It asserts a DIFFERENT control on each, because the two screens offer
    different ones and asserting the old page's control is absent from a
    screen that never drew it would prove nothing.
    """
    from tests.test_the_part_page_is_three_blocks import three_block_parts

    # Less the harness's parts, which `_section` draws on the old page (brief
    # v25 step BP, `tests/last_resort.py`).
    from tests.last_resort import PARTS as LAST_RESORT
    migrated = three_block_parts() - set(LAST_RESORT)
    # `pages == 0`, the same condition the clause selects rows on. A
    # derivation using a different predicate could return a part whose rows
    # the clause then finds none of.
    holds = [c for c in view["categories"]
             if any(f.get("pages") == 0 for f in c["findings"])]
    # An old-page part FIRST, because that is where the strong assertion
    # lives: it has a page control to be absent, and the part page has none
    # for any row. The fixture plants `llms-txt-missing` on `ai-surface` to
    # guarantee one exists. The three-block branch is the fallback for the
    # day that stops being true, and it asserts a weaker but still real
    # property - see the test.
    for cat in holds:
        if cat["key"] not in migrated:
            return cat["label"], False
    if holds:
        return holds[0]["label"], True
    raise AssertionError(
        "no part on this fixture holds a finding that names no page; this "
        "clause has nothing to drive")


# --- on the wire ------------------------------------------------------------

def _payload(base: str, site: str) -> dict:
    import httpx

    return httpx.get(f"{base}/api/sites/{site}/anatomy", timeout=60).json()


def _findings(view: dict) -> list[dict]:
    return [f for c in view["categories"] for f in c["findings"]]


def test_the_count_and_the_list_behind_it_agree_on_the_wire(served):  # noqa: F811
    """The screen may branch on `urls` only because the server keeps these two
    in step: `pages` is `len(affected_urls)` and `urls` is the same list cut
    to ten (`runs.anatomy_view`).

    Asserted rather than read out of the source, because the whole feature is
    "the count is a control when there is something behind it" — the day a
    finding arrives with `pages` above zero and an empty `urls`, the control
    is offered onto nothing, which is the one thing the acceptance signal
    forbids by name.
    """
    base, ids = served
    found = _findings(_payload(base, ids["site"]))
    assert found, "the fixture served no findings to check"

    for f in found:
        assert len(f["urls"]) <= f["pages"], (
            f"{f['check_id']} carries more URLs than pages: "
            f"{len(f['urls'])} > {f['pages']}")
        assert bool(f["urls"]) == (f["pages"] > 0), (
            f"{f['check_id']} disagrees with itself: pages={f['pages']}, "
            f"urls={f['urls']}")


def test_the_fixture_can_express_all_three_cases(served):  # noqa: F811
    """DISCIPLINE rule 5, before anything below is believed.

    Without a cut finding the truncation clause reads as passing on a screen
    that has never had to state a truncation, and without a page-less finding
    the no-control clause is a `for` loop over nothing.
    """
    base, ids = served
    found = _findings(_payload(base, ids["site"]))

    cut = [f for f in found if f["pages"] > len(f["urls"])]
    assert cut, ("no fixture finding crosses the payload's URL cap, so no "
                 "assertion here can tell a stated truncation from a silent "
                 "one")
    none = [f for f in found if f["pages"] == 0]
    assert none, "no fixture finding names zero pages"
    whole = [f for f in found if 0 < f["pages"] == len(f["urls"])]
    assert whole, "no fixture finding carries its list complete"


# --- on the screen, in a browser --------------------------------------------

def live(fn):
    from clauditseo import axe

    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


def _section(pg, base: str, site: str, name: str) -> None:
    """The section screen with one section opened, as the operator opens it."""
    on_the_layout_of_last_resort(pg)
    pg.goto(f"{base}/#/sites/{site}?tab=findings", wait_until="load")
    pg.wait_for_selector(".anat-layout", timeout=20_000)
    open_part(pg, name)
    # Not the shop's table, which is Analyses' body until the part opens
    # (brief v24 step BO).
    pg.wait_for_selector("table.findings:not(.catalogue-table)", timeout=15_000)
    # Instances stand under their causes since brief v2 step E: open every
    # cause, so the rows these clauses read are on screen.
    for i in range(pg.locator("table.causes .group-toggle").count()):
        pg.locator("table.causes .group-toggle").nth(i).click()
    pg.wait_for_timeout(150)
    pg.wait_for_timeout(300)


def _stamp(pg) -> None:
    """A token on `window` that a navigation would destroy.

    The signal says the URLs are reached *"without a new page load"*, and
    "the DOM changed" does not distinguish an expansion from a re-render
    after a route change. This does.
    """
    pg.evaluate("() => { window.__f11 = 'held'; }")


def _held(pg) -> bool:
    return pg.evaluate("() => window.__f11") == "held"


@live
def test_a_count_above_zero_opens_the_pages_it_counted(served, browser_page):  # noqa: F811
    """The whole of the entry, on the screen it was written against.

    Locates the row from the payload rather than by position: the section
    sorts by severity then by descending pages, and a row index is the first
    thing a new fixture finding moves.
    """
    base, ids = served
    view = _payload(base, ids["site"])
    cat = next(c for c in view["categories"] if c["label"] == cut_section(view))
    whole = next(f for f in cat["findings"]
                 if 0 < f["pages"] == len(f["urls"]))

    _section(browser_page, base, ids["site"], cut_section(view))
    _stamp(browser_page)

    row = f"table.findings tr:has(code:text-is('{whole['check_id']}'))"
    btn = browser_page.query_selector(f"{row} .pages-btn")
    assert btn, (f"{whole['check_id']} reads PAGES {whole['pages']} and the "
                 "count is not a control")
    assert btn.get_attribute("aria-expanded") == "false", (
        "the control does not say it is closed")
    assert not browser_page.query_selector(".pages-list"), (
        "a page list is open before anything was pressed")

    btn.click()
    browser_page.wait_for_selector(".pages-list", timeout=5_000)
    assert _held(browser_page), (
        "the page reloaded — the URLs were not reached in place")

    hrefs = browser_page.eval_on_selector_all(
        f"{row} + tr.pages-row .pages-list a", "els => els.map(e => e.href)")
    assert hrefs == whole["urls"], (
        f"the list under {whole['check_id']} does not hold the URLs the "
        f"payload named: {hrefs} against {whole['urls']}")

    # It closes again, and says so. A disclosure that only opens leaves the
    # table taller every time a count is read.
    browser_page.query_selector(f"{row} .pages-btn").click()
    browser_page.wait_for_timeout(200)
    assert not browser_page.query_selector(f"{row} + tr.pages-row"), (
        "the list did not close")


@live
def test_each_url_is_followable_to_the_page_it_names(served, browser_page):  # noqa: F811
    """`Each URL is followable to the page it names`, read literally: an
    anchor carrying the absolute URL, not a label that looks like one.

    **The target is not fetched here, and the reason is the fixture rather
    than the feature.** `served` crawls `FixtureSite` and then stops it — the
    audit is in the database long before any browser renders it — so every
    `affected_url` on this site points at a port that has been closed since
    seeding. A request against one proves the fixture is torn down and
    nothing about the screen. Fetching the *served* pages is what
    `test_a11y_rendered` already does, over the app itself.

    So what is asserted is the four things that make an anchor followable and
    that the old cell had none of: an absolute `href`, equal to the URL the
    payload named, opening away from the screen rather than replacing it, and
    carrying `rel="noopener noreferrer"` with the `target`.

    The visible labels are paths — `UrlLinks` renders `pathname + search` —
    and the last clause asserts they stay distinct, because the finding this
    entry was written against names three URLs differing only in a `utm_`
    query and three identical labels would defeat the whole disclosure.
    """
    base, ids = served
    view = _payload(base, ids["site"])
    cat = next(c for c in view["categories"] if c["label"] == cut_section(view))
    whole = next(f for f in cat["findings"]
                 if 0 < f["pages"] == len(f["urls"]))

    _section(browser_page, base, ids["site"], cut_section(view))
    row = f"table.findings tr:has(code:text-is('{whole['check_id']}'))"
    browser_page.click(f"{row} .pages-btn")
    browser_page.wait_for_selector(".pages-list", timeout=5_000)

    links = browser_page.query_selector_all(f"{row} + tr.pages-row a")
    assert links, "the list rendered no links"
    assert len(links) == len(whole["urls"]), (
        f"{len(links)} links for {len(whole['urls'])} URLs")

    for a, url in zip(links, whole["urls"]):
        href = a.get_attribute("href")
        assert href == url, f"a page link points elsewhere: {href!r} != {url!r}"
        assert href.startswith("http"), f"not an absolute URL: {href!r}"
        assert a.get_attribute("target") == "_blank", (
            f"{href} replaces the section screen rather than opening beside "
            "it — the operator loses the finding they were reading")
        assert a.get_attribute("rel") == "noopener noreferrer", (
            f"{href} opens a new context without noopener: "
            f"{a.get_attribute('rel')!r}")

    labels = [a.inner_text().strip() for a in links]
    assert len(set(labels)) == len(labels), (
        f"two page links read the same and cannot be told apart: {labels}")


@live
def test_a_finding_that_names_no_page_offers_no_control(served, browser_page):  # noqa: F811
    """`renders no control at all rather than an empty one`.

    The negative half, and the one that gets dropped first. An affordance
    that opens onto nothing is worse than none, and a site-scoped finding
    legitimately names no page — which of them is the open half of Q-20 and
    is deliberately not decided here.
    """
    base, ids = served
    view = _payload(base, ids["site"])
    label, three_block = no_page_section(view)
    cat = next(c for c in view["categories"] if c["label"] == label)
    none = [f for f in cat["findings"] if f["pages"] == 0]
    assert none, (f"{label} holds no page-less finding any more — "
                  "re-pick the section before touching this test")

    if not three_block:
        _section(browser_page, base, ids["site"], label)
        for f in none:
            row = f"table.findings tr:has(code:text-is('{f['check_id']}'))"
            cell = browser_page.eval_on_selector(
                f"{row} td.num", "el => el.innerText.trim()")
            assert cell == "0", f"{f['check_id']} reads {cell!r} rather than 0"
            assert not browser_page.query_selector(f"{row} .pages-btn"), (
                f"{f['check_id']} names no page and still offers a control "
                "that would open onto nothing")
        return

    # The part page, since brief v16e gave Accessibility one.
    #
    # NOT the checks table: it draws no page control for any row, so
    # asserting one is absent there is a check that cannot fail - the shape
    # DISCIPLINE rule 5 is about. What this layout renders per finding is
    # `.fix-page`, the path the card is about, and a page-less finding drew
    # it EMPTY: `pathOf("")` is "", so every site-scoped row carried a bare
    # `<code>` beside it. That is the same affordance-onto-nothing the old
    # page's clause forbids, in this layout's own terms, and it was a real
    # defect found by teaching this clause rather than by reading the code.
    on_the_layout_of_last_resort(browser_page)
    browser_page.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load")
    browser_page.wait_for_selector(".anat-layout", timeout=20_000)
    open_part(browser_page, label)
    browser_page.wait_for_selector(".checks-table, .fix-card", timeout=15_000)
    browser_page.wait_for_timeout(400)

    cards = browser_page.locator(".fix-card").count()
    assert cards, f"{label}'s part page drew no fix cards to read"
    for f in none:
        card = f"[data-fix-check='{f['check_id']}']"
        if not browser_page.query_selector(card):
            continue
        assert not browser_page.query_selector(f"{card} .fix-page"), (
            f"{f['check_id']} names no page and its card still renders a "
            "page element, which is empty and points at nothing")

    # And `.fix-page` IS drawn where there is a page, so the absence above
    # can disagree with the screen rather than passing because the selector
    # names nothing this layout ever renders.
    assert browser_page.query_selector(".fix-card .fix-page"), (
        "no card on this part renders `.fix-page` at all, so the assertion "
        "above is the absence of a thing the screen never draws")


@live
def test_a_truncated_list_says_what_it_is_showing(served, browser_page):  # noqa: F811
    """`Truncation is stated where it happens`.

    Both numbers, from the payload: the screen must not print the total it
    was sent as though it were the total that exists. The sentence names no
    cap of its own — ten is the server's number and a client repeating it
    goes stale the day it changes.
    """
    base, ids = served
    view = _payload(base, ids["site"])
    cat = next(c for c in view["categories"] if c["label"] == cut_section(view, "truncated"))
    cut = next((f for f in cat["findings"] if f["pages"] > len(f["urls"])), None)
    assert cut, [(f["check_id"], f["pages"], len(f["urls"])) for f in cat["findings"]]

    _section(browser_page, base, ids["site"], cut_section(view, "truncated"))
    row = f"table.findings tr:has(code:text-is('{cut['check_id']}'))"
    browser_page.click(f"{row} .pages-btn")
    browser_page.wait_for_selector(".pages-list", timeout=5_000)

    shown = browser_page.eval_on_selector_all(
        f"{row} + tr.pages-row .pages-list a", "els => els.length")
    assert shown == len(cut["urls"]), (
        f"the screen rendered {shown} links of the {len(cut['urls'])} it was "
        "sent")

    note = browser_page.query_selector(f"{row} + tr.pages-row .pages-cut")
    assert note, (f"{cut['check_id']} shows {len(cut['urls'])} of "
                  f"{cut['pages']} pages and does not say so")
    text = note.inner_text()
    assert str(len(cut["urls"])) in text and str(cut["pages"]) in text, (
        f"the truncation note states neither number: {text!r}")


@live
def test_the_whole_list_is_stated_without_a_truncation_note(served, browser_page):  # noqa: F811
    """The counter-assertion, and it is the reason the one above means
    anything: a note on every row is a note nobody reads, so the ordinary
    case has to stay quiet for the unusual one to carry weight.

    Same shape `caption.table-note` and `_breadth_phrase` already use.
    """
    base, ids = served
    view = _payload(base, ids["site"])
    cat = next(c for c in view["categories"] if c["label"] == cut_section(view))
    whole = next(f for f in cat["findings"]
                 if 0 < f["pages"] == len(f["urls"]))

    _section(browser_page, base, ids["site"], cut_section(view))
    row = f"table.findings tr:has(code:text-is('{whole['check_id']}'))"
    browser_page.click(f"{row} .pages-btn")
    browser_page.wait_for_selector(".pages-list", timeout=5_000)
    assert not browser_page.query_selector(f"{row} + tr.pages-row .pages-cut"), (
        f"{whole['check_id']} carries its whole list and still claims a "
        "truncation")


@live
def test_the_disclosure_names_which_cap_it_is_stating(served, browser_page):  # noqa: F811
    """UX-93, on the screen it was found on. `QUESTIONS.md` Q-26.

    Two caps reach this sentence and it used to state one of them against the
    other: `"Showing 10 of 20. ... the rest are stored"`, where the twenty was
    itself a cap and thirty-one of the fifty-one the summary named had never
    been stored at all. The payload now carries `total` beside `pages`, so the
    sentence can say which cut it is describing.

    **Rule 1, in the form this file's header already records for F-11.** The
    subject is the built bundle, so `scripts/prove_fail.py` refuses it by
    name — *"runs against dashboard/dist, which this script does not
    rebuild"*. Measured instead the way the five clauses above were: run
    against the bundle on disk before rebuilding, **1 failed**, on
    ``assert "of the 12 URLs stored" in text`` against the sentence as it
    was — ``"Showing 10 of 12. This screen's payload caps the URL list it
    carries per finding — the rest are stored and are not reachable from here
    (BACKLOG.md B-30)."``

    **What this fixture can and cannot show, said plainly rather than left
    for a reader to discover.** `served` audits sixteen routes over
    `TEC ONP A11Y CNT` with no sitemap, so none of the four capping emitters
    fires on it: the only cut here is the payload's, and the second clause —
    the one that says URLs were never recorded — is unpainted by any test.
    That gap is `KNOWN_ISSUES.md` and not a silence; what is asserted here is
    the half the fixture can disagree with, plus the negative that stops the
    unpainted clause appearing where it does not belong.
    """
    base, ids = served
    view = _payload(base, ids["site"])
    cat = next(c for c in view["categories"] if c["label"] == cut_section(view, "truncated"))
    cut = next((f for f in cat["findings"] if f["pages"] > len(f["urls"])), None)
    assert cut, [(f["check_id"], f["pages"], len(f["urls"])) for f in cat["findings"]]
    assert cut["total"] == cut["pages"], (
        "the fixture's cut finding is now emitter-capped as well — re-read "
        "this test, it was written for the payload cut alone")

    _section(browser_page, base, ids["site"], cut_section(view, "truncated"))
    row = f"table.findings tr:has(code:text-is('{cut['check_id']}'))"
    browser_page.click(f"{row} .pages-btn")
    browser_page.wait_for_selector(".pages-list", timeout=5_000)

    text = browser_page.eval_on_selector(
        f"{row} + tr.pages-row .pages-cut", "el => el.innerText")
    assert f"of the {cut['pages']} URLs stored" in text, (
        "the note states a total without saying what it is the total of, so "
        f"a capped one would read the same as a whole one: {text!r}")
    assert "never recorded" not in text, (
        "the note claims the check dropped URLs on a finding whose whole "
        f"list was stored: {text!r}")


@live
def test_the_emitter_cut_clause_is_painted_and_not_only_denied(served, browser_page):  # noqa: F811
    """CQ-235 / `KNOWN_ISSUES.md` KI-57: the other half of UX-93's disclosure,
    observed rendered rather than assumed.

    The test above asserts the emitter clause is **absent** where it does not
    belong. Nothing asserted it **present** where it does, so deleting the
    `cutBefore` branch from `PagesList` left the whole suite green — the shape
    DISCIPLINE rule 5 rejects, one step removed: a sentence no check could
    disagree with.

    **Why this route and not the two KI-57 named.** That entry offers a second
    seeded fixture for this one screen, or an assertion on the payload rather
    than the screen. The first is a suite-wide risk — the `served` crawl is
    budgeted at `max_pages=30` and shared by every rendered guard in the tree,
    and raising a real emitter cap needs either a sitemap or `PRF`/`LOC` in
    the seed's dimensions, each of which moves the anatomy tree, the category
    totals and the scores a dozen tests read. The second does not answer the
    finding at all: CQ-235 is about a clause that is *rendered*, and a payload
    assertion would stay green with the branch deleted. So the payload is
    fulfilled at the route instead, which is this repo's established way of
    putting a shape in front of the real component — `test_fetch_state.py:249`
    and `test_a11y_rendered.py:1309` both intercept this same `/anatomy` — and
    costs no crawl and no fixture change.

    **The shape served is one the server can produce, not an invented one.**
    `runs.anatomy_view` sets `pages` to `len(urls_full)` and `total` to the
    row's `affected_total`, which four emitters cap before storage; `total`
    above `pages` is exactly what those four write. One finding whose list is
    complete is given a `total` above its `pages`, so `cutHere` stays false
    and `cutBefore` alone fires — which makes this the discriminating case,
    not merely a second painting of the sentence the test above already reads.

    **Rule 1, measured, and in the same form the header records for F-11 —
    `scripts/prove_fail.py` refuses this file by name because the subject is
    the built bundle.** With the four lines of the `cutBefore` branch cut out
    of `PagesList` and `dashboard/` rebuilt, this clause **failed** on the
    first assertion below — ``assert 'The check found 32 and stored the first
    1' in 'Showing all 1 URLs stored.'`` — and with the branch restored and
    rebuilt again it passes.

    **The other half of that measurement is the one worth keeping**, because
    it is the finding rather than the fix: on that same neutered bundle
    `test_the_disclosure_names_which_cap_it_is_stating` above **passed**. Its
    ``"never recorded" not in text`` is satisfied by the branch being gone, so
    the guard that reads this sentence could not tell a correct screen from a
    deleted one. That is CQ-235 reproduced, not restated.
    """
    import json

    base, ids = served
    view = _payload(base, ids["site"])
    cat = next(c for c in view["categories"] if c["label"] == cut_section(view))
    whole = next((f for f in cat["findings"]
                  if 0 < f["pages"] == len(f["urls"])), None)
    assert whole is not None, (
        f"no finding in {cut_section(_payload(base, ids['site']))!r} carries its list complete, so this "
        "test cannot isolate the emitter cut from the payload cut")
    assert whole["total"] == whole["pages"], (
        "the fixture's whole finding is already emitter-capped — re-read this "
        "test, it fabricates the cap it needs and would then be asserting the "
        "fixture's own instead")

    kept = whole["pages"]
    found = kept + 31
    whole["total"] = found
    body = json.dumps(view)
    browser_page.route(
        "**/api/sites/*/anatomy*",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=body))

    _section(browser_page, base, ids["site"], cut_section(view))
    row = f"table.findings tr:has(code:text-is('{whole['check_id']}'))"
    browser_page.click(f"{row} .pages-btn")
    browser_page.wait_for_selector(".pages-list", timeout=5_000)

    text = browser_page.eval_on_selector(
        f"{row} + tr.pages-row .pages-cut", "el => el.innerText")
    assert f"The check found {found} and stored the first {kept}" in text, (
        "the screen was sent a finding the check capped before storing and "
        f"says nothing about it: {text!r}")
    assert f"the other {found - kept} were never recorded" in text, (
        "the disclosure names the two counts and not the gap between them, "
        f"which is the number of URLs no surface can reach: {text!r}")
    assert "not reachable from here" not in text, (
        "the payload-cut clause fired on a finding whose list this payload "
        f"carries whole, so the sentence names the wrong cut: {text!r}")


# --- the rule, stated wider than the screen ---------------------------------

def test_the_section_screen_is_the_only_count_left_without_its_list(served):  # noqa: F811
    """The entry asks for a rule, not a fix: *wherever the product states a
    quantity of affected things, the operator can reach those things in one
    action from where the quantity is stated.*

    Checked over the three surfaces that render a finding's affected pages,
    enumerated by grep over `affected_urls` and `f.urls` in `dashboard/src`
    before this was written (DISCIPLINE rule 3):

      `views.tsx:983`      the full findings list — `UrlLinks` already
      `components.tsx:479` the run's findings — `UrlLinks` already
      `anatomy.tsx`        the section table — this feature

    Asserted against the source because there is no fourth surface to render
    and the point is that a new one cannot appear silently: a component that
    states `f.pages` and never names `f.urls` is the defect coming back.
    """
    import pathlib
    import re

    src = pathlib.Path(__file__).resolve().parents[1] / "dashboard" / "src"
    anat = (src / "anatomy.tsx").read_text(encoding="utf-8")

    assert re.search(r"\bf\.pages\b", anat), (
        "the section table no longer renders a page count — re-read this "
        "test before deleting it")
    assert "PagesCount" in anat and "PagesList" in anat, (
        "the count is rendered and the list behind it is not")

    # Every module that renders a findings table renders the URLs with it.
    for name in ("views.tsx", "components.tsx"):
        text = (src / name).read_text(encoding="utf-8")
        if "affected_urls" in text:
            assert "UrlLinks" in text, (
                f"{name} names affected_urls and renders no link to any of "
                "them")
