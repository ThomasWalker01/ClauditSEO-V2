"""A "found nothing" hold is a pass, and a hold naming a record field links
to it (items 270 r11, 271 r12).

Structured data held rows reading "no hidden markup found" - a check that
ran and found nothing. And holds naming geo, priceRange, openingHours,
areaServed, the ID page or a page's triple sent the operator nowhere.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.analysts import contract

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_found_nothing_is_a_pass():
    for reason in ("no hidden markup found on this page", "no orphan node was found",
                   "no duplicate blocks found"):
        assert contract._PASS_REASON.search(reason), reason
    assert not contract._PASS_REASON.search("needs the GBP primary category")


def test_record_fields_link():
    src = SRC.read_text(encoding="utf-8")
    assert "openinghours|areaserved|id page|\\btriple\\b|primary entity" in src
