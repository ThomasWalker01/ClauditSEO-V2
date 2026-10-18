"""A card names its page on its own line (item 266, row 13).

The page path sat at .74rem among the pills on the card's first line, where
it wrapped wherever the pills ended. It takes its own line under the title,
at body size.
"""

from __future__ import annotations

from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "styles.css"


def test_the_page_line_rule():
    assert ".fix-head .fix-page { flex-basis: 100%; order: 99; font-size: .84rem; }" in \
        CSS.read_text(encoding="utf-8")
