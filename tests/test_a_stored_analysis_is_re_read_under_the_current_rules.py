"""A stored analysis is re-read under the rules as they now stand, without a
model call (item 249, step 1).

Round-2 screen audits, cross-cutting item 2 of 5. Items 216, 217, 228, 231
and 234 each changed a prompt or `analysts/contract.py`, and the reader's
rules run only when an answer is parsed - once per purchase. So the analyses
of 23 Sept still showed the rows those items were filed to remove: the
`/web-design1/` 301 with its `copy change` button, four per-template Speed
rows filed on `/`.

The model's own answer has been kept beside each analysis since migration
0055. `reparse_report` runs the whole reader over it again.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from clauditseo.analysts import expert
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Site
from clauditseo.persistence import repo, runs
from clauditseo.persistence.repo import create_id, now_iso

BASE = "https://t.fixture"
PAGES = [BASE + "/", BASE + "/web-design1/", BASE + "/seo/on-page/a/", BASE + "/seo/on-page/b/"]
SITE = Site(domain="t.fixture")


def _fence(rows: list[dict]) -> str:
    return ("```json\n" + json.dumps({"rows": rows}) + "\n```\n\n"
            "### Assessment\nAs the model wrote it.\n")


URL_ROW = {"check": "TEC/url-slug-not-descriptive", "page": "/web-design1/", "status": "FAIL",
           "severity": "MEDIUM", "evidence": "the slug ends in a numeral",
           "replacement": "/web-design/ — 301 /web-design1/ → /web-design/; update 45 internal links",
           "kind": "rename", "note": ""}

#: As the reader of 23 Sept kept it: the rename and its copy intact.
URL_STORED = {**URL_ROW, "dimension": "TEC", "check_id": "url-slug-not-descriptive",
              "page": BASE + "/web-design1/", "severity": "medium"}


@pytest.fixture()
def stored(tmp_path, monkeypatch):
    """A run with four pages, the sweep's own slug finding on /web-design1/,
    and a URLs analysis stored the way the old reader left it, raw answer
    beside it."""
    conn = connect(tmp_path / "reread.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "T Co"), "t.fixture")
    run_id = runs.create_run(conn, site_id, ["TEC", "PRF"], "T2", scan_scope="site")
    runs.store_evidence(conn, run_id, {"pages": [{"url": u, "status": 200} for u in PAGES]})
    runs.mark_complete(conn, run_id, now_iso())
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, fingerprint, created_at) VALUES (?, ?, 'TEC', 'url-slug-not-descriptive',"
            " 'medium', 'deterministic', 'slug', ?, 'sweep-slug', ?)",
            (create_id(), run_id, json.dumps([BASE + "/web-design1/"]), now_iso()))
    # The context the reader is handed is the analysis's own; what it holds
    # is not what these clauses are about.
    monkeypatch.setattr(expert, "build_context", lambda *a, **k: {"LOCALE": "en-AU"})

    def store(tool: str, rows_then: list[dict], raw: str | None) -> None:
        runs.store_expert_report(conn, run_id, tool, {
            "model": "stub", "report": "as stored", "findings": [], "raw": raw,
            "contract": {"status": "read", "part": tool, "rows": rows_then, "dropped": [],
                         "assumptions": [], "not_assessable": [], "uncovered": []}})
        runs.record_contract_findings(conn, run_id, tool, "stub", rows_then)
        runs.recompute_contract_states(conn, site_id, tool)

    yield conn, site_id, run_id, store
    conn.close()


def test_a_301_from_the_wrong_check_re_reads_to_a_convention_with_nothing_to_copy(stored):
    conn, site_id, run_id, store = stored
    store("urls", [URL_STORED], _fence([URL_ROW]))

    got = expert.reparse_report(conn, run_id, "urls", SITE)
    assert got["source"] == "raw"
    rows = got["after"]["rows"]
    assert len(rows) == 1, (rows, got["after"]["dropped"])
    assert rows[0]["kind"] == "convention" and rows[0]["replacement"] is None, rows[0]
    # The stored contract and the readable report are the re-read ones.
    kept = runs.expert_report(conn, run_id, "urls")
    assert kept["contract"]["reparsed_from"] == "raw"
    assert kept["contract"]["rows"][0]["replacement"] is None
    assert "As the model wrote it." in kept["report"]
    # And nothing in the record still offers the 301 to copy.
    for (ev,) in conn.execute("SELECT evidence FROM findings WHERE run_id=?"
                              " AND source='model-judgement'", (run_id,)):
        assert "301" not in (ev or ""), ev

    changes = expert.contract_changes(got["before"], got["after"])
    assert changes["rows"] == (1, 1) and len(changes["changed"]) == 1, changes


def test_a_second_re_read_changes_nothing(stored):
    conn, site_id, run_id, store = stored
    store("urls", [URL_STORED], _fence([URL_ROW]))
    expert.reparse_report(conn, run_id, "urls", SITE)
    again = expert.reparse_report(conn, run_id, "urls", SITE)
    changes = expert.contract_changes(again["before"], again["after"])
    assert not (changes["gone"] or changes["new"] or changes["changed"]), changes


def test_a_template_row_filed_on_the_home_page_is_re_filed_on_its_template(stored):
    """Item 217's rule, reaching a row stored before it: `page: null` with a
    template was filed on `/`."""
    conn, site_id, run_id, store = stored
    raw_row = {"check": "PRF/critical-path", "page": None, "template": "/seo/on-page/<slug>/",
               "status": "FAIL", "severity": "MEDIUM", "evidence": "render-blocking CSS",
               "replacement": "inline the critical CSS", "note": ""}
    then = {**raw_row, "dimension": "PRF", "check_id": "critical-path", "page": BASE + "/",
            "severity": "medium"}
    store("speed", [then], _fence([raw_row]))

    got = expert.reparse_report(conn, run_id, "speed", SITE)
    assert got["source"] == "raw"
    pages = [r["page"] for r in got["after"]["rows"]]
    assert pages and all(p != BASE + "/" for p in pages), (pages, got["after"]["dropped"])
    assert all("/seo/on-page/" in p for p in pages), pages


def test_without_the_models_answer_the_stored_rows_are_re_judged(stored):
    """A row from before migration 0055 has no raw answer: `enforce` over
    the rows the old reader kept is what there is."""
    conn, site_id, run_id, store = stored
    store("urls", [URL_STORED], None)
    got = expert.reparse_report(conn, run_id, "urls", SITE)
    assert got["source"] == "rows"
    assert got["after"]["reparsed"] is True


def test_the_site_command_re_reads_every_analysis_and_rebuilds_the_record(stored, monkeypatch, capsys):
    conn, site_id, run_id, store = stored
    store("urls", [URL_STORED], _fence([URL_ROW]))

    results = expert.reparse_site(conn, site_id, SITE)
    assert [(r["tool_id"], r["source"]) for r in results] == [("urls", "raw")]
    reason = conn.execute("SELECT reason FROM latest_view_log WHERE site_id=?"
                          " ORDER BY rowid DESC LIMIT 1", (site_id,)).fetchone()
    assert reason and "re-read under the current rules" in reason[0], reason

    # The command, on the same database.
    from clauditseo import cli

    class _Cfg:
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]

    from pathlib import Path
    _Cfg.db_path = Path(_Cfg.db_path)
    monkeypatch.setattr(cli, "settings", lambda: _Cfg)
    assert cli.main(["reparse-contracts", "--site", "t.fixture", "--verbose"]) == 0
    out = capsys.readouterr().out
    assert "t.fixture: 1 stored analyses re-read" in out, out
    assert "urls" in out and "unchanged" in out, out
    assert cli.main(["reparse-contracts", "--site", "nowhere.fixture"]) == 2
