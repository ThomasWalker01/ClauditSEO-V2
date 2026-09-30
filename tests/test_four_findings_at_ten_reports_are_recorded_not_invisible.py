"""Four findings that crossed ten reports at round 110, recorded as strict xfails.

`.claude/skills/audit-fix/SKILL.md` step 4: at ten rounds survived a finding
must take exactly one of six dispositions before the round may select any
other lever, and *naming is not a disposition*. Six findings crossed that
threshold at round 110 — CQ-221, CQ-222, CQ-223, CQ-224, CQ-225 and UI-22,
all first raised at report 099 and unbroken to report 110. CQ-224 was
**taken** as part of this round's sweep. CQ-223 is **blocked** on a spend
decision that is genuinely the operator's, recorded as `QUESTIONS.md` Q-32.
The four here are **strict xfails, and round 113 is the deadline**.

**Strict, so the marker cannot outlive the defect.** The day one of these is
fixed the clause XPASSes and the suite goes red, forcing whoever fixed it to
retire the marker. A non-strict xfail is a finding that has been made
invisible rather than recorded, which is the outcome the register exists to
prevent.

**Why xfail rather than one more round of "blocked".** Round 107 blocked nine
findings on `QUESTIONS.md` Q-30, round 108 left them standing on that block,
and Q-30 is still unanswered at round 110. Adding four more to an unanswered
question would make the same weak disposition bigger without moving anything.
These four are all decidable from source, so they are recorded here where a
fix trips over them, rather than parked behind a question none of them needs.

Each clause asserts the **fixed** state. Read the failure text to see what is
actually wrong today.

**Round 113 is the deadline and round 113 took all four.** The markers are
retired here, in the commit that fixed them, which is what `strict=True` is
for: the day the defect went the clauses XPASSed and the suite went red, and
retiring them was not optional. They stay as live guards rather than being
deleted -- a finding that survived ten reports is worth a standing assertion,
and three of the four are one-line shapes a later edit could reintroduce
without noticing.

**`UI-22`'s clause was rewritten rather than merely un-marked, and that is
part of the fix.** As written it derived its population from the presence of
`trendDay(` on the line composing the break label, so the symmetric fix --
one label helper, called at both ends -- emptied the population and the
clause failed on "nothing to check" rather than passing. A guard that cannot
observe the fixed state it asked for is CQ-221's own failure class, which is
the finding sitting beside it in this file. It now derives the date-only
formatters from the file itself, so renaming `trendDay` cannot defeat it
either.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

HOME = Path("dashboard/src/home.tsx")
COMPONENTS = Path("dashboard/src/components.tsx")
#: The trend's own file since brief v16f. `trendDay`, `trendLabels` and the
#: chart moved out of `components.tsx` when the block stopped being a
#: paragraph and became a drawing; UI-22 is about those labels, so its two
#: clauses read the file the labels are in rather than the file they were in.
TREND = Path("dashboard/src/score_trend.tsx")
GOLDEN = Path("clauditseo/golden.py")
TESTS = Path("tests")

DEADLINE = "must resolve by round 113"

#: A formatter that answers with a date and nothing else, found by what it
#: does rather than by what it is called. `const trendDay = (iso: string) =>
#: (iso || "").slice(0, 10);` is the one in the tree today.
DATE_ONLY = re.compile(
    r"^(?:const|let)\s+(\w+)\s*=\s*\([^)]*\)\s*=>.*\.slice\(0,\s*10\)",
    re.M)


def _component_body(source: str, name: str) -> str:
    """One component's source, split out of the file it lives in."""
    assert f"function {name}(" in source, (
        f"{name} is no longer defined where this guard reads it; the "
        "population is empty and the clause would pass by finding nothing")
    return source.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


def test_a_driven_test_paints_the_domain_correction_control():
    """CQ-221 (High). `test_a_site_domain_can_be_corrected_in_the_product.py`
    records WF-81 closed on `assert "SiteDomain" in home` — a string read out
    of a source file. Its own docstring defers the rest to "the rendered
    sweep", and the rendered sweep does not paint it: no test renders the
    control, presses it, or asserts it exists. A finding recorded closed on a
    matcher weaker than its own claim is the failure class
    `.claude/loop/PROFILE.md` calls a defeated verification gate.

    Population derived from the tree: every test file mentioning the component.
    """
    mentions = sorted(p for p in TESTS.rglob("test_*.py")
                      if p.name != Path(__file__).name
                      and "SiteDomain" in p.read_text(encoding="utf-8"))
    assert mentions, "no test mentions SiteDomain at all; population is empty"
    # A driving *construct*, not the word "page". The first draft of this
    # clause matched the vocabulary `page|pw|chromium` and found "chromium"
    # in its own regex literal, so it XPASSed against an unfixed tree. That
    # is the exact failure CQ-221 names -- a claim recorded closed on a
    # matcher weaker than the claim -- committed by the clause recording it,
    # and it is why the matcher below names calls rather than words, and why
    # the population excludes this file.
    DRIVES = re.compile(r"sync_playwright\(|page\.goto\(|page\.locator\(|"
                        r"page\.get_by_|page\.click\(")
    driven = [p for p in mentions
              if DRIVES.search(p.read_text(encoding="utf-8"))]
    assert driven, (
        "SiteDomain is asserted only as a string in a source file "
        f"({[str(p) for p in mentions]}); nothing renders the control or "
        "presses it, so the guard cannot tell a rendered button from a "
        "comment naming one")


