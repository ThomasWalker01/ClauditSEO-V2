"""Numbered migration runner.

Migrations live in ``clauditseo/db/migrations/NNNN_name.sql`` and are applied
in filename order inside a transaction each. Applied filenames are recorded in
``schema_migrations`` so re-running is a no-op. The SQL sticks to the subset
shared by SQLite and Postgres wherever practical, to keep the P9 platform
port realistic.

A migration may also be ``NNNN_name.py`` exposing ``apply(conn)``, for the
one thing SQL cannot say: a repair that must look before it alters. SQLite
has no ``ADD COLUMN IF NOT EXISTS``, and the first such repair (``0033``)
has to be a no-op on a database that already carries the columns and add
them on one that does not - KI-59, where a migration file was edited after
it had run on the operator's database. Numbered and recorded exactly like
the SQL files, so the ledger stays one list.

Each file's content hash is recorded beside its filename as it is applied and
checked on every later call, so a file edited after it ran is named where a
phantom file already is rather than found at the first failing INSERT. Q-44,
answered by the operator 2026-09-03.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import sqlite3
from pathlib import Path

LOG = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _files() -> list[Path]:
    """The migrations on disk, in the order they are applied.

    Factored out so `migrate` and `phantom_migrations` read one glob rather
    than two that could drift — the second copy of a rule is how the rule
    itself goes wrong.
    """
    return sorted(list(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
                  + list(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.py")))


def _content_hash(path: Path) -> str:
    """The sha256 of a migration's text, with newlines normalised.

    Normalised because on this repository newlines are not content: there is
    no `* text=auto` rule in `.gitattributes` and `core.autocrlf` is on for
    the machine this runs on, so `0032_run_scope_and_depth.sql` is LF and
    `0033_run_scope_and_depth_repair.py` is CRLF in the same directory at the
    same commit. A hash over raw bytes would differ between two clones of one
    commit and name a file nobody had edited, and a detector that fires on a
    fresh clone is one the operator turns off. `read_text` translates
    universal newlines, so this hashes the text the runner itself executes.
    """
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _ensure_ledger(conn: sqlite3.Connection) -> None:
    """Create `schema_migrations`, and add `content_hash` where it is absent.

    The ledger is not itself a numbered migration — it is created here,
    because the runner needs it before it can run anything — so its own new
    column has to be added here too, guarded, for the same reason `0033` had
    to guard its `ALTER TABLE`s: SQLite has no `ADD COLUMN IF NOT EXISTS`.
    Rows written before this column existed keep NULL; that is the operator's
    answer to Q-44, and `hash_mismatches` records why.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')),"
        " content_hash TEXT)"
    )
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(schema_migrations)")}
    if "content_hash" not in columns:
        conn.execute("ALTER TABLE schema_migrations ADD COLUMN content_hash TEXT")


def applied(conn: sqlite3.Connection) -> set[str]:
    _ensure_ledger(conn)
    return {row["filename"] for row in conn.execute("SELECT filename FROM schema_migrations")}


def applied_hashes(conn: sqlite3.Connection) -> dict[str, str | None]:
    """Every applied filename against the hash recorded for it, or None."""
    _ensure_ledger(conn)
    return {row["filename"]: row["content_hash"] for row in
            conn.execute("SELECT filename, content_hash FROM schema_migrations")}


def hash_mismatches(conn: sqlite3.Connection) -> list[str]:
    """Applied filenames whose file no longer hashes to what was recorded.

    The other half of CQ-113, and CQ-243 / KI-59 is what leaving it cost:
    `0032_run_scope_and_depth.sql` was applied to the operator's database as a
    draft spelling its columns `scope`/`depth`/`scope_url`, was renamed to
    `scan_*` before it was committed, and could never re-apply — the runner
    keys on filename alone — so every `create_run` against that database
    raised `table audit_runs has no column named scan_scope` while the suite,
    which builds its databases from the files, stayed green.

    **Rows applied before this column existed stay NULL and are never
    reported.** Q-44, answered by the operator 2026-09-03: NULL means "applied
    before this existed and never verified", which is true, where back-filling
    them from the files as they stand today would record an agreement nobody
    checked — the same defect this function detects, committed by the detector
    itself. The cost the operator accepted with it: `0032`, the edit that
    prompted the question, is one of those NULL rows and is invisible here.
    Its own instance is closed by other means (`0033`, `52c7252`, KI-59), and
    every migration applied from this commit on is covered.

    A filename with no file behind it is a phantom, not a mismatch, and is
    `phantom_migrations`' to report — one database's one problem, named once.
    """
    on_disk = {p.name: p for p in _files()}
    drifted = []
    for filename, recorded in applied_hashes(conn).items():
        path = on_disk.get(filename)
        if recorded is None or path is None:
            continue
        if _content_hash(path) != recorded:
            drifted.append(filename)
    return sorted(drifted)


