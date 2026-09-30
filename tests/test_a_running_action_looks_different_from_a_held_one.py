"""A running action looks different from a held one (item 204).

The operator pressed "Run analysis" on the Images part and could not tell it
was running. The filing traced that to a stylesheet that never read
`aria-busy` or `aria-disabled` on a button. **Half of that was false**, and
the false half is why this file asserts what it does:

- `aria-disabled` WAS painted (item 178, `.tone.btn[aria-disabled="true"]`),
  and the factories set it for `busy` as well as for `why`. So a pressed
  button did change: gold to grey, solid to dashed, pointer to not-allowed.
- A button held for a reason - price unknown, the other check starting -
  wore **exactly** that look. Measured on the built stylesheet: busy and held
  differed on nothing. Every change from rest was a subtraction, and a
  control that goes quiet reads as switched off, not as working.

So the invariant is not "a busy button looks different from rest" - it
already did - but "busy is told apart from held", and that the words beside
it read as live rather than as the provenance line they sat level with
(`.act-busy` .76rem muted against `.part-prov` .74rem muted).

Three layers, because each can pass while the others fail:

1. **Source.** Every `role="status"` region whose busy words are a literal
   ending in the ellipsis wraps them in `<Working>`. A new region written the
   old way would render the old look and nothing else here would notice.
2. **The stylesheet**, on synthetic markup against the BUILT css (the item
   161 harness): busy and held differ in `::before`; the ring survives
   `prefers-reduced-motion` without its animation; `.working` is not the
   provenance line's ink.
3. **Driven**, on the product: the analysis POST held open by a route, the
   pressed button ringed, its held neighbour not, the words live, a seconds
   count after three, and all of it gone when the request answers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from clauditseo import axe
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_heading_fault import browser_page  # noqa: F401  (reused fixture)
from tests.parts import open_part

UI = Path(__file__).resolve().parents[1] / "dashboard" / "src"

#: A three-block part, so the actions row is `PartPage`'s - the row the
#: operator pressed in, with the free re-check beside the paid analysis.
PART = "Indexability & canonicals"


def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


# --- 1. source ----------------------------------------------------------------

#: A status region and its children, up to the tag that closes it. The
#: children of these regions are expressions and short words, never a nested
#: element of the same tag, which is what makes the lazy match safe here.
REGION = re.compile(r'<(span|div|p)\b[^>]*role="status"[^>]*>(.*?)</\1>', re.S)
#: Busy words: the ellipsis closing a literal (`"checking…"`) or closing JSX
#: text at a tag (`checking…</Working>`, or bare, `checking…</span>`). The
#: second form matters: wrapping the words moves them out of their quotes, and
#: the first version of this pattern, quotes only, stopped seeing every region
#: it had just fixed - the count below is what caught it.
BUSY_WORDS = re.compile(r'…["`<]')


#: Comments go first, kept to their line count. The house comments quote
#: the pattern they explain - `{urlVerdict && <p role="status">}` in
#: `views.tsx` - and the first run of this scanner matched the quotation,
#: reported it, and swallowed the real region beneath it.
#: Not after a word character or a slash: `accept="image/*"` in `admin.tsx`
#: otherwise opens a comment that runs to the next one and hides a region.
COMMENT = re.compile(r"(?<![\w/\"])/\*.*?\*/", re.S)

#: Regions that say a PAGE is loading rather than that a PRESS is in flight.
#: The loading word is `components.tsx`'s `Loading`, a different signal with
#: its own rules; drawing it as work somebody started would claim a press
#: nobody made.
LOADING = {"cl-landing-wait"}


def _regions():
    for path in sorted(UI.glob("*.tsx")):
        text = COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"),
                           path.read_text(encoding="utf-8"))
        for m in REGION.finditer(text):
            if any(c in m.group(0)[:m.group(0).find(">")] for c in LOADING):
                continue
            line = text.count("\n", 0, m.start()) + 1
            yield f"{path.name}:{line}", m.group(2)


def test_every_busy_sentence_is_drawn_as_working():
    """The clause that keeps the next region from being written the old way.

    Counted as well as checked: a regex that stopped matching regions would
    pass by finding nothing to complain about, so the number wrapped is
    asserted to be the sweep's, not merely non-zero.
    """
    bare, wrapped = [], []
    for where, body in _regions():
        if not BUSY_WORDS.search(body):
            continue
        (wrapped if "<Working" in body else bare).append(where)
    assert not bare, (
        "these status regions say an action is in flight in the muted ink of "
        "the provenance line beside them, which is the look item 204 retired: "
        f"wrap the busy words in <Working>. {bare}")
    assert len(wrapped) >= 38, (
        f"only {len(wrapped)} busy regions were found at all, against the "
        f"sweep's 38; the scanner has stopped matching: {wrapped}")


def test_the_ring_is_for_buttons_and_the_mark_is_for_words():
    """The selectors the harness below relies on, pinned to the source, so a
    rename in one place cannot leave the harness testing a rule nobody uses."""
    css = (UI / "styles.css").read_text(encoding="utf-8")
    assert 'button.tone[aria-busy="true"]::before' in css
    assert ".working::before" in css
    working = (UI / "working.tsx").read_text(encoding="utf-8")
    assert 'className="working"' in working
    assert 'aria-hidden="true"' in working, (
        "the seconds count sits inside a polite live region; without "
        "aria-hidden it is announced every second")


# --- 2. the built stylesheet ----------------------------------------------------

def _built_css() -> str:
    return next((DIST / "assets").glob("index-*.css")).read_text(encoding="utf-8")


#: The factory's exact classes and attributes for each state (`buttons.tsx`,
#: `spend.tsx`): busy sets both attributes, held only `aria-disabled`.
HARNESS = """
<div class="part-actions"><div class="part-acts">
  <button id="rest" class="tone tone-action-paid btn btn-spend spend-btn">Run analysis</button>
  <button id="busy" class="tone tone-action-paid btn btn-spend spend-btn"
          aria-busy="true" aria-disabled="true">Run analysis</button>
  <button id="held" class="tone tone-action-paid btn btn-spend spend-btn"
          aria-disabled="true">Run analysis</button>
  <button id="pill" class="tone tone-action-free" aria-busy="true" disabled>run precheck</button>
  <span class="muted act-busy" role="status"><span id="words" class="working">Running…</span></span>
