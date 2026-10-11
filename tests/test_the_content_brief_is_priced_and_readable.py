"""The content brief is priced, and the written brief can be read (item
269, row 11).

"Write a brief for this page" said it had no price while the lanes payload
held one, and once written it said "brief written for /" with nothing to
open. The button takes the lanes price, and the written brief opens under it.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_priced_and_readable():
    src = SRC.read_text(encoding="utf-8")
    brief = src.split("export function WriteBrief", 1)[1].split("\n}\n", 1)[0]
    assert "price={price}" in brief and "price={null}" not in brief
    assert "<Report title=" in brief and "read the brief" in brief
    assert '.find((a) => a.tool === "content-brief")?.est_cost' in src
