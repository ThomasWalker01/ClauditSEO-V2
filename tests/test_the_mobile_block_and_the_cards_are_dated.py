"""The Mobile block and the cards are dated (item 274, row 5).

"Templates at 412 px" drew the analysis of 23 Sept, which read the crawl of
18 Sept, directly under the 29 Sept automatic checks' provenance and with
no date of its own. And `TEC/tap-target` drew 13 cards over 12 counted with
no "Measured X to Y" line, so nothing said one card was older. The block now
says which analysis and crawl it drew, and the range line fires wherever a
card was measured on a day other than the automatic checks'.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_block_names_its_analysis_and_crawl():
    src = SRC.read_text(encoding="utf-8")
    block = src.split("function MobileNow", 1)[1].split("\n}\n", 1)[0]
    assert "From the analysis of {dayOf(part.brief_run.at)}" in block
    assert "which read the crawl of ${dayOf(part.brief_run.crawl_at)}" in block


def test_a_card_measured_on_another_day_opens_the_range():
    src = SRC.read_text(encoding="utf-8")
    assert "cardDates.some((d) => day(d) !== day(sweep.at))" in src
    assert "cardDates={pageFixes.map((f) => f.measuredAt)" in src
