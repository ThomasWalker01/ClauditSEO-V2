"""A Content card strikes only what it replaces (item 269, row 10).

Free Content cards drew the finding's sentence struck through with nothing
under it - "this page has no named author" crossed out, as though fixed. The
sentence is struck only where a replacement stands under it; a free card
carries the automatic checks' own advice instead.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_strike_only_with_a_replacement():
    src = SRC.read_text(encoding="utf-8")
    body = src.split("function ContentFixBody", 1)[1].split("\n}\n", 1)[0]
    assert "{fix.current && (fix.replacement" in body
    assert '<span className="fix-lbl">Do this: </span>{fix.recommendation}' in body
