"""A group's sample cards are its template's members, and the two checks
tables share one grid (item 270, row 17).

"orphan-instance · 43 pages · template /seo/*: 28 of 43" was followed by
/about/, /privacy-policy/ and /seo-category/seo-local/ - no member of the
template it named. And the Analysis table wrapped check ids mid-token where
the Free table kept them on a line.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_members_first_and_one_grid():
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "ranked.filter((f) => pathOf(f.page).startsWith(sample.prefix))" in page
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    assert re.search(r"\.checks-table \{ table-layout: fixed; \}", css)
    # One grid, its widths fixed; the check column narrowed for the state
    # column (screen audits round 4, Security UI-01 and others).
    assert ".checks-table th:nth-child(2) { width: 28%; }" in css
    assert ".checks-table th.checks-state-head { width: 32%; }" in css