def test_the_domain_editor_resyncs_to_what_was_stored():
    """CQ-222 (Medium). `SiteDomain` seeds its editable value with
    `useState(row.domain)` — an initialiser, not a subscription — so after one
    correction the field shows what was typed while the button beside it names
    what is stored. The server normalises through `crawl.site_host`, so typing
    `HTTP://Example.COM/` stores `example.com` and reopening offers the typed
    string back. The component's own docstring says it shows the **stored**
    string deliberately, which is the intent the code fails to keep.
    """
    body = _component_body(HOME.read_text(encoding="utf-8"), "SiteDomain")
    assert "useState(row.domain)" in body, (
        "the initialiser this clause is about has changed shape; re-read the "
        "component before trusting either outcome")
    resyncs = ("useEffect" in body and "row.domain" in
               body.split("useEffect", 1)[1])
    assert resyncs, (
        "SiteDomain never resynchronises `value` to `row.domain`, so once the "
        "server normalises a correction the open editor and the collapsed "
        "button disagree about what is stored")


def test_the_golden_register_default_is_not_a_checkout_path():
    """CQ-225 (Low). `clauditseo/golden.py` ships in the wheel
    (`pyproject.toml` includes `clauditseo*`) and defaults its output path to
    `Path(__file__).resolve().parent.parent / "TIMINGS.md"` — the repository
    root, which in an install resolves to `<site-packages>/TIMINGS.md`. The
    failure then arrives as an `OSError` out of library code rather than as a
    refusal that says what is wrong.
    """
    source = GOLDEN.read_text(encoding="utf-8")
    assert "REGISTER" in source, "golden.py declares no REGISTER; population empty"
    assert not re.search(
        r'REGISTER\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\.parent',
        source), (
        "golden.py's REGISTER default walks out of the package to a file that "
        "exists only in a source checkout; an installed copy gets an OSError "
        "instead of a refusal naming the missing register")


def test_a_trend_break_label_can_name_two_runs_on_one_day():
    """UI-22 (Low, seen on live data). The trend's break labels were composed
    from a date-only slice at both ends, so two runs on one day read
    `2026-08-15 → 2026-08-15`. The points were 2h06m apart and `captured_at`
    carries the full stamp, so the information was present and discarded.

    The date-only formatters are derived from the file rather than named.
    This clause's first draft hardcoded `trendDay`, which would have let a
    rename retire the guard silently -- the same defeat CQ-221 above is
    about, and one this file has already committed once in CQ-221's own
    first draft.
    """
    source = TREND.read_text(encoding="utf-8")
    formatters = set(DATE_ONLY.findall(source))
    assert formatters, (
        "no date-only formatter is declared in score_trend.tsx; this clause's "
        "population is empty and it would pass by finding nothing")

    composition = [ln for ln in source.splitlines()
                   if "→" in ln and "${" in ln]
    assert composition, (
        "no line composes a label around an arrow; this clause's population "
        "is empty and it would pass by finding nothing")
    both_ends_date_only = [
        ln for ln in composition
        if sum(ln.count(f"{f}(") for f in formatters) >= 2]
    assert not both_ends_date_only, (
        "a trend break label is composed from a date-only slice at both ends, "
        f"so two runs on one day render the same date twice: "
        f"{both_ends_date_only}")


def test_the_trend_paints_no_bare_day_beside_a_label_that_carries_a_time():
    """The other half of UI-22, and the half its impact sentence is about.

    A break label naming `2026-08-15 14:22 → 2026-08-15 16:28` is only useful
    if the operator can find those two points in the table under it, and that
    table rendered the same date-only slice. Fixing the sentence and leaving
    the column would have moved the collision one element sideways.

    Stated as "no date-only formatter is *called* inside `ScoreTrend`" rather
    than as a claim about a particular cell: the component renders one label
    per point from one place, and any second call site is a second answer to
    the same question. `trendLabels` itself is module-level and is the one
    owner, so it is outside this population by construction.

    `ScoreTrend` is what `TrendChart` became in brief v16f — the same block,
    now a chart with an axis rather than a paragraph, and with more places in
    it that could paint a bare day than the paragraph ever had: a point's own
    date label under the axis is one, and it is drawn from `trendLabels` for
    exactly this reason.
    """
    source = TREND.read_text(encoding="utf-8")
    formatters = set(DATE_ONLY.findall(source))
    assert formatters, "no date-only formatter declared; population empty"
    body = _component_body(source, "ScoreTrend")
    called = sorted(f for f in formatters if f"{f}(" in body)
    assert not called, (
        f"ScoreTrend calls the date-only formatter(s) {called} directly, so "
        "something on the trend still renders a bare day while the labels "
        "beside it carry a time -- two runs on one day collide in whichever "
        "element kept the bare slice")
