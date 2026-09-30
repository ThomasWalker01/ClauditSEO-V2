"""A CLI run stores its crawl evidence whichever branch it takes (KI-11).

`--tier` defaults to `auto`, and that branch dispatches to `run_adaptive`,
which calls `store_evidence` at both its exits. The explicit fixed-tier branch
called it at neither, so `clauditseo audit run --tier T2` completed a run and
recorded nothing about what the crawl reached: `crawl_evidence` NULL beside a
populated `crawled_paths`. Three of the eighteen stored runs are in that state
— `93bdd2b2`, `8fdeb042`, `d9c14277`, all T2 — and on such a run
`_breadth_phrase`, the run report's "what the crawl actually reached" section
and `_snapshot_metrics`' scope for `measured_share` have nothing to read.

The guard runs the real entry point — `cli.main(["audit", "run", ...])`, not
`_cmd_audit_run` with a hand-built namespace — because the defect was in which
branch the dispatch chose, and a test that picks the branch itself cannot see
that. It asserts the evidence is *populated*, not merely non-NULL: an empty
snapshot is a JSON object, so `IS NOT NULL` alone would pass on a crawl that
reached nothing, and the request log is asserted non-empty in the same test so
the population the evidence describes is known to exist.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from clauditseo import cli
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo


def _page(links: list[str] = (), title: str = "t") -> tuple[int, dict, str]:
    anchors = "".join(f'<a href="{href}">x</a>' for href in links)
    return (200, {}, f"<html><head><title>{title}</title></head>"
                     f"<body><h1>{title}</h1>{anchors}</body></html>")


@pytest.fixture
def cli_site(tmp_path, monkeypatch, make_site):
    """A fixture site, and a throwaway database the CLI will find via config.

    `settings()` reads the environment fresh on every call, so pointing
    `CLAUDITSEO_DB` at `tmp_path` is enough to keep the CLI off the operator's
    real database — nothing here writes to `data/clauditseo.db`.
    """
    site = make_site({
        "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nAllow: /\n"),
        "/": _page(["/about"], title="home"),
        "/about": _page(title="about"),
    })
    db_path = tmp_path / "cli.db"
    monkeypatch.setenv("CLAUDITSEO_DB", str(db_path))

    conn = connect(db_path)
    migrate(conn)
    op_id, _ = repo.create_operator(conn, "Tester", None, "owner")
    client_id = repo.create_client(conn, op_id, "Acme")
    repo.create_site(conn, client_id, site.base_url + "/")
    conn.close()
    return site, db_path


def _runs(db_path) -> list[sqlite3.Row]:
    conn = connect(db_path)
    try:
        return conn.execute(
            "SELECT id, tier, status, crawled_paths, crawl_evidence"
            " FROM audit_runs ORDER BY created_at").fetchall()
    finally:
        conn.close()


def test_a_fixed_tier_cli_run_stores_the_crawl_evidence(cli_site):
    site, db_path = cli_site

    rc = cli.main(["audit", "run", "--client", "Acme", "--site", site.base_url + "/",
                   "--tier", "T2", "--dims", "TEC,ONP"])
    assert rc == 0

    assert site.request_log, "the crawl fetched nothing — the guard has no population"

    rows = _runs(db_path)
    assert len(rows) == 1, "expected exactly one run"
    row = rows[0]
    assert row["tier"] == "T2", "the fixed-tier branch is the one under test"
    assert row["crawl_evidence"] is not None, \
        "a fixed-tier CLI run stored no crawl evidence (KI-11)"

    evidence = json.loads(row["crawl_evidence"])
    assert evidence["pages"], "crawl evidence stored, but it records no page"
    assert evidence["start_url"].startswith(site.base_url)
    reached = {page["url"] for page in evidence["pages"]}
    assert any(url.endswith("/about") for url in reached), \
        f"the crawl reached /about but the evidence does not say so: {reached}"

    # The pair KI-11 is about: a populated `crawled_paths` beside a NULL
    # `crawl_evidence` was the observable state of the defect, so both halves
    # are asserted rather than only the one that was missing.
    assert json.loads(row["crawled_paths"]), "crawled_paths is empty"


def test_the_adaptive_cli_branch_still_stores_it(cli_site):
    """The control. `--tier auto` already stored evidence before this fix; if
    the guard above passed because of something that changed for every run,
    this would not be evidence that the fixed-tier branch was repaired.
    """
    site, db_path = cli_site

    rc = cli.main(["audit", "run", "--client", "Acme", "--site", site.base_url + "/",
                   "--tier", "auto", "--dims", "TEC,ONP"])
    assert rc == 0

    rows = _runs(db_path)
    assert len(rows) == 1
    assert rows[0]["crawl_evidence"] is not None
    assert json.loads(rows[0]["crawl_evidence"])["pages"]
