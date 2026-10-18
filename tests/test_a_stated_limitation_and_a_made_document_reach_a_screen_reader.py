"""Two announcements the dashboard owed and did not make.

**UX-87, carried from report 094 to report 111 — sixteen reports.** The
headline dimension table states three different limitations on a displayed
score — *not applicable*, *nothing was measured*, and *scored on part of this
dimension* — and all three put the reason in a `title` on a non-focusable
`<span>`. A keyboard reaches the abbreviation (`n/a`, `not assessed`,
`62% measured`) and never the sentence behind it. Sixty lines below, in the
same file, `AccessibilityScore` makes the opposite choice on the same screen
and says why in a comment: *"Rendered text, not a title: what this number is
not part of is a stated limitation on a displayed value, and the provenance
invariant puts those in text a keyboard can reach."* The fix shape was
already written down; only the cell had not adopted it.

**UX-88, carried from report 095 to report 111 — fifteen reports.** On the
comparison screen's generate control, *failure* is announced — `ErrorNote`
carries `role="alert"` — and *success* is not. The `Saved to … open the
document` line is a plain `<p className="muted">` with no live region, and
the button caption simply returns from `Generating…` to
`Generate comparison report`. A screen-reader operator who pressed it heard
the label change back and could not tell whether a client document had been
written. WCAG 2.2 AA 4.1.3 Status Messages.

**Why the busy word moves off the label.** `dashboard/src/reports.tsx:270-289`
already fixed the same defect on the Deliverables regenerate control (UX-64)
and recorded the reason: *"A control whose name changes mid-action is
announced as a different control, and the label is the accessible name — so
the state has to be said beside it rather than in it."* This file holds the
comparison control to the convention that fix established rather than
inventing a second one.

**Why the region is mounted unconditionally.** A live region inserted into
the DOM at the same moment as its content is not announced by most screen
readers — the region has to be there ahead of the text. `Loading`
(`dashboard/src/components.tsx:775`) is the house pattern for the words
themselves; the always-mounted wrapper is what makes them arrive.

**Both halves are read from source, not driven.** These are two source-level
claims about which element carries which attribute, and a Chromium drive
would answer a different question — whether a screen reader speaks it — that
no test in this repository can answer either. The clauses below are written
so a fix that satisfies them cannot leave the fact mouse-only.
"""

from __future__ import annotations

import re
from pathlib import Path

VIEWS = Path("dashboard/src/views.tsx")

#: The two components under test, each named rather than located by line, so
#: an edit above them cannot silently move this guard's population.
DIM = "DimScore"
COMPARE = "CompareView"


def _source() -> str:
    return VIEWS.read_text(encoding="utf-8")


def _body(owner: str) -> str:
    """One component's source, from the export/declaration to the first
    column-zero close brace — the same reading
    `tests/test_a_price_scope_note_claims_no_statistic.py` takes of
    `PriceScopeNote`, kept identical on purpose so a change cannot satisfy one
    guard and defeat the other."""
    source = _source()
    for opener in (f"export function {owner}", f"function {owner}"):
        if opener in source:
            return source.split(opener, 1)[1].split("\n}", 1)[0]
    raise AssertionError(
        f"{owner} is not defined in {VIEWS}; this guard's population is empty "
        "and every clause below would pass by finding nothing")


def _uncommented(body: str) -> str:
    """Source with comments removed. Both defects are described at length in
    the comments this fix leaves behind, and a guard that read them would be
    reading its own explanation back as the defect."""
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    return re.sub(r"//[^\n]*", " ", body)


# --------------------------------------------------------------------------
# Population. Both clauses below are about components that must exist and must
# still render the thing the finding is about; without these, a rename would
# turn this file green by emptying it.
# --------------------------------------------------------------------------

def test_the_dimension_cell_still_states_three_limitations():
    body = _uncommented(_body(DIM))
    for token in ("applicable", "coverage", "unmeasured"):
        assert token in body, (
            f"{DIM} no longer reads {token!r}; the three-state cell UX-87 is "
            "about has changed shape and this guard's premise has gone")


def test_the_comparison_screen_still_makes_a_document():
    body = _uncommented(_body(COMPARE))
    assert "Generate comparison report" in body, (
        f"{COMPARE} no longer carries the generate control UX-88 is about")
    assert "made" in body and "madeError" in body, (
        f"{COMPARE} no longer distinguishes a made document from a failure; "
        "the asymmetry UX-88 names has gone")


# --------------------------------------------------------------------------
# UX-87
# --------------------------------------------------------------------------

