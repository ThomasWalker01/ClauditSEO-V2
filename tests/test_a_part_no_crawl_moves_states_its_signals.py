"""A part no crawl moves states its signals (item 278, row 8).

Backlinks' header stated crawl coverage ("45 pages audited of 74 known") for
a part whose rail says it reads the domain, and the one coverage figure that
describes it - signals measured - appeared nowhere. Its PAGES column read "0"
on every row, which reads as "affects nothing". The header now states the
signals, from the not-assessed row's own evidence, and the column is gone
where the part reads no page.
"""

from __future__ import annotations

import json
from pathlib import Path

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo.persistence.repo import create_id

HOST = "signals.fixture"
AT = "2026-10-06T00:00:00+00:00"
SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "anatomy.tsx"


def test_the_signals_are_read_from_the_not_assessed_row(tmp_path):
    conn = connect(tmp_path / "signals.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Signals Co"), HOST)
    assert runs.signal_coverage_payload(conn, site_id)["measured"] == [
        "referring domains", "anchor text distribution"]
    run = runs.create_run(conn, site_id, ["OFP"], "T2")
    runs.store_evidence(conn, run, {"start_url": f"https://{HOST}/", "pages": []})
    runs.mark_complete(conn, run, AT)
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, fingerprint, created_at, evidence) VALUES (?, ?, 'OFP',"
            " 'backlinks-not-assessed', 'info', 'deterministic', 'Not assessed: anchors', '[]',"
            " 'fp-ofp', ?, ?)",
            (create_id(), run, AT, json.dumps({"unmeasured": ["anchor text distribution"],
                                               "providers_answering": ["moz"]})))
        conn.execute("INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                     " updated_at) VALUES (?, 'fp-ofp', 'open', ?, ?)", (site_id, run, AT))
    got = runs.signal_coverage_payload(conn, site_id)
    assert got == {"total": 2, "measured": ["referring domains"],
                   "unmeasured": ["anchor text distribution"], "providers": ["moz"],
                   "needs": []}, got
    conn.close()


def test_the_header_and_the_table_follow_it():
    src = SRC.read_text(encoding="utf-8")
    assert "current?.refresh?.crawl_blind && current.signal_coverage ? (" in src
    assert '{current.refresh?.per_page !== false && <th className="num">Pages</th>}' in src
    assert src.count("current.refresh?.per_page !== false && (") == 2
