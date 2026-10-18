"""PAGES reads what a check found, not its URL cap (item 276, row 6).

`sri-missing` keeps 20 URLs and stores `affected_total=45`; the checks table
counted the 20 while the card said "across 45 page(s)". The record now
serves the total, the card carries it, and PAGES reads it (never past the
population it is a share of).
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
import { fixesOf } from "%s";
const urls = Array.from({ length: 20 }, (_, i) => `https://t.co/p${i}/`);
const states = [{ dimension: "SEC", check_id: "sri-missing", severity: "medium", state: "open",
  fingerprint: "s1", summary: "", affected_urls: urls, affected_total: 45,
  source: "deterministic" }];
const part = { key: "security", brief_checks: ["SEC/sri-missing"] };
console.log(JSON.stringify(fixesOf(part, states, "").map((f) => f.affectedTotal)));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_the_card_carries_what_the_check_found(tmp_path):
    src = (DASH / "src" / "part_page").as_posix()
    (tmp_path / "probe.ts").write_text(PROBE % src, encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True, capture_output=True,
                         text=True, encoding="utf-8")
    assert json.loads(out.stdout) == [45], out.stdout


def test_the_record_serves_the_total_and_the_table_reads_it():
    import inspect
    assert "f.affected_total" in inspect.getsource(runs.site_states)
    src = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    assert "const found = Math.max(0, ...counted.map((f) => f.affectedTotal ?? 0));" in src
    # And on a site-scoped part, where it was first left out (Security, whose
    # `sri-missing` still read 20 on twenty22 after the change landed).
    assert "const pages = allInCrawl && found > counted0.count.value\n" in src.replace("\r\n", "\n")


def test_the_total_lifts_only_pages_inside_the_crawl():
    """Screen audits round 3 (Crawl AC-01): `unreachable` read "8 of 45 pages
    crawled" for eight pages never reached, because the total lifted a count
    whose URLs were all outside the crawl."""
    src = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert ("const allInCrawl = counted0.count.value > 0 && counted0.unfetched === 0\n"
            "      && !(counted0.errored ?? 0);") in src


def test_the_checks_table_wraps_inside_its_columns():
    """Screen audits round 3 (Crawl UI-01): on the fixed grid, PAGES phrases
    held on one line ran over STATE, and a long token in STATE ran out of
    its cell. Measured on twenty22 after the fix: no cell overflows."""
    css = (DASH / "src" / "styles.css").read_text(encoding="utf-8")
    assert ".checks-table .count-of, .checks-table .prev-outside { white-space: normal; }" in css
    assert ".checks-table td { overflow-wrap: anywhere; }" in css
