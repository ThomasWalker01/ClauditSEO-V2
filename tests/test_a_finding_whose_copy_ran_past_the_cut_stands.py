"""A title or description finding whose replacement ran past the cut stands,
and its card says copy was written and why it was not kept.

Screen audits round 3, Title & description AC-03 and AC-05 (High): five
near-duplicate titles the sweep's exact-match test cannot see were dropped
whole because their replacements measured past 410 px, so the table read
`title-duplicate` clean while the analysis's prose named them; and no card
said a replacement had been written and dropped.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.analysts import contract
from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parent.parent / "dashboard" / "src"


def test_the_reader_keeps_the_fault_and_marks_the_copy():
    src = inspect.getsource(contract)
    assert contract.COPY_NOT_KEPT == "the replacement written was not kept: "
    gate = src[src.index("past = None if soft else _past_the_cut"):]
    gate = gate[:gate.index("_drop(parsed, row.as_dict(), past)")]
    assert 'in ("FAIL", "WARN")' in gate and "row.replacement = None" in gate
    assert "f\"{COPY_NOT_KEPT}{past}\"" in gate and "kept.append(row)" in gate


def test_the_view_and_the_card_carry_the_reason():
    assert 'd["copy_not_kept"] = note.split(COPY_NOT_KEPT, 1)[1].strip() or None' \
        in inspect.getsource(runs)
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "copyNotKept: word === \"brief\" ? s.copy_not_kept ?? null : null," in page
    assert "The analysis wrote a replacement and it was not kept ({fix.copyNotKept})" in page
    assert ".fix-copy-not-kept {" in (SRC / "styles.css").read_text(encoding="utf-8")
