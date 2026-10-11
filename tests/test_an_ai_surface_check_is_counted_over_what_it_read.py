"""An AI-surface check is counted over what it read (item 267, row 3).

The crawler access test fetches the home page and a couple of probe pages as
each agent; `content-behind-js` reads the pages the rendered pass visited; and
three rows are about the site as one subject. The checks table counted every
one of them "of 45 pages crawled": a firewall block on 3 of 3 probed URLs read
"3 of 45", and `llms-txt-missing`, which names no page, drew a 0 - the zero the
renderer itself says reads as clean.
"""

from __future__ import annotations

import json
from pathlib import Path

from clauditseo.db.connection import connect
from clauditseo.persistence import latest_view, repo, runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_the_part_carries_each_checks_own_population(tmp_path):
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    db = tmp_path / "clauditseo.db"
    app = create_app(db_path=db)
    conn = connect(db)
    op = repo.ensure_default_operator(conn, "AIS")
    site_id = repo.create_site(conn, repo.create_client(conn, op, "AIS Co"), "x.test")
    probed = ["https://x.test/", "https://x.test/a/", "https://x.test/b/"]
    ev = {"start_url": "https://x.test/",
          "pages": [{"url": f"https://x.test/p{i}/", "status": 200} for i in range(10)],
          "ua_matrix": [{"agent": "GPTBot", "bodies": {u: {} for u in probed}},
                        {"agent": "ClaudeBot", "bodies": {probed[0]: {}}}]}
    run_id = runs.create_run(conn, site_id, ["AIS", "A11Y"], "T2")
    conn.execute("UPDATE audit_runs SET status='complete', crawl_evidence=?, started_at=?,"
                 " finished_at=? WHERE id=?", (json.dumps(ev), "2026-10-02T03:57:00+00:00",
                                               "2026-10-02T03:57:00+00:00", run_id))
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
        " affected_urls, fingerprint, created_at, evidence) VALUES ('f1', ?, 'A11Y',"
        " 'axe-sampled', 'info', 'deterministic', 's', '[]', 'fp1', '2026-10-02', ?)",
        (run_id, json.dumps({"text_blocks": {"https://x.test/p1/": [], "https://x.test/p2/": []}})))
    conn.commit()
    latest_view.rebuild(conn, site_id, "test: one audit with a crawler access test")
    conn.close()
    with TestClient(app) as http:
        body = http.get(f"/api/sites/{site_id}/anatomy").json()
    ais = next(c for c in body["categories"] if c["key"] == "ai-surface")
    s = ais["samples"]
    assert s["edge-blocks-ai-ua"] == {"n": 3, "basis": "probed"}, s
    assert s["ua-sensitive"] == {"n": 3, "basis": "probed"}, s
    assert s["content-behind-js"] == {"n": 2, "basis": "rendered"}, s
    assert s["llms-txt-missing"] == {"n": None, "basis": "site"}, s


def test_the_table_reads_the_population_and_draws_site_for_a_site_row():
    src = SRC.read_text(encoding="utf-8")
    assert "own?.n ? { n: own.n, basis: own.basis }" in src
    assert 'r.siteRow ? <span className="muted">site</span>' in src
    assert '"URL the crawler access test probed"' in src
