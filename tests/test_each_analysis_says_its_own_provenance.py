"""Each analysis says its own provenance (item 269, row 4).

Content has several analyses writing to it, and the part carried one
`brief_run`: the newest. Its "rows returned" was that analysis's rows plus
the drops of every analysis, a count no run produced. The part now carries
`brief_runs`, one per tool with its own rows, drops and cost; the actions row
names them and sums the cost, and each has its own line.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_payload_carries_one_line_per_analysis():
    src = inspect.getsource(runs.anatomy_view)
    assert '"dropped": brief_dropped.get(part, 0) - dropped_before,' in src
    assert '"brief_runs": brief_runs.get(c.key, []),' in src
    assert '"tool": er["tool_id"]})' in src


def test_the_screen_counts_each_analysis_by_itself():
    page = SRC.read_text(encoding="utf-8")
    # Held rows count as returned (screen audits round 4, Headings AC-01).
    assert "b.rows + b.dropped + (b.held_rows ?? 0)} rows returned" in page
    assert "part.brief_runs!.reduce((s, b) => s + (b.cost ?? 0), 0)" in page
