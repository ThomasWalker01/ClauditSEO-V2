"""Speed's "copy change" is offered only over text to paste.

Screen audits round 3, Speed UX-02 (High): "copy change" was on all three
analysis cards, whose changes were advice and references to rows that were
not there - "same TTFB fix as above" (no row above), "same TTFB investigation
as the article template" (dropped), "verify LiteSpeed cache-hit". URLs and
Indexability gate the control with `isChange`; Speed did not.

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
import { isChange, isPointerAdvice } from "%s";
const ok = (rep) => isChange({ replacement: rep, current: null }) && !isPointerAdvice(rep);
console.log(JSON.stringify({
  above: ok("same TTFB fix as above"),
  article: ok("same TTFB investigation as the article template"),
  verify: ok("verify LiteSpeed cache-hit on the template"),
  preload: ok('<link rel="preload" as="image" href="/hero.webp">'),
}));
"""


def test_the_speed_renderer_gates_its_copy():
    page = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    speed = page[page.index("  speed: { now: SpeedPageNow"):]
    speed = speed[:speed.index("},") + 2]
    assert "copyWhen: (f) => isChange(f) && !isPointerAdvice(f.replacement)" in speed


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_advice_pointing_elsewhere_is_not_copied(tmp_path):
    (tmp_path / "probe.ts").write_text(PROBE % (DASH / "src" / "part_page").as_posix(),
                                       encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = json.loads(subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True,
                                    capture_output=True, text=True, encoding="utf-8").stdout)
    assert out == {"above": False, "article": False, "verify": False, "preload": True}, out
