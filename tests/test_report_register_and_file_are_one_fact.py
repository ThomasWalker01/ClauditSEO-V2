"""A deliverable and its register row are one fact, written in one frame.

Three defects live in twelve consecutive lines of `generate()`, and the fix
for any one of them rewrites the others' code, so they are guarded together.

  - WF-75: the file is written at what was `:264`, outside the `with conn:`
    that inserts the row. Anything that stops the insert leaves a document on
    disk that the product cannot see. The live database is the proof: 35
    documents in `reports/out`, 13 rows, and nine of the 22 orphans are
    client-facing comparison documents for a live client.
  - CQ-124, carried from report 061 to 073: the filename is dated from
    `date.today()` (the operator's local date) and the row from
    `repo.now_iso()` (UTC), two lines apart. For an en-AU operator that is
    UTC+10, so every generation between midnight and 10am local carries two
    dates and neither shows a zone.
  - The reconciliation half of WF-75: nothing adopts a document that is
    already orphaned, so fixing the write forward leaves the existing 22
    unreachable for ever.

**Why the run ids are recovered from the document's text and not its name.**
Report 073's remedy proposed parsing the filename. A filename cannot yield
`run_ids`, which is `NOT NULL` and is what `site_client_reports` reads to
compute the Deliverables screen's "Still current?" column; parsing it would
write `run_ids=[]`, which that screen renders as "audit no longer in history"
- a false reason rather than a missing one. Every comparison document opens
"Baseline run `<32 hex>` versus current run `<32 hex>`", and all nine live
orphans' runs are still present in `audit_runs`, so the body carries honest
provenance where the name carries none. Checked against the nine before this
was written, not assumed.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo.reporting import generate as gen

# Reused rather than rebuilt: this fixture crawls two fixture sites and
# completes two audits, which is what `generate()` needs before it will write
# anything at all. Importing it keeps one definition of "a database a report
# can be generated from".
from tests.test_reporting_g7 import db_with_runs  # noqa: F401

DIMS = ["TEC", "ONP"]


def test_a_failed_insert_leaves_no_document_on_disk(db_with_runs, tmp_path, monkeypatch):
    """WF-75's forward half. The file and the row are one fact or they are not.

    The insert is made to fail the way it actually can - an id collision on
    the primary key - rather than by patching `conn.execute`, so the failure
    is one the database itself produces.
    """
    conn, run_ids = db_with_runs
    out = tmp_path / "out"
    out.mkdir()

    fixed = "f" * 32
    monkeypatch.setattr(repo, "create_id", lambda: fixed)
    site_id = conn.execute("SELECT site_id FROM audit_runs WHERE id=?",
                           (run_ids[0],)).fetchone()["site_id"]
    conn.execute(
        "INSERT INTO reports (id, site_id, run_ids, template, audience, path,"
        " created_at) VALUES (?, ?, '[]', 'run', 'client', ?, ?)",
        (fixed, site_id, str(out / "squatter.md"), repo.now_iso()))
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        gen.generate(conn, "run", "client", [run_ids[0]], out_dir=out)

    left = sorted(p.name for p in out.glob("*.md"))
    assert left == [], (
        "the insert failed and a document was left on disk with no register "
        f"row, so the product cannot see it: {left}")


def test_the_filename_and_the_row_name_the_same_day(db_with_runs, tmp_path, monkeypatch):
    """CQ-124. One timestamp, or the document has two dates.

    The clock is frozen rather than waited on: the defect only shows between
    midnight and 10am for an en-AU operator, so a test that read the real
    clock would pass for fourteen hours a day and prove nothing. Freezing
    `repo.now_iso` - the register's own clock, reached as a module attribute
    because `generate` imports the module and not the function - makes the
    disagreement deterministic.
    """
    conn, run_ids = db_with_runs
    out = tmp_path / "out"
    out.mkdir()

    frozen = "2020-01-02T03:04:05+00:00"
    monkeypatch.setattr(repo, "now_iso", lambda: frozen)

    report = gen.generate(conn, "run", "client", [run_ids[0]], out_dir=out)
    row = conn.execute("SELECT created_at, path FROM reports WHERE id=?",
                       (report["id"],)).fetchone()
    named = re.search(r"(\d{4}-\d{2}-\d{2})", Path(row["path"]).name)
    assert named, f"the filename carries no date at all: {Path(row['path']).name!r}"
    assert named.group(1) == row["created_at"][:10], (
        "the deliverable's filename and its register row are dated from two "
        f"different clocks: the file says {named.group(1)} and the row says "
        f"{row['created_at'][:10]}")


@pytest.fixture
def db_with_an_orphan(tmp_path):
    """A site, a run, and two documents on disk that no row points at.

    No crawl: adoption reads the directory and the document text, so the only
    database state it needs is a site whose host matches one filename's slug
    and a run whose id appears in that document's body.
    """
    conn = connect(tmp_path / "adopt.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Adopt Co")
    site_id = repo.create_site(conn, client, "adopt.fixture")
    run_id = runs.create_run(conn, site_id, DIMS, "T2", analyst_enabled=False)
    other = runs.create_run(conn, site_id, DIMS, "T2", analyst_enabled=False)

    out = tmp_path / "out"
    out.mkdir()
    mine = out / f"adopt-fixture-comparison-client-2026-08-17-{'a' * 8}.md"
    mine.write_text(
        "# Comparison report - adopt.fixture\n\n"
        f"Baseline run `{run_id}` (15 August 2026) versus current run "
        f"`{other}` (15 August 2026). Findings are matched by fingerprint.\n",
        encoding="utf-8")
    stranger = out / f"nobody-here-run-client-2026-08-17-{'b' * 8}.md"
    stranger.write_text("# Run report - nobody.here\n", encoding="utf-8")

    yield conn, site_id, run_id, other, out, mine, stranger
    conn.close()


def test_an_orphaned_document_is_adopted_with_the_runs_its_own_text_names(
        db_with_an_orphan):
    conn, site_id, run_id, other, out, mine, _stranger = db_with_an_orphan

    result = gen.adopt_orphans(conn, out_dir=out)

    row = conn.execute("SELECT * FROM reports WHERE path=?",
                       (str(mine),)).fetchone()
    assert row is not None, (
        "a document owned by a known site was left with no register row, so "
        f"it stays invisible to the Deliverables screen: {result}")
    assert row["site_id"] == site_id
    assert row["template"] == "comparison" and row["audience"] == "client"
    assert sorted(json.loads(row["run_ids"])) == sorted([run_id, other]), (
        "the adopted row does not name the runs the document itself names, "
        "so the screen's 'Still current?' column has nothing true to read: "
        f"{row['run_ids']!r}")
    # The register's frame is UTC and every row already written uses it, so an
    # adopted row states an observed UTC instant rather than the local date its
    # filename happens to carry.
    assert row["created_at"].endswith("+00:00"), (
        f"the adopted row is not in the register's frame: {row['created_at']!r}")
    assert datetime.fromisoformat(row["created_at"]).tzinfo == timezone.utc


def test_a_document_no_site_owns_is_reported_rather_than_ignored(db_with_an_orphan):
    """Silence is what produced the 22 in the first place.

    The thirteen `fixture-test-*` documents in the live directory belong to no
    site in `sites` and must not be adopted; the failure to avoid is adopting
    them quietly OR skipping them quietly.
    """
    conn, _site_id, _run_id, _other, out, _mine, stranger = db_with_an_orphan

    result = gen.adopt_orphans(conn, out_dir=out)

    assert conn.execute("SELECT COUNT(1) FROM reports WHERE path=?",
                        (str(stranger),)).fetchone()[0] == 0, (
        "a document whose slug matches no site was adopted anyway")
    named = {Path(s["path"]).name: s["reason"] for s in result["skipped"]}
    assert stranger.name in named, (
        "a document that could not be adopted was passed over in silence, "
        f"which is the defect: {result}")
    assert named[stranger.name], "the skip carries no reason"


def test_a_dry_run_reports_the_same_work_and_writes_none_of_it(db_with_an_orphan):
    """Written after the failure, not before it — and the failure was real.

    `scripts/adopt_reports.py` first implemented `--dry-run` as BEGIN, adopt,
    rollback, on the reasoning that one code path cannot disagree with itself.
    `adopt_orphans` commits per row, so the outer transaction was closed by the
    first adoption and the rollback undid nothing. Run against the operator's
    own database on 21 August 2026 it printed "dry run - nothing written" and
    took the live `reports` table from 13 rows to 22. It was caught by querying
    the table rather than reading the console line, which is the only way this
    class of defect is ever caught.

    So the dry run must report exactly what the real run would do — the parse,
    the site resolution and the run validation all still run — and write none
    of it.
    """
    conn, _site_id, _run_id, _other, out, mine, _stranger = db_with_an_orphan
    before = conn.execute("SELECT COUNT(1) FROM reports").fetchone()[0]

    dry = gen.adopt_orphans(conn, out_dir=out, dry_run=True)

    assert conn.execute("SELECT COUNT(1) FROM reports").fetchone()[0] == before, (
        "a dry run wrote rows")
    assert conn.execute("SELECT COUNT(1) FROM reports WHERE path=?",
                        (str(mine),)).fetchone()[0] == 0

    real = gen.adopt_orphans(conn, out_dir=out)
    assert [a["path"] for a in dry["adopted"]] == [a["path"] for a in real["adopted"]], (
        "the dry run named different work from the run that followed it, so "
        "reading it tells the operator nothing about what will happen")
    assert [s["reason"] for s in dry["skipped"]] == [s["reason"] for s in real["skipped"]]


def test_adopting_twice_adds_nothing_the_second_time(db_with_an_orphan):
    """The pass is one-shot by intent and idempotent by construction - an
    operator who runs it twice must not get two rows for one document."""
    conn, _site_id, _run_id, _other, out, mine, _stranger = db_with_an_orphan

    first = gen.adopt_orphans(conn, out_dir=out)
    second = gen.adopt_orphans(conn, out_dir=out)

    assert len(first["adopted"]) == 1 and second["adopted"] == []
    assert conn.execute("SELECT COUNT(1) FROM reports WHERE path=?",
                        (str(mine),)).fetchone()[0] == 1
