"""A check owed per raised page, and not returned, is said so (item 271, row 4).

`links.md` asks for a `link-suggestion` row "for each page failing inlinks-low
or orphan". On twenty22 the Links analysis returned none while `inlinks-low`
was open on 23 pages, and the part read it clean. The run now logs each owed
page as uncovered, and the checks table names the gap with its pages.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from clauditseo.analysts import expert

DASH = Path(__file__).resolve().parents[1] / "dashboard"
ESBUILD = DASH / "node_modules" / ".bin" / ("esbuild.cmd" if shutil.which("cmd") else "esbuild")

#: Resolved once: a bare name is looked up through System32 first on Windows.
NODE = shutil.which("node")

B = "https://t.fixture"


@pytest.fixture()
def conn(tmp_path):
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    c = connect(tmp_path / "c.db")
    migrate(c)
    site = repo.create_site(c, repo.create_client(c, repo.ensure_default_operator(c), "C"),
                            "t.fixture")
    yield c, runs.create_run(c, site, ["LNK"], "T2")
    c.close()


def _finding(conn, run_id, check, urls, source="deterministic"):
    conn.execute(
        "INSERT INTO findings (run_id, check_id, dimension, severity, summary, affected_urls,"
        " evidence, recommendation, source, fingerprint, created_at)"
        " VALUES (?, ?, 'LNK', 'medium', 's', ?, '{}', '', ?, ?, '2026-10-04')",
        (run_id, check, json.dumps(urls), source, f"fp-{check}-{len(urls)}"))


class _Row:
    def __init__(self, check, page):
        self.check, self.page, self.image, self.also_resolves = check, page, None, []


def test_each_page_owed_a_suggestion_and_not_given_one_is_uncovered(conn):
    conn, run_id = conn
    _finding(conn, run_id, "inlinks-low", [B + "/a/", B + "/b/"])
    _finding(conn, run_id, "orphan", [B + "/c/"])
    rows = [_Row("LNK/link-suggestion", B + "/a/")]
    got = expert._uncovered(conn, run_id, ["LNK/link-suggestion"], rows,
                            [B + "/a/", B + "/b/", B + "/c/"])
    assert sorted((g["page"], g["owed_by"]) for g in got) == [
        (B + "/b/", "LNK/inlinks-low"), (B + "/c/", "LNK/orphan")], got


PROBE = """
import { owedPages } from "%s";
const f = (checkId, page, sources) => ({ checkId, page, urls: [page], sources });
console.log(JSON.stringify({
  owed: owedPages("link-suggestion", [f("inlinks-low", "https://t/a/", ["sweep"]),
                                      f("inlinks-low", "https://t/b/", ["sweep"]),
                                      f("orphan", "https://t/a/", ["sweep"])]),
  analysisOnly: owedPages("link-suggestion", [f("inlinks-low", "https://t/a/", ["brief"])]),
  other: owedPages("hub", [f("inlinks-low", "https://t/a/", ["sweep"])]),
}));
"""


@pytest.mark.skipif(not NODE or not ESBUILD.exists(),
                    reason="node or the dashboard's esbuild is not installed")
def test_the_table_counts_the_pages_owed_a_row(tmp_path):
    src = (DASH / "src" / "part_page").as_posix()
    (tmp_path / "probe.ts").write_text(PROBE % src, encoding="utf-8")
    subprocess.run([str(ESBUILD), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=DASH)
    out = subprocess.run([NODE, str(tmp_path / "probe.cjs")], check=True, capture_output=True,
                         text=True, encoding="utf-8")
    got = json.loads(out.stdout)
    assert got == {"owed": {"triggers": ["inlinks-low", "orphan"], "pages": 2},
                   "analysisOnly": None, "other": None}, got


def test_the_screen_and_the_contract_name_the_same_triggers():
    from clauditseo.analysts.contract import REQUIRED_BY
    src = (DASH / "src" / "part_page.tsx").read_text(encoding="utf-8")
    for check, triggers in REQUIRED_BY.items():
        bare = [t.split("/")[-1] for t in triggers]
        assert f'"{check.split("/")[-1]}": {json.dumps(bare)}' in src
