"""A Links card strikes only the old anchor (item 271, row 7).

`LinksFixBody` drew the finding's sentence struck through above the
replacement, so "3 internal links on /x whose anchor text says nothing" read
as text to delete. The sentence is now the card's reason; an anchor card
strikes each old anchor alone and sets the new one beside it, read from the
replacement's own entries.

Run as the screen runs it: `anchorSwaps` bundled by the dashboard's esbuild
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

PROBE = """
import { anchorSwaps } from "%s";
console.log(JSON.stringify([
  anchorSwaps("'Learn more' \u2192 'what Birch Events does' (\u2192 /birch-events-what-we-do); "
              + "'Learn more' \u2192 'the Birch Events team' (\u2192 /birch-events-team)"),
  anchorSwaps("Rewrite the anchors on this page."),
]));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_each_entry_is_one_swap_and_prose_is_none(tmp_path):
    src = (DASH / "src" / "part_page").as_posix()
    (tmp_path / "probe.ts").write_text(PROBE % src, encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True, capture_output=True,
                         text=True, encoding="utf-8")
    swaps, prose = json.loads(out.stdout)
    assert swaps == [
        {"from": "Learn more", "to": "what Birch Events does", "target": "/birch-events-what-we-do"},
        {"from": "Learn more", "to": "the Birch Events team", "target": "/birch-events-team"},
    ], swaps
    assert prose == []


def test_the_sentence_is_the_reason_not_struck():
    page = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    body = page.split("function LinksFixBody", 1)[1].split("\nexport function anchorSwaps", 1)[0]
    assert '<p className="fix-why">{fix.current}</p>' in body
    assert "<s>{fix.current}</s>" not in body
