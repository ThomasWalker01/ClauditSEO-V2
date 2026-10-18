"""An analysis describes the crawl it was handed, and the site keeps moving.

Twenty-three written analyses all read the 12 August audit while three newer
ones existed, and nothing on the screen said so. An auditor quoting one of
them can put a finding in front of a client that a later audit has already
closed — the same failure as the sitemap-coverage bug, arriving through a
different door.

It had already happened by the time it was noticed: a review of this app cited
accessibility at "10.9% of composite weight", which was true of the superseded
run and false of every run since — the weight is now zero. The staleness bug
produced a wrong number in the document reporting on it.

Also here: why a cost is missing, which is a different question from whether
one is.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs


@pytest.fixture
def site(tmp_path):
    conn = connect(tmp_path / "cur.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    return conn, site_id


def _run(conn, site_id, when: str) -> str:
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    conn.execute("UPDATE audit_runs SET status='complete', started_at=?,"
                 " composite_score=90 WHERE id=?", (when, run_id))
    conn.commit()
    return run_id


def _analysis(conn, run_id, tool="crawl", cost=None):
    runs.store_expert_report(conn, run_id, tool, {
        "model": "m", "report": "r", "tokens": 100, "cost": cost,
        "findings": [{"severity": "high", "summary": "x"}]})


def test_an_analysis_on_the_newest_audit_is_not_marked(site):
    conn, site_id = site
    _analysis(conn, _run(conn, site_id, "2026-08-13T10:00:00"))
    out = runs.site_reports(conn, site_id)
    assert out["stale_analyses"] == 0
    assert out["reports"][0]["audits_since"] == 0
    assert out["reports"][0]["is_latest"] is True


def test_an_analysis_counts_the_audits_that_came_after_it(site):
    """Counted, not flagged: "superseded" is not something an operator can
    act on, but "three audits since" is — one is a re-read, five a rewrite."""
    conn, site_id = site
    first = _run(conn, site_id, "2026-08-12T10:00:00")
    _analysis(conn, first)
    for day in ("13", "14", "15"):
        _run(conn, site_id, f"2026-08-{day}T10:00:00")

    out = runs.site_reports(conn, site_id)
    assert out["stale_analyses"] == 1
    row = out["reports"][0]
    assert row["audits_since"] == 3 and row["is_latest"] is False


def test_the_headline_is_computed_once_server_side(site):
    """Two screens deriving it from the rows could derive it differently."""
    conn, site_id = site
    old = _run(conn, site_id, "2026-08-12T10:00:00")
    _analysis(conn, old, "crawl")
    _analysis(conn, old, "onpage-hygiene")
    new = _run(conn, site_id, "2026-08-14T10:00:00")
    _analysis(conn, new, "content-brief")

    out = runs.site_reports(conn, site_id)
    assert out["stale_analyses"] == 2, "two old, one current"
    assert out["newest_run_id"] == new


# --- why a cost is missing --------------------------------------------------

def test_no_price_anywhere_reads_as_no_rate_set(site):
    conn, site_id = site
    _analysis(conn, _run(conn, site_id, "2026-08-13T10:00:00"))
    out = runs.site_reports(conn, site_id)
    assert out["rate_is_set"] is False
    assert out["total_cost"] is None


def test_a_price_exists_so_the_absence_is_historical_not_configuration(site):
    """The false sentence. The screen said "no dollar rate set" while rates
    were set for sixteen models and Home was showing $0.70 from the entries
    that do carry a cost — two screens reading as contradictory about money
    while both were right about their own rows."""
    from clauditseo.persistence.repo import now_iso

    conn, site_id = site
    conn.execute("INSERT INTO model_prices (model, input_usd, output_usd,"
                 " entered_at, source) VALUES ('m', 3, 15, ?, 'test')",
                 (now_iso(),))
    conn.commit()
    _analysis(conn, _run(conn, site_id, "2026-08-13T10:00:00"), cost=None)

    out = runs.site_reports(conn, site_id)
    assert out["rate_is_set"] is True, "a rate IS set"
    assert out["total_cost"] is None, "but this analysis carries no cost"
    assert out["unpriced"] == 1


def test_a_priced_analysis_totals_normally(site):
    from clauditseo.persistence.repo import now_iso

    conn, site_id = site
    conn.execute("INSERT INTO model_prices (model, input_usd, output_usd,"
                 " entered_at, source) VALUES ('m', 3, 15, ?, 'test')",
                 (now_iso(),))
    conn.commit()
    _analysis(conn, _run(conn, site_id, "2026-08-13T10:00:00"), cost=0.25)
    out = runs.site_reports(conn, site_id)
    assert out["total_cost"] == 0.25 and out["unpriced"] == 0


# --- the deliverable itself -------------------------------------------------

def test_a_generated_deliverable_can_be_listed_and_read_back(site, tmp_path):
    """Two reports existed on disk and were recorded in the database, and
    nothing listed them: the client rail read "Client report ✓ 2 generated"
    while neither file was reachable from the app that wrote it. A
    deliverable you cannot open is indistinguishable from one that was never
    produced — and it is the artefact the whole run exists to create."""
    conn, site_id = site
    run_id = _run(conn, site_id, "2026-08-13T10:00:00")
    path = tmp_path / "report.md"
    path.write_text("# SEO audit report\n\nBody.\n", encoding="utf-8")
    conn.execute("INSERT INTO reports (id, site_id, run_ids, template,"
                 " audience, path, created_at) VALUES ('r1', ?, ?, 'run',"
                 " 'client', ?, '2026-08-13T11:00:00')",
                 (site_id, json.dumps([run_id]), str(path)))
    conn.commit()

    listed = runs.client_reports(conn, site_id)
    assert [r["id"] for r in listed] == ["r1"]
    assert listed[0]["on_disk"] is True and listed[0]["bytes"] > 0

    got = runs.client_report(conn, "r1")
    assert got["markdown"].startswith("# SEO audit report")
    assert got["run_ids"] == [run_id]


def test_a_recorded_report_whose_file_is_gone_says_so(site, tmp_path):
    """Recorded and present are different states. Regenerating silently would
    hand back a document that is not the one delivered to the client."""
    conn, site_id = site
    conn.execute("INSERT INTO reports (id, site_id, run_ids, template,"
                 " audience, path, created_at) VALUES ('r2', ?, '[]', 'run',"
                 " 'client', ?, '2026-08-13T11:00:00')",
                 (site_id, str(tmp_path / "deleted.md")))
    conn.commit()

    assert runs.client_reports(conn, site_id)[0]["on_disk"] is False
    got = runs.client_report(conn, "r2")
    assert got["markdown"] is None
    assert "no longer on disk" in got["reason"]


def test_an_unknown_report_is_absent_rather_than_empty(site):
    conn, _site_id = site
    assert runs.client_report(conn, "nope") is None


# --- deliverables go stale two different ways ---------------------------------
#
# The analyses table has counted "N audits since" for a while. The client
# deliverable — the artefact that actually leaves the building — carried no
# such mark, which is the wrong way round. And a document can be out of date
# without the site having moved at all: six stored reports read "Title
# duplicate on 2 pages" above a list of thirteen URLs long after the renderer
# stopped producing that, and nothing on the screen could tell them apart
# from a correct one.


def _deliverable(conn, site_id, report_id, run_ids, path, *, renderer=None):
    conn.execute("INSERT INTO reports (id, site_id, run_ids, template,"
                 " audience, path, created_at, renderer_version)"
                 " VALUES (?, ?, ?, 'run', 'client', ?, ?, ?)",
                 (report_id, site_id, json.dumps(run_ids), str(path),
                  "2026-08-13T11:00:00", renderer))
    conn.commit()


def test_a_deliverable_on_the_newest_audit_is_not_marked(site, tmp_path):
    from clauditseo.reporting.render import RENDERER_VERSION
    conn, site_id = site
    run_id = _run(conn, site_id, "2026-08-13T10:00:00")
    path = tmp_path / "d.md"; path.write_text("x", encoding="utf-8")
    _deliverable(conn, site_id, "r1", [run_id], path, renderer=RENDERER_VERSION)

    row = runs.client_reports(conn, site_id)[0]
    assert row["audits_since"] == 0
    assert row["renderer"] == "current"


def test_a_deliverable_counts_the_audits_that_came_after_it(site, tmp_path):
    conn, site_id = site
    first = _run(conn, site_id, "2026-08-12T10:00:00")
    path = tmp_path / "d.md"; path.write_text("x", encoding="utf-8")
    _deliverable(conn, site_id, "r1", [first], path)
    for day in ("13", "14", "15"):
        _run(conn, site_id, f"2026-08-{day}T10:00:00")

    assert runs.client_reports(conn, site_id)[0]["audits_since"] == 3


def test_a_report_written_before_tracking_is_unknown_not_current(site, tmp_path):
    """The distinction the whole column exists for.

    Reading a missing version as "current" would leave exactly the document
    this is meant to catch sitting in the list looking fine.
    """
    conn, site_id = site
    run_id = _run(conn, site_id, "2026-08-13T10:00:00")
    path = tmp_path / "d.md"; path.write_text("x", encoding="utf-8")
    _deliverable(conn, site_id, "r1", [run_id], path, renderer=None)

    assert runs.client_reports(conn, site_id)[0]["renderer"] == "unknown"


def test_a_report_from_an_older_renderer_is_superseded(site, tmp_path):
    conn, site_id = site
    run_id = _run(conn, site_id, "2026-08-13T10:00:00")
    path = tmp_path / "d.md"; path.write_text("x", encoding="utf-8")
    _deliverable(conn, site_id, "r1", [run_id], path, renderer="0.0.1")

    row = runs.client_reports(conn, site_id)[0]
    assert row["renderer"] == "superseded"
    assert row["renderer_version"] == "0.0.1"


def test_generating_a_report_records_the_renderer_that_wrote_it(site, tmp_path,
                                                               monkeypatch):
    """Otherwise every new document is born "unknown" and the mark is noise."""
    from clauditseo.reporting import generate as gen
    from clauditseo.reporting.render import RENDERER_VERSION

    conn, site_id = site
    run_id = _run(conn, site_id, "2026-08-13T10:00:00")
    monkeypatch.setattr(gen, "OUT_DIR", tmp_path)
    gen.generate(conn, "run", "client", [run_id])

    rows = runs.client_reports(conn, site_id)
    assert rows and rows[0]["renderer_version"] == RENDERER_VERSION
    assert rows[0]["renderer"] == "current"

def test_the_part_page_says_how_far_back_its_analysis_reads(site):
    """The same staleness, arriving through the part page's door.

    `site_reports` has counted the audits since an analysis was written since
    this file was opened; the part page printed the analysis's clock time and
    nothing else, so an analysis written against an audit two days old read as
    "· 11:06" beside a sweep from this morning. Measured on twenty22: the
    stored `ai-surface` analysis is three audits back and the header said
    nothing.
    """
    conn, site_id = site
    first = _run(conn, site_id, "2026-08-12T10:00:00")
    _analysis(conn, first)
    assert runs._audits_since(conn, site_id, first) == 0, "it is the newest"

    for day in ("13", "14"):
        _run(conn, site_id, f"2026-08-{day}T10:00:00")
    assert runs._audits_since(conn, site_id, first) == 2

    # The number the part page draws is the number the Reports screen draws.
    out = runs.site_reports(conn, site_id)
    row = next(r for r in out["reports"] if r["run_id"] == first)
    assert row["audits_since"] == runs._audits_since(conn, site_id, first)


def test_a_run_that_is_not_a_reading_is_not_counted_to_zero(site):
    """`None`, not 0. Zero means "this audit", which is a claim this cannot
    make about an analysis run by hand against a page scan — and the page
    scan is not evidence the site moved either, which is why it is not in the
    order at all."""
    conn, site_id = site
    assert runs._audits_since(conn, site_id, "no-such-run") is None


def test_the_header_draws_the_count_it_is_given():
    """Held on the source: the line is built in one place, and a date without
    the count (or a count without the date) is the half-answer this replaced."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "part_page.tsx").read_text(encoding="utf-8")
    i = src.index('className="muted checks-prov"')
    block = src[i:i + 1200]
    assert "audits_since" in block, "the header ignores the count the payload carries"
    assert "audits since" in block, "the reader is told in the Reports screen's words"

