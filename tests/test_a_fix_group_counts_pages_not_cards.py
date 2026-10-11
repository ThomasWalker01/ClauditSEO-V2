"""A Fixes group counts pages, not cards (item 267, row 4).

The group label counted cards and called them pages: four crawlers' edge
blocks, all on the one page "/", read "AIS/edge-blocks-ai-ua · 4 pages"
beside a table reading 3 of 3 probed. And a raised row naming no page drew
PAGES "0", the zero that reads as clean.

Run as the screen runs it: `groupCount` bundled by the dashboard's esbuild
and executed by node.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1] / "dashboard"
ESBUILD = DASH / "node_modules" / ".bin" / ("esbuild.cmd" if shutil.which("cmd") else "esbuild")

#: Resolved once: a bare name is looked up through System32 first on Windows.
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                                reason="node or the dashboard's esbuild is not installed")

PROBE = """
import { groupCount } from "%s";
const probed = ["https://t.co/", "https://t.co/a/", "https://t.co/b/"];
const agent = () => ({ page: "https://t.co/", urls: probed });
const page = (p) => ({ page: `https://t.co${p}`, urls: [`https://t.co${p}`] });
console.log(JSON.stringify({
  crawlers: groupCount("edge-blocks-ai-ua", [agent(), agent(), agent(), agent()]),
  entities: groupCount("entity-unnamed", [{ page: "" }, { page: "" }]),
  pages: groupCount("depth-deep", [page("/x/"), page("/y/"), page("/x/")]),
  nopage: groupCount("llms-txt-missing", [{ page: "" }, { page: "" }]),
}));
"""


def test_the_group_label_counts_distinct_pages_and_says_its_subjects(tmp_path):
    src = (DASH / "src" / "part_page").as_posix()
    (tmp_path / "probe.ts").write_text(PROBE % src, encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True, capture_output=True,
                         text=True, encoding="utf-8")
    got = json.loads(out.stdout)
    assert got == {"crawlers": "4 crawlers · 3 pages", "entities": "2 entities",
                   # Item 275 (row 8): three cards on two pages say both.
                   "pages": "2 pages · 3 cards", "nopage": "2 cards"}, got


def test_a_raised_row_naming_no_page_draws_a_dash():
    src = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    assert "const noPage = !named.some(Boolean);" in src
    assert 'r.noPage ? <span title="the finding names no page">—</span>' in src
    assert "· {groupCount(checkId, cards)}" in src
