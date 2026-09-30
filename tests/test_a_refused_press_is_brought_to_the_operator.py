"""UX-82's second half: a refused write must report where the operator is.

Round 087 closed the first half - `ErrorNote` gained `role="alert"`, so the
message is announced. What it left, in its own words at
`tests/test_an_error_the_operator_must_notice_is_announced.py:26-30`, is where
the message renders: the record screen paints a refused verb *above* a table
that pages at fifty (`dashboard/src/views.tsx`, `const PAGE = 50`), so a press
on row 40 put the only report of its failure above a fold the operator had
scrolled past.

**The remaining defect is sighted-operator-only, which is narrower than the
finding's wording.** The `role="alert"` already tells assistive technology
whatever the viewport is doing - verified against the served bundle at
`OPERATOR_ACTIONS.md:193`. The operator who cannot see it is the one who
pressed the button and is looking at row 40.

**Three mechanisms, and the choice was the operator's.** Filed as `Q-8`,
because the obvious one reverses a written decision: the comment at the call
site records WF-95 choosing this position deliberately - *"above the table
rather than in the row, because the row the press failed on may not be on
screen once the table re-reads"*. The options were to move the note into the
row, to bring the operator to the note, or to take focus to it. Answered
2026-08-24: **bring the operator to the note.** So the assertion below is
about the viewport, not about where in the DOM the paragraph sits - a fix that
moved the note into the row would fail this file, and correctly, because that
is the option that was not chosen.

**Driven, not read.** The claim is "the operator can see it", and no amount of
source says whether an element is on screen. The browser clause below scrolls
the real bundle past the fold, forces a real 404 out of the real route, and
reads the painted paragraph's rectangle against the viewport - the same reason
`test_an_error_the_operator_must_notice_is_announced.py` drives its 503 rather
than grepping for `role`. The static clause is a different question: that the
mechanism is spelled the one way this codebase already spells it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clauditseo import axe
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

#: A `scrollIntoView` call and whatever it was given, on one line.
SCROLL = re.compile(r"scrollIntoView\(([^)]*)\)")


def _scroll_calls():
    """Every `scrollIntoView` in the dashboard, as `(path, line, args)`."""
    for path in sorted(SRC.glob("*.tsx")):
        for i, line in enumerate(path.read_text(encoding="utf-8").split("\n")):
            for m in SCROLL.finditer(line):
                yield path, i + 1, m.group(1)


def test_the_tree_holds_scroll_calls_for_this_to_check():
    """DISCIPLINE rule 5. A pattern that matches nothing satisfies the clause
    below without reading a line of the product, and it looks exactly like a
    clean tree.

    Two at the time of writing - `anatomy.tsx`'s heading mark and
    `components.tsx`'s error note - and the floor is one rather than two on
    the reasoning the sibling guard states: either call could be legitimately
    deleted, and a floor that is also today's count turns an ordinary
    deletion red. What must never pass silently is a regex that matches
    nothing, which is what one catches.
    """
    found = list(_scroll_calls())
    assert len(found) >= 1, (
        "`SCROLL` matched almost nothing, so the convention check below tests "
        f"almost nothing: {[(p.name, n) for p, n, _ in found]}")


def test_every_scroll_into_view_uses_the_convention_already_in_the_tree():
    """One spelling, chosen once and argued once.

    `anatomy.tsx` got here first and wrote down why: `center` rather than
    `nearest`, because `nearest` leaves an element that is technically on
    screen exactly where it already sat - which is the whole failure here, an
    operator who cannot find the message. And no `behavior`, so the scroll
    obeys the browser's own motion setting instead of animating regardless of
    what the operator asked their machine for.

    A second convention would be the shape UX-82 was in the first place: a
    rule the codebase knew and re-decided per call site.
    """
    offenders = []
    for path, line, args in _scroll_calls():
        if 'block: "center"' not in args:
            offenders.append(f'{path.name}:{line} - no `block: "center"`: {args!r}')
        elif "behavior" in args:
            offenders.append(f"{path.name}:{line} - sets `behavior`: {args!r}")
    assert not offenders, (
        "a second scroll convention is being invented - `anatomy.tsx` states "
        'this one as `{ block: "center" }` with no `behavior`, and says why '
        "at the call:\n  " + "\n  ".join(offenders))


def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


#: Short enough that the record table runs past it on the fixture's own
#: findings, rather than needing fifty seeded rows before a fold exists. The
#: premise is asserted below rather than assumed, so a fixture that shrank
#: reddens here instead of passing on a page that never scrolled.
VIEWPORT = {"width": 1280, "height": 600}


@live
def test_a_refused_verb_brings_its_report_into_the_operators_view(
        served):  # noqa: F811
    """The finding itself, measured as a rectangle against a viewport.

    The route is forced to 404 the way the product's own refusal answers -
    `set_state` matched no row - so the paragraph under test is the real
    `ErrorNote` the real bundle renders from the real catch, not a component
    mounted alone.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served

    def refuse(route):
        if route.request.method == "POST":
            route.fulfill(status=404, content_type="application/json",
                          body='{"detail": "no such finding state"}')
        else:
            route.continue_()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        try:
            page.route("**/api/sites/*/states/*", refuse)
            # `group=none`: the verbs pressed here are a finding's own, and
            # the record groups by check since brief step 6.
            page.goto(f"{base}/#/sites/{ids['site']}?tab=all&group=none",
                      wait_until="domcontentloaded")
            verbs = page.locator("table.findings tbody button.btn")
            verbs.first.wait_for(timeout=15000)
            pressable = verbs.count()

            # Where the operator actually is: the bottom of a long table.
            page.evaluate(
                "window.scrollTo(0, document.documentElement.scrollHeight)")
            fold = page.evaluate(
                "document.querySelector('table.findings')"
                ".getBoundingClientRect().top")

            verbs.last.click()
            # Item 178: withdraw and accept risk ask first.
            if page.locator("[role=alertdialog]").count():
                page.click("[role=alertdialog] .confirm-go")
            note = page.locator("p.error", has_text="failed:")
            note.wait_for(timeout=15000)
            seen = page.evaluate(
                """() => {
                    const p = [...document.querySelectorAll('p.error')]
                        .find((e) => e.textContent.includes('failed:'));
                    const r = p.getBoundingClientRect();
                    return {top: r.top, bottom: r.bottom,
                            view: window.innerHeight, text: p.textContent};
                }""")
        finally:
            browser.close()

    # The premise, before the claim. A table that never left the viewport
    # would make the assertion below pass without the fix having done a thing.
    assert pressable > 1, (
        f"the fixture offered {pressable} verb button(s), so there is no row "
        "far from the note and nothing here was tested")
    assert fold < 0, (
        f"the table's top sat at {fold:.0f}px after scrolling to the bottom, "
        "so the place the note renders was still on screen and this test "
        "proves nothing")

    assert "failed:" in seen["text"], (
        f"the refusal never reached the screen: {seen['text']!r}")
    assert 0 <= seen["top"] and seen["bottom"] <= seen["view"], (
        "the operator pressed a verb at the bottom of the record and the "
        f"only report of its refusal painted at {seen['top']:.0f}px in a "
        f"{seen['view']}px viewport - off screen, which is where UX-82 says "
        f"it has been since WF-95: {seen['text']!r}")
