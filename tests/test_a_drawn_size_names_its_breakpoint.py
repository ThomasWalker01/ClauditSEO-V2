"""A drawn size names the viewport it was measured at (item 272, row 7).

The chart said "256×176 drawn" for an image whose widest box was the
tablet's; at 1440 it drew 180×123. The box comes with the viewport width it
was measured at.
"""

from __future__ import annotations

from clauditseo.persistence.runs import image_state

BUDGET = {"image_kb": 300, "bytes_per_pixel": 1, "floor_kb": 20}


def test_the_breakpoint():
    got = image_state({"rendered": {"1440": [180, 123], "768": [256, 176]}, "weight_kb": 40,
                       "alt": "x"}, BUDGET)
    assert (got["drawn_w"], got["drawn_h"], got["drawn_at"]) == (256, 176, 768)
    assert image_state({"weight_kb": 40, "alt": "x"}, BUDGET)["drawn_at"] is None
