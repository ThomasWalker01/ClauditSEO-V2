"""One template rule (item 268, row 6).

The skip table said every shape had "no shared template" (`templatesOf`,
ten pages or more) and closed with "Fix the no shared template template";
forty lines down a Fixes group named "template /seo-category/*, 5 of 12"
(`templateOf`, two pages or more), and a group of holds named one too. One
rule now: `templateOf` reads `templatesOf`; the closing line says nothing
for the residual bucket; a group of holds names no template.

Run as the screen runs it: bundled by the dashboard's esbuild, executed by
node.
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
import { templateOf } from "%s";
import { closingLine } from "%s";
const many = Array.from({ length: 12 }, (_, i) => `https://t.co/seo-category/p${i}/`);
const few = ["https://t.co/seo-category/a/", "https://t.co/seo-category/b/", "https://t.co/x/"];
console.log(JSON.stringify({
  many: templateOf(many), few: templateOf(few),
  residual: closingLine([{ prefix: "", rooted: false, pages: 9, label: "h2>h4", code: "s", examples: [] }]),
}));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_templates_are_named_by_one_rule(tmp_path):
    src = DASH / "src"
    (tmp_path / "probe.ts").write_text(
        PROBE % ((src / "part_page").as_posix(), (src / "headings_outline").as_posix()),
        encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = json.loads(subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True,
                                    capture_output=True, text=True, encoding="utf-8").stdout)
    assert out["many"] == {"prefix": "/seo-category/", "n": 12}, out
    # Two pages under one segment were a template; by the shared rule they are not.
    assert out["few"] is None, out
    assert out["residual"] is None, out


def test_a_group_of_holds_names_no_template():
    page = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    assert "const tpl = step || cards.every((f) => f.needs) ? null" in page
