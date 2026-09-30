"""UX-82: an error paragraph that arrives after paint must be announced.

WCAG 2.2 AA 4.1.3 Status Messages. `ErrorNote` is the dashboard's shared
report-a-failure element and it rendered `<p className="error">` with no
`role` and no `aria-live` - so every asynchronous failure the app shows, at
fifty-six call sites across ten modules, reached a screen-reader operator as
silence. The site added by round 086 to report a record verb the route refused
(`dashboard/src/views.tsx`) was the fifty-sixth.

**Why the component and not the call sites.** The codebase already knew the
pattern and decided it per call site: `App.tsx`'s server-down paragraph sets
`role="alert"` by hand, `components.tsx`'s loading line sets
`role="status" aria-live="polite"`, and `advice.tsx`, `anatomy.tsx` and
`reports.tsx` each decide it again. Fifty-six inheritors of one component is
the only shape in which this rule can be stated once, which is why the source
half below enumerates the paragraphs from the tree rather than asserting
against a list somebody keeps up to date.

**Two halves, and neither replaces the other.** The browser half drives a real
failure through a real bundle and reads the attribute off what was painted -
static analysis checks what the author declared, and this codebase has already
paid twice for the difference (`tests/test_dashboard_a11y.py`'s own docstring).
The source half is what covers the fifty-five call sites one browser drive
cannot reach, and the hand-rolled paragraphs that are not `ErrorNote` at all.

**What is deliberately not asserted here.** UX-82's evidence also says the
message can render above a fold the operator has scrolled past - `PAGE` is 50,
so a verb pressed on row 40 of the record puts the only report of its failure
off-screen. That is a placement question, not an announcement one; nothing
below tests it and the finding's second clause is not closed by this file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clauditseo import axe
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

#: An opening `<p>` tag whose class list begins `error`. Every one in the tree
#: is written on a single line, which is checked below rather than assumed: a
#: tag this cannot see is a paragraph this guard silently waves through, and a
#: guard that can be evaded by a line break is not a guard.
ERROR_P = re.compile(r'<p\s+className="error(?:\s[^"]*)?"[^>]*>')

#: A live region: either the assertive kind, or a polite one that says so.
#: `role="status"` alone is the shape UX-69 accepted and Q3 answered - mount
#: timing, not marking - so it counts here.
ANNOUNCED = (re.compile(r'role="alert"'), re.compile(r'role="status"'))

#: The spend warning, which is content rather than a status message.
#:
#: Three screens paint `budget.warning` and all three paint it *with the card
#: it lives in*, from data the screen fetched before it rendered - Admin above
#: `This month: ...`, Home in the same card as the matching `Stat`, and Tools
#: beside its own. Nothing arrives in response to a press, so an operator
#: reading the page meets it as ordinary text in reading order. Marking it
#: `role="alert"` would make it interrupt on arrival, which is the shape the
#: operator answered on at `audits/DISPOSITIONS.md` Q3 - a region that mounts
#: with its first content is accepted here and the loop should not re-shape it.
#:
#: Keyed on a marker in the three lines ending at the tag, not on a line
#: number: line numbers move on every commit above them, and an exception
#: register that goes stale silently is worse than none.
#: `budgetWarn` left with item 188: it was `tools.tsx`'s marker, and an
#: exemption for a file that no longer exists is an exemption that can
#: never be exercised - which this clause fails on rather than carries.
MOUNTS_WITH_ITS_CARD = ("budget.warning", "error home-setup")

#: How many lines above the tag the marker may sit. Two was for `tools.tsx`,
#: which wrote its guard on the line before the tag; the two remaining write
#: theirs on the tag's own line. Kept at two rather than tightened to one,
#: because a marker one line up is still the same guard and tightening it
#: would fail the next screen that wraps its condition.
LOOKBACK = 2


def _tsx() -> list[Path]:
    return sorted(p for p in SRC.glob("*.tsx"))


def _paragraphs():
    """Every error paragraph in the tree, as `(path, line number, tag, window)`."""
    for path in _tsx():
        lines = path.read_text(encoding="utf-8").split("\n")
        for i, line in enumerate(lines):
            for m in ERROR_P.finditer(line):
                window = "\n".join(lines[max(0, i - LOOKBACK):i + 1])
                yield path, i + 1, m.group(0), window


def test_the_tree_holds_error_paragraphs_for_this_to_check():
    """The enumeration itself, asserted rather than assumed.

    A regex that matches nothing passes every clause below it. `ErrorNote` and
    the hand-rolled paragraphs were ten at the time of writing; the floor is
    stated low enough to survive a legitimate deletion and high enough that a
    silently-broken pattern reddens here rather than turning the real guard
    into a no-op.
    """
    found = list(_paragraphs())
    assert len(found) >= 8, (
        "ERROR_P matched almost nothing, so the guard below tests almost "
        f"nothing: {[(p.name, n) for p, n, _, _ in found]}")


def test_no_error_paragraph_is_split_across_lines():
    """`ERROR_P` reads one line at a time, so a multi-line opening tag is
    invisible to it. This is the assertion that keeps that from being a way
    through: a `<p` whose `className="error..."` lands on a later line fails
    here instead of passing the clause below in silence."""
    offenders = []
    for path in _tsx():
        lines = path.read_text(encoding="utf-8").split("\n")
        for i, line in enumerate(lines):
            if re.search(r"<p\s*$", line):
                nxt = lines[i + 1] if i + 1 < len(lines) else ""
                if 'className="error' in nxt:
                    offenders.append(f"{path.name}:{i + 1}")
    assert not offenders, (
        "an error paragraph's opening tag spans two lines, which `ERROR_P` "
        "cannot see - put it on one line:\n  " + "\n  ".join(offenders))


def test_every_error_paragraph_is_announced():
    """UX-82, over the whole tree rather than over the one component.

    The rule is the component's to state and the call sites inherit it, so in
    the fixed tree `ErrorNote` carries the only interesting row here - but the
    hand-rolled paragraphs implement the same rule and one added tomorrow
    would too, which is why this asks the tree and not `ErrorNote`.
    """
    offenders = []
    for path, line, tag, window in _paragraphs():
        if any(marker in window for marker in MOUNTS_WITH_ITS_CARD):
            continue
        if any(p.search(tag) for p in ANNOUNCED):
            continue
        offenders.append(f"{path.name}:{line} - {tag}")
    assert not offenders, (
        "an error that arrives after paint is announced to nobody - give the "
        'paragraph `role="alert"`, or register it in '
        "`MOUNTS_WITH_ITS_CARD` with the reason it is content rather than a "
        "status message:\n  " + "\n  ".join(offenders))


def test_the_exempt_paragraphs_are_all_still_there():
    """The register's own counter-assertion. Every marker in
    `MOUNTS_WITH_ITS_CARD` must still match a paragraph, so an entry left
    behind by a deletion reddens here rather than quietly widening the
    exemption for whatever is written next."""
    windows = [w for _, _, _, w in _paragraphs()]
    unused = [m for m in MOUNTS_WITH_ITS_CARD
              if not any(m in w for w in windows)]
    assert not unused, (
        "these exemptions match no error paragraph any more, so they are "
        f"holding the door open for nothing: {unused}")


def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


@live
def test_a_failed_request_paints_a_paragraph_a_screen_reader_is_told_about(
        served):  # noqa: F811
    """The finding itself, read off the painted element.

    A site fetch is forced to 503 the way `tests/test_fetch_state.py` forces
    one, so the paragraph under test is a real `ErrorNote` rendered by the
    real bundle in response to a real failure - not a component mounted in
    isolation, which would prove the attribute is in the source and nothing
    about what the app serves.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        try:
            page.route(
                f"**/api/sites/{ids['site']}",
                lambda route: route.fulfill(
                    status=503, content_type="application/json",
                    body='{"detail": "alpha is unavailable"}'))
            page.goto(f"{base}/#/sites/{ids['site']}",
                      wait_until="domcontentloaded")
            page.wait_for_selector("p.error", timeout=15000)
            painted = page.inner_text("p.error")
            role = page.get_attribute("p.error", "role")
        finally:
            browser.close()

    assert "alpha is unavailable" in painted, (
        f"the failure never reached the screen, so nothing was tested: {painted!r}")
    assert role == "alert", (
        "the served bundle paints the failure with role="
        f"{role!r} - a screen-reader operator is told nothing, while the "
        f"sighted one reads {painted!r}")