def phantom_migrations(conn: sqlite3.Connection) -> list[str]:
    """Applied filenames with no file behind them, sorted.

    CQ-113 / KI-27. The runner keys on filename alone, so `schema_migrations`
    is trusted rather than checked: a row naming a file that does not exist
    means some other tree's SQL has been run against this database and the
    shape it left is not the shape this repository describes. Every layer that
    could have noticed is silent by name — a same-named migration is skipped
    by filename, `CREATE TABLE IF NOT EXISTS` is skipped by name, and a fresh
    database has neither the row nor the table, so the suite passes either
    way. The operator's live database has carried `0025_probe_results.sql`
    against a directory running `…0024_page_advice.sql, 0026_probe_results.sql`
    since an abandoned F-05 attempt, and the first real probe against it
    returned HTTP 500 `table probe_results has no column named target`.

    Reported, never deleted. Removing the row is a write to a client's
    database and a decision the operator holds; burning the number is
    permanent either way. This function's job is to stop it being invisible.

    Derived from the directory rather than from a list of the ghosts known
    when it was written, which is the defect the one existing guard for this
    carries: `tests/test_probes.py`'s reconciliation hard-codes that filename
    and those columns, so it proves the instance and cannot see the class.

    Not the whole of CQ-113 by itself: a file whose *content* changed after it
    was applied is a different condition, and `hash_mismatches` is the half
    that reports it. That half was left here deliberately for months — it
    needed a column and a back-fill decision for rows applied before the
    column existed — and KI-59 is what the deferral cost. Q-44 settled the
    decision on 2026-09-03 and the column now exists.
    """
    return sorted(applied(conn) - {p.name for p in _files()})


def migration_names() -> frozenset[str]:
    """The filenames of the migrations on disk - `_files()`, as names."""
    return frozenset(p.name for p in _files())


def is_current(conn: sqlite3.Connection, names: frozenset[str]) -> bool:
    """Whether every one of `names` is already recorded as applied.

    The API's per-request question, answered from the ledger alone. `migrate`
    answers it too, but by globbing the directory and reading and hashing
    every file for the drift check - ~9 ms on each request, which was more
    than the query most routes run. The drift and phantom checks are about the
    files, and the files do not change under a running process's code: they
    run in full at startup and on `clauditseo migrate`. False where the ledger
    is missing, so a database swapped for an empty one is still migrated.
    """
    try:
        done = {row[0] for row in conn.execute("SELECT filename FROM schema_migrations")}
    except sqlite3.OperationalError:
        return False
    return names <= done


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply pending migrations; return the filenames applied this call."""
    done = applied(conn)
    ghosts = sorted(done - {p.name for p in _files()})
    if ghosts:
        # A warning rather than a refusal. This runs at API startup, and a
        # runner that halted the product over a row it cannot repair would
        # take the operator's only route to their own data away over a
        # condition that has been survivable for days.
        LOG.warning(
            "schema_migrations records %d migration(s) with no file in %s: %s"
            " - this database has had SQL from another tree applied to it, so"
            " its shape may not match this repository. Not removed: that is a"
            " write to your data and your decision.",
            len(ghosts), MIGRATIONS_DIR, ", ".join(ghosts))
    drifted = hash_mismatches(conn)
    if drifted:
        # Warned, never refused — the reason directly above, and the operator's
        # answer to Q-44 in the same words. Not re-applied either: the ledger
        # records that the OLD content ran, and running the new content now is
        # not the same as never having run the old one. The repair is a new
        # numbered migration, as `0033` was, never an edit to the file that ran.
        LOG.warning(
            "schema_migrations records %d migration(s) whose file has changed"
            " since it was applied: %s - this database was migrated by a"
            " different version of that file, so its shape may not match this"
            " repository. Not re-applied: repair with a new numbered migration,"
            " never by editing the one that ran.",
            len(drifted), ", ".join(drifted))
    ran: list[str] = []
    for path in _files():
        if path.name in done:
            continue
        # Hashed before it is applied, so the row records the content that
        # actually ran rather than whatever the file says by the time it lands.
        digest = _content_hash(path)
        with conn:
            if path.suffix == ".py":
                _apply_python(path, conn)
            else:
                conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (filename, content_hash) VALUES (?, ?)",
                (path.name, digest))
        ran.append(path.name)
    return ran


def _apply_python(path: Path, conn: sqlite3.Connection) -> None:
    """Load ``path`` as a module and call its ``apply(conn)``."""
    spec = importlib.util.spec_from_file_location(f"clauditseo_migration_{path.stem}", path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.apply(conn)
