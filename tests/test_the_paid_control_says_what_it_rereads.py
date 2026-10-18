"""The paid control says what a re-run re-reads and what its price is the
median of (item 271, row 10).

"Re-run analysis · ~USD 0.10" said neither how many rows the analysis would
read again nor what the figure was taken over. It now says "median of N
runs" (the estimate's own `cost_samples`), and "re-reads N rows · M on pages
the automatic checks still raise".
"""

from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo import analyses

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_samples_ride_to_the_button():
    assert '"est_samples": est.get("cost_samples"),' in inspect.getsource(analyses.lanes)
    src = SRC.read_text(encoding="utf-8")
    # Item 276 (row 11): no median where the last cost is the price shown.
    assert "estRuns={floored ? null : mine?.est_samples ?? null}" in src
    assert "on pages the automatic checks still raise" in src
