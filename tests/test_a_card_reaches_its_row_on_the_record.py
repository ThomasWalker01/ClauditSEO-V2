"""A card reaches its row on the Record (item 273, row 7).

A part page's card had no way to its row on the Record, where its history
and every state are. The Record takes its text filter from the address
(`?find=`), matches every word of it over the check, the sentence and the
pages, and each card links there with its check and page.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_link_and_the_filter():
    record = (SRC / "pane_record.tsx").read_text(encoding="utf-8")
    assert '.get("find") ?? ""' in record
    assert 'needle.split(/\\s+/).every((w) => hay.toLowerCase().includes(w))' in record
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "?tab=all&state=all&find=${" in page
