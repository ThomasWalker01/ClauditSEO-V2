"""The two accessibility defects in the product's newest control.

**UX-96 and UX-97, both carried from report 102 to report 112 — ten reports,
and named as the *first lever* by every report from 104 onward without a round
ever taking them.** They cross the ten-report threshold at round 112, which is
what finally brings them under `audit-fix/SKILL.md` step 4's cohort rule
rather than under a severity ranking a fresher High always won.

**UX-96.** `LauncherView`'s "Check this URL" button swaps its own caption to
`Checking…` while the request is in flight. The label is a button's accessible
name, so a name that changes mid-press is announced as a *different control
appearing* — the operator who pressed one button is told another now has
focus. `dashboard/src/reports.tsx:270-289` fixed exactly this on the
Deliverables regenerate control (UX-64) and wrote the reason down; round 111
then applied the same shape a second time, to `CompareView`'s generate control
(UX-88), thirteen hundred lines above this one in this same file. This control
is the third instance of a defect whose fix is twice-precedented in the tree.

**UX-97.** The verdict paragraph is mounted only once there is a verdict:
`{urlVerdict && (<p role="status">…</p>)}`. A live region inserted into the
DOM in the same render as its content gives assistive technology nothing to
observe a change against, so the announcement most screen readers make is
none. `components.tsx:775` (`Loading`) is the house pattern for the words;
round 111's UX-88 fix is the house pattern for the *mounting*, and its own
comment states the rule: the region "has to be here" ahead of the text.

**Why one file for both.** They are one control and one press: the operator
presses, hears nothing useful about the state, and then is not told the answer.
A fix for either alone leaves the same press half-announced.

**Read from source, not driven.** These are claims about which element carries
which attribute. A Chromium drive would answer whether a screen reader *speaks*
it, which no test in this repository can answer — the same reading round 111's
`test_a_stated_limitation_and_a_made_document_reach_a_screen_reader.py` took of
the same pair of defects, and the clauses below are written in its shape so a
fix cannot satisfy one guard and defeat the other.
"""

from __future__ import annotations

import re
from pathlib import Path

VIEWS = Path("dashboard/src/views.tsx")

#: Named rather than located by line, so an edit above it cannot silently
#: empty this guard's population.
LAUNCHER = "LauncherView"

#: The control's caption, which is also its accessible name.
LABEL = "Check this URL"


def _source() -> str:
    return _as_buttons(VIEWS.read_text(encoding="utf-8"))



def _as_buttons(source: str) -> str:
    """Item 183: every button is one of the five variants now, and the two that
    render a `<button>` are written `PrimaryButton` and `SecondaryButton`. Read
    as the element they render, so this guard keeps reading captions."""
    source = re.sub(r"<(?:PrimaryButton|SecondaryButton)\b", "<button", source)
    return re.sub(r"</(?:PrimaryButton|SecondaryButton)>", "</button>", source)


def _body(owner: str) -> str:
    """One component's source, from its declaration to the first column-zero
    close brace — the identical reading round 111's guard takes, kept the same
    on purpose."""
    source = _source()
    for opener in (f"export function {owner}", f"function {owner}"):
        if opener in source:
            return source.split(opener, 1)[1].split("\n}", 1)[0]
    raise AssertionError(
        f"{owner} is not defined in {VIEWS}; this guard's population is empty "
        "and every clause below would pass by finding nothing")


def _uncommented(body: str) -> str:
    """Source with comments removed. The fix explains itself in comments that
    quote the defect, and a guard that read them would find its own
    explanation and report it as the fault."""
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    return re.sub(r"//[^\n]*", " ", body)


# --------------------------------------------------------------------------
# Population. Without these, deleting the control turns this file green.
# --------------------------------------------------------------------------

