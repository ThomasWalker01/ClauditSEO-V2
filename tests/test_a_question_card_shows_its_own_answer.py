"""A "Question heading with no answer" card shows its own change.

Screen audits round 4, Headings UX-01 (High): the card on /website-seo/ drew
the heading-skip card's three relevelled lines as its Replace-with and never
its own answer stub; the brief repeats one corrected outline on every failing
row of a page, and the diff window kept every move in it.
"""
from __future__ import annotations

from pathlib import Path

PAGE = (Path(__file__).resolve().parent.parent / "dashboard" / "src" / "part_page.tsx").read_text(
    encoding="utf-8")


def test_the_question_card_marks_its_stubs_only():
    assert 'const answerCard = fix.checkId === "h2-question-unanswered";' in PAGE
    assert '? after.map((line) => (stubbed(line) ? "answer added below" : null))' in PAGE
    assert "struck: answerCard ? false :" in PAGE
