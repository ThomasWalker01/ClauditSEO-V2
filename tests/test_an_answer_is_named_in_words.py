"""An answer is named in words (item 270, row 15).

The three answers on a card were named "Confirm article-author-missing on
/seo/on-page/" - the check's id, read out letter by letter. They are named by
the card's plain name and page: "Confirm: Article without an author,
/seo/on-page/".
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_named_in_words():
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert page.count("subject={`${plainName(fix.checkId)}, ${pathOf(fix.page)}`}") == 2
    assert "subject={`${fix.check} on" not in page
    assert "`${verb}: ${subject}`" in (SRC / "to_confirm.tsx").read_text(encoding="utf-8")
