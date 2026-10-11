"""The record's order: severity by rank, and what waits for the operator
straight after what came back (item 258, the record audit's AC-01 and the
order half of UX-02).

`site_states` sorted `f.severity` as a string - high, info, low, medium - so on
twenty22 216 info and low rows sat above 337 medium ones under "open", and
every medium group after the first was behind "show 50 more". And the "to
confirm" rows of item 237, in the record's default chip, came last.
"""

from __future__ import annotations

import json
from pathlib import Path

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo.persistence.repo import create_id
from tests.needs_build import needs_build
from tests.test_a11y_rendered import served  # noqa: F401  (module fixture)

RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _plant(conn, site, run, check, severity, state, n):
    fp = f"order-{check}-{n}"
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
        " affected_urls, fingerprint, created_at) VALUES (?, ?, 'TEC', ?, ?, 'deterministic',"
        " 's', ?, ?, '2026-09-01T00:00:00+00:00')",
        (create_id(), run, check, severity, json.dumps([f"https://order.test/{n}"]), fp))
    conn.execute("INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                 " updated_at) VALUES (?, ?, ?, ?, '2026-09-01T00:00:00+00:00')",
                 (site, fp, state, run))
    return fp


def test_severity_is_ranked_not_sorted_as_a_word(tmp_path):
    conn = connect(tmp_path / "order.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "Order Co"), "order.test")
    run = runs.create_run(conn, site, ["TEC"], "T2", scan_scope="site")
    for n, (sev, state) in enumerate([("info", "open"), ("low", "open"), ("medium", "open"),
                                      ("high", "open"), ("medium", "regressed"),
                                      ("info", "regressed"), ("low", "fixed"),
                                      ("critical", "fixed")]):
        _plant(conn, site, run, f"c{n}", sev, state, n)
    conn.commit()
    got = [(s["state"], s["severity"]) for s in runs.site_states(conn, site)]
    assert got == [("regressed", "medium"), ("regressed", "info"),
                   ("open", "high"), ("open", "medium"), ("open", "low"), ("open", "info"),
                   ("fixed", "critical"), ("fixed", "low")], got


def test_what_waits_for_the_operator_comes_after_what_came_back(monkeypatch, tmp_path):
    conn = connect(tmp_path / "order.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "Order Co"), "order.test")
    run = runs.create_run(conn, site, ["TEC"], "T2", scan_scope="site")
    _plant(conn, site, run, "open-high", "high", "open", 1)
    waits = _plant(conn, site, run, "waits", "low", "candidate", 2)
    _plant(conn, site, run, "seen-once", "high", "candidate", 3)
    _plant(conn, site, run, "back", "low", "regressed", 4)
    conn.commit()
    monkeypatch.setattr(runs, "awaiting_confirmation", lambda c, s: {waits})
    got = [s["check_id"] for s in runs.site_states(conn, site)]
    assert got == ["back", "waits", "open-high", "seen-once"], got


@needs_build
def test_the_record_draws_its_groups_in_the_servers_order(served):
    """The pane keeps the order the rows come in (`groupsOf`, first row
    first), so the server's order is what the reader sees."""
    from playwright.sync_api import sync_playwright
    base, ids = served
    conn = connect(Path(ids["db"]))
    conn.row_factory = __import__("sqlite3").Row
    try:
        states = runs.site_states(conn, ids["site"])
    finally:
        conn.close()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page(viewport={"width": 1568, "height": 1100})
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}?tab=all&state=all&group=check", wait_until="load")
            pg.wait_for_selector("tr.group-row", timeout=30_000)
            pg.wait_for_timeout(800)
            drawn = pg.evaluate("""() => [...document.querySelectorAll('tr.group-row')]
              .map((r) => r.querySelector('code').textContent.trim())""")
        finally:
            browser.close()
    first: list[str] = []
    for s in states:
        if s.get("coverage_note"):
            continue
        key = f"{s['dimension']}/{s['check_id']}"
        if key not in first:
            first.append(key)
    assert drawn and drawn == first[:len(drawn)], (drawn[:12], first[:12])
    # And within the open rows the ranks never go back up.
    ranks = [RANK.get((s["severity"] or "").lower(), 4) for s in states
             if s["state"] == "open" and not s.get("coverage_note")]
    assert ranks == sorted(ranks), "open rows are not in severity order"
