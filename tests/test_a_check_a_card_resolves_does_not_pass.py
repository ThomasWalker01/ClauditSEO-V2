"""A check a card resolves does not pass on the page (item 270, row 6).

Page mode's clean line read "15 checks pass on this page" and named
`schema-orphan-instance`, while the "Wrong shape" card on the same screen
listed `ONP/schema-orphan-instance` among the checks it resolves. The line
tested only `fixes.some(f => f.checkId === c)`; it now reads `alsoResolves`
as the table does.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_clean_line_reads_also_resolves():
    src = SRC.read_text(encoding="utf-8")
    # Followed since screen audits round 3 by the page's site-level filter.
    assert "|| (f.alsoResolves ?? []).some((r) => (r.split(\"/\").pop() ?? r) === c)))" in src