</div><div class="part-prov"><span id="prov" class="prov-line">automatic checks</span></div></div>
"""

READ = """() => {
  const b = (id) => getComputedStyle(document.getElementById(id), '::before');
  const c = (id) => getComputedStyle(document.getElementById(id)).color;
  return {
    rest: b('rest').content, busy: b('busy').content, held: b('held').content,
    pill: b('pill').content,
    busyWidth: parseFloat(b('busy').width) || 0,
    busyAnim: b('busy').animationName, wordsAnim: b('words').animationName,
    words: c('words'), prov: c('prov'),
  };
}"""


def _harness(pg, reduced: bool):
    pg.emulate_media(reduced_motion="reduce" if reduced else "no-preference")
    pg.set_content("<!doctype html><html><head><style>" + _built_css()
                   + "</style></head><body>" + HARNESS + "</body></html>")
    return pg.evaluate(READ)


@live
def test_busy_is_told_apart_from_held_on_the_built_stylesheet(browser_page):
    """The fault in one comparison. Before item 204 all three of these read
    `none`, and busy and held were the same button."""
    got = _harness(browser_page, reduced=False)
    assert got["rest"] == "none" and got["held"] == "none", (
        f"the ring is drawn on a button that is not working: {got}")
    assert got["busy"] != "none" and got["busyWidth"] > 0, (
        "a working button draws nothing a held one does not, so the reader "
        f"cannot tell 'running' from 'not allowed yet': {got}")
    assert got["pill"] != "none", (
        "a raw <Pill as=\"button\"> in flight draws no ring; the rule is "
        f"scoped to factory buttons only: {got}")
    assert got["busyAnim"] == "btn-spin" and got["wordsAnim"] == "working-pulse", got
    assert got["words"] != got["prov"], (
        "the busy words are the provenance line's ink, which is the half of "
        f"the report the filing had right: {got}")


@live
def test_without_motion_the_ring_still_says_working(browser_page):
    """Reduced motion takes the animation, not the distinction: a still ring
    that is only present on busy is still a difference from held."""
    got = _harness(browser_page, reduced=True)
    assert got["busy"] != "none" and got["held"] == "none", got
    assert got["busyAnim"] == "none" and got["wordsAnim"] == "none", (
        f"something still moves under prefers-reduced-motion: {got}")


# --- 3. driven ------------------------------------------------------------------

DRIVEN_READ = """() => {
  const brief = document.querySelector('.part-actions .act-brief');
  const sweep = document.querySelector('.part-actions .act-sweep');
  const region = document.querySelector('.part-actions .act-busy');
  const b = (el) => getComputedStyle(el, '::before');
  return {
    briefBusy: brief.getAttribute('aria-busy'),
    briefRing: b(brief).content, briefWidth: parseFloat(b(brief).width) || 0,
    sweepHeld: sweep.getAttribute('aria-disabled'), sweepRing: b(sweep).content,
    sweepDisabled: sweep.disabled,
    working: !!region.querySelector('.working'),
    text: region.textContent,
  };
}"""


@live
def test_a_pressed_analysis_is_drawn_working_until_it_answers(served, browser_page):
    """The operator's press, with the model call held open so the in-flight
    state can be read for as long as it is needed and then ended on cue."""
    base, ids = served
    held: list = []

    def hold(route):
        if route.request.method == "POST":
            held.append(route)
        else:
            route.continue_()

    browser_page.route("**/api/runs/*/expert/*", hold)
    browser_page.goto(f"{base}/#/sites/{ids['site']}?tab=findings", wait_until="load")
    browser_page.wait_for_selector(".anat-layout", timeout=15_000)
    open_part(browser_page, PART)
    browser_page.wait_for_selector('.part-actions .act-brief:not([aria-disabled="true"])',
                                   timeout=15_000)

    browser_page.click(".part-actions .act-brief")
    browser_page.click(".confirm-dialog .confirm-go")
    browser_page.wait_for_selector('.part-actions .act-brief[aria-busy="true"]', timeout=10_000)
    assert held, "the press reached no analysis POST, so nothing was in flight to draw"

    got = browser_page.evaluate(DRIVEN_READ)
    assert got["briefRing"] != "none" and got["briefWidth"] > 0, (
        f"the pressed button is in flight and draws no ring: {got}")
    assert got["sweepHeld"] == "true" and got["sweepRing"] == "none", (
        "the re-check beside it should be held (not working) while the "
        f"analysis runs, and drawn as held: {got}")
    assert not got["sweepDisabled"], (
        "the re-check is held by a real `disabled` again, which draws it "
        f"solid on white beside a dashed neighbour: {got}")
    assert got["working"] and "Running the analysis" in got["text"], got

    browser_page.wait_for_function(
        """() => /· \\d+ s/.test(document.querySelector('.part-actions .act-busy').textContent)""",
        timeout=8_000)

    for route in held:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True}))
    browser_page.wait_for_selector('.part-actions .act-brief:not([aria-busy="true"])',
                                   timeout=10_000)
    after = browser_page.evaluate(DRIVEN_READ)
    assert after["briefRing"] == "none" and not after["working"], (
        f"the request answered and the working look stayed: {after}")
