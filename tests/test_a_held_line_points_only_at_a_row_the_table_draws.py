"""A held line points only at a row the table draws (item 276, row 4).

On the whole part, Fixes names a held check and sends the reader to its
"not assessable" row in the checks table. Found live on twenty22 the day it
landed: Links pointed `redirect-chain` at a row the table did not draw. The
check is free, the automatic checks measured it after the analysis held it,
and so the table reads it clean (item 251). Both now read one rule,
`sweepOutranks`, and an outranked hold keeps its reason under Fixes.
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
import { sweepOutranks } from "%s";
const part = { key: "links", brief_run: { at: "2026-09-23T11:26:00Z" },
               check_cost: { "LNK/redirect-chain": "free", "LNK/anchor-entity": "model" } };
const none = new Map();
console.log(JSON.stringify({
  free: sweepOutranks(part, "LNK/redirect-chain", "redirect-chain", "2026-10-02T03:00:00Z", none),
  model: sweepOutranks(part, "LNK/anchor-entity", "anchor-entity", "2026-10-02T03:00:00Z", none),
  older: sweepOutranks(part, "LNK/redirect-chain", "redirect-chain", "2026-09-20T03:00:00Z", none),
  unmeasured: sweepOutranks(part, "LNK/redirect-chain", "redirect-chain", "2026-10-02T03:00:00Z",
                            new Map([["redirect-chain", "not run"]])),
  // Screen audits round 3, Indexability AC-01: an analysis run on 3 Oct that
  // read the 2 Oct crawl is outranked by the sweep of that same crawl.
  sameCrawl: sweepOutranks({ ...part, brief_run: { at: "2026-10-03T10:25:00Z", run_id: "r2",
                                                   crawl_at: "2026-10-02T03:20:00Z" } },
                           "LNK/redirect-chain", "redirect-chain", "2026-10-02T02:57:00Z", none, "r2"),
  readLater: sweepOutranks({ ...part, brief_run: { at: "2026-10-03T10:25:00Z", run_id: "r3",
                                                   crawl_at: "2026-10-03T09:00:00Z" } },
                           "LNK/redirect-chain", "redirect-chain", "2026-10-02T02:57:00Z", none, "r2"),
}));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_a_newer_reading_of_a_free_check_outranks_the_hold(tmp_path):
    src = (DASH / "src" / "part_page").as_posix()
    (tmp_path / "probe.ts").write_text(PROBE % src, encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True, capture_output=True,
                         text=True, encoding="utf-8")
    assert json.loads(out.stdout) == {"free": True, "model": False, "older": False,
                                      "unmeasured": False, "sameCrawl": True,
                                      "readLater": False}, out.stdout


def test_the_table_and_the_held_line_read_the_one_rule():
    src = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    # Three reads of one rule: the table, Fixes, and the hold lines that say an
    # outranked hold as one (screen audits round 4, Crawl IP-01).
    assert src.count("sweepOutranks(part, ") == 3, "the table and Fixes do not both read it"
    assert "heldN > 0 && sweepOutranks(part, full, checkId, sweepAt, unmeasured, sweepRun)" in src
    assert "!sweepOutranks(part, f.check, f.checkId, sweep?.at, unmeasured, sweep?.run_id ?? null)" in src
