"""The crawler matrix leads with what it found (item 275, row 11).

Sixteen agents allowed and served 200 on every probed page stood in the
table beside the one rule block and the refusals, in the list's own order.
The blocks and refusals lead; the rest fold under one line saying how many.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "crawl_now.tsx"


def test_blocks_lead_and_the_rest_fold():
    src = SRC.read_text(encoding="utf-8")
    assert "now.ua_matrix.filter((r) => !servedEverywhere(r))" in src
    assert "served on every probed page" in src
    assert "function servedEverywhere(r: UaRow): boolean {" in src
