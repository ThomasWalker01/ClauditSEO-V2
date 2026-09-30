"""UX-07: what a score's band *means* was reachable only by hovering.

The composite is the product's headline number, and `ScoreBadge` drew it as a
coloured mark and a figure - `[dot] 84.2` - with the band word in an `sr-only`
span and the numeric range that defines the band in a `title` on a
non-focusable `<span>`. A keyboard reaches neither the span nor the tooltip,
so "84.2 is good, and good means 80 or above" was mouse-only at all eight
places the app shows a score.

**The invariant this is held to is the codebase's own, and it is stricter than
"give it to a screen reader".** `components.tsx`'s `BriefPriceFrame` states it
in as many words: a stated limitation on a displayed value appears in rendered
text, *"not only in a tooltip or an `sr-only` element"*. So moving the range
into the badge's `sr-only` sentence would satisfy the finding's wording and
breach the rule behind it, and the browser half below is written to fail if
that is what was done.

**Why an owner plus a key, and not a `title` per badge.** The band vocabulary
had two spellings in one expression - `SCORE_BANDS[].word` for the word and a
three-way ternary inside the `title` template for the range - which is the
shape UX-43 found for `withdrawn` and settled the same way: one exported
array, one small component that renders it, and a guard whose population is
parsed out of the owner rather than kept by hand in the test.

**Three tables could not take a `<caption>`, which decided the element.**
`views.tsx:689`, `reports.tsx:418` and `reports.tsx:499` already give their
table its one permitted `<caption>` to `NarrowRunNote`, so the key is a
paragraph beside the table rather than a second caption - read rather than
assumed, and the reason the shape differs from `NarrowRunNote`'s.

**What this file does not assert.** The source half below is per *file*: a
module that renders a score and renders a key passes, even if it has two score
tables and one key. Placement per surface is not statically decidable in JSX
without matching on line proximity, which moves on every commit above it. The
browser half covers the screen that actually carries a score for real, and the
gap between them is stated here rather than papered over.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clauditseo import axe
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_dashboard_a11y import _spoken, title_attrs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"
OWNER = SRC / "components.tsx"

#: The owner's array literal, from `export const SCORE_BANDS` to its closing
#: bracket.
BANDS_BLOCK = re.compile(r"export const SCORE_BANDS[^=]*=\s*\[(.*?)\n\];",
                         re.DOTALL)
#: One band's two readable fields. `word` is what the operator hears, `means`
#: is the range that defines it - the string that used to live in the `title`.
BAND_FIELDS = re.compile(r'word:\s*"([^"]+)"[^}]*?means:\s*"([^"]+)"')
#: Any `title=` attribute value, on one line or wrapped across several. The
#: dumb version deliberately: this is the *independent* enumeration of what
#: there is to read, and a matcher drawn from the thing it checks can only
#: ever pass.
TITLE_ATTR = re.compile(r"title=\{?[`\"]([^`\"]*)[`\"]", re.DOTALL)

#: The commit whose `components.tsx` carried UX-07. `70ed763` is the audit
#: commit of report 092, one commit before `21af44e` fixed the tooltip, so
#: its blob is the last tree where the defect this file guards was present.
UNFIXED = "70ed763"
#: What the unfixed tree says at `components.tsx:73`, and the only band range
#: a matcher has to reach to see the defect. `_bands()` supplies the
#: population; this names one member of it so the proof does not depend on
#: which band the ternary happens to put first.
UNFIXED_LINE = 73
UNFIXED_MEANS = "80 or above"
#: That blob, kept beside the tests. Read from `git show` it skipped wherever
#: the history is not there - the public tree starts at one commit - and the
#: rendered-a11y job turns a skip red (V2 CI, 2026-09-24).
UNFIXED_BLOB = Path(__file__).resolve().parent / "fixtures" / f"components_{UNFIXED}.tsx.txt"


def _titles(text: str):
    """`(line, spoken)` for every `title=` this source builds.

    One swap point, and it earned being one. The regex above stops at the
    first quote character inside a template literal, so on the unfixed
    `components.tsx` it captures `${band.word} - ${band.cls === ` and reaches
    none of the three band ranges the nested ternary chooses between - the
    clause below then reports the defect tree clean. Measured against the
    `70ed763` blob: 4 captures, 0 offenders.

    `title_attrs` is brace-balanced and `_spoken` joins interpolations, and
    `_spoken`'s own docstring names `components.tsx:73` - this exact
    expression - as the shape it was written for. Importing the pair costs
    nothing in independence: the strings still come from `SCORE_BANDS` via
    `_bands()`, and the walker is a JSX lexer that has never heard of a score
    band. Writing a third matcher instead is how the second one came to be
    wrong.
    """
    for line, expr in title_attrs(text):
        yield line, _spoken(expr)


#: The one element that paints a band badge. Everything that puts a score on
#: a screen reaches this span, directly or through a wrapper, so it is the
#: owner the population below is closed from - not a list of its callers.
BADGE_SPAN = re.compile(r"className=\{`score \$\{")
#: A component definition, exported or not. `DimScore` is module-private in
#: `views.tsx`, so requiring `export` would lose a third of the population.
COMPONENT_DEF = re.compile(r"^(?:export )?function (\w+)", re.MULTILINE)
#: The wrappers this file has always known about, kept only as the
#: counter-assertion's floor. This is not the population and nothing reads it
#: as one - that is the whole of CQ-208.
KNOWN_WRAPPERS = ("ScoreBadge", "RunScore", "DimScore")
#: The component that states the vocabulary in text.
# Item 176: Home moved the key into the shared legend (item 166), whose
# registry entries `score-good`, `score-fair` and `score-poor` carry the bands.
RENDERS_THE_KEY = re.compile(r"<ScoreBandKey\b|<Legend ids=\{\[[^\]]*\"score-good\"")


def _defs(text: str) -> dict[str, str]:
    """`name -> body` for every component in one module.

    A body runs to the next definition, which over-reads by whatever trails
    the last one. Harmless here: the only question asked of a body is whether
    it renders a member, and a tag belonging to the following component would
    put that component *into* the population, never take one out. Erring
    large is the safe direction for a guard whose failure mode is a screen it
    never looked at.
    """
    marks = list(COMPONENT_DEF.finditer(text))
    return {m.group(1): text[m.end():(marks[i + 1].start()
                                      if i + 1 < len(marks) else len(text))]
            for i, m in enumerate(marks)}


def _reaches_badge(defs: dict[str, str], seeds: set[str]) -> set[str]:
    """The components in one namespace that reach the badge, as a fixed point.

    Loops rather than running to a depth someone guessed at: a wrapper around
    a wrapper is the case a fixed list gets wrong twice over.
    """
    members = {name for name, body in defs.items() if BADGE_SPAN.search(body)}
    members |= seeds
    while True:
        grown = {name for name, body in defs.items()
                 if any(re.search("<" + m + r"\b", body) for m in members)}
        if grown <= members:
            return members
        members |= grown


def _score_components(extra: str = "") -> set[str]:
    """The shared vocabulary: components in the owner module that are a score.

    Hand-kept until CQ-208, eight lines below a population this same file
    derives from its owner and argues in a comment for deriving - "a list
    kept in the test is a list that goes stale the first time a band is
    added". The list was the three names in `KNOWN_WRAPPERS`, and it decided
    which modules the key clause inspects, so a fourth wrapper was invisible
    both to that clause and to the counter-assertion beneath it, whose floor
    of three the three surviving names satisfied on their own.

    **The dead end, recorded because the next reader will reach for it
    first.** The obvious derivation is one fixed point over the whole tree:
    seed at the badge span, then anything rendering a member is a member.
    Run, it returned `Router`, `HomeView`, `ReportsView`, `SiteDetailView`,
    `RunDetailView` and `Unreachable`, and reported `App.tsx` as a module
    that shows a score and hides the key. It does not - it mounts a router.
    "Renders a member" cannot tell a wrapper from a screen, because a screen
    containing a score is exactly the thing the key clause exists to catch;
    promote it into the vocabulary and the clause starts catching whatever
    contains *that*, all the way to the root.

    So the closure stops at the module boundary. The vocabulary is what the
    owner module exports - shared components any screen may import - and each
    module's own local wrappers are closed separately in `_renders_a_score`,
    where they cannot leak to a module that merely imports the screen.

    `extra` is source appended to the owner, so the closure can be asked the
    one question the tree cannot answer today: does a wrapper nobody typed in
    here join the population.
    """
    return _reaches_badge(_defs(OWNER.read_text(encoding="utf-8") + extra),
                          set())


def _renders_a_score(text: str) -> bool:
    """Does this module put a band badge on a screen.

    The shared vocabulary, plus whatever this module wraps it in locally -
    `DimScore` lives in `views.tsx`, not in the owner, so a check that read
    only the owner's exports would miss a third of the population.
    """
    members = _score_components()
    members = _reaches_badge(_defs(text), members)
    return any(re.search("<" + name + r"\b", text) for name in members)


def _every_score_component() -> set[str]:
    """The floor's population: the vocabulary and every module's wrappers."""
    members = _score_components()
    for path in _tsx():
        members |= _reaches_badge(_defs(path.read_text(encoding="utf-8")),
                                  _score_components())
    return members


def _tsx() -> list[Path]:
    return sorted(p for p in SRC.glob("*.tsx"))


def _bands() -> dict[str, str]:
    """`word -> means`, parsed out of the owner.

    The population comes from `SCORE_BANDS` for the reason `STATE_MEANING`'s
    guard gives: a list kept in the test is a list that goes stale the first
    time a band is added, and a stale population is a guard that waves the new
    one through.
    """
    m = BANDS_BLOCK.search(OWNER.read_text(encoding="utf-8"))
    if not m:
        return {}
    return dict(BAND_FIELDS.findall(m.group(1)))


def test_the_band_vocabulary_names_its_range_in_one_place():
    """The owner assertion, and the floor every clause below stands on.

    Before this finding was taken, `SCORE_BANDS` carried `word` and the range
    lived in a ternary inside the `title` template beside it - so the two
    halves of one vocabulary were written in two places and only one of them
    was data. This fails on that tree: there is no `means` to parse, and an
    unexported const is not an owner anything else can read.
    """
    bands = _bands()
    assert len(bands) >= 3, (
        "`SCORE_BANDS` in components.tsx does not export a `means` for each "
        "band, so the range that defines a band is not owned anywhere a "
        f"reader or a guard can find it: parsed {bands!r}")
    for word, means in bands.items():
        assert means.strip(), f"band {word!r} declares an empty range"


def test_no_title_states_what_a_score_band_means():
    """UX-07 itself, over the whole tree rather than over the one component.

    Asked of every `.tsx` and not of `ScoreBadge`, because the rule is the
    tree's: a badge added tomorrow that explains its band in a tooltip is the
    same defect, and this is the clause that would catch it.
    """
    bands = _bands()
    assert len(bands) >= 3, (
        "the population is empty, so this clause tests nothing - fix "
        "`test_the_band_vocabulary_names_its_range_in_one_place` first")
    offenders = []
    for path in _tsx():
        text = path.read_text(encoding="utf-8")
        for line, spoken in _titles(text):
            for word, means in bands.items():
                if means.lower() in spoken.lower():
                    offenders.append(f"{path.name}:{line} - {means!r}")
    assert not offenders, (
        "a score band's range is in a `title`, so a keyboard reaches the "
        "number and not what it means - render it with `ScoreBandKey`, which "
        "reads the same strings from `SCORE_BANDS`:\n  "
        + "\n  ".join(offenders))


def test_every_module_that_shows_a_score_also_shows_the_key():
    """Rule 3's clause, enumerated from the tree rather than from a list.

    `components.tsx` is the owner and is excluded: it declares both and
    renders a score only inside `RunScore`, which is an indirection its
    callers place, not a screen.
    """
    offenders = []
    for path in _tsx():
        if path == OWNER:
            continue
        text = path.read_text(encoding="utf-8")
        if _renders_a_score(text) and not RENDERS_THE_KEY.search(text):
            offenders.append(path.name)
    assert not offenders, (
        "these modules put a score on a screen and never say what its band "
        "means, so the number is unexplained wherever they are read: "
        + ", ".join(offenders))


def test_the_enumeration_finds_the_screens_it_is_meant_to_cover():
    """The counter-assertion. A population matching nothing would pass the
    clause above in silence, so what it found is asserted here.

    Two assertions, and the second is the one CQ-208 asked for. The module
    count is a floor from history - four modules rendered a score when this
    was written, anatomy, home, reports and views, and three is set below
    that so a legitimate deletion does not redden this while a broken pattern
    does. It is named as a historical floor rather than dressed up as a
    derived count, because it is not one: modules and components are
    different populations and a count of one cannot bound the other.

    The floor that did rise is the second. It was `len(found) >= 3`, which
    the three hand-typed names satisfied on their own - so a derivation that
    silently shrank to two would still have passed. It now names the three
    wrappers this file has always held and asserts the derivation still
    contains them, which no shrinkage can satisfy.
    """
    found = [p.name for p in _tsx()
             if p != OWNER
             and _renders_a_score(p.read_text(encoding="utf-8"))]
    assert len(found) >= 3, (
        "the score population matched almost nothing, so the guard above "
        f"tests almost nothing: {found}")
    derived = _every_score_component()
    assert derived >= set(KNOWN_WRAPPERS), (
        "the derivation lost a wrapper this file has held since it was "
        f"written: derived {sorted(derived)}, floor {sorted(KNOWN_WRAPPERS)}")


#: A fourth wrapper, of the shape the three real ones have: it renders the
#: badge and adds chrome around it. Written here rather than added to the
#: product because the question is what the *population* does when the tree
#: grows, and the tree is not the thing under test.
A_FOURTH_WRAPPER = """
export function HeadlineScore({ score }: { score: number | null }) {
  return <div className="headline-a11y"><ScoreBadge score={score} /></div>;
}
"""


def test_a_new_wrapper_joins_the_population_without_anyone_typing_it_in():
    """CQ-208. The population is closed from the owner, not listed.

    **Observed red before the closure was written**, against the three names
    that used to be `RENDERS_A_SCORE`: `HeadlineScore` renders the badge and
    the list had never heard of it, so the clause that decides which modules
    must show the key would have skipped its screen and the counter-assertion
    beneath it would have passed on the three survivors.

    The seed is the badge span itself - `className={`score ${band.cls}`}` at
    the one place a band is painted - so this closure is grounded in what the
    browser draws rather than in what a test author remembered. That is the
    same argument `_bands()` makes eight lines up, finally applied to the
    other population in this file.
    """
    grown = _score_components(extra=A_FOURTH_WRAPPER)
    assert "HeadlineScore" in grown, (
        "a component that renders the badge did not join the population, so "
        "the screens it appears on are outside every clause in this file: "
        f"derived {sorted(grown)}")
    assert grown > _score_components(), (
        "adding a wrapper changed nothing, which means the population is not "
        "being derived from the source it was handed")


def test_the_population_is_closed_from_the_badge_the_browser_paints():
    """The counter-assertion for the closure itself.

    A seed that stops resolving makes `_score_components` return an empty set,
    and an empty set makes `_renders_a_score` false everywhere - which passes
    the key clause in silence, exactly the failure the counter-assertion above
    was written for one level down.
    """
    text = OWNER.read_text(encoding="utf-8")
    assert BADGE_SPAN.search(text), (
        "the badge span is no longer at its owner, so the population below "
        "has no seed - re-derive `BADGE_SPAN` against `ScoreBadge`")
    seeds = [name for name, body in _defs(text).items()
             if BADGE_SPAN.search(body)]
    assert seeds == ["ScoreBadge"], (
        "the badge is painted by something other than `ScoreBadge`, which is "
        f"a change this file has to be told about: {seeds}")


def test_the_matcher_can_see_the_defect_this_file_was_written_for():
    """Rule 5, asked of this file's own matcher rather than of the product.

    The clause above is declared to hold UX-07 for the whole tree. Declared
    is not measured: run it over the tree it was written against and it must
    name the offender. `70ed763` is that tree - report 092's audit commit,
    one before the fix - so this is the one blob where the answer is known in
    advance and a green result means something.

    **This clause was observed red before the matcher was changed**, which is
    the whole reason it exists. Against the shipped `TITLE_ATTR` the walk
    returned 4 titles and 0 offenders on the defect blob, because the capture
    class excludes both quote characters and so stops at the first quote
    inside the template literal at line 73. The commit body that shipped that
    clause reported "4 of 5 cases failed" and that was its empty-population
    floor going red on an unexported `SCORE_BANDS`, not the tooltip being
    seen.

    Kept as its own clause rather than folded into the one above, because
    they fail for different reasons and a reader has to tell them apart: red
    here means the lens stopped working, red above means the product regrew
    the defect.
    """
    seen = list(_titles(UNFIXED_BLOB.read_text(encoding="utf-8")))
    hits = [(line, spoken) for line, spoken in seen
            if UNFIXED_MEANS.lower() in spoken.lower()]
    assert hits, (
        f"the matcher read {len(seen)} `title=` attributes on the {UNFIXED} "
        f"blob and reached none of the band ranges, so the clause that says "
        f"it holds UX-07 for the whole tree reports the defect tree clean. "
        f"What it read: {[t for _, t in seen]!r}")
    assert any(line == UNFIXED_LINE for line, _ in hits), (
        f"the band range was found, but not at components.tsx:{UNFIXED_LINE} "
        f"where the tooltip was - found at {[line for line, _ in hits]}")


def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


@live
def test_the_home_screen_says_what_a_score_band_means_without_a_mouse(
        served):  # noqa: F811
    """The finding, read off the served bundle rather than off the source.

    `inner_text` and not `text_content`, and the assertion that the key is not
    `sr-only`, are both load-bearing: the invariant this file is held to says
    rendered text specifically, so a fix that moved the range into the badge's
    hidden span would pass a `text_content` check and fail the rule. This
    reads what a sighted keyboard operator can actually see.
    """
    from playwright.sync_api import sync_playwright

    base, _ = served
    bands = _bands()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(f"{base}/#/", wait_until="domcontentloaded")
            page.wait_for_selector(".score", timeout=15000)
            # Item 176: the key is the shared legend's, opened from the
            # keyboard - focus its summary and press Enter, no pointer.
            page.focus(".home-row details.legend > summary")
            page.keyboard.press("Enter")
            page.wait_for_selector(".home-row details.legend[open] .legend-row", timeout=5000)
            painted = page.inner_text("body")
            classes = page.eval_on_selector_all(
                ".home-row details.legend[open]", "els => els.map(e => e.className)")
        finally:
            browser.close()

    missing = [m for m in bands.values() if m.lower() not in painted.lower()]
    assert not missing, (
        "the served home screen shows scores and never states what their "
        f"bands mean in text a reader can see: {missing} absent from the "
        "rendered page")
    assert classes, "no legend opened on Home, so nothing above was tested"
    assert not any("sr-only" in c for c in classes), (
        "the key is hidden from sight, which satisfies this finding's words "
        "and breaches the invariant behind it - `BriefPriceFrame`'s docstring "
        f"is the authority: {classes}")
