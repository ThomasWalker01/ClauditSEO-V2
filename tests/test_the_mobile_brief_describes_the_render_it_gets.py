"""Item 231 (Mobile, change 1): the Mobile brief describes the render the
engine sends.

The brief said the sweep measured every template "at 360 px" and that RENDER
carried element boxes, fixed elements and a screenshot. The engine renders at
412 x 823 (`perf._MOBILE_VIEWPORT`, a Pixel 5 emulation) and sends counts
only (`expert._mobile_render_table`). So the page said 360 px beside a
412 px measurement, and the analysis held safe-area and the keyboard check
"for want of a render" it had been told it would get.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo import perf

BRIEF = (Path(__file__).resolve().parents[1] / "clauditseo" / "prompts"
         / "mobile-viewport.md").read_text(encoding="utf-8")
FLAT = " ".join(BRIEF.split())


def test_the_width_is_the_engines():
    w, h = perf._MOBILE_VIEWPORT["width"], perf._MOBILE_VIEWPORT["height"]
    assert f"{w} x {h}" in FLAT
    assert "360" not in BRIEF


def test_render_lists_only_what_the_engine_sends():
    assert "No element boxes, no fixed-element list, no form inventory and no screenshot are sent." in FLAT
    assert "interactive-element boxes" not in FLAT


def test_a_hold_names_the_input_that_is_not_sent_and_a_non_need_is_said():
    assert "the fixed-element list from the 412 x 823 render, not sent" in FLAT
    assert "nothing in the 412 x 823 render calls for it" in FLAT