def test_no_limitation_on_a_dimension_score_is_mouse_only():
    """UX-87. `title` is the mouse-only channel; the cell must not use it.

    The whole finding is that three sentences live in `title` attributes on
    non-focusable spans. Forbidding the attribute outright, rather than
    checking for the sentences elsewhere, is what makes a partial fix — one
    of the three moved, two left — fail this clause.
    """
    body = _uncommented(_body(DIM))
    found = re.findall(r"title\s*=", body)
    assert not found, (
        f"{DIM} still carries {len(found)} title attribute(s). A title is "
        "reachable by hovering a mouse and by nothing else, and "
        "AccessibilityScore in this same file renders the same class of "
        "statement as text for exactly that reason "
        "(dashboard/src/views.tsx, 'Rendered text, not a title').")


def test_the_unmeasured_checks_are_named_in_text_the_cell_renders():
    """UX-87, and **a floor rather than a defect clause** — stated because it
    is the one clause in this file that passed against the unfixed tree, and
    round 110 recorded a guard that looked red-proven and was not.

    It passes on both trees on purpose. At HEAD the enumeration existed but
    lived inside a `title`; after the fix it exists as a text node. What this
    clause forbids is the *third* tree, the one a careless fix produces:
    titles deleted, list dropped, three bare abbreviations left and the guard
    above satisfied. Read with the `title=` prohibition immediately above it,
    the pair says the list is present and is not in a title — which is the
    finding. Neither clause says that alone.
    """
    body = _uncommented(_body(DIM))
    assert re.search(r"unmeasured[^\n]*join", body), (
        f"{DIM} no longer joins the unmeasured list into anything; the "
        "enumeration UX-87 is about is not reaching the screen at all")


# --------------------------------------------------------------------------
# UX-88
# --------------------------------------------------------------------------

def _generate_button(body: str) -> str:
    """The generate control's JSX element, from `<button` to its close."""
    # Item 183: the control is a PrimaryButton; read as the button it renders.
    body = re.sub(r"<(?:PrimaryButton|SecondaryButton)\b", "<button", body)
    body = re.sub(r"</(?:PrimaryButton|SecondaryButton)>", "</button>", body)
    match = re.search(r"<button[^>]*>.*?Generate comparison report.*?</button>",
                      body, flags=re.S)
    assert match, (
        f"the generate control could not be located inside {COMPARE}; this "
        "guard reads the element rather than a line number and the element "
        "has changed shape")
    return match.group(0)


def test_the_generate_control_keeps_its_name_while_it_works():
    """UX-88, and the half UX-64's fix recorded the reason for: the accessible
    name is the label, so a label that changes mid-press is announced as a
    different control."""
    button = _generate_button(_uncommented(_body(COMPARE)))
    assert "Generating" not in button, (
        "the comparison generate control still swaps its own caption for a "
        "busy word. dashboard/src/reports.tsx:270-289 moved that word off the "
        "label for UX-64 and wrote down why; this control is the same case.\n"
        f"Element: {' '.join(button.split())}")


def test_the_made_document_is_announced_and_not_only_painted():
    """UX-88. The success outcome must sit inside a live region.

    Failure already does — `ErrorNote` carries `role="alert"`. This clause is
    the other half of that asymmetry: a document was written to disk and the
    only operator told about it was one who could see the paragraph appear.
    """
    body = _uncommented(_body(COMPARE))
    regions = re.findall(r'role="status"', body)
    assert regions, (
        f"{COMPARE} mounts no role=\"status\" region at all. The failure path "
        'carries role="alert" through ErrorNote, so the screen announces the '
        "outcome where nothing was produced and stays silent on the one where "
        "a client document was.")
    # The saved-document sentence must be inside one of them, not beside it.
    for region in re.finditer(
            r'<div[^>]*role="status"[^>]*>(.*?)</div>', body, flags=re.S):
        if "Saved to" in region.group(1):
            return
    raise AssertionError(
        'the "Saved to …" sentence is not inside a role="status" region. '
        "Mounting a region elsewhere on the screen does not announce this "
        "outcome; the text has to arrive inside a region that was already "
        "there.")


def test_the_live_region_is_mounted_before_it_has_anything_to_say():
    """UX-88, and the reason the region is not wrapped in `{made && …}`.

    A region created in the same render as its content is not announced —
    the assistive tech has nothing to observe a change against. So the
    element must not be gated on the state it reports.
    """
    body = _uncommented(_body(COMPARE))
    match = re.search(r"(.{0,120})<div[^>]*role=\"status\"", body, flags=re.S)
    assert match, f"{COMPARE} mounts no role=\"status\" region"
    preceding = match.group(1)
    assert not re.search(r"\{\s*made\s*&&\s*\(?\s*$", preceding), (
        'the role="status" region is mounted only once there is a document '
        "to report, which is the case a screen reader does not announce. "
        "Mount it unconditionally and let it be empty while idle.")
