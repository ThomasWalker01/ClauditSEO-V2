"""Item 239 step 3: a page's facts are read from the Latest View.

`page_facts` picked each field from the newest run that RECORDED it. A run's
evidence holds every field of every page it fetched, whatever it measured, so
twenty22's ONP-only T2 supplied TEC's status and an unweighed image record.
Each field now comes from the newest run that MEASURED it (the write rules,
`latest_view.PAGE_FIELDS`), dated; the image record is the markup of the
newest ONP reading joined to the weights of the newest run that weighed them;
crawl-relative facts come from the reference crawl.

Fixture: `test_the_latest_view`'s T1, T3 (weighed), refresh, ONP-only T2.
"""

from __future__ import annotations

from clauditseo.persistence import latest_view, runs
from tests.test_the_latest_view import BASE, _history as _made, _run


def _history(tmp_path, name, with_t2=True):
    """The fixture, with the days between its runs that a real history has:
    its runs finish in one second, and "the newest" of a tie is no answer."""
    conn, site, ids = _made(tmp_path, name, with_t2)
    day = {"T1": "17", "T3": "18", "refresh": "19", "T2": "23"}
    for rid, label in ids.items():
        conn.execute("UPDATE audit_runs SET started_at=?, finished_at=? WHERE id=?",
                     (f"2026-09-{day[label]}T00:00:00+00:00",) * 2 + (rid,))
    conn.commit()
    latest_view.rebuild(conn, site, "test")
    return conn, site, ids


def test_each_field_is_the_run_that_measured_it(tmp_path):
    conn, site, ids = _history(tmp_path, "f")
    run = {v: k for k, v in ids.items()}
    facts = runs.page_facts(conn, site, BASE + "/p3/")
    assert facts["title"].startswith("T2 "), facts["title"]            # ONP: the T2
    assert facts["from_run"] == run["T2"]
    assert "status" in facts["dated"] and "title" not in facts["dated"], facts["dated"]
    weighed = facts["image_inventory"]
    assert weighed and weighed[0]["weight_kb"] == 300, weighed          # weights: T3
    assert facts["observations"] == 2, facts["observations"]


def test_a_page_only_the_t3_read_is_the_t3s(tmp_path):
    conn, site, ids = _history(tmp_path, "g")
    facts = runs.page_facts(conn, site, BASE + "/p50/")
    assert facts["title"].startswith("T3 ") and not facts["dated"], facts["dated"]


def test_a_page_that_answered_an_error_keeps_its_status(tmp_path):
    conn, site, ids = _history(tmp_path, "h", with_t2=False)
    run = runs.create_run(conn, site, ["TEC"], "T2")
    runs.store_evidence(conn, run, {"start_url": BASE + "/", "pages": [
        {"url": BASE + "/gone/", "status": 404, "content_type": "text/html"}]})
    runs.mark_complete(conn, run, "2099-01-01T00:00:00+00:00")
    facts = runs.page_facts(conn, site, BASE + "/gone/")
    assert facts and facts["status"] == 404, facts
    assert latest_view.field_run(conn, site, BASE + "/gone/", "title") is None


def test_an_import_with_no_dimensions_still_writes_the_facts_it_carries(tmp_path):
    conn, site, ids = _history(tmp_path, "i", with_t2=False)
    run = runs.create_run(conn, site, [], "T3")
    runs.store_evidence(conn, run, {"start_url": BASE + "/", "pages": [
        {"url": BASE + "/imported/", "status": 200, "content_type": "text/html",
         "title": "Imported"}]})
    runs.mark_complete(conn, run, "2099-01-01T00:00:00+00:00")
    assert runs.page_facts(conn, site, BASE + "/imported/")["title"] == "Imported"
    _ = _run
