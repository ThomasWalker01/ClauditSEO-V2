"""An Images card draws what it copies, and no empty tag (item 272, row 5).

At site scope `ImagesFixBody` read the image's record from the page in
scope, which is none, and drew an empty `<img>` as Now. And "copy markup"
was drawn on cards whose replacement held no `<img>`, where the body drew no
Replace with pane. The Now pane says what the finding says where no record is
in hand, and the copy control follows the pane.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_no_empty_tag_and_no_copy_without_a_pane():
    src = SRC.read_text(encoding="utf-8")
    body = src.split("function ImagesFixBody", 1)[1].split("\nexport type Bounds", 1)[0]
    assert "{!before.length ? (" in body
    assert "copyWhen: (fix) => attrsIn(fix.replacement).length > 0," in src
    assert "(fix.replacement && (render.copyWhen?.(fix) ?? true))" in src
