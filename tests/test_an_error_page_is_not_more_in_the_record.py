"""An error page is not "more in the record" (item 275, row 7).

The prevalence cell named pages the run fetched but left out of the eligible
set - pages that answered an error - as "3 more in the record", which is the
sentence for pages the run never fetched. The crawl population now carries
the fetched-not-eligible paths, and the cell says "3 fetched with an error".

Run as the screen runs it: `prevalence` bundled by the dashboard's esbuild
and executed by node.
"""

from __future__ import annotations

import json
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
import { prevalence } from "%s";
const pops = { crawl: { size: 2, basis: "crawled pages", paths: ["/", "/a"],
                        errored_paths: ["/gone"] },
               site: { size: null, basis: "", paths: [] }, record: { size: 4, basis: "", paths: [] },
               scope: { pages: null, basis: "" } };
const got = prevalence(["https://t.co/a", "https://t.co/gone", "https://t.co/old"], pops);
console.log(JSON.stringify({ n: got.count.value, unfetched: got.unfetched, errored: got.errored }));
"""


def test_the_payload_names_the_fetched_error_pages():
    ev = {"start_url": "https://t.co/", "pages": [
        {"url": "https://t.co/", "status": 200, "content_type": "text/html"},
        {"url": "https://t.co/gone", "status": 404, "content_type": "text/html"}]}
    assert runs.fetched_not_eligible_paths(ev) == ["/gone"]


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_the_cell_says_fetched_with_an_error(tmp_path):
    (tmp_path / "probe.ts").write_text(PROBE % (DASH / "src" / "population").as_posix(),
                                       encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = json.loads(subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True,
                                    capture_output=True, text=True, encoding="utf-8").stdout)
    assert out == {"n": 1, "unfetched": 1, "errored": 1}, out
