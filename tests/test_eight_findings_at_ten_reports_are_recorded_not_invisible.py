"""Eight findings that crossed ten reports at round 111, recorded as strict xfails.

`.claude/skills/audit-fix/SKILL.md` step 4: at ten rounds survived a finding
must take exactly one of six dispositions before the round may select any
other lever, and *naming is not a disposition*. Eight findings crossed that
threshold at round 111 — CQ-227, CQ-228, CQ-229, CQ-230, CQ-231, UI-23,
UX-94 and UX-95, all first raised at report 100 and carried unbroken to
report 111. None had a row in `audits/DISPOSITIONS.md` before this round.

**All eight are strict xfails, and round 116 is the deadline.** Five rounds,
the same distance round 110 gave its four.

**Strict, so the marker cannot outlive the defect.** The day one of these is
fixed the clause XPASSes and the suite goes red, forcing whoever fixed it to
retire the marker. A non-strict xfail is a finding that has been made
invisible rather than recorded, which is the outcome the register exists to
prevent.

**Why xfail rather than "blocked", for all eight and not just most of them.**
Round 107 blocked nine findings on `QUESTIONS.md` Q-30, round 108 left them
standing on it, rounds 110 and 111 found it still unanswered. `SKILL.md` step
4 forbids a third blocking without an answer, and adding eight more to a
question already at that ceiling would make the weakest disposition bigger
while moving nothing. Every one of these eight is decidable from source by
whoever picks it up — none needs an operator — so each is recorded here,
where a fix trips over it, rather than parked behind a question none of them
asked for.

**What this file is not.** It is not a claim that eight findings were worked.
It is the opposite: a claim that eight were *not* worked this round, written
somewhere the suite will not let the loop forget. Round 111's actual lever is
UX-87 and UX-88, in
`tests/test_a_stated_limitation_and_a_made_document_reach_a_screen_reader.py`.

**Each clause asserts the fixed state, and every one was watched failing
against this round's tree before it was committed.** Read the failure text to
see what is actually wrong today.

---

**Round 116 was the deadline and round 114 took all eight, two rounds early.**
The markers are retired here, in the commit that fixed them, which is what
`strict=True` is for: as each defect went its clause XPASSed and the pinned
suite went red, so retiring the marker was never a judgement the fixing round
got to make. They stay as live guards rather than being deleted — a finding
that survived fifteen reports is worth a standing assertion, and six of the
eight are shapes a later edit could reintroduce without noticing.

**`import pytest` and `DEADLINE` went with the markers.** They had no other
reader once the eight decorators were gone, and a deadline constant naming a
round that no longer gates anything is the stale-comment shape `CQ-216`
records one file over. The paragraphs above are kept in the past tense they
were written in: they say what was true when the eight were recorded, which is
the account the register exists to preserve.

**One clause was read for the fix and not weakened for it, and it is worth
naming which.** `UX-94`'s slices the aside at the first `)}`, which the
existing `at.slice(0, 10)}` already supplies — so it reads only the head of
the block, and the fix has to put `run_id` there. It does, because the honest
fix is to make the whole stamp the link; the guard was not adjusted to meet a
fix placed elsewhere.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_anchors as ca  # noqa: E402

ANATOMY = ROOT / "dashboard/src/anatomy.tsx"
FIXLOOP = ROOT / "dashboard/src/fixloop.tsx"
ONP = ROOT / "clauditseo/modules/onp.py"
TEC = ROOT / "clauditseo/modules/tec.py"
RUNS = ROOT / "clauditseo/persistence/runs.py"
SCOPE_GUARD = ROOT / "tests/test_a_scope_statement_is_never_a_regression.py"
CHECK_ANCHORS = ROOT / "scripts/check_anchors.py"


def _component_body(source: str, name: str) -> str:
    r"""One component's source, split out of the file it lives in.

    **The end marker is a brace that owns its line, and that repair is part
    of taking UI-23.** The sibling guards in this suite split on `"\n}"`,
    which is the component's closing brace *and also* the end of a multi-line
    props type annotation — and `PagesCount` has one::

        function PagesCount({ f, open, onToggle }: {
          f: Finding; open: boolean; onToggle: () => void;
        }) {

    So the body this returned was the two lines of the signature, and the
    clause below failed on *"PagesCount no longer carries the sr-only name"* —
    the empty-population failure, not the defect it was written for. It was an
    xfail, so it was red either way and nothing had to say which. That is
    round 113's UI-22 case exactly, and DISCIPLINE rule 4: a guard's
    population has to be reported, not assumed.

    Repaired rather than relaxed. `"\n}\n"` matches only a `}` alone on its
    line, which is how every component in these files closes, and it is
    strictly narrower than what was here — the old marker matched that brace
    too, it just stopped at an earlier one first. The clause is proven red
    against the unfixed component, which is what says the repair restored a
    population rather than invented a pass.
    """
    assert f"function {name}(" in source, (
        f"{name} is no longer defined where this guard reads it; the "
        "population is empty and the clause would pass by finding nothing")
    body = source.split(f"function {name}(", 1)[1].split("\n}\n", 1)[0]
    assert "return" in body, (
        f"the body read for {name} carries no `return`, so the split found a "
        "brace inside the signature rather than the one that closes the "
        f"component. Read: {body[:200]!r}")
    return body


# --------------------------------------------------------------------------
# CQ-227 — the source half of the anchor check reports no skip count
# --------------------------------------------------------------------------

def test_the_source_anchor_summary_reports_what_it_skipped():
    """CQ-227. The audits half prints "N bare filenames skipped"; the source
    half prints no skip count at all, while resolving 15 of 47 citations.

    `scripts/check_anchors.py`'s own docstring makes reporting skips the rule:
    *"It reports what it skipped, not only what it checked … DISCIPLINE rule 4
    is that coverage nobody reports is coverage nobody has."* A clean line
    over two thirds of the population is exactly the coverage nobody has.
    """
    source = CHECK_ANCHORS.read_text(encoding="utf-8")
    summary = source.split('print(f"source: ', 1)
    assert len(summary) == 2, (
        "the source summary line is no longer printed where this guard reads "
        "it; the premise CQ-227 rests on has changed")
    # The printed line, up to the closing paren of the print call.
    line = summary[1].split(")\n", 1)[0]
    assert "skipped" in line and "bare" in line, (
        "the source half of check_anchors prints no count of the citations it "
        "skipped, while the audits half three lines above prints "
        '"N bare filenames skipped". What it printed instead was:\n'
        f"  source: {line}")


# --------------------------------------------------------------------------
# CQ-228 — the scope-statement guard's matcher is weaker than its population
# --------------------------------------------------------------------------

def _flagged_emitters() -> set[str]:
    """Every check id constructed with `scope_statement=True` under
    `clauditseo/`, re-derived from the tree rather than listed here."""
    out: set[str] = set()
    for path in sorted((ROOT / "clauditseo").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "Finding"):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            check, flag = kw.get("check_id"), kw.get("scope_statement")
            if (isinstance(check, ast.Constant)
                    and isinstance(check.value, str)
                    and isinstance(flag, ast.Constant) and flag.value is True):
                out.add(check.value)
    return out


def test_every_flagged_emitter_is_inside_the_guard_that_keeps_the_flag():
    """CQ-228. The guard walks all 69 `Finding(...)` constructions and then
    narrows the must-be-flagged set to ids ending `-not-assessed`. Ten
    emitters carry the flag and five are outside that suffix, so a flag
    silently dropped from one of the five passes the guard — and a scope limit
    that stops being declared reads to the client as a defect relapsing.
    """
    flagged = _flagged_emitters()
    assert flagged, "the source scan found no flagged emitter at all"
    guard = SCOPE_GUARD.read_text(encoding="utf-8")
    outside = sorted(c for c in flagged
                     if not c.endswith("-not-assessed") and c not in guard)
    assert not outside, (
        "these emitters carry `scope_statement=True` and are outside both the "
        "guard's `-not-assessed` matcher and its source. Losing the flag on "
        "any of them is invisible to the check meant to keep it:\n  "
        + "\n  ".join(outside))


# --------------------------------------------------------------------------
# CQ-229 — four outcome words copied at three sites with nothing binding them
# --------------------------------------------------------------------------

def test_the_verification_outcome_words_are_bound_across_their_three_sites():
    """CQ-229. `runs.py` produces four words, `app.py` counts them through a
    `Counter` that answers zero for a key that is not there, and
    `fixloop.tsx`'s `WORD` map assigns only when the lookup succeeds. A rename
    in the producer reports zeroes on the server and a blank chip on the
    screen, with a green suite — the silent-zero shape this codebase names
    elsewhere as a failure class.

    The fixed state is one test that names all four on the producer side and
    the screen side together, so the two cannot drift apart unnoticed.
    """
    words = {"still_present", "cleared", "not_checked", "unchanged"}
    binding = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        # This file itself names all four words and `WORD` — in the clause
        # describing the defect. Written as an exclusion rather than as a
        # cleverer matcher because the first version XPASSed against the
        # unfixed tree by finding itself, which is round 110's CQ-221 mistake
        # repeated: a guard whose population includes its own text is
        # measuring its own prose.
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        if words <= set(re.findall(r"\b\w+\b", text)) and "WORD" in text:
            binding.append(path.name)
    assert binding, (
        "no test names the four verification outcome words together with "
        "`fixloop.tsx`'s `WORD` map, so nothing holds the producer "
        "(clauditseo/persistence/runs.py) and the two consumers "
        "(clauditseo/api/app.py, dashboard/src/fixloop.tsx) to the same "
        "vocabulary. Both consumers absorb an unknown word silently.")


# --------------------------------------------------------------------------
# CQ-230 — an evidence key that reframes a count, and no reader for it
# --------------------------------------------------------------------------

def test_the_key_that_reframes_a_duplicate_count_has_a_reader():
    """CQ-230. The duplicate checks changed the population their counts are
    taken over and recorded the excluded members under `canonical_aliases`.
    Grepping the tree returns two writes and one assertion: no renderer, no
    screen, no API field. The summary still says N pages share the title with
    no word for which N it is, so a drop between two runs of the same site
    reads to the client as a fix.
    """
    written = "canonical_aliases"
    readers = []
    for root in ("clauditseo", "dashboard/src"):
        for path in sorted((ROOT / root).rglob("*")):
            if path.suffix not in {".py", ".ts", ".tsx"} or not path.is_file():
                continue
            if path in {ONP}:
                continue          # the writer is not a reader
            if written in path.read_text(encoding="utf-8"):
                readers.append(path.relative_to(ROOT).as_posix())
    assert readers, (
        f"nothing outside {ONP.relative_to(ROOT).as_posix()} reads "
        f"{written!r}. The key exists to say which pages a changed count "
        "stopped covering, and no renderer, screen or API field asks for it.")


# --------------------------------------------------------------------------
# CQ-231 — --context prints nothing about a row written in the house style
# --------------------------------------------------------------------------

def test_the_context_reader_prints_the_claim_of_a_house_style_row():
    """CQ-231. `_claim` takes the first sentence by splitting on `[.?!]\\s`,
    and this board's convention opens a new row with a short bolded lead —
    so the split lands on the lead and the reading surface WF-96's remedy
    rests on prints almost nothing for exactly the rows a round is told to
    check first: the newest Highs.

    The cell below is the real opening of report 100's own CQ-227 row.
    """
    cell = ("**New, measured over the tree. The Q-16 source-anchor check "
            "resolves 15 of the 47 `file:line` citations in product source "
            "and reports the 32 it skips nowhere.** "
            "`scripts/check_anchors.py:617-619` prints the audits half's "
            "skip count and never the source half's.")
    claim = ca._claim(cell)
    assert len(claim) > 45, (
        "`--context` prints only the bolded lead of a house-style row, not "
        f"its claim. For this cell it printed {claim!r} ({len(claim)} chars). "
        "The rows it does serve are the carried ones, whose "
        "'Claim as first raised in report NNN' prefix happens to survive the "
        "split.")


# --------------------------------------------------------------------------
# UI-23 — an accessible name that does not agree with its own number
# --------------------------------------------------------------------------

def test_the_pages_disclosure_pluralises_the_name_it_announces():
    """UI-23. `PagesCount` appends a fixed screen-reader-only string after the
    count, so a finding naming one page announces "1 pages — show them". The
    visible label is a bare digit, so the plural exists only in the name a
    screen reader hears — the one part of this control a sighted operator
    never reads is the one part that is ungrammatical. Every other count in
    the product is pluralised at its render site (`fixloop.tsx:462-464`).
    """
    body = _component_body(ANATOMY.read_text(encoding="utf-8"), "PagesCount")
    sr = re.search(r'<span className="sr-only">(.*?)</span>', body, flags=re.S)
    assert sr, "PagesCount no longer carries the sr-only name UI-23 is about"
    text = sr.group(1)
    assert re.search(r"f\.pages\s*===?\s*1|pages === 1|\bpage\b(?!s)", text), (
        "the disclosure's accessible name says \"pages\" whatever the count "
        f"beside it is, so a one-page finding announces \"1 pages\". Name: "
        f"{' '.join(text.split())!r}")


# --------------------------------------------------------------------------
# UX-94 — the pane names a run and will not open it
# --------------------------------------------------------------------------

def test_the_run_that_moved_the_standing_position_can_be_opened():
    """UX-94. `last_move` is built as an at, a kind and a run id
    (`clauditseo/persistence/runs.py`), and the aside renders the first two
    and discards the third — the screen names an object it will not open,
    which is the affordance invariant's own wording. The same file links a
    run in four other places, so the route exists and the id is in hand.
    """
    source = ANATOMY.read_text(encoding="utf-8")
    assert "last_move" in source, (
        "anatomy.tsx no longer renders last_move; UX-94's premise has gone")
    aside = source.split("last_move &&", 1)[1].split(")}", 1)[0]
    assert "run_id" in aside, (
        "the standing-position aside renders last_move's date and kind and "
        "drops its run_id, so the verification it names cannot be opened and "
        "the operator cannot see what that run actually did. Aside: "
        f"{' '.join(aside.split())!r}")


# --------------------------------------------------------------------------
# UX-95 — a development register cited in operator-facing text
# --------------------------------------------------------------------------

def test_no_screen_cites_a_development_register_to_the_operator():
    """UX-95. The truncation notice ends with a parenthesised backlog id and
    the browser renders it: *"… the rest are stored and are not reachable
    from here (BACKLOG.md B-30)."* It is the only rendered register citation
    in the dashboard — every other mention of a register filename in
    `dashboard/src` is inside a comment.
    """
    registers = ("BACKLOG.md", "KNOWN_ISSUES.md", "QUESTIONS.md",
                 "OPERATOR_ACTIONS.md")
    source = ANATOMY.read_text(encoding="utf-8")
    uncommented = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    uncommented = re.sub(r"//[^\n]*", " ", uncommented)
    cited = sorted(r for r in registers if r in uncommented)
    assert not cited, (
        "a development register is named in text the operator reads, in a "
        "product whose other screens never mention one. The operator has no "
        f"such file and nothing on the screen leads anywhere: {cited}")
