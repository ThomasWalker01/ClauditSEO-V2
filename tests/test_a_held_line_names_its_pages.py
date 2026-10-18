"""A held line names its pages (item 266, row 10).

"url-slug-entity not assessable on 6 pages - needs ..." said how many and
not which. The line names the first three and how many more, and reads its
reason as given.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_line_names_pages():
    src = SRC.read_text(encoding="utf-8")
    # Up to five named whole (screen audits round 4, Headings IP-01).
    assert "const shown = paths.slice(0, cap).join(\", \");" in src
    assert "const cap = paths.length <= 5 ? 5 : 3;" in src
    assert "})()} — {heldSays(l.needs ?? \"\")}" in src
