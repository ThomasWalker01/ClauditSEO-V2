"""A part counts one per card (item 276).

Where the automatic checks and an analysis both hold a row on one (check,
page), the part page draws one card - `fixesOf` keys a card by the check and
its page - and the part's count read two. On twenty22's Security the chip and
its aria-label said 25 over 13 cards, and the landing's total and the
held-report count carried the difference.
"""

from __future__ import annotations

import pytest

from clauditseo.persistence.runs import _one_per_card


def _row(check, url, source, fp, state="open"):
    return {"check_id": check, "urls": [url], "source": source, "fingerprint": fp,
            "state": state}


def test_a_check_on_a_page_held_by_both_sources_counts_once():
    rows = [_row("csp-weak", "https://s.test/", "model-judgement", "m1"),
            _row("csp-weak", "https://s.test", "deterministic", "d1"),
            _row("csp-weak", "https://s.test/about/", "model-judgement", "m2")]
    got = _one_per_card(rows)
    assert [r["fingerprint"] for r in got] == ["d1", "m2"], got


def test_per_agent_rows_on_one_page_stay_one_each():
    rows = [_row("edge-blocks-ai-ua", "https://s.test/", "deterministic", f"d{i}")
            for i in range(3)]
    assert len(_one_per_card(rows)) == 3


def test_a_regressed_row_keeps_its_state_when_merged():
    rows = [_row("hsts", "https://s.test/", "deterministic", "d1"),
            _row("hsts", "https://s.test/", "model-judgement", "m1", state="regressed")]
    assert [r["state"] for r in _one_per_card(rows)] == ["regressed"]


@pytest.mark.integrity_threshold
def test_the_report_hold_counts_cards_and_not_verdicts(tmp_path):
    """The held client report's "N Critical or High" counted every row: a
    sweep row and the analysis row on its card were two, and an analysis
    verdict (PASS-OVERRIDE) was one more."""
    import json
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import latest_view, repo, runs
    from clauditseo.persistence.repo import create_id
    conn = connect(tmp_path / "hold.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Hold Co"), "hold.test")
    run = runs.create_run(conn, site_id, ["ONP"], "T2")
    runs.store_evidence(conn, run, {"start_url": "https://hold.test/", "pages": [
        {"url": "https://hold.test/", "status": 200, "content_type": "text/html"}]})
    runs.mark_complete(conn, run, "2026-10-03T00:00:00+00:00")

    def add(source, sev, fp, evidence=None, check="title-missing"):
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, fingerprint, created_at, evidence) VALUES (?, ?, 'ONP', ?, ?, ?,"
            " 's', ?, ?, '2026-10-03', ?)",
            (create_id(), run, check, sev, source, json.dumps(["https://hold.test/"]), fp,
             json.dumps(evidence or {})))
    with conn:
        add("deterministic", "high", "d1")
        add("model-judgement", "critical", "m1", {"contract": True, "status": "FAIL"})
        add("model-judgement", "high", "m2", {"contract": True, "status": "PASS-OVERRIDE"},
            check="h1-missing")
    conn.execute("INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                 " updated_at) SELECT ?, fingerprint, 'open', ?, '2026-10-03'"
                 " FROM findings WHERE run_id=?", (site_id, run, run))
    conn.commit()
    got = runs.open_severe(conn, site_id)
    # One card on (title-missing, /), at its worst severity; the verdict is none.
    assert got == {"count": 1, "critical": 1, "high": 0}, got
    conn.close()
