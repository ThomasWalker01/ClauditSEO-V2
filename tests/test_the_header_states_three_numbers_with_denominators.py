"""The client header's three numbers, each with its denominator stated (150
step BJ, the render half).

BJ's engine landed at `0d76ada` and nothing read it; item 155's part-header
coverage line was the first surface, and this is the second and the one the
brief actually names. The header read:

    68 IN THE RECORD · 49 PUBLISHED · 45 IN THIS AUDIT'S CRAWL

Three populations with no stated relationship, and every count elsewhere on
the screen silently picked one of them without saying which. That is the root
of 146z — the length strip drew the crawl set while the check table counted
the record, and the two differed by three on Twenty22 T3 with nothing on
screen to explain it.

It now reads **on the site · audited · been through · in the record**, where
the first is `declared ∪ discovered`, the second is `crawled of site size` with
its percentage, the third is `findings not open of findings in the run`, and
the last is bookkeeping rather than a denominator.

**Four figures and not five, and the reason is a measured budget.** A first
pass gave each figure a third line for the sentence qualifying it and added
the declared-versus-discovered gap as a fifth — the bar went to 213px against
`test_the_scope_bar_is_three_columns`'s 120 and pushed the rail 296px down
against `test_the_rail_is_a_strip`'s 230. Both are geometry guards and both
were right. So the qualifier rides in the LABEL where it is short
(`audited · 85%`) and in the title where it is not, and the gap moved to the
part header's coverage sentence, which is where it reads as a statement rather
than as a fifth number.

**Driven at the rendered header, not at the payload.** The payload half is
`test_the_headline_numbers.py`, which pins the arithmetic. What these clauses
ask is a different question the payload cannot answer: whether the screen
divides by the right one. `.fig-size`, `.fig-coverage` and `.fig-assessed` are
hooks for exactly that — a clause that pointed at "the third div" would be
asserting an index that four reorderings of this bar have already moved.

**Since brief v23 step BL the three numbers are the state sentence**, not a
row of figures: "T2 audited 45 pages, 85% of the 53 on the site; 12 of 60
findings (20%) have been through" (the verb added at 2bb7947). The hooks and titles moved with them -
`.fig-size`, `.fig-coverage` and `.fig-assessed` are spans in the sentence, and
the record is `.fig-record` in the "What has been measured" lane's head - so
these clauses still ask whether the screen divides by the right number, read
off the words a reader now sees. Since item 174 `.fig-assessed` is the fourth
number the sentence has shed: it is the Settled lane's "Assessed" entry, so the
headline sets in two lines (channel ruling 20260917-1430).

**Measured against the old bundle, DISCIPLINE rule 1.** With `dashboard/src`
stashed and the previous bundle rebuilt, **all four rendered clauses failed**:
there was no `.bj-figs` and no `.fig-*` row at all, the header still drew
`in the record / published / in this audit's crawl`, and the unknown-size
clause found no `[data-unknown]` to read. The arithmetic clause below it is an
ordinary test of `runs.site_size` and was green before and after — it is here
because the screen's claim rests on it.
"""

from __future__ import annotations

import json
import re

import pytest

from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)


def live(fn):
    from clauditseo import axe

    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


