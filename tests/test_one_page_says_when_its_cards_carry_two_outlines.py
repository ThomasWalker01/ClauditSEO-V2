"""A Headings card says when another card on its page carries a different
corrected outline.

Screen audits round 3, Headings AC-04 (High): `/web-design1/` carried a
28-line outline on its `h1-triple-restated` and `heading-skip` cards, keeping
four empty H3s, and a 24-line outline on its `h2-overstuffed` card, which
removes them. `copy outline` on the first two pasted the duplicates the third
is about, and nothing on the screen said which to paste. Each card is a whole
outline, so the screen names the others rather than choosing.
"""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "dashboard" / "src"
PAGE = (SRC / "part_page.tsx").read_text(encoding="utf-8")
CSS = (SRC / "styles.css").read_text(encoding="utf-8")


def test_the_rivals_are_the_pages_other_differing_outlines():
    body = PAGE[PAGE.index("const rivalsOf = (f: Fix) =>"):PAGE.index("const passed = new Map")]
    assert 'part.key !== "headings"' in body
    assert "o.page === f.page" in body
    assert "outlineCopy(o.replacement)" in body and "seen.has(theirs)" in body
    assert "!o.needs && !o.override" in body


def test_each_card_names_them_and_says_they_are_not_merged():
    assert "rivals={rivalsOf(f)}" in PAGE
    note = PAGE[PAGE.index('className="muted fix-rivals"'):]
    note = note[:note.index("</p>")]
    assert "a different corrected outline" in note
    assert "not merged: paste one" in note
    assert ".fix-rivals {" in CSS
