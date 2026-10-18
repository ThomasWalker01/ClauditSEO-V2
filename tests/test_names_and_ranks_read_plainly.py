"""Names and ranks read plainly (items 267 r19, 266 r12, 268 r10, 276 r11).

`plainName` printed "Llms.txt missing" and "Ai crawler ua"; the part header's
"ranked 51" said no "of how many" and read as a score.
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

PROBE = """
import { plainName } from "%s";
console.log(JSON.stringify(["AIS/llms-txt-missing", "AIS/edge-blocks-ai-ua", "AIS/id-page-absent"]
  .map((c) => plainName(c))));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_plain_names(tmp_path):
    (tmp_path / "probe.ts").write_text(PROBE % (DASH / "src" / "part_page").as_posix(),
                                       encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    got = json.loads(subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True,
                                    capture_output=True, text=True, encoding="utf-8").stdout)
    assert got[0] == "llms.txt missing", got
    assert got[1].endswith("AI UA"), got
    assert got[2].startswith("ID page"), got


def test_the_rank_says_of_how_many():
    src = (DASH / "src" / "anatomy.tsx").read_text(encoding="utf-8")
    assert "ranked {r} of {lanes!.triage!.ranked.length} in triage" in src