@pytest.fixture
def browser():
    """A browser rather than a page: two of these clauses serve a doctored
    headline, and a route has to be attached before the navigation."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            yield b
        finally:
            b.close()


#: A headline in the shape `runs.headline_numbers` returns, with the brief's
#: own Twenty22 figures: 49 declared, 4 linked-but-undeclared, 53 on the site,
#: 45 crawled, 85%. Written here so a clause can read a number it knows rather
#: than whatever the fixture happens to produce — the fixture has no sitemap,
#: so its own size is `unknown`, which is the OTHER case and has its own clause.
TWENTY22 = {
    "run_id": "r",
    "site_size": {"size": 53, "declared": 49, "discovered": 45, "gap": 4,
                  "unknown": False, "unknown_reason": None},
    "coverage": {"crawled": 45, "size": 53, "pct": 85, "unknown": False,
                 "unknown_reason": None},
    "assessed": {"assessed": 12, "total": 60, "pct": 20},
    "audited": 45,
}

UNKNOWN = {
    "run_id": "r",
    "site_size": {"size": None, "declared": 0, "discovered": 16, "gap": 16,
                  "unknown": True, "unknown_reason": "source failed"},
    "coverage": {"crawled": 16, "size": None, "pct": None, "unknown": True,
                 "unknown_reason": "source failed"},
    "assessed": {"assessed": 0, "total": 41, "pct": 0},
    "audited": 16,
}

_FIGS_JS = """() => {
  const span = (sel) => {
    // The sentence is the bar's; the record rides in the landing's lane head
    // since brief v24 step BM.
    const d = document.querySelector('.run-scope ' + sel) || document.querySelector('.cl-landing ' + sel);
    if (!d) return null;
    return {
      text: (d.textContent || '').replace(/\\s+/g, ' ').trim(),
      value: (d.querySelector('b')?.textContent || '').trim(),
      title: (d.getAttribute('title') || '').replace(/\s+/g, ' '),
      unknown: d.getAttribute('data-unknown') === '1',
      pct: d.getAttribute('data-pct'),
      href: d.querySelector('a')?.getAttribute('href') || null,
    };
  };
  return {
    size: span('.fig-size'),
    gap: span('.fig-gap'),
    coverage: span('.fig-coverage'),
    assessed: span('.fig-assessed'),
    assessedChip: (document.querySelector('.cl-landing .cl-assessed dd.fig')?.textContent || '').trim(),
    assessedTitle: (document.querySelector('.cl-landing .cl-assessed dt')?.textContent || '').trim(),
    record: span('.fig-record'),
    text: (document.querySelector('.run-scope .bl-sentence')?.textContent || '')
      .replace(/\\s+/g, ' ').trim(),
  };
}"""


def _open(browser, base: str, site_id: str, headline=None):
    pg = browser.new_page(viewport={"width": 1500, "height": 1000})
    if headline is not None:
        def anatomy(route):
            data = route.fetch().json()
            data["headline"] = headline
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(data))

        pg.route("**/api/sites/*/anatomy*", anatomy)
    pg.goto(f"{base}/#/sites/{site_id}", wait_until="load")
    pg.wait_for_selector(".run-scope .bl-sentence .fig-coverage", timeout=20_000)
    # Item 174: the assessed share is the Settled lane's entry, not a clause.
    pg.wait_for_selector(".cl-landing .lane-settled .cl-assessed .fig-assessed", timeout=20_000)
    pg.wait_for_selector(".cl-landing .fig-record", timeout=20_000)
    pg.wait_for_timeout(250)
    return pg


@live
def test_the_header_states_the_site_size_and_never_the_declaration_alone(served, browser):  # noqa: F811
    """Site size is `declared ∪ discovered`, and the header says which halves
    it is made of.

    **Never `crawled ÷ declared`.** Divide by the declaration and coverage
    rises exactly when the declaration fails — Acme's `272 to 50` is the
    case, and the operator has classed that a retrieval failure rather than a
    change in the site. So the clause reads both halves off the screen: a
    header showing 49 where the site is 53 would be the defect with a new
    label.
    """
    base, ids = served
    pg = _open(browser, base, ids["site"], TWENTY22)
    got = pg.evaluate(_FIGS_JS)

    assert got["size"], f"no site-size figure in the sentence: {got['text']}"
    assert got["size"]["value"] == "53", got["size"]
    # Item 168: the sentence reads "across 45 of the 53 pages on the site", so
    # `.fig-size` carries the figure alone and the words follow it.
    assert got["size"]["text"] == "53", got["size"]
    assert "45 of the 53 pages on the site" in got["text"], got["text"]
    # Both halves named, so the number cannot be read as the declaration.
    # In the TITLE rather than on a third line - see the docstring's note on
    # the bar's measured height budget. A title is not a label's equal, and
    # that is the trade the budget forced; what matters is that the reader who
    # asks "53 of what?" is answered rather than left to guess.
    assert "49 declared" in got["size"]["title"], got["size"]
    assert "45 " in got["size"]["title"], got["size"]
    assert "never the declaration alone" in got["size"]["title"], got["size"]
    # And the declaration is NOT the headline figure.
    assert got["size"]["value"] != "49", (
        "the header is stating the declaration as the size of the site")


@live
def test_coverage_is_crawled_over_site_size_and_says_the_percentage(served, browser):  # noqa: F811
    """`45 of 53`, 85%. The figure PD-01 and 146z were both reaching for, and
    the one every site-scoped count on the screen now reads against."""
    base, ids = served
    pg = _open(browser, base, ids["site"], TWENTY22)
    got = pg.evaluate(_FIGS_JS)

    assert got["coverage"], f"no coverage figure: {got['text']}"
    assert got["coverage"]["value"] == "45", got["coverage"]
    # Item 168 (channel ruling 20260917-0045): the percentage is a derivation
    # of two numbers already in the sentence, so it left the prose for the
    # figure's `data-pct` and the first clause of its title. That is how this
    # clause keeps pinning the denominator after the prose stopped saying it.
    assert got["coverage"]["text"] == "45", got["coverage"]
    assert got["coverage"]["pct"] == "85", got["coverage"]
    assert got["coverage"]["title"].startswith("85% of the site:"), got["coverage"]
    assert "45 of the 53 pages on the site" in got["text"], got["text"]
    # The record is still on screen and is NOT what coverage divides by.
    assert got["record"], "the record was dropped rather than demoted"
    assert got["record"]["text"].endswith("in the record"), got["record"]
    assert "of the 68" not in got["text"] and "of the 16" not in got["text"], (
        f"coverage is divided by something other than the site size: {got['text']}")
    # The gap is NOT a figure in the bar - it is stated in the part header's
    # coverage sentence, which `test_the_gap_is_stated_and_not_bracketed`
    # below drives. What this clause holds is that the bar did not keep a
    # bracket: the old parenthetical is gone from it entirely.
    assert got["gap"] is None, got["gap"]
    # The sentence carries one bracket of its own, the assessed percentage;
    # what must not be bracketed is the gap, so the clause names the gap's
    # words rather than any parenthesis.
    assert "not in sitemap" not in got["text"] and "not declared" not in got["text"], (
        f"the gap is still a parenthetical in the bar: {got['text']}")


@live
def test_assessed_is_findings_been_through_and_never_reads_as_progress(served, browser):  # noqa: F811
    """`12 of 60` findings been through — unweighted, and labelled so it cannot
    be read as progress toward fixed.

    Unweighted is correct for this question and no other. Forty low-contrast
    labels and one keyboard trap are not forty to one, which is the argument
    `page_strip_parts_mockup.html` already makes about Accessibility — so the
    word on screen is "been through" and never "done" or "fixed".
    """
    base, ids = served
    pg = _open(browser, base, ids["site"], TWENTY22)
    got = pg.evaluate(_FIGS_JS)

    assert got["assessed"], f"no assessed figure: {got['text']}"
    # Item 174 (channel ruling 20260917-1430): the clause "; 12 of them (20%)
    # have been through" left the sentence, which could not set in two lines
    # with it, for the Settled lane's "Assessed" entry - still visible without
    # hovering, which is 0125's reason for keeping it, and still in `data-pct`.
    assert "have been through" not in got["text"], got["text"]
    assert got["assessedTitle"] == "Assessed" and got["assessedChip"] == "12", got
    assert got["assessed"]["text"] == ("20% of this audit's 60 findings have been through. "
                                       "Unweighted: a Low looked at counts as much as a "
                                       "Critical."), got["assessed"]
    assert "It found 60 findings" in got["text"], got["text"]
    assert got["assessed"]["pct"] == "20", got["assessed"]
    assert "not progress toward fixed" in got["assessed"]["title"], got["assessed"]
    # Not dressed as progress. The words that would make it one are absent
    # from what a reader sees without hovering.
    low = got["assessed"]["text"].lower()
    for word in ("fixed", "done", "complete", "progress", "resolved"):
        assert word not in low, (
            f"the assessed figure reads as progress toward fixed: {got['assessed']}")


@live
def test_an_unknown_site_size_makes_coverage_not_computable_and_says_so(served, browser):  # noqa: F811
    """The fourth state, and the one that matters.

    A sitemap that could not be read cleanly leaves the size unknown, and then
    coverage is not a number at all. Not 90%, not 100%, and **not a dash that
    reads as zero** — the brief rules out all three by name. The screen says
    `not known` and `coverage not computable`, and the reason travels with it.
    """
    base, ids = served
    pg = _open(browser, base, ids["site"], UNKNOWN)
    got = pg.evaluate(_FIGS_JS)

    assert got["size"]["unknown"], got["size"]
    # Item 168: the caveat left the sentence - it lives in the Waiting lane's
    # retrieval entry - and `.fig-size` stays, on the word "pages", carrying
    # the "not known" title so the hook and its reason both survive.
    assert "site size not known" in got["size"]["title"].lower(), got["size"]
    assert "source failed" in got["size"]["title"], got["size"]
    assert "not known" not in got["text"], (
        f"the retrieval caveat is back in the sentence: {got['text']}")
    assert "across 16 pages" in got["text"], got["text"]
    # Coverage states what was crawled and refuses the ratio. The label stays
    # the bare word: `audited · not computable` wrapped the column and broke
    # the bar's height budget, and the figure beside it reading `not known`
    # already says no share of the site can be computed.
    assert got["coverage"]["value"].strip() == "16", got["coverage"]
    assert got["coverage"]["text"] == "16", got["coverage"]
    assert got["coverage"]["pct"] == "", got["coverage"]
    assert not got["coverage"]["title"][:1].isdigit(), (
        f"a percentage leads a title over a denominator nobody read: {got['coverage']}")
    assert "%" not in got["coverage"]["text"], (
        f"a percentage is drawn over a denominator nobody read: {got['coverage']}")
    # And no gap figure: every discovered page is "not declared" when the
    # declaration failed, so drawing 16 there would report our own fetch as a
    # fact about the site.
    assert got["gap"] is None, (
        f"the gap is stated against a declaration that failed: {got['gap']}")


@live
def test_the_gap_is_stated_and_not_bracketed(served, browser):  # noqa: F811
    """"The declared-versus-discovered gap is promoted to a finding. It is
    currently a parenthetical: *68 audited (4 nav pages not in sitemap)*. It is
    the difference between the site the owner believes they publish and the one
    that exists, and it deserves to be stated rather than bracketed."

    It is stated in the part header's coverage sentence, where there is room
    for the words — the bar could not carry a fifth figure without breaking a
    geometry guard, and a number in a bar is not more "stated" than a clause in
    a sentence. What the brief forbids is the bracket, and the bracket is gone.

    **Not an engine finding, and that is the brief's own argument rather than
    scope.** A gap computed from a declaration that failed is our fetch
    reported as a fact about the site — precisely the Acme `272 to 50` case
    the operator has classed a retrieval failure. So it is suppressed entirely
    where the size is unknown, and the finding waits on the sitemap re-fetch
    that makes the declaration trustworthy (the separately-filed crawl-layer
    item).
    """
    base, ids = served
    pg = _open(browser, base, ids["site"], TWENTY22)
    line = pg.evaluate("""() => {
      const p = document.querySelector('.part-coverage');
      return p ? { text: p.textContent.replace(/\s+/g, ' ').trim(),
                   gap: p.querySelector('.part-gap')?.getAttribute('data-gap') ?? null }
               : null;
    }""")
    # The coverage line only draws with a part open, so open one.
    if line is None:
        open_first_part(pg)
        pg.wait_for_selector(".part-coverage", timeout=15_000)
        line = pg.evaluate("""() => {
          const p = document.querySelector('.part-coverage');
          return { text: p.textContent.replace(/\s+/g, ' ').trim(),
                   gap: p.querySelector('.part-gap')?.getAttribute('data-gap') ?? null };
        }""")
    assert line["gap"] == "4", line
    assert "4 found and not declared" in line["text"], line
    assert "(4" not in line["text"] and "(4 nav" not in line["text"], (
        f"the gap is still bracketed: {line['text']}")

    # And nothing about it where the declaration failed.
    pg2 = _open(browser, base, ids["site"], UNKNOWN)
    open_first_part(pg2)
    pg2.wait_for_selector(".part-coverage", timeout=15_000)
    unknown_line = pg2.text_content(".part-coverage")
    assert "not declared" not in unknown_line, (
        "the gap is stated against a declaration that failed, which reports "
        f"our own fetch as a fact about the site: {unknown_line!r}")


def test_the_size_is_the_union_and_the_gap_is_what_the_owner_does_not_publish(served):  # noqa: F811
    """The arithmetic the screen above rests on, asserted on the payload the
    screen is actually served — not on the constants the rendered clauses
    inject. An ordinary test, green before this item: it is here so that the
    day `site_size` changes shape the header's claim fails with it rather than
    drawing a stale number confidently."""
    import httpx

    base, ids = served
    view = httpx.get(f"{base}/api/sites/{ids['site']}/anatomy", timeout=60).json()
    head = view["headline"]
    assert head, "the header has no numbers to draw"
    size = head["site_size"]
    # This fixture has no sitemap, so it is the UNKNOWN case - which is why the
    # rendered clauses inject figures. Asserted rather than assumed, so the day
    # the fixture grows a sitemap this file is told instead of silently
    # changing which case it drives.
    assert size["unknown"] is True and size["size"] is None, size
    assert head["coverage"]["pct"] is None, head["coverage"]
    assert size["declared"] == 0 and size["discovered"] > 0, size
    # Everything discovered is undeclared here, which is the gap by definition.
    assert size["gap"] == size["discovered"], size
    # And the record is a different number from the crawl, so the two cannot be
    # confused for each other on the screen above.
    assert len(view["pages"]) >= head["coverage"]["crawled"], (
        len(view["pages"]), head["coverage"])


def open_first_part(pg) -> None:
    """The first part in the product's order, through the address (brief v24
    step BO), which is what `pg.click(".anat-leaf")` pressed."""
    from tests.test_fetch_state import _PART_KEYS_JS, open_part_key
    open_part_key(pg, pg.evaluate(_PART_KEYS_JS)[0])

def test_the_assessed_figure_and_its_explanation_name_the_same_states():
    """The figure counts every state but `open`; its tooltip named three.

    `run_assessed`: "Only `open` is unassessed; `fixed`, `regressed`,
    `candidate`, `accepted-risk` and `withdrawn` all count." The hover said
    "someone has decided about - fixed, accepted, withdrawn", which leaves out
    the two that carry the number. Measured on twenty22, run `d6f5049f`: 418
    open and 87 regressed, none fixed, accepted or withdrawn — so the figure
    read 87 while its own explanation described a set of size nought.

    Held on the source, in both files that draw it, because the defect is that
    a rendered sentence disagreed with the engine, and only the words can say
    whether it still does.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "dashboard" / "src"
    # Every file that draws the figure with an explanation. Two until item 168
    # removed `population.tsx`'s `HeadlineFigures`, which was never mounted;
    # the part header's `part-assessed` line there carries no title of its own.
    drawn = sorted(p.name for p in src.glob("*.tsx")
                   if 'className="fig-assessed"' in p.read_text(encoding="utf-8"))
    assert drawn == ["client_lanes.tsx"], drawn
    for name in drawn:
        text = (src / name).read_text(encoding="utf-8")
        i = text.find("Findings this audit raised")
        assert i != -1, f"{name} no longer explains the figure at all"
        tip = text[i:i + 400]
        for state in ("fixed", "regressed", "accepted", "withdrawn", "candidate"):
            assert state in tip, (name, f"the explanation omits `{state}`, which the "
                                        "engine counts")
        assert "decided about" not in tip, (
            name, "`regressed` is not something anyone decided; it is the state machine "
                  "reporting a fix that did not hold")


