"""The client report is a frozen copy of The Latest View (item 239 step 7,
the operator's ruling of 2026-09-24: "the report can run independently, then
just update a complete record that is 'The Latest View'"; "the client report
is a frozen copy of The Latest View taken at generation, stored with the
report, with every section's dates").

  - The document is the site's record as of a day: its score is the current
    audit's composite, named and dated, whichever audit the request named;
    its findings are the ledger's open ones, each dated by the audit that
    last measured it; a finding assessed since is not listed.
  - The copy is stored with the report - composite, blocks, analyses, pages,
    findings, each with its run and date, and the hold - and the document it
    was built into does not change when the record moves on.
  - A brief appears from its newest run on the site, dated.

The hold over that copy is `test_the_report_cannot_be_generated_with_an_
unassessed_critical_or_high`'s subject.
"""

from __future__ import annotations

import json

from clauditseo.persistence import latest_view, runs
from clauditseo.reporting import generate as gen
from tests.test_reporting_g7 import db_with_runs  # noqa: F401  (fixture)
from tests.test_the_report_cannot_be_generated_with_an_unassessed_critical_or_high import (
    _plant_high, _site)


def _stored(conn, report_id):
    row = conn.execute("SELECT latest_view_copy, path FROM reports WHERE id=?",
                       (report_id,)).fetchone()
    return json.loads(row["latest_view_copy"]), row["path"]


def test_a_report_asked_of_an_older_audit_is_the_sites_record(db_with_runs):
    conn, run_ids = db_with_runs
    older = run_ids[0]
    current = latest_view._get(conn, _site(conn, older), "composite", "current")
    assert current and current["run_id"] != older, "precondition: the older audit is not current"
    md = gen.generate(conn, "run", "client", [older])["markdown"]
    assert "the site's record as of that day" in md, md[:600]
    assert f"score from audit `{current['run_id']}`" in md, md[:600]
    assert f"run `{older}`" not in md


def test_the_findings_are_the_ledgers_open_ones_each_dated(db_with_runs):
    conn, run_ids = db_with_runs
    older = run_ids[0]
    _plant_high(conn, older)                      # raised by the older audit only
    report = gen.generate(conn, "run", "internal", [run_ids[-1]])
    assert "robots-missing" in report["markdown"], "an open finding of an older audit was left out"
    copy, _path = _stored(conn, report["id"])
    planted = [f for f in copy["findings"] if f["check_id"] == "robots-missing"]
    assert planted and planted[0]["run_id"] == older and planted[0]["measured_at"], planted
    assert "Each finding below is dated by the audit that last measured it" in report["markdown"]
    # Assessed, it leaves the record, and the next copy.
    runs.set_state(conn, _site(conn, older), planted[0]["fingerprint"], "accepted-risk")
    again = gen.generate(conn, "run", "internal", [run_ids[-1]])
    assert "robots-missing" not in again["markdown"]


def test_the_copy_is_stored_and_the_document_does_not_move_with_the_record(db_with_runs):
    conn, run_ids = db_with_runs
    report = gen.generate(conn, "run", "client", [run_ids[-1]])
    copy, path = _stored(conn, report["id"])
    for key in ("taken_at", "composite", "blocks", "analyses", "pages", "findings", "hold"):
        assert key in copy, key
    assert copy["composite"]["run_id"] and copy["blocks"], copy.keys()
    assert all(f["measured_at"] and f["run_id"] for f in copy["findings"])
    before = open(path, encoding="utf-8").read()
    _plant_high(conn, run_ids[0])                 # the record moves on
    assert open(path, encoding="utf-8").read() == before
    assert _stored(conn, report["id"])[0] == copy


def test_a_brief_appears_from_its_newest_run(db_with_runs):
    conn, run_ids = db_with_runs
    older, newer = run_ids[0], run_ids[-1]
    for run_id, words in ((older, "An older reading of the sitemap."),
                          (newer, "A newer reading of the sitemap.")):
        finding = {"code": "sitemap-coverage", "severity": "medium", "summary": words}
        runs.store_expert_report(conn, run_id, "crawl",
                                 {"model": "m-1", "report": "## SUMMARY", "findings": [finding]})
        runs.record_expert_findings(conn, run_id, "crawl", "m-1", [finding])
    md = gen.generate(conn, "run", "internal", [older])["markdown"]
    briefs = md.split("## Specialist briefs", 1)[1]
    assert "A newer reading of the sitemap." in briefs
    assert "An older reading of the sitemap." not in briefs
    assert "· analysed " in briefs, "the brief's heading does not say when it ran"
