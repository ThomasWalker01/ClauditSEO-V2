"""A length card says what the page has, and by how much (item 273, rows 4
and 5).

On the site view a title or description card had no page facts, so its Now
was the engine's sentence ("Title on / is 561 px and is cut at ..."), struck
through whether or not anything replaced it. The finding's own string is
carried to the card, struck only under a replacement, with the overage and
length beside it and the sentence beneath.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_carried_and_said():
    runs = (ROOT / "clauditseo" / "persistence" / "runs.py").read_text(encoding="utf-8")
    assert 'd["said"] = said if isinstance(said, str) else None' in runs
    src = (ROOT / "dashboard" / "src" / "part_page.tsx").read_text(encoding="utf-8")
    body = src.split("function TitleDescFixBody", 1)[1].split("\n}\n", 1)[0]
    assert "const current = now || fix.said || null;" in body
    assert "(fix.replacement && !keep ? <s>{current}</s> : <span>{current}</span>)" in body
    assert "px over · {current.length} chars" in body


def test_ordered_by_overage():
    src = (ROOT / "dashboard" / "src" / "part_page.tsx").read_text(encoding="utf-8")
    assert "sort((a, b) => (b.overPx ?? -1) - (a.overPx ?? -1))" in src


def test_a_merged_card_keeps_the_measurement():
    """Screen audits round 3 (title-desc AC-04): when the analysis row was
    read first, the sweep row's merge copied the summary and not the page's
    string or its overage, so 17 of 30 cards lost both and sorted last."""
    src = (ROOT / "dashboard" / "src" / "part_page.tsx").read_text(encoding="utf-8")
    merge = src.split('if (word === "sweep") {\n        seen.sweepFp', 1)[1].split("\n      }\n", 1)[0]
    assert "seen.said = s.said ?? seen.said;" in merge
    assert "seen.overPx = s.over_px ?? seen.overPx;" in merge
