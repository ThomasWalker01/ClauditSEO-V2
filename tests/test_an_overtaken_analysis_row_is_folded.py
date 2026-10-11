"""An analysis row the automatic checks overtook is folded, not counted
(item 270).

Item 239 dated an analysis row the sweep has since cleared on every page it
names ("superseded on ..."), and the card said so - but it stayed a card, a
count in AUTOMATIC/ANALYSIS/PAGES and a count in the strip. On twenty22's
Structured data that was 43 `schema-orphan-instance` rows behind a "show all
43" button, over a check the automatic checks raised once.
"""

from __future__ import annotations

import json
from pathlib import Path

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import latest_view, repo, runs
from clauditseo.persistence.repo import create_id

HOST = "overtaken.fixture"
BASE = f"https://{HOST}"
FIRST, SECOND = "2026-09-18T00:00:00+00:00", "2026-09-29T00:00:00+00:00"
SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def _run(conn, site_id: str, at: str) -> str:
    run = runs.create_run(conn, site_id, ["ONP"], "T2")
    runs.store_evidence(conn, run, {"start_url": BASE + "/", "pages": [
        {"url": BASE + p, "status": 200, "content_type": "text/html", "title": p}
        for p in ("/", "/a/")]})
    runs.mark_complete(conn, run, at)
    conn.execute("UPDATE audit_runs SET started_at=?, finished_at=? WHERE id=?", (at, at, run))
    conn.commit()
    return run


def _finding(conn, run: str, source: str, fp: str, evidence: dict) -> None:
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
        " affected_urls, fingerprint, created_at, evidence) VALUES (?, ?, 'ONP',"
        " 'schema-orphan-instance', 'medium', ?, 'An orphan node', ?, ?, ?, ?)",
        (create_id(), run, source, json.dumps([BASE + "/a/"]), fp, FIRST, json.dumps(evidence)))


def _brief(conn, site_id: str, run: str, paths: list[str]) -> None:
    """The analysis's rows, stored as a run of the brief stores them."""
    rows = [{"check": "ONP/schema-orphan-instance", "dimension": "ONP", "check_id": "schema-orphan-instance",
             "page": BASE + p, "status": "FAIL", "severity": "medium",
             "evidence": "e", "replacement": "No change on present evidence."} for p in paths]
    runs.store_expert_report(conn, run, "schema", {
        "model": "claude-sonnet-5", "cost": 0.01, "report": "## Assessment\nText.\n",
        "findings": [], "contract": {"status": "read", "part": "x", "rows": rows, "dropped": [],
                                     "assumptions": [], "not_assessable": [], "uncovered": []}})
    runs.record_contract_findings(conn, run, "schema", "claude-sonnet-5", rows)
    runs.recompute_contract_states(conn, site_id, "schema")


def test_an_overtaken_analysis_row_is_not_counted_in_the_part(tmp_path):
    conn = connect(tmp_path / "overtaken.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Overtaken Co"), HOST)
    first = _run(conn, site_id, FIRST)
    with conn:
        _finding(conn, first, "deterministic", "fp-sweep", {})
    _brief(conn, site_id, first, ["/a/"])
    _run(conn, site_id, SECOND)          # read /a/ again and raised nothing
    latest_view.rebuild(conn, site_id, "test: the sweep cleared what the analysis read")
    model = [s for s in runs.site_states(conn, site_id) if s["source"] == "model-judgement"]
    assert len(model) == 1 and model[0]["superseded_on"], model
    parts = {c["key"]: c for c in runs.anatomy_view(conn, site_id)["categories"]}
    schema = parts[__import__("clauditseo.anatomy", fromlist=["x"]).categorise(
        "schema-orphan-instance", "ONP")]
    assert schema["total"]["value"] == 0, schema["total"]
    conn.close()


def test_the_part_page_folds_overtaken_rows_into_one_line_per_check():
    src = SRC.read_text(encoding="utf-8")
    assert src.count("export const overtaken") == 1
    assert "f.checkId === checkId && !overtaken(f)" in src
    assert "!f.coverageNote && !overtaken(f)" in src
    assert 'className="muted part-fix-overtaken"' in src
