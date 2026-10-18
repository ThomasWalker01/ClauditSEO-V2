"""An analysis verdict is not a fault (item 269).

The cannibalisation prompt answers a free `title-overlap` flag it judges
harmless with a PASS-OVERRIDE row ("No consolidation on present evidence").
The parser stores it as a finding, and on twenty22's Content three of them
were drawn as Medium faults with a copy button and counted in ANALYSIS,
PAGES and the parts strip. The part's count leaves them out; the card draws
the verdict as one sentence with no severity and nothing to copy.
"""

from __future__ import annotations

import json
from pathlib import Path

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import latest_view, repo, runs
from clauditseo.persistence.repo import create_id

HOST = "verdict.fixture"
BASE = f"https://{HOST}"
AT = "2026-09-29T00:00:00+00:00"
SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def _finding(conn, run: str, source: str, path: str, evidence: dict, fp: str) -> None:
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
        " affected_urls, fingerprint, created_at, evidence) VALUES (?, ?, 'CNT',"
        " 'title-overlap', 'medium', ?, 'Titles overlap', ?, ?, ?, ?)",
        (create_id(), run, source, json.dumps([BASE + path]), fp, AT, json.dumps(evidence)))


def _brief(conn, site_id: str, run: str, paths: list[str]) -> None:
    """The analysis's rows, stored as a run of the brief stores them."""
    rows = [{"check": "CNT/title-overlap", "dimension": "CNT", "check_id": "title-overlap",
             "page": BASE + p, "status": "PASS-OVERRIDE", "severity": "medium",
             "evidence": "e", "replacement": "No change on present evidence."} for p in paths]
    runs.store_expert_report(conn, run, "content-cannibalisation", {
        "model": "claude-sonnet-5", "cost": 0.01, "report": "## Assessment\nText.\n",
        "findings": [], "contract": {"status": "read", "part": "x", "rows": rows, "dropped": [],
                                     "assumptions": [], "not_assessable": [], "uncovered": []}})
    runs.record_contract_findings(conn, run, "content-cannibalisation", "claude-sonnet-5", rows)
    runs.recompute_contract_states(conn, site_id, "content-cannibalisation")


def test_a_pass_override_is_not_counted_in_the_part(tmp_path):
    conn = connect(tmp_path / "verdict.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Verdict Co"), HOST)
    run = runs.create_run(conn, site_id, ["CNT"], "T2")
    runs.store_evidence(conn, run, {"start_url": BASE + "/", "pages": [
        {"url": BASE + p, "status": 200, "content_type": "text/html", "title": p}
        for p in ("/", "/hosting/")]})
    runs.mark_complete(conn, run, AT)
    with conn:
        _finding(conn, run, "deterministic", "/", {}, "fp-sweep")
    latest_view.rebuild(conn, site_id, "test: one sweep row")
    _brief(conn, site_id, run, ["/hosting/", "/"])
    verdicts = [s for s in runs.site_states(conn, site_id) if s["source"] == "model-judgement"]
    assert [s["brief_status"] for s in verdicts] == ["PASS-OVERRIDE"] * 2, verdicts
    parts = {c["key"]: c for c in runs.anatomy_view(conn, site_id)["categories"]}
    content = parts["content"]
    # The automatic checks' flag counts; the two verdicts do not.
    assert content["total"]["value"] + content["seen_once"]["value"] == 1, (
        content["total"], content["seen_once"])
    conn.close()


def test_the_card_draws_a_verdict_as_one(tmp_path):
    src = SRC.read_text(encoding="utf-8")
    # One rule for "the analysis closed this", read by the table, the Fixes
    # heading and the card.
    assert src.count("export const closedByAnalysis") == 1
    assert 's.brief_status === "PASS-OVERRIDE"' in src
    assert "Analysis closes this: " in src
    assert "automatic checks flagged, analysis overrides" in src
    # No copy button on a verdict.
    # Item 279 (row 5): a card may also copy what it names (a selector).
    # The condition gained a renderer's say (item 272, row 5); a verdict still
    # draws no copy control.
    assert "|| render.copyFrom?.(fix))\n         && !fix.override && (" in src
    # And nothing to confirm: a verdict is not a candidate fault.
    assert "fix.candidate && !closedByAnalysis(fix)" in src
    assert "awaiting && siteId && !closedByAnalysis(fix)" in src


def test_a_content_check_that_does_not_read_this_type_of_page_is_not_a_pass():
    """Item 269, row 2: `/` (home) was stamped "Author: named · Facts: enough
    · Updated: current" by three checks that read articles, and pages with a
    floor, only."""
    from clauditseo.modules import cnt
    assert cnt.not_run_on("home") == ["fact-density", "no-author", "stale"]
    assert cnt.not_run_on("article") == []
    assert cnt.not_run_on("service") == ["no-author"]
    src = SRC.read_text(encoding="utf-8")
    assert "(facts.content_not_run ?? []).includes(check) && !raised.has(check)" in src
    assert "&& !notRead.includes(c)" in src
