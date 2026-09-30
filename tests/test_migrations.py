import logging
import sqlite3
from pathlib import Path

from clauditseo.db.connection import connect
from clauditseo.db import migrate as runner
from clauditseo.db.migrate import migrate

EXPECTED_TABLES = {
    "operators", "clients", "sites", "audit_runs", "cost_entries",
    "findings", "finding_states", "metric_snapshots", "reports", "analyst_cache",
}


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


def test_migrations_apply_on_fresh_db(tmp_path):
    conn = connect(tmp_path / "t.db")
    ran = migrate(conn)
    assert ran, "expected at least one migration to run"
    assert EXPECTED_TABLES <= _tables(conn)
    conn.close()


def test_migrations_are_idempotent(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    assert migrate(conn) == []
    conn.close()


def test_severity_and_tier_constraints(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    conn.execute(
        "INSERT INTO operators (id, name, role, created_at) VALUES ('op1','x','owner','2026-01-01')"
    )
    conn.execute(
        "INSERT INTO clients (id, owner_id, name, created_at) VALUES ('c1','op1','x','2026-01-01')"
    )
    conn.execute(
        "INSERT INTO sites (id, client_id, domain, created_at) VALUES ('s1','c1','x.example','2026-01-01')"
    )
    try:
        conn.execute(
            "INSERT INTO audit_runs (id, site_id, dimensions, tier, engine_version, created_at)"
            " VALUES ('r1','s1','[]','T9','0','2026-01-01')"
        )
        assert False, "invalid tier should be rejected"
    except sqlite3.IntegrityError:
        pass
    conn.close()


# --- the applied set against the directory that is supposed to define it -----
#
# CQ-113 / KI-27. `applied()` returns filenames and nothing has ever compared
# them to `MIGRATIONS_DIR`, so a row for a file that does not exist is silent
# at every layer: a same-named migration is skipped by filename, a
# `CREATE TABLE IF NOT EXISTS` is skipped by name, and a fresh test database
# has neither the row nor the table — which is why the whole suite passed
# while the operator's live database carried `0025_probe_results.sql` against
# a directory running `…0024_page_advice.sql, 0026_probe_results.sql`.
#
# The one guard that existed for this (`tests/test_probes.py`, the ghost-table
# reconciliation) hard-codes that filename and those columns, so it proves the
# instance and cannot see the class. These derive the expected set from the
# directory listing instead, which is the whole point: a literal list of the
# ghosts known when the test was written would go stale the next time one
# appeared.


def _directory_names() -> set[str]:
    """The filenames on disk, read the way the runner reads them.

    Through the runner's own `_files()` rather than a second glob: this said
    `*.sql` alone until `0033_run_scope_and_depth_repair.py` landed, at which
    point "the way the runner reads them" and what this returned were two
    different things — the second copy of a rule going wrong, which is the
    defect `_files()` was factored out to prevent.
    """
    return {p.name for p in runner._files()}


def test_an_applied_migration_with_no_file_behind_it_is_reported(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrate(conn)

    # Derived, not named: one past the highest number actually present, so
    # this cannot collide with a real migration and cannot go stale when the
    # next one lands.
    highest = max(int(n[:4]) for n in _directory_names())
    ghost = f"{highest + 1:04d}_never_written.sql"
    conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (ghost,))

    assert runner.phantom_migrations(conn) == [ghost]
    conn.close()


def test_a_database_matching_its_directory_reports_no_phantom(tmp_path):
    """The other direction. Without it the check above is satisfied by a
    function that reports everything."""
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    assert runner.phantom_migrations(conn) == []
    conn.close()


def test_the_runner_says_so_where_the_operator_reads_it(tmp_path, caplog):
    """Reporting it to a caller nobody calls is not reporting it. `migrate()`
    runs at API startup and on `clauditseo migrate`, so the warning is the
    one path that reaches the operator without anyone going looking."""
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    highest = max(int(n[:4]) for n in _directory_names())
    ghost = f"{highest + 1:04d}_never_written.sql"
    conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (ghost,))

    with caplog.at_level(logging.WARNING, logger="clauditseo.db.migrate"):
        migrate(conn)

    assert any(ghost in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records]
    conn.close()


# --- the applied file's content against the content that was applied ---------
#
# CQ-113's other half. A phantom row names a file that is not there; these
# cover the row whose file IS there and is no longer what ran. That is the
# mechanism of CQ-243 / KI-59: `0032_run_scope_and_depth.sql` was applied to
# the operator's database as a draft naming its columns `scope`/`depth`/
# `scope_url`, renamed to `scan_*` before it was committed, and never
# re-applied — the runner keys on filename alone — so every `create_run` on
# that database raised `table audit_runs has no column named scan_scope`.
#
# The suite could not see it and stayed green throughout, because it builds
# every database from the files: the disagreement was between the code and
# ONE database, and no test read that database. So these tests do not try to
# reproduce it by reading the operator's file. They build the disagreement
# itself — a database migrated from one text, and a directory now holding
# another — which is the class rather than the instance.
#
# Q-44, answered by the operator 2026-09-03: hash from here, leave the rows
# applied before the column existed NULL, warn only where a hash is recorded
# and differs. `test_a_row_applied_before_the_hash_column_existed_is_silent`
# is that decision made checkable, in both of its directions.


def _one_migration_dir(monkeypatch, tmp_path, body: str) -> Path:
    """A directory holding a single migration, standing in for the real one.

    The runner reads `MIGRATIONS_DIR` through `_files()`, so pointing the
    module at a temporary directory is enough — and it means no test here ever
    edits a file in `clauditseo/db/migrations/`, which is the one thing that
    would make these guards a cause of the defect they detect.
    """
    directory = tmp_path / "migrations"
    directory.mkdir()
    (directory / "0001_alpha.sql").write_text(body, encoding="utf-8")
    monkeypatch.setattr(runner, "MIGRATIONS_DIR", directory)
    return directory


def test_every_migration_this_repository_applies_records_a_hash(tmp_path):
    """Against the real directory: nothing is applied without a hash beside it.

    Derived from what was applied rather than from a count, so a migration
    added later is covered without this test being touched."""
    conn = connect(tmp_path / "t.db")
    ran = migrate(conn)
    recorded = runner.applied_hashes(conn)
    assert set(ran) <= set(recorded)
    unhashed = sorted(name for name in ran if recorded[name] is None)
    assert unhashed == [], unhashed
    assert runner.hash_mismatches(conn) == []
    conn.close()


def test_a_file_edited_after_it_was_applied_is_reported(tmp_path, monkeypatch):
    """KI-59's mechanism, as a class. The database was migrated by the first
    text; the directory now holds the second; nothing else changed."""
    directory = _one_migration_dir(monkeypatch, tmp_path, "CREATE TABLE alpha (id TEXT);")
    conn = connect(tmp_path / "t.db")
    assert migrate(conn) == ["0001_alpha.sql"]
    assert runner.hash_mismatches(conn) == []

    (directory / "0001_alpha.sql").write_text(
        "CREATE TABLE alpha (id TEXT, renamed TEXT);", encoding="utf-8")

    assert runner.hash_mismatches(conn) == ["0001_alpha.sql"]
    # And it stays reported rather than being silently re-applied: the ledger
    # records that the OLD content ran, which is still true.
    assert migrate(conn) == []
    assert runner.hash_mismatches(conn) == ["0001_alpha.sql"]
    conn.close()


def test_a_file_that_has_not_changed_reports_no_mismatch(tmp_path, monkeypatch):
    """The other direction. Without it the check above is satisfied by a
    function that reports everything — the defect rule 5 names."""
    directory = _one_migration_dir(monkeypatch, tmp_path, "CREATE TABLE alpha (id TEXT);")
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    # Rewritten with identical content: an mtime change is not a content change.
    (directory / "0001_alpha.sql").write_text("CREATE TABLE alpha (id TEXT);", encoding="utf-8")
    assert runner.hash_mismatches(conn) == []
    conn.close()


def test_a_file_differing_only_in_line_endings_is_not_reported(tmp_path, monkeypatch):
    """Why the hash normalises newlines, as a guard rather than a comment.

    `.gitattributes` sets no `* text=auto` and `core.autocrlf` is on for the
    machine this runs on, so `0032_...sql` is LF and `0033_....py` is CRLF in
    the same directory at the same commit. A byte hash would differ between
    two clones of one commit and name a file nobody edited; a detector that
    fires on a fresh clone is one that gets turned off."""
    directory = _one_migration_dir(monkeypatch, tmp_path, "CREATE TABLE alpha (\nid TEXT);")
    conn = connect(tmp_path / "t.db")
    migrate(conn)

    (directory / "0001_alpha.sql").write_bytes(b"CREATE TABLE alpha (\r\nid TEXT);")

    assert runner.hash_mismatches(conn) == []
    conn.close()


def test_a_row_applied_before_the_hash_column_existed_is_silent(tmp_path, monkeypatch):
    """Q-44's answer, both halves, in one test.

    A NULL hash means "applied before this column existed and never verified",
    so it is never reported however far the file has drifted — the option the
    operator refused was back-filling those rows from the files as they stand
    today, which would record an agreement nobody checked. And the row is not
    made NULL-proof by accident: hash the same row and the same drift is
    reported, which is what shows the silence is the NULL and not the file."""
    directory = _one_migration_dir(monkeypatch, tmp_path, "CREATE TABLE alpha (id TEXT);")
    conn = connect(tmp_path / "t.db")
    migrate(conn)

    # The state of every row in the operator's database at this commit.
    conn.execute("UPDATE schema_migrations SET content_hash = NULL")
    (directory / "0001_alpha.sql").write_text(
        "CREATE TABLE alpha (id TEXT, renamed TEXT);", encoding="utf-8")

    assert runner.applied_hashes(conn) == {"0001_alpha.sql": None}
    assert runner.hash_mismatches(conn) == []

    conn.execute("UPDATE schema_migrations SET content_hash = 'not-the-current-hash'")
    assert runner.hash_mismatches(conn) == ["0001_alpha.sql"]
    conn.close()


def test_a_phantom_is_reported_once_and_not_also_as_a_mismatch(tmp_path, monkeypatch):
    """One database's one problem, named once. A row with a recorded hash and
    no file behind it is a phantom; counting it twice would make the operator
    chase two conditions where there is one."""
    _one_migration_dir(monkeypatch, tmp_path, "CREATE TABLE alpha (id TEXT);")
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    conn.execute(
        "INSERT INTO schema_migrations (filename, content_hash) VALUES (?, ?)",
        ("0002_never_written.sql", "a" * 64))

    assert runner.phantom_migrations(conn) == ["0002_never_written.sql"]
    assert runner.hash_mismatches(conn) == []
    conn.close()


def test_the_runner_says_a_file_has_drifted_where_the_operator_reads_it(
        tmp_path, monkeypatch, caplog):
    """Reporting it to a caller nobody calls is not reporting it — the same
    reason the phantom warning exists. `migrate()` runs at API startup and on
    `clauditseo migrate`, which is the one path that reaches the operator
    without anyone going looking, and it is where KI-59 would have been named
    hours before the 500 rather than after it."""
    directory = _one_migration_dir(monkeypatch, tmp_path, "CREATE TABLE alpha (id TEXT);")
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    (directory / "0001_alpha.sql").write_text(
        "CREATE TABLE alpha (id TEXT, renamed TEXT);", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="clauditseo.db.migrate"):
        migrate(conn)

    assert any("0001_alpha.sql" in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records]
    conn.close()


def test_the_drift_warning_does_not_stop_the_product_starting(tmp_path, monkeypatch):
    """Warn, never refuse — the operator's answer says so in those words, and
    the phantom warning above it was written for the same reason: a runner
    that halted over a file it cannot un-edit takes away the only route to the
    data. So a drifted ledger still applies what is pending and still returns."""
    directory = _one_migration_dir(monkeypatch, tmp_path, "CREATE TABLE alpha (id TEXT);")
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    (directory / "0001_alpha.sql").write_text(
        "CREATE TABLE alpha (id TEXT, renamed TEXT);", encoding="utf-8")
    (directory / "0002_beta.sql").write_text("CREATE TABLE beta (id TEXT);", encoding="utf-8")

    assert migrate(conn) == ["0002_beta.sql"]
    assert "beta" in _tables(conn)
    conn.close()
