"""An analysis accounts for its own cards (item 275, row 5).

Crawl & sitemaps' provenance read "24 rows returned · 7 kept · 17 dropped"
while its accounting line read "1 merged · 18 on their own · 5 held · 17
dropped": seven kept rows cannot make nineteen cards. The audit's TO CONFIRM
asked where the 17 `LNK/depth-deep` analysis cards came from. The stored
record answers it: on twenty22 they are the Links analysis's rows
(`from_brief: "links"`), filed against the same audit run and drawn on Crawl
because `depth-deep` belongs there. The accounting now counts this
analysis's own cards and says the others apart; and a check the model
returned as NOT_ASSESSABLE, dropped as a row and drawn as a hold, is counted
once, as the hold.

Run as the screen runs it: `fixesOf` bundled by the dashboard's esbuild and
executed by node.
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
import { fixesOf } from "%s";
const row = (over) => ({ dimension: "LNK", check_id: "depth-deep", severity: "low",
  state: "open", summary: "", affected_urls: [over.url], source: "model-judgement",
  fingerprint: over.url + over.brief, ...over });
const states = [
  row({ url: "https://t.co/a/", brief: "links" }),
  row({ url: "https://t.co/b/", brief: "links" }),
  row({ url: "https://t.co/c/", brief: "crawl" }),
  row({ url: "https://t.co/a/", brief: "crawl" }),
];
const part = { key: "crawl", brief_checks: ["LNK/depth-deep"] };
console.log(JSON.stringify(fixesOf(part, states, "").map((f) => ({
  page: f.page, briefs: f.briefs }))));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_a_card_knows_which_analyses_wrote_it(tmp_path):
    src = (DASH / "src" / "part_page").as_posix()
    (tmp_path / "probe.ts").write_text(PROBE % src, encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True, capture_output=True,
                         text=True, encoding="utf-8")
    by = {c["page"]: c["briefs"] for c in json.loads(out.stdout)}
    assert by == {"https://t.co/a/": ["links", "crawl"], "https://t.co/b/": ["links"],
                  "https://t.co/c/": ["crawl"]}, by


def test_the_accounting_counts_its_own_and_a_hold_once():
    page = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    assert 'fixes.filter((f) => f.sources.includes("brief") && mine(f));' in page
    assert "Also on this page: {others.length} card" in page
    assert "const dropped = Math.max(0, (part.brief_dropped ?? 0) - alsoHeld);" in page
