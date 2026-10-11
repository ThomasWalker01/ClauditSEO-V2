"""The page-mode image note reconciles as site mode's does (item 272, row 7).

Site mode said placements, distinct images and what the crawl recorded; page
mode said "7 distinct images on /" over a wall of 11, and nothing said where
the other four went. The payload carries each page's own tally, and the note
says it: "11 images on /: 7 distinct drawn, 2 repeat placements, 2 with no
rendered box."
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "images_budget.tsx"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
def test_the_note():
    src = SRC.read_text(encoding="utf-8")
    fn = src.split("export function pageNote", 1)[1].split("\n}\n", 1)[0]
    js = ("function pageNote(t, distinct, scope) {" + fn.split(": string {", 1)[1].replace("(n: number)", "(n)") + "\n}\n"
          + "console.log(JSON.stringify([pageNote({total: 11, unmeasured: 0, unplaced: 2, placed: 9}, 7, 'on /'),"
          + " pageNote(undefined, 1, 'on /a/')]))")
    out = json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                                    check=True).stdout)
    assert out == ["11 images on /: 7 distinct drawn, 2 repeat placements, 2 with no rendered box.",
                   "1 distinct image on /a/."]


def test_the_payload_carries_each_pages_tally():
    runs = (Path(__file__).resolve().parents[1] / "clauditseo" / "persistence" / "runs.py"
            ).read_text(encoding="utf-8")
    assert '"per_page": per_page,' in runs
