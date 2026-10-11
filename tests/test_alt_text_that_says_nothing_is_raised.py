"""Alt text that says nothing is raised (item 272, row 11).

An image whose alt is its own filename in words ("IMG 4821") or a page
builder's default ("Frames (Bricks)") passes `img-alt-missing` and tells a
screen reader nothing. A free check raises it, per image, folded by template
as the other image checks are.
"""

from __future__ import annotations

from clauditseo.anatomy import CHECK_CATEGORY
from clauditseo.checks import default_severities
from clauditseo.modules import onp


def test_the_rule():
    assert onp._alt_says_nothing("IMG_4821", "/up/IMG_4821.jpg") == "the file's name"
    assert onp._alt_says_nothing("Frames (Bricks)", "/up/x.jpg") == "a page builder's default"
    assert onp._alt_says_nothing("The team at the 2025 gala", "/up/team.jpg") is None
    assert onp._alt_says_nothing("", "/up/x.jpg") is None


def test_it_is_registered():
    assert default_severities()["ONP/img-alt-filename"] == "low"
    assert CHECK_CATEGORY["img-alt-filename"] == "images"
