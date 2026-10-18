"""A page's candidates are numbered and counted (item 270, row 5).

Page mode on Structured data: the strip read "3", the checklist listed three
items, and the Fixes block drew four cards. `anatomy_view` fed the checklist
and the strip from open and regressed rows only, and page mode had no "seen
once" companion (`if not page_url`). The entity-model card, the page's one
substantive analysis finding, could not be reached from the picture. A
page's candidates now count as seen once at page scope, and the picture
numbers them after the open rows, saying which they are.
"""

from __future__ import annotations

import json
from pathlib import Path

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import latest_view, repo, runs

HOST = "seen.fixture"
BASE = f"https://{HOST}"
AT = "2026-10-05T00:00:00+00:00"
SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def _brief(conn, site_id: str, run: str, paths: list[str]) -> None:
    rows = [{"check": "CNT/title-overlap", "dimension": "CNT", "check_id": "title-overlap",
             "page": BASE + p, "status": "FAIL", "severity": "medium",
             "evidence": "e", "replacement": "Retitle one of them."} for p in paths]
    runs.store_expert_report(conn, run, "content-cannibalisation", {
        "model": "claude-sonnet-5", "cost": 0.01, "report": "## Assessment\nText.\n",
        "findings": [], "contract": {"status": "read", "part": "x", "rows": rows, "dropped": [],
                                     "assumptions": [], "not_assessable": [], "uncovered": []}})
    runs.record_contract_findings(conn, run, "content-cannibalisation", "claude-sonnet-5", rows)
    runs.recompute_contract_states(conn, site_id, "content-cannibalisation")


def test_page_mode_counts_the_pages_own_candidates(tmp_path):
    conn = connect(tmp_path / "seen.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Seen Co"), HOST)
    run = runs.create_run(conn, site_id, ["CNT"], "T2")
    runs.store_evidence(conn, run, {"start_url": BASE + "/", "pages": [
        {"url": BASE + p, "status": 200, "content_type": "text/html", "title": p}
        for p in ("/", "/hosting/")]})
    runs.mark_complete(conn, run, AT)
    latest_view.rebuild(conn, site_id, "test: two pages")
    _brief(conn, site_id, run, ["/hosting/", "/"])
    states = [s["state"] for s in runs.site_states(conn, site_id)
              if s["source"] == "model-judgement"]
    assert states == ["candidate", "candidate"], states

    def seen(page):
        parts = {c["key"]: c for c in runs.anatomy_view(conn, site_id, page)["categories"]}
        return parts["content"]["seen_once"]["value"]

    assert seen(None) == 2
    # The page's own, not the site's, and not nothing.
    assert seen(BASE + "/") == 1
    conn.close()


def test_the_picture_numbers_a_candidate_after_the_open_rows():
    facts = {"url": BASE + "/", "jsonld_raw": [{"source": "inline", "text": json.dumps(
        {"@context": "https://schema.org", "@type": "Organization", "name": "Seen Co"})}]}
    items = [
        {"check_id": "schema-sameas-misplaced", "dimension": "SCH", "severity": "low",
         "summary": "sameAs on the wrong node", "source": "deterministic", "state": "open"},
        {"check_id": "schema-entity-model", "dimension": "SCH", "severity": "high",
         "summary": "The entity model is incomplete", "source": "model-judgement",
         "state": "candidate", "to_confirm": True},
    ]
    model = runs.schema_graph_payload(facts, items, [], "home")
    by = {f["n"]: f for f in model["findings"]}
    assert by[1]["state"] == "open" and by[1]["to_confirm"] is False, by[1]
    assert by[2]["state"] == "candidate" and by[2]["to_confirm"] is True, by[2]
    assert by[2]["checks"] == ["SCH/schema-entity-model"], by[2]


def test_the_checklist_says_the_state():
    src = (SRC / "schema_graph.tsx").read_text(encoding="utf-8")
    assert '{f.state === "candidate" && (' in src
    assert "{candidateWord(f.to_confirm)}" in src
    view = (Path(runs.__file__)).read_text(encoding="utf-8")
    assert 'c["findings"] + sorted(page_candidates.get("schema", [])' in view


def test_the_switcher_says_seen_once_too():
    src = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    assert "{(c.seen_once?.value ?? 0) > 0 && (" in src
    assert "{note && (c.seen_once?.value ?? 0) > 0 && (" not in src
