"""The URL patterns say what they show (item 266, rows 9 and 11).

The Patterns table's templates narrow the fixes, and nothing said so; a
pressed template was only bolder; and the table's one finding - which
templates sit past the depth limit - was left for the reader to add up.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_caption_sentence_and_pressed_style():
    src = (SRC / "urls_now.tsx").read_text(encoding="utf-8")
    assert "Press a template to show only its fixes." in src
    assert "over depth {now.thresholds.max_depth} in {deep.length}" in src
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    assert ".un-template.on { box-shadow: inset 3px 0 0 var(--accent);" in css
