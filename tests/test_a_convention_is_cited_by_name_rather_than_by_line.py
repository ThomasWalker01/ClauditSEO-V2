"""CQ-242. A comment pointing at this repo's own convention names it, not a line.

`PROFILE.md`'s "address in a comment" invariant already requires that a cited
`path:line` resolve, and `scripts/check_anchors.py` holds that to zero. This
guard covers the case that invariant explicitly leaves open, in the words of
its own text: the tool *resolves* an address, it "does not judge whether the
line still says what the comment claims", and a citation carrying no directory
is "skipped by construction" because guessing which `app.py` is meant is the
mistake being guarded against.

**Neither escape hatch applies to a same-file self-reference, and round 135
paid for the gap between them.** Its UX-66 sweep wrote twenty-one comments
across eleven files pointing a reader at the explanatory comment beside
`views.tsx`'s `ReportView` generate control, addressed as `views.tsx:2296`.
The same commit had already inserted fifteen lines earlier in `views.tsx` for
the same sweep, so by the time the citations were written the target sat eleven
lines further down. Every one of them resolved -- `views.tsx` exists and is
longer than 2296 lines -- and every one of them landed on
`<div className="inline-form">` instead of the convention. `check_anchors.py`
was clean throughout, correctly: this is the drift case, in the form the
directory-less skip makes invisible.

**Why this guard names a region rather than matching prose.** The profile
records two candidate semantic matchers measured and rejected at round 129, and
`check_anchors.py`'s own docstring refuses to guess whether a line still says
what a comment claims. So nothing here guesses. The rule is positional and
mechanical: the convention lives inside one component, that component's bounds
are read from the tree rather than hard-coded, and a citation addressing any
line inside it by number is the defect -- because the invariant's own stated
remedy is available and cheaper. `ReportView` does not move when the file
grows; line 2296 did, within a single commit.

Citations to lines *outside* that component are untouched. `reports.tsx:270-289`,
`components.tsx:812` and `views.tsx:1832` are cross-references to stable
addresses that resolve and that no sweep has been observed to shift, and
widening this guard to cover them would be a different finding with a different
population.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "dashboard" / "src"
CONVENTION_FILE = "views.tsx"
CONVENTION_SYMBOL = "ReportView"

#: A `/* ... */` span (which `{/* ... */}` contains) or a `//` line comment.
_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)

#: `views.tsx:2296` or `dashboard/src/views.tsx:2296`. A line range is matched
#: at its first number, which is the address a reader actually follows.
_QUALIFIED = re.compile(
    r"(?<![\w/])(?:[\w./-]*/)?" + re.escape(CONVENTION_FILE) + r":(\d{2,5})\b"
)

#: Inside `views.tsx` itself the house form drops the filename: "takes at
#: :2296". Only there does a bare address refer to this file.
_BARE = re.compile(r"(?<![\w/.:]):(\d{2,5})\b")


def _component_bounds(source: str, symbol: str) -> tuple[int, int]:
    """First and last line of a top-level component, read from the source.

    Hard-coding the bounds would make the guard stale the moment the file
    grows -- which is the exact failure it exists to catch, so it must not
    commit that failure itself.
    """
    lines = source.splitlines()
    tops = [i for i, ln in enumerate(lines, start=1)
            if re.match(r"(?:export )?function [A-Z]", ln)]
    start = next(i for i in tops
                 if re.match(rf"(?:export )?function {symbol}\b", lines[i - 1]))
    later = [i for i in tops if i > start]
    return start, (later[0] - 1 if later else len(lines))


def _citations_into_the_convention(
    files: dict[str, str], bounds: tuple[int, int]
) -> list[tuple[str, int, int]]:
    """Every comment citation addressing a line inside the convention.

    The population is whatever files are handed in, all of their comments, with
    no literal list of call sites anywhere: a hard-coded list of three is how a
    partial fix passes (DISCIPLINE rule 3).
    """
    low, high = bounds
    found = []
    for name, source in sorted(files.items()):
        for comment in _COMMENT.finditer(source):
            text = comment.group(0)
            at = source[: comment.start()].count("\n") + 1
            addresses = [int(n) for n in _QUALIFIED.findall(text)]
            if name == CONVENTION_FILE:
                addresses += [int(n) for n in _BARE.findall(text)]
            found += [(name, at, a) for a in addresses if low <= a <= high]
    return found


def _product_files() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in SRC.glob("*.tsx")}


def test_no_comment_addresses_the_convention_by_line() -> None:
    """The finding itself: nothing points at the convention by number."""
    views = (SRC / CONVENTION_FILE).read_text(encoding="utf-8")
    bounds = _component_bounds(views, CONVENTION_SYMBOL)
    offenders = _citations_into_the_convention(_product_files(), bounds)
    assert not offenders, (
        f"{len(offenders)} comment(s) address a line inside "
        f"`{CONVENTION_FILE}`'s `{CONVENTION_SYMBOL}` (lines "
        f"{bounds[0]}-{bounds[1]}) by number, which is the drift "
        f"`check_anchors.py` resolves and cannot judge. Name "
        f"`{CONVENTION_SYMBOL}` instead: "
        + ", ".join(f"{f}:{at} cites :{a}" for f, at, a in offenders)
    )


#: The reader has to be shown to find something, and the product stops being a
#: sample the moment the sweep empties it -- round 135's own guard lost its
#: population exactly that way, and had to move the sample off the product.
#: So the sample lives here: the citation shapes round 135 wrote, and the
#: shapes this round leaves.
_BEFORE = {
    "views.tsx": (
        "export function Other() {}\n"
        "export function ReportView({ runId }: { runId: string }) {\n"
        + "  // filler\n" * 8
        + "  {/* UX-66. The caption no longer swaps to a busy word. */}\n"
        "  <button />\n"
        "}\n"
        "export function After() {}\n"
    ),
    "admin.tsx": (
        "{/* UX-66, the convention `views.tsx:11` states in full. */}\n"
        "{/* `reports.tsx:270-289` set for UX-64 and `views.tsx:11` took. */}\n"
    ),
    "analyses.tsx": "{/* `views.tsx:10` is the house pattern. */}\n",
    "panels.tsx": "/* UX-66. The convention `views.tsx:11` states in full. */\n",
}

_AFTER = {
    "views.tsx": _BEFORE["views.tsx"],
    "admin.tsx": (
        "{/* UX-66, the convention `views.tsx`'s `ReportView` states. */}\n"
        "{/* `reports.tsx:270-289` set for UX-64 and `ReportView` took. */}\n"
    ),
    "analyses.tsx": "{/* `views.tsx`'s `ReportView` is the house pattern. */}\n",
    "panels.tsx": "/* UX-66. The convention `ReportView` states in full. */\n",
}


def test_the_reader_finds_every_citation_in_the_shape_the_sweep_wrote() -> None:
    bounds = _component_bounds(_BEFORE["views.tsx"], CONVENTION_SYMBOL)
    found = _citations_into_the_convention(_BEFORE, bounds)
    assert len(found) == 4, f"expected 4 citations, got {found}"
    assert {f for f, _, _ in found} == {
        "admin.tsx", "analyses.tsx", "panels.tsx"}, found


def test_the_shape_the_fix_leaves_is_not_read_as_a_citation() -> None:
    bounds = _component_bounds(_AFTER["views.tsx"], CONVENTION_SYMBOL)
    assert not _citations_into_the_convention(_AFTER, bounds)


def test_an_address_outside_the_convention_is_left_alone() -> None:
    """`reports.tsx:270-289` and friends are a different population."""
    bounds = _component_bounds(_BEFORE["views.tsx"], CONVENTION_SYMBOL)
    outside = {"admin.tsx": "{/* `views.tsx:1` and `components.tsx:812`. */}\n"}
    assert not _citations_into_the_convention(outside, bounds)


def test_a_bare_self_reference_counts_only_inside_the_convention_file() -> None:
    bounds = _component_bounds(_BEFORE["views.tsx"], CONVENTION_SYMBOL)
    inside = {"views.tsx": _BEFORE["views.tsx"]
              + "{/* this file's own control takes at :11. */}\n"}
    assert len(_citations_into_the_convention(inside, bounds)) == 1
    elsewhere = {"admin.tsx": "{/* the control takes at :11. */}\n"}
    assert not _citations_into_the_convention(elsewhere, bounds)


def test_the_bounds_follow_the_component_when_the_file_grows() -> None:
    """The guard reads the bounds; it does not remember them.

    Fifteen inserted lines are what moved the real target, so the fixture
    inserts fifteen and asserts the window moves with them.
    """
    grown = _BEFORE["views.tsx"].replace(
        "export function ReportView",
        "  // pad\n" * 15 + "export function ReportView")
    before = _component_bounds(_BEFORE["views.tsx"], CONVENTION_SYMBOL)
    after = _component_bounds(grown, CONVENTION_SYMBOL)
    assert after[0] == before[0] + 15, (before, after)
    assert after[1] == before[1] + 15, (before, after)
