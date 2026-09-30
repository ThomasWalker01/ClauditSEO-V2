"""Item 239 step 4 (amendment 10): an analysis is its newest run, dated by
the crawl it read, and says what the automatic checks have done since.

  - A run's silence clears an analysis row only where that run fetched the
    page the row named: a brief read over twenty22's ONP-only T2, which
    fetched 40 pages of 60, says nothing about the other 20.
  - A row the automatic ledger has cleared on every page it names, after
    the analysis read it, is marked "superseded on <date>".
  - The part's analysis line names the crawl it read where the part's checks
    have been measured since.

Fixture: `test_the_latest_view`'s T1, T3, refresh and ONP-only T2, dated
17, 18, 19 and 23 Sept.
"""

from __future__ import annotations

from clauditseo.persistence import runs
from tests.test_page_facts_read_the_latest_view import _history
from tests.test_the_latest_view import BASE

TOOL = "title-desc"


def _row(check, path):
    return {"check": f"ONP/{check}", "dimension": "ONP", "check_id": check,
            "page": BASE + path, "status": "WARN", "severity": "high", "evidence": "x",
            "replacement": "A replacement of a sensible length for this page, naming it.",
            "note": ""}


def _brief(conn, site, run, rows):
    runs.store_expert_report(conn, run, TOOL, {
        "model": "m-1", "cost": 0.2, "report": "## Title & description", "findings": [],
        "contract": {"status": "read", "part": TOOL, "rows": rows, "dropped": [],
                     "assumptions": [], "not_assessable": [], "uncovered": []}})
    runs.record_contract_findings(conn, run, TOOL, "m-1", rows)
    runs.recompute_contract_states(conn, site, TOOL)


def _brief_state(conn, site, check, path):
    row = conn.execute(
        "SELECT s.state FROM finding_states s JOIN findings f ON f.fingerprint = s.fingerprint"
        " WHERE s.site_id=? AND f.check_id=? AND f.source='model-judgement'"
        " AND f.affected_urls=? LIMIT 1", (site, check, f'["{BASE}{path}"]')).fetchone()
    return row["state"] if row else None


def test_a_run_clears_an_analysis_row_only_on_a_page_it_fetched(tmp_path):
    conn, site, ids = _history(tmp_path, "w")
    run = {v: k for k, v in ids.items()}
    _brief(conn, site, run["T3"], [_row("title-length", "/p3/"), _row("title-length", "/p50/")])
    assert _brief_state(conn, site, "title-length", "/p50/") == "candidate"
    _brief(conn, site, run["T2"], [])
    # T2 fetched /p3/ and did not repeat it: a first sighting, gone.
    assert _brief_state(conn, site, "title-length", "/p3/") is None
    # T2 never fetched /p50/: its silence is not evidence.
    assert _brief_state(conn, site, "title-length", "/p50/") == "candidate"


def test_a_row_the_automatic_checks_cleared_since_says_when(tmp_path):
    conn, site, ids = _history(tmp_path, "s")
    run = {v: k for k, v in ids.items()}
    sweep = {s["check_id"]: s for s in runs.site_states(conn, site)
             if s["source"] == "deterministic" and s["check_id"] == "title-missing"}
    assert sweep["title-missing"]["state"] == "fixed", sweep     # T2 fetched /p1/
    _brief(conn, site, run["T3"], [_row("title-missing", "/p1/"), _row("title-missing", "/p2/")])
    rows = {s["affected_urls"][0]: s for s in runs.site_states(conn, site)
            if s["source"] == "model-judgement"}
    assert (rows[BASE + "/p1/"]["superseded_on"] or "").startswith("2026-09-23"), rows[BASE + "/p1/"]
    assert rows[BASE + "/p2/"]["superseded_on"] is None           # nothing cleared it


def test_the_part_names_the_crawl_its_analysis_read(tmp_path):
    conn, site, ids = _history(tmp_path, "c")
    run = {v: k for k, v in ids.items()}
    _brief(conn, site, run["T3"], [_row("title-length", "/p50/")])
    part = next(c for c in runs.anatomy_view(conn, site)["categories"]
                if (c.get("brief_run") or {}).get("tool") == TOOL)
    br = part["brief_run"]
    assert br["crawl_at"].startswith("2026-09-18"), br               # T3's crawl
    assert (br["checked_since"] or "").startswith("2026-09-23"), br  # ONP: the T2
