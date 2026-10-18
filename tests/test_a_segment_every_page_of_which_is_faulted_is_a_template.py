"""A segment whose every page carries a fault is a template (channel ruling
20261016-1440, screen audits round 3, Headings US-01).

`templatesOf` named nothing under ten faulted pages, so twenty22's five
`/seo-category/` pages - every page of that segment, all H1 -> H3, one
WordPress archive template - never got "fix the /seo-category/* template".
The ruling added a coverage test beside the count test: a first segment is
a template when the fault is on every page read under it and it has at
least three. The server sends the pages read per segment; every reader
passes them, so the rule stays one rule (item 268).

Run as the screen runs it: bundled by the dashboard's esbuild, executed by
node.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from tests.test_one_template_rule import DASH, ESBUILD, NODE

PROBE = """
import { templatesOf } from "%s";
import { templateOf } from "%s";
import { skipRows } from "%s";
const cat = ["seo-local", "seo-main", "seo-off-page", "seo-on-page", "seo-technical"]
  .map((s) => `https://t.co/seo-category/${s}/`);
const item = (u) => ({ fingerprint: u, urls: [u], state: "open", names_a_page: true });
const shapes = (segments) => ({ run_id: "r", recorded: true, scope: null, crawled: 45, pages: 45,
  at: Object.fromEntries([...cat, "https://t.co/about/", "https://t.co/"]
                         .map((u) => [u, ["skip:1>3"]])),
  labels: { "skip:1>3": { label: "H1 → H3", tone: "warn", check: "heading-skip" } },
  segments });
console.log(JSON.stringify({
  whole: templatesOf(cat.map(item), { "/seo-category/": 5 }).map((t) => [t.prefix, t.pages]),
  part: templatesOf(cat.map(item), { "/seo-category/": 40 }).map((t) => [t.prefix, t.pages]),
  two: templatesOf(cat.slice(0, 2).map(item), { "/seo-category/": 2 }).map((t) => t.prefix),
  bare: templatesOf(cat.map(item)).map((t) => t.prefix),
  group: templateOf(cat, { "/seo-category/": 5 }),
  rows: skipRows(shapes({ "/seo-category/": 5 })).map((r) => [r.prefix, r.pages]),
  spread: skipRows(shapes({ "/seo-category/": 40 })).map((r) => [r.prefix, r.pages]),
}));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_every_page_of_a_segment_faulted_is_its_template(tmp_path):
    src = DASH / "src"
    (tmp_path / "probe.ts").write_text(PROBE % (
        (src / "anatomy").as_posix(), (src / "part_page").as_posix(),
        (src / "headings_outline").as_posix()), encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = json.loads(subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True,
                                    capture_output=True, text=True, encoding="utf-8").stdout)
    # twenty22's shape: 5 of 5 is the template.
    assert out["whole"][0] == ["/seo-category/", 5], out
    assert out["group"] == {"prefix": "/seo-category/", "n": 5}, out
    # 5 faulted of 40 read under the segment is not.
    assert out["part"] == [], out
    # Under three pages coverage proves nothing.
    assert out["two"] == [], out
    # Without the counts the rule is the count test alone, as before.
    assert out["bare"] == [], out
    # The skip table: one template row, the rest residual.
    assert out["rows"] == [["/seo-category/", 5], ["", 2]], out
    assert out["spread"] == [["", 7]], out

