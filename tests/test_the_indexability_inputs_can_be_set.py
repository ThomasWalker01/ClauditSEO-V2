"""The Indexability inputs can be set (item 277, row 4).

`intended_noindex`, `migration_map` and `parameter_rules` were stored on
the site record (migration 0050) and read by the brief, but no screen or
route could set them, so three analysis checks were held for an input the
operator had no way to give. The site patch takes them, Admin › Sites edits
them, and a held card naming one links to the record.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.api.app import SitePatch

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_patch_takes_them():
    got = SitePatch(intended_noindex=["/webdesign/*/"], migration_map={"/old/": "/new/"},
                    parameter_rules=["utm_* strip"])
    assert got.intended_noindex == ["/webdesign/*/"]
    assert got.migration_map == {"/old/": "/new/"}


def test_admin_edits_them_and_the_card_links():
    admin = (SRC / "admin.tsx").read_text(encoding="utf-8")
    for name in ("intended_noindex", "migration_map", "parameter_rules"):
        assert f'"{name}",' in admin, name
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "intended[_ -]noindex|noindex list|migration[_ ]map|parameter[_ ]rules" in page
