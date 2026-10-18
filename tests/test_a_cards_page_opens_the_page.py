"""A card's page opens the page (item 275, row 9).

The fix card named its page as plain code; every other screen that names a
page links it to the page's dossier. The card does too, where it has a site
and a full URL.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_link():
    src = SRC.read_text(encoding="utf-8")
    card = src.split("function FixCard", 1)[1].split("\n}\n", 1)[0]
    assert "#/sites/${siteId}/dossier/${encodeURIComponent(fix.page)}" in card
