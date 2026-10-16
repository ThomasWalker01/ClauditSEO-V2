"""A part no automatic check covers offers no re-check (item 274, finishing
item 232).

International has no sweep: `part.refresh` is null. Its "Re-check
International · this part's checks · free" was enabled, left-most and did
nothing, and the provenance line under it fell back to "ONP" and dated the
part by the On-page sweep ("measured 2 days ago").
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def _actions() -> str:
    src = SRC.read_text(encoding="utf-8")
    start = src.index("function Actions(")
    return src[start:src.index("\n}\n", start)]


def test_the_recheck_is_held_where_no_automatic_check_covers_the_part():
    body = _actions()
    assert 'part.refresh ? null : "no automatic check covers this part"' in body
    assert "why={noRecheck ??" in body


def test_no_sweep_line_is_drawn_for_a_part_with_no_dimension():
    body = _actions()
    assert '?? "ONP"' not in body
    assert "{sweep && dim && (" in body


def test_the_spend_reason_is_the_gates_own_first_sentence():
    body = _actions()
    assert "part.gate?.reason" in body
    assert "it presents one locale. It runs once a" not in body


def test_an_analysis_check_with_no_row_is_not_called_clean():
    """Items 274, 276 (and 265 row 3): the briefs report faults and omit
    passes, so an analysis check with no row was never said to pass. On
    Security, "5 checks clean" named csp-policy, which rides on the csp-weak
    card, and platform-limits, which returned nothing."""
    src = SRC.read_text(encoding="utf-8")
    assert '{!away && section === "model" && spotless.length > 0 && (' in src
    assert '{!away && section !== "model" && spotless.length > 0 && (' in src
    assert "returned no row for" in src and "It reports faults, not passes" in src
    # And on one page: the pass line names free checks only.
    assert 'const cleanModel = cleanMeasured.filter((c) => costOf(part, fullOf(c)) === "model" && !passedHere.has(c));' in src
