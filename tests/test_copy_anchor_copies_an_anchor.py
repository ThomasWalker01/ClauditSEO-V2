""""copy anchor" copies an anchor, and says for which page (item 271, row 8).

Every Links card's button read "copy anchor" and copied the replacement
prose ("from /x - anchor 'y' - after h2 ..."). It now copies the first
suggestion's anchor, or an anchor card's new anchors; a removal or a
hand-off draws none; and each button's name says the page it is for.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_links_copy_reads_the_anchor():
    src = SRC.read_text(encoding="utf-8")
    assert 'copyWhen: (fix) => !["remove", "handoff"].includes(fix.kind ?? ""),' in src
    assert "copyText: (rep, fix) => fix.suggestions?.length ? fix.suggestions[0].anchor" in src


def test_each_copy_button_names_its_page():
    src = SRC.read_text(encoding="utf-8")
    assert ': `${render.copyLabel ?? "copy replacement"} for ${fix.page ? pathOf(fix.page) : fix.check}`}' in src