def test_the_launcher_still_offers_a_url_check():
    body = _uncommented(_body(LAUNCHER))
    assert LABEL in body, (
        f"{LAUNCHER} no longer carries the {LABEL!r} control UX-96 and UX-97 "
        "are both about; this guard's premise has gone")
    assert "urlVerdict" in body and "checking" in body, (
        f"{LAUNCHER} no longer distinguishes an in-flight check from its "
        "verdict, so neither clause below is deciding anything")


# --------------------------------------------------------------------------
# UX-96 — the name must not change under the press
# --------------------------------------------------------------------------

def _check_button(body: str) -> str:
    """The control's JSX element, read by its caption rather than its line."""
    match = re.search(r"<button[^>]*>.*?" + re.escape(LABEL) + r".*?</button>",
                      body, flags=re.S)
    assert match, (
        f"the {LABEL!r} control could not be located inside {LAUNCHER}; this "
        "guard reads the element rather than a line number and the element "
        "has changed shape")
    return match.group(0)


def test_the_url_check_control_keeps_its_name_while_it_works():
    """UX-96. The caption is the accessible name; it must be one word for the
    whole press."""
    button = _check_button(_uncommented(_body(LAUNCHER)))
    assert "Checking" not in button, (
        "the URL check control still swaps its own caption for a busy word. "
        "reports.tsx:270-289 moved that word off the same kind of button for "
        "UX-64 and recorded why, and round 111 applied the same shape to "
        "CompareView's generate control in this same file. This control is "
        "the third instance of the one defect.\n"
        f"Element: {' '.join(button.split())}")


def test_the_in_flight_state_is_carried_by_something_other_than_the_name():
    """UX-96, the other half. A caption that stops swapping and reports the
    state nowhere is not a fix — it removes the sighted operator's only signal
    and gives the screen-reader operator nothing in exchange. `aria-busy` is
    what UX-88's fix put in its place, and this holds this control to that."""
    button = _check_button(_uncommented(_body(LAUNCHER)))
    assert re.search(r"aria-busy\s*=\s*\{", button), (
        "the URL check control reports its in-flight state through no "
        "attribute at all. UX-88's fix moved the state to `aria-busy` when it "
        "took the word off the label; taking the word off without that leaves "
        "the press silent.\n"
        f"Element: {' '.join(button.split())}")


# --------------------------------------------------------------------------
# UX-97 — the region must predate the thing it announces
# --------------------------------------------------------------------------

def test_the_verdict_is_spoken_from_a_live_region():
    """UX-97. The answer to the press has to arrive inside a region, not as a
    paragraph that appears."""
    body = _uncommented(_body(LAUNCHER))
    assert re.search(r'role="status"', body), (
        f'{LAUNCHER} mounts no role="status" region, so the verdict an '
        "operator pressed a button to obtain is painted and not announced")
    assert (re.search(r'role="status"[^>]*aria-live', body)
            or re.search(r'aria-live[^>]*role="status"', body)), (
        'the verdict region carries role="status" without an explicit '
        '`aria-live`. The house pattern is both together — components.tsx:775 '
        "(`Loading`) and reports.tsx:284 — and this control is not the place "
        "to start a second convention")


def test_the_verdict_region_is_mounted_before_there_is_a_verdict():
    """UX-97, and the load-bearing half. A region created in the same render
    as its content is not announced: assistive technology has nothing to
    observe the change against. So the element must not be gated on the state
    it reports."""
    body = _uncommented(_body(LAUNCHER))
    match = re.search(r"(.{0,160})<p[^>]*role=\"status\"", body, flags=re.S)
    assert match, (
        f'{LAUNCHER} mounts no role="status" paragraph for the verdict')
    preceding = match.group(1)
    assert not re.search(r"\{\s*urlVerdict\s*&&\s*\(?\s*$", preceding), (
        "the verdict's role=\"status\" region is mounted only once there is a "
        "verdict to report, which is precisely the case a screen reader does "
        "not announce. Mount it unconditionally and let it be empty while "
        "idle — the shape round 111 shipped for UX-88 in this same file.\n"
        f"Preceding source: {' '.join(preceding.split())[-120:]}")
