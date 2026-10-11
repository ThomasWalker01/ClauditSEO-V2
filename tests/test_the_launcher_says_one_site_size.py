"""The launcher says one size for the site (screen audits round 3, launch
IP-02 to IP-04).

twenty22 read five page populations on one block - 74, 68, 53, 49 and 45 -
the precheck tile said "49 Full" and the grid 180 px below "Full ... 53
pages", and "68 audited" was the record's page list, not a count of anything
audited. The site's size is the current reading's: what the sitemap declares
and what the crawl found besides (74).
"""

from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.persistence import runs

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"


def test_the_precheck_carries_the_current_reading_s_size():
    app = (ROOT / "clauditseo" / "api" / "app.py").read_text(encoding="utf-8")
    assert 'out["site_size"] = head["site_size"] if head else None' in app
    assert 'reading = runs.current_reading_id(conn, site_id)' in app
    assert "part_only_runs(conn, site_id)" in inspect.getsource(runs.current_reading_id)


def test_the_grid_and_the_tile_read_it():
    grid = (SRC / "scanmatrix.tsx").read_text(encoding="utf-8")
    assert ": pre.site_size?.size != null" in grid
    tile = (SRC / "precheck.tsx").read_text(encoding="utf-8")
    assert '{sized ? "declared and found"' in tile


def test_audited_is_what_the_reading_audited():
    pane = (SRC / "pane_precheck.tsx").read_text(encoding="utf-8")
    assert "const auditedN = precheck.audited ?? null;" in pane
    assert "data.pages.length" not in pane
