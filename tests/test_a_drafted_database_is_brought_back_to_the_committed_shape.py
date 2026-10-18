"""A database that ran a migration's draft is brought back to the committed
shape, and one that ran the committed file is left alone.

KI-59 / CQ-243, report 139. `0032_run_scope_and_depth.sql` was applied to the
operator's database as a draft naming its columns `scope`, `depth` and
`scope_url`, then renamed to the `scan_` prefix and committed seventeen
minutes later. The runner keys on filename alone, so the committed content
never ran there, and every route that creates a run raised on the live
install - `table audit_runs has no column named scan_scope` - while the
suite, which builds every database from the files, stayed green.

**Why this builds the drafted shape by hand.** The suite cannot reach the
case any other way: a fixture database always runs the files as committed.
So this applies every migration up to `0031`, then applies `0032`'s DRAFT -
the committed file with the three names put back the way the draft had
them - and records `0032` as applied, which is exactly the ledger the
operator's database holds. Then it runs the runner.

**Both directions, because a repair that broke a healthy database would be
worse than the defect.** A fresh database runs `0032` as committed and then
`0033`, and must end with the three columns once, not a duplicate-column
error and not six columns.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clauditseo.db import migrate as migrate_mod
from clauditseo.db.connection import connect
from clauditseo.db.migrate import MIGRATIONS_DIR, applied, migrate
from clauditseo.persistence import repo, runs
from tests.test_coverage import DIMS

REPAIR = "0033_run_scope_and_depth_repair.py"
RENAMED = "0032_run_scope_and_depth.sql"
SCAN = ("scan_scope", "scan_depth", "scan_url")
DRAFT = ("scope", "depth", "scope_url")


def _columns(conn: sqlite3.Connection) -> list[str]:
    return [r[1] for r in conn.execute("PRAGMA table_info(audit_runs)")]


def _drafted(db: Path) -> sqlite3.Connection:
    """A database in the operator's state: everything through `0031` as
    committed, `0032` as its draft, and the ledger saying `0032` ran."""
    conn = connect(db)
    files = [p for p in migrate_mod._files() if p.name < RENAMED]
    assert files and files[-1].name.startswith("0031"), [p.name for p in files]
    applied(conn)  # creates the ledger
    for path in files:
        with conn:
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,))
    draft = (MIGRATIONS_DIR / RENAMED).read_text(encoding="utf-8")
    for new, old in zip(SCAN, DRAFT):
        assert f"ADD COLUMN {new} " in draft, new
        draft = draft.replace(f"ADD COLUMN {new} ", f"ADD COLUMN {old} ")
    with conn:
        conn.executescript(draft)
        conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (RENAMED,))
    return conn


def test_the_repair_adds_the_three_columns_a_drafted_database_lacks(tmp_path):
    conn = _drafted(tmp_path / "drafted.db")
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Repair Co"), "repair.fixture")
    before = _columns(conn)
    assert all(c in before for c in DRAFT) and not any(c in before for c in SCAN), (
        f"precondition: the drafted shape was not built: {before[-6:]}")
    try:
        runs.create_run(conn, site_id, DIMS, "T2")
    except sqlite3.OperationalError as e:
        assert "scan_scope" in str(e), e
    else:
        raise AssertionError(
            "precondition: create_run succeeded on the drafted shape, so the "
            "defect this repairs is not reproduced")

    ran = migrate(conn)
    # Later migrations (`0034`'s backfill) run after the repair; the repair
    # is the first thing a drafted database gets.
    assert ran and ran[0] == REPAIR, ran
    after = _columns(conn)
    assert all(c in after for c in SCAN), after[-6:]
    # The orphans stay, by the decision the migration records.
    assert all(c in after for c in DRAFT), after[-6:]
    # And the product's core job works again.
    run_id = runs.create_run(conn, site_id, DIMS, "T2", scan_scope="site",
                             scan_depth="quick")
    row = conn.execute("SELECT scan_scope, scan_depth FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    assert tuple(row) == ("site", "quick"), tuple(row)
    assert migrate(conn) == [], "the repair ran twice"
    conn.close()


def test_a_fresh_database_is_left_alone_by_the_repair(tmp_path):
    conn = connect(tmp_path / "fresh.db")
    ran = migrate(conn)
    assert RENAMED in ran and REPAIR in ran, ran
    cols = _columns(conn)
    assert [c for c in cols if c in SCAN] == list(SCAN), cols[-6:]
    assert not any(c in cols for c in DRAFT), (
        f"a fresh database carries the draft's columns: {cols[-6:]}")
    assert cols.count("scan_scope") == 1
    conn.close()
