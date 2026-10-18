"""A hold on page `all` is a hold on every page (item 269, row 3).

A brief writes `*` for a check it could not assess anywhere on the site, and
narrowing keeps those rows: a site-wide answer is an answer about this page
too. The Content analysis wrote `all` for `cannibalisation`, and narrowing
dropped it, so the check fell into "12 checks pass on this page" on `/`.

Run as the screen runs it: `fixesOf` bundled by the dashboard's esbuild and
executed by node; and the payload's own filter, which is the same set.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from clauditseo.persistence import runs

DASH = Path(__file__).resolve().parents[1] / "dashboard"
ESBUILD = DASH / "node_modules" / ".bin" / ("esbuild.cmd" if shutil.which("cmd") else "esbuild")

#: Resolved once: a bare name is looked up through System32 first on Windows.
NODE = shutil.which("node")

PROBE = """
import { fixesOf } from "%s";
const held = (page) => ({ check: "CNT/cannibalisation", page, needs: "search console data" });
const part = { key: "content", brief_checks: ["CNT/cannibalisation"],
               brief_held: [held("all"), held("*")] };
console.log(JSON.stringify(fixesOf(part, [], "https://t.co/").filter((f) => f.needs)
  .map((f) => f.page)));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_a_hold_on_page_all_is_kept_on_a_narrowed_page(tmp_path):
    src = (DASH / "src" / "part_page").as_posix()
    (tmp_path / "probe.ts").write_text(PROBE % src, encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True, capture_output=True,
                         text=True, encoding="utf-8")
    assert sorted(json.loads(out.stdout)) == ["*", "all"], out.stdout


def test_the_screen_and_the_payload_read_one_set():
    src = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    m = re.search(r"SITE_WIDE_PAGES = new Set\(\[([^\]]*)\]\)", src)
    assert m, "SITE_WIDE_PAGES is not declared in part_page.tsx"
    assert tuple(json.loads(f"[{m.group(1)}]")) == runs.SITE_WIDE_PAGES
    assert "all" in runs.SITE_WIDE_PAGES
