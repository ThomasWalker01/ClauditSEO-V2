"""A source comment that cites `file:line` must cite a line that still says it.

`scripts/check_anchors.py` (`source`) already holds every source-comment anchor
to *resolving* — the cited file exists and is long enough. The profile's "an
address in a comment" invariant names the half it does not decide, in as many
words: it "does not judge whether the line still says what the comment claims —
the drift `--context` exists for on the reports side, with no source equivalent
yet." This is that equivalent, for the claims round 129 swept.

Round 129 measured the cost of the gap. Of the 51 resolvable line citations in
source comments under `clauditseo/`, `dashboard/src/` and `scripts/`, **22 cited
a line that no longer said what the comment claimed** — every one of them
resolving cleanly, so `check_anchors.py` reported the tree clean throughout. The
class self-propagates: the profile records that eight of the eleven rounds
carrying CQ-151 added a fresh instance in the very commit that explained a fix,
and CQ-240 is that again — round 128 corrected this exact citation in
`KNOWN_ISSUES.md` KI-54 and left the copy two lines away in `tools.tsx`.

**No line number is written down here.** Each claim names the citing file, a
marker phrase in the comment, the file it cites, and a token that must be at the
cited address. The test reads the *address itself out of the comment* at run
time. So a correct edit to a citation keeps this green with no change here,
while a target that moves under an unedited comment goes red — which is the
whole defect, and the only shape of guard that does not itself rot.

Deliberately NOT a general matcher over all 51. Round 129 measured two candidate
general signals: "the cited line is itself inside a comment" flagged 23 of 51,
and "a backticked token near the citation appears near the address" flagged 19 of
26 — both dominated by false positives, because a comment citing another comment
block is legitimate and `scripts/check_anchors.py` quotes bad anchors on purpose
as its own documentation. Shipping either would be the profile's own
weaker-matcher defect: a derived population whose membership is decided by a
matcher that cannot carry it. The population here is explicit and the matcher is
exact.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# (citing file, a unique marker phrase in the citing comment, cited file, the
#  token that must appear at the cited address). The address is never written
#  here — it is read from the comment the marker locates.
CLAIMS = [
    # Items 178-183 (2026-09-18) moved eight cited lines in one round; each
    # comment now names the symbol, as this file recommends, and its row went.
    # DROPPED, and the drop is the point (item 141, brief v19 step BC). The
    # `ofp.py` -> `prf.py` citation was corrected four times in one item -
    # `:176-181`, `:215-219`, `:228-232`, `:306-310` - every one of them
    # because a constant was added above it in `prf.py` and none of them
    # because the reasoning moved. This file's own failure message says what
    # to do about that ("replace it with the symbol name, which does not go
    # stale and is the cheaper form"), so the comment now cites `cwv_names` by
    # name and there is no address left for this clause to check. Left here as
    # a record rather than deleted: the next citation that drifts twice should
    # take the same route.
    ("clauditseo/reporting/checks.py", "Backticked check ids",
     "clauditseo/reporting/render.py", "check_id"),
    ("clauditseo/reporting/render.py", "a fourth shape and is a named deferral",
     "dashboard/src/components.tsx", "confidence)"),
    # The line address here was corrected three times in one round as
    # `page_facts` moved, so it was reduced to the symbol name at brief v15
    # step AR and the claim goes with it. What the comment says is still
    # checkable by reading `runs.py:page_facts`; what it no longer says is
    # a line number, and a claim about a line nobody wrote is the thing
    # this register exists to stop.
    # The runs table is the Audit pane's file since brief step 8.
    ("dashboard/src/components.tsx", "recorded that divergence as deliberate",
     "clauditseo/money.py", "Thousands are grouped"),
    # Brief v18 step AY added five site-record fields to `SitePatch` and a
    # `front` parameter to `render_run_report`, which moved every line
    # after them in `app.py` and `render.py`. Five claims went stale in one
    # commit - the largest single move this register has seen - and all
    # five were reduced to the symbol name the test's own message
    # recommends rather than re-numbered. A line address that has been
    # corrected once will be corrected again; `runs_costed` will not move.
    # Dropped 2026-09-07 (relay 136j): the citation it watched was
    # `runs.py:2443-2466`, which drifted to ~2545 when Part B added the
    # screenshot route and retention above it. This guard's own message
    # names the cheaper repair - "replace it with the symbol name, which
    # cannot go stale" - and the comment now cites `expert_report` instead,
    # so there is no line address left to watch. Removing the row is what
    # that repair costs, and the guard asks for it in the same commit.
]

# How far outside the cited range the token may sit. One line, for a statement
# wrapped across two.
#
# **Not four, and the difference is the whole guard.** Written at four this test
# passed on CQ-240 itself: the citation was two lines stale, `s[0]?.id` sat three
# lines past the cited range, and a four-line tolerance swallowed it — a guard
# blind to precisely the defect it was written for. Drift of one or two lines is
# the common case, because it is what a small insertion above produces; a
# tolerance wider than the typical drift cannot see any of it. Where a claim
# genuinely spans a few lines, widen the *citation* into a range, which is true,
# rather than the window, which hides.
WINDOW = 1

# Lines either side of the marker that may carry the citation: a citation is
# routinely wrapped onto the line after the phrase that introduces it.
SPAN = 3


def _read(rel: str) -> list[str]:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()


def _addresses(text: str, cited: str) -> list[tuple[int, int]]:
    """Every `<cited>:<a>[-b]` address in `text`, as inclusive line ranges.

    Trailing `,805` and `, :685` forms repeat the file only as a number, and
    both spellings are in use, so they are collected off the end of the match
    rather than requiring the filename again.
    """
    base = re.escape(Path(cited).name)
    out: list[tuple[int, int]] = []
    for m in re.finditer(rf"(?:[A-Za-z0-9_./-]*/)?{base}:(\d+)(?:\s*-\s*(\d+))?", text):
        a = int(m.group(1))
        out.append((a, int(m.group(2)) if m.group(2) else a))
        tail = re.match(r"\A(?:\s*,\s*`?:?(\d+)`?)+", text[m.end():])
        if tail:
            for n in re.findall(r"(\d+)", tail.group(0)):
                out.append((int(n), int(n)))
    return out


@pytest.mark.parametrize(
    "citing,marker,cited,token",
    CLAIMS,
    ids=[f"{Path(c).stem}-{m[:22]}-{Path(t).stem}" for c, m, t, _ in CLAIMS],
)
def test_the_cited_line_still_carries_what_the_comment_says_is_there(
    citing: str, marker: str, cited: str, token: str
) -> None:
    lines = _read(citing)
    at = [i for i, line in enumerate(lines) if marker in line]
    assert len(at) == 1, (
        f"{citing}: marker {marker!r} matched {len(at)} lines, expected exactly one. "
        "The marker identifies which citation this claim is about; if the comment "
        "was reworded, re-point the claim rather than loosening the match."
    )
    i = at[0]
    window = "\n".join(lines[max(0, i - SPAN): i + SPAN + 1])
    addrs = _addresses(window, cited)
    assert addrs, (
        f"{citing}:{i + 1}: no address into {cited} within {SPAN} lines of the marker. "
        "If the citation was deliberately reduced to a symbol name — which does not "
        "go stale and is the cheaper form — drop this claim in the same commit."
    )

    target = _read(cited)
    misses = []
    for lo, hi in addrs:
        assert hi <= len(target), (
            f"{citing}:{i + 1} cites {cited}:{hi}, past the end of a "
            f"{len(target)}-line file."
        )
        passage = "\n".join(target[max(0, lo - 1 - WINDOW): hi + WINDOW])
        if token not in passage:
            misses.append(f"{cited}:{lo}-{hi}" if lo != hi else f"{cited}:{lo}")
    assert not misses, (
        f"{citing}:{i + 1} says {token!r} is at {', '.join(misses)}, and it is not "
        f"(searched +/-{WINDOW} lines). The address resolves, so check_anchors.py "
        "reports it clean — that is the gap this test covers. Correct the address, "
        "or replace it with the symbol name, which cannot go stale."
    )


def test_every_claim_names_a_file_that_exists_so_the_set_cannot_pass_by_vacuity() -> None:
    """The population is explicit, so it is asserted rather than derived.

    A claims table can go quietly empty — a renamed file, a reworded comment, a
    bad merge — and a parametrised test over nothing passes. This is the
    population assertion the profile's guard invariant requires: the count is
    pinned, and both ends of every claim must exist.
    """
    # THREE have been retired now, each when its address became a symbol name,
    # and each for the same reason: the line moved more often than the
    # reasoning did. Brief v4 Item 3e retired expert.tsx's pointer at the
    # analyses tab's `ReportView`, when the tab became the drawer. Brief v15
    # step AR retired anatomy.tsx's `heading_counts` line: `page_facts` moved
    # three times in one round and the number was corrected three times with
    # it. Brief v19 step BC retires `ofp.py`'s pointer into `prf.py` -
    # corrected FOUR times in one item (`:176-181`, `:215-219`, `:228-232`,
    # `:306-310`), every one of them because a constant was added above it and
    # none of them because anything about the reasoning changed. The comment
    # cites `cwv_names` by name and there is no line left to check.
    assert len(CLAIMS) == 3, (
        "The swept set is 3 claims. Nine addresses were reduced to symbol names "
        "earlier - five at brief v18 step AY, the expert-handler one at relay 136j, "
        "the ofp->prf one at brief v19 step BC - and nine more at items 178-183 "
        "(2026-09-18), when the button migration moved every cited line in "
        "tools, views, selection, components, reports, expert, money and app. Add "
        "or remove a claim deliberately, with the round that changes the sweep."
    )
    for citing, _, cited, _ in CLAIMS:
        assert (ROOT / citing).is_file(), f"citing file missing: {citing}"
        assert (ROOT / cited).is_file(), f"cited file missing: {cited}"


def test_the_ipv6_guard_comment_names_a_symbol_rather_than_a_line_that_moved() -> None:
    """CQ-240's twenty-second site, fixed the durable way rather than re-addressed.

    `crawl.py`'s CQ-133 comment claimed the `Invalid IPv6 URL` raise happened at
    `crawl.py:128`, which is a `#:` note about tracking parameters. The true site
    is `urlsplit` inside `_canonical_spelling`, which `normalise_url` delegates
    to — and naming those two symbols is both correct and immune to the drift
    that produced the defect, which is why this one is not in CLAIMS.
    """
    text = (ROOT / "clauditseo/crawler/crawl.py").read_text(encoding="utf-8")
    start = text.index("CQ-133's other half")
    block = text[start:start + 1400]
    assert "raises inside `normalise_url`" in block
    assert "_canonical_spelling" in block, (
        "The comment must name the symbol the raise actually comes from."
    )
    assert not re.search(r"crawl\.py:\d+", block), (
        "A line-numbered self-citation is back in the CQ-133 comment. That is the "
        "address that rotted; the symbol name is what replaced it."
    )