@live
def test_the_primary_action_says_what_the_click_does_and_counts_what_it_acts_on(served, browser):  # noqa: F811
    """Item 168, channel ruling 20260917-0045, question 2.

    "next: Triage" named a step and read as a status. The action is now a verb
    for what the click does, and sentence three names the same step, so the
    reader is told what is left and handed the button for it in one place.

    The served fixture is at Precheck, so this holds the rule on whichever step
    is next rather than one step: the verb matches the step the sentence names,
    and a count appears only where the step has one. The triage count - findings
    not yet been through, `total - assessed` - is held on the source below and
    was read live on twenty22 as "Start triage · 418" beside 505 found and 87
    been through.
    """
    base, ids = served
    pg = _open(browser, base, ids["site"], TWENTY22)
    got = pg.evaluate("""() => ({
      primary: (document.querySelector('.run-scope .bl-primary')?.textContent || '').trim(),
      left: (document.querySelector('.run-scope .bl-s3')?.textContent || '').trim(),
    })""")
    if not got["primary"]:
        pytest.skip("the fixture has no next step, so there is no primary action to read")
    assert not got["primary"].startswith("next:"), got
    pairs = {"The precheck": "Run the precheck", "An audit": "Start an audit",
             "Triage": "Start triage", "The catalogue": "Open the catalogue",
             "The record": "Open the record", "The client report": "Build the client report"}
    left = got["left"].removesuffix(" is what is left.")
    assert left in pairs, got
    assert re.match(rf"^{re.escape(pairs[left])}( · \d+)?$", got["primary"]), got


def test_the_triage_count_is_what_the_click_will_act_on():
    """The half the fixture cannot reach, held on the source: the count on
    "Start triage" is the findings not yet been through, off the headline the
    sentence reads - a promise about the click, not about the audit."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "anatomy.tsx").read_text(encoding="utf-8")
    body = src[src.index("export function primaryCount("):src.index("export function destinationsOf(")]
    assert 'step.name === "Triage"' in body, body
    assert "headline.assessed.total - headline.assessed.assessed" in body, body
