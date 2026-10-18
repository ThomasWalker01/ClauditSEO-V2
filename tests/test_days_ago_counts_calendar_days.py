""""N days ago" counts calendar days (screen audits round 4, Home IP-02,
AC-02, IP-01, UX-02).

Home and the landing floored elapsed time to whole days, so an audit of
12 Oct 18:48 read "3 days ago" on 16 Oct 15:45. Both now count calendar days
in the reader's zone. And the Home card said "11 back after a fix. 621 open",
which read as 632; the regressed rows are said inside the open count and open
the Record on them.

Run as the screen runs it: bundled by the dashboard's esbuild, executed by
node.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.test_one_template_rule import DASH, ESBUILD, NODE

PROBE = """
import { ago as homeAgo } from "%s";
import { ago as laneAgo } from "%s";
const now = new Date(2026, 9, 16, 15, 45);
const then = new Date(2026, 9, 12, 18, 48).toISOString();
const late = new Date(2026, 9, 15, 23, 50).toISOString();
console.log(JSON.stringify({
  home: homeAgo(then, now), lane: laneAgo(then, now.getTime()),
  homeY: homeAgo(late, now), laneY: laneAgo(late, now.getTime()),
}));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_four_calendar_days_read_four_days(tmp_path):
    src = DASH / "src"
    (tmp_path / "probe.ts").write_text(PROBE % ((src / "home").as_posix(),
                                                (src / "client_lanes").as_posix()),
                                       encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = json.loads(subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True,
                                    capture_output=True, text=True, encoding="utf-8").stdout)
    assert out == {"home": "4 days ago", "lane": "4 days ago",
                   "homeY": "yesterday", "laneY": "15 hours ago"}, out


def test_the_regressed_rows_are_said_inside_the_open_count():
    h = (DASH / "src" / "home.tsx").read_text(encoding="utf-8")
    assert "of them back after a fix</a>" in h
    assert "?tab=all&state=regressed" in h
    assert "ago(s.recheck_label ? s.score_at ?? null : s.last_run_at)}`" in h


def test_a_narrow_score_wears_no_site_band_and_a_running_audit_is_said():
    """Home AC-01, UX-01."""
    c = (DASH / "src" / "components.tsx").read_text(encoding="utf-8")
    assert 'className="score score-narrow"' in c
    h = (DASH / "src" / "home.tsx").read_text(encoding="utf-8")
    assert 'narrow={s.narrow_scope ?? "narrow"}' in h
    assert "An audit is running, started {stamp(s.running_since)}." in h
    app = (DASH.parent / "clauditseo" / "api" / "app.py").read_text(encoding="utf-8")
    assert '"running_since":' in app
