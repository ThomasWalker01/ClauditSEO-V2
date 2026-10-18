"""Dropped rows are grouped by reason (item 277, row 14).

The dropped list said the same sentence once per row - "free check; the
automatic checks measured it and raised nothing on 4 pages" eleven times with
a different page each. Rows are grouped by reason (a count or a path in it
does not make a second reason), each reason said once with the checks it
dropped, and the pages behind a disclosure.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
def test_grouping():
    src = SRC.read_text(encoding="utf-8")
    body = src.split("export function droppedByReason", 1)[1].split("\n}\n", 1)[0]
    body = body.split(") {", 1)[1]
    # Strip the TypeScript: the generic, the annotations, the tuple casts.
    body = re.sub(r"new Map<[^(]*>\(\)", "new Map()", body, flags=re.S)
    js = "function droppedByReason(rows) {" + body + "\n}\n" + """
const rows = [
  {check: "noindex-in-sitemap", page: "https://t.co/a/", reason: "reported a pass on /a/; passes are not stored"},
  {check: "noindex-in-sitemap", page: "https://t.co/b/", reason: "reported a pass on /b/; passes are not stored"},
  {check: "redirect-chain", page: null, reason: "reported a pass on /; passes are not stored"},
  {check: "noindex-intent", page: "https://t.co/c/", reason: "a hold written as a row on 4 pages"},
];
console.log(JSON.stringify(droppedByReason(rows).map((g) => [g.rows.length, g.checks])));
"""
    out = json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                                    check=True).stdout)
    assert out == [[3, [["noindex-in-sitemap", 2], ["redirect-chain", 1]]],
                   [1, [["noindex-intent", 1]]]]


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
def test_a_figure_the_rows_disagree_on_is_a_range():
    """Screen audits round 3 (title-desc AC-01): ten rows measuring 431 to
    578 px were said as "replacement 578 px, cut at 410 px"."""
    src = SRC.read_text(encoding="utf-8")
    body = src.split("export function droppedByReason", 1)[1].split("\n}\n", 1)[0]
    body = body.split(") {", 1)[1]
    body = re.sub(r"new Map<[^(]*>\(\)", "new Map()", body, flags=re.S)
    js = "function droppedByReason(rows) {" + body + "\n}\n" + """
const rows = [578, 431, 559].map((px) => ({check: "title-length", page: null,
  reason: `replacement ${px} px, cut at 410 px on mobile`}));
console.log(JSON.stringify(droppedByReason(rows).map((g) => g.reason)));
"""
    out = json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                                    encoding="utf-8", check=True).stdout)
    assert out == ["replacement 431–578 px, cut at 410 px on mobile"]
