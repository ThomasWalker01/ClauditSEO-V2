"""The Speed template picker leads with the worst template and says each
one's LCP.

Screen audits round 3, Speed UX-01 (High): the twelve chips each read "1 of
12 pages traced", with no vital and no order, and the part opened on `/`, so
finding the worst template took twelve clicks.

Run as the screen runs it: bundled by the dashboard's esbuild, executed by node.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1] / "dashboard"
ESBUILD = DASH / "node_modules" / ".bin" / ("esbuild.cmd" if shutil.which("cmd") else "esbuild")
NODE = shutil.which("node")

PROBE = """
import { worstFirst } from "%s";
const t = (pattern, band, value) => ({ pattern, vitals: band === undefined ? [] :
  [{ key: "lcp", label: "LCP", value, unit: "ms", band, basis: "", proxy: null, over: null }] });
console.log(JSON.stringify(worstFirst([
  t("/", "good", 1900), t("/blog/*", "poor", 4300), t("/x/*", undefined),
  t("/seo/*", "needs improvement", 2900), t("/web/*", "poor", 5100), t("/a/*", "good", 2296),
]).map((x) => x.pattern)));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_the_templates_are_ordered_worst_first(tmp_path):
    (tmp_path / "probe.ts").write_text(PROBE % (DASH / "src" / "speed_now").as_posix(),
                                       encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = json.loads(subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True,
                                    capture_output=True, text=True, encoding="utf-8").stdout)
    assert out == ["/web/*", "/blog/*", "/seo/*", "/a/*", "/", "/x/*"], out


def test_the_part_opens_on_the_first_of_that_order_and_chips_say_lcp():
    src = (DASH / "src" / "speed_now.tsx").read_text(encoding="utf-8")
    assert "const ordered = worstFirst(now.templates);" in src
    assert "?? ordered[0];" in src and "{ordered.map((x) => (" in src
    assert "LCP {ms(g.value, g.unit)}" in src and "LCP not read" in src
