"""A markup card lays out its replacement and drops a Where that says
markup (item 270, row 17).

The model writes JSON-LD on one line; beside the laid-out Now it read as a
long scroll. And "Where: markup" stood under the two markup panels.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src" / "part_page.tsx"
NODE = shutil.which("node")


def test_the_card_source():
    src = SRC.read_text(encoding="utf-8")
    body = src.split("function SchemaFixBody", 1)[1].split("\n}\n", 1)[0]
    assert "laidOut(fix.replacement" in body
    assert '["markup", (fix.kind ?? "").toLowerCase()]' in body


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
def test_laid_out():
    src = SRC.read_text(encoding="utf-8")
    fn = src.split("export function laidOut", 1)[1].split("\n}\n", 1)[0]
    js = "function laidOut" + fn + "\n}\n" + """
const long = JSON.stringify({"@context": "https://schema.org", "@type": "Organization",
  "name": "Birch Events", "url": "https://birch.example/"});
console.log(JSON.stringify([laidOut(long), laidOut('{"a":1}'), laidOut("x".repeat(90))]));
"""
    js = js.replace("(text: string): string", "(text)")
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True).stdout
    long, short, prose = json.loads(out)
    assert long.count("\n") >= 4
    assert short == '{"a":1}'
    assert prose == "x" * 90
