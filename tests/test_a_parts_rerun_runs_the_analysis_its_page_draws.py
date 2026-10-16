"""A part's Re-run runs the analysis whose rows the page draws.

Screen audits round 3, Content UX-01 (High): the part's only paid control ran
content-benchmark - the first lane whose part was `content` - which returned 0
rows for USD 0.12, while content-substance's 18 kept rows filled the page and
its brief had changed. The others were named in plain text pointing at
another screen, with no link.

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
import { partAnalysis } from "%s";
const lane = (tool) => ({ tool, part: "content" });
const lanes = { ready: [lane("content-benchmark"), lane("content-substance")],
                available: [lane("content-brief")] };
const run = (tool, rows, at) => ({ tool, rows, at, model: null, run_id: "r", dropped: 0, cost: 0.1 });
console.log(JSON.stringify({
  ran: partAnalysis({ key: "content", brief_runs: [run("content-benchmark", 0, "2026-09-23"),
                                                    run("content-substance", 18, "2026-09-20")] }, lanes)?.tool,
  tie: partAnalysis({ key: "content", brief_runs: [run("content-benchmark", 2, "2026-09-23"),
                                                    run("content-substance", 2, "2026-09-20")] }, lanes)?.tool,
  none: partAnalysis({ key: "content", brief_runs: [] }, lanes)?.tool,
  gone: partAnalysis({ key: "content", brief_runs: [run("content-old", 30, "2026-09-01")] }, lanes)?.tool,
}));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_the_analysis_with_the_rows_is_the_one_rerun(tmp_path):
    (tmp_path / "probe.ts").write_text(PROBE % (DASH / "src" / "part_page").as_posix(),
                                       encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = json.loads(subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True,
                                    capture_output=True, text=True, encoding="utf-8").stdout)
    assert out == {"ran": "content-substance", "tie": "content-benchmark",
                   "none": "content-benchmark", "gone": "content-benchmark"}, out


def test_the_run_handler_and_the_button_share_the_rule():
    anat = (DASH / "src" / "anatomy.tsx").read_text(encoding="utf-8")
    assert "const briefOf = (c: Category): string | null => partAnalysis(c, lanes)?.tool ?? null;" in anat
    page = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    assert "const mine: Analysis | undefined = partAnalysis(part, lanes);" in page
    assert 'othersHref={siteId ? `#/sites/${siteId}?tab=analyses` : null}' in page
