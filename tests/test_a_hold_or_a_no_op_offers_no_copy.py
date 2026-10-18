"""A hold or a no-op offers nothing to copy (item 277, row 6).

Indexability cards offered "copy change" over a replacement reading "held:
needs the intended-noindex list", and over a canonical set to the URL the
page already declares. Neither is a change to paste.
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
def test_is_change():
    src = SRC.read_text(encoding="utf-8")
    body = src.split("export function isChange", 1)[1].split("\n}\n", 1)[0]
    body = body.split("): boolean {", 1)[1]
    body = re.sub(r"\(s: string\)", "(s)", body)
    js = ("function isChange(fix) {" + body + "\n}\n"
          + "console.log(JSON.stringify(["
          + "isChange({replacement: 'held: needs the intended-noindex list'}),"
          + "isChange({kind: 'rename', replacement: 'https://t.co/a/', current: 'https://t.co/a'}),"
          + "isChange({kind: 'rename', replacement: 'https://t.co/b/', current: 'https://t.co/a/'}),"
          + "isChange({replacement: 'keep as is'}),"
          + "isChange({kind: 'markup', replacement: 'no markup change here - resolve via TEC/noindex-intent first'})]))")
    out = json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                                    check=True).stdout)
    assert out == [False, False, True, False, False]


@pytest.mark.skipif(NODE is None, reason="node not on PATH")
def test_title_desc_offers_no_copy_for_keep():
    """Screen audits round 3 (title-desc AC-02): the bare word is the brief's
    "leave it"; a title that begins with it is a change."""
    src = SRC.read_text(encoding="utf-8")
    assert "copyWhen: (fix) => !isKeep(fix), siteNow: TitleDescSiteNow }" in src
    assert "The analysis keeps the text as it is: no change." in src
    line = src.split("export const isKeep = ", 1)[1].split(";\n", 1)[0]
    line = line.replace("(fix: { replacement?: string | null })", "(fix)")
    js = ("const isKeep = " + line + ";\nconsole.log(JSON.stringify(["
          "isKeep({replacement: 'keep'}), isKeep({replacement: ' Keep. '}),"
          "isKeep({replacement: 'Keep your site fast with managed hosting'}),"
          "isKeep({replacement: null})]))")
    out = json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                                    check=True).stdout)
    assert out == [True, True, False, False]
