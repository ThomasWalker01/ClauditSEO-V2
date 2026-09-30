"""Database snapshots and the numbers an operator needs to trust them.

Copying the database file while the server runs is not safe: SQLite in WAL
mode keeps recent writes in a sidecar, so a plain copy can silently omit the
most recent audits and still open cleanly. That failure is invisible until a
restore. The backup API below reads through a live connection and produces a
consistent snapshot, so no service interruption is required — and every
snapshot is verified and row-counted before it is reported as a success.
"""

from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path

COUNTED_TABLES = ("operators", "clients", "sites", "audit_runs", "findings",
                  "finding_states", "metric_snapshots", "cost_entries",
                  "analyst_cache", "reports")


def backup_dir(db_path: Path) -> Path:
    return db_path.parent / "backups"


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def database_stats(conn: sqlite3.Connection, db_path: Path) -> dict:
    counts: dict[str, int] = {}
    for table in COUNTED_TABLES:
        try:
            counts[table] = conn.execute(
                f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            counts[table] = -1        # table absent: report, don't crash
    return {
        "path": str(db_path),
        "bytes": _file_size(db_path),
        "wal_bytes": _file_size(Path(str(db_path) + "-wal")),
        "rows": counts,
    }


def list_backups(db_path: Path) -> list[dict]:
    directory = backup_dir(db_path)
    if not directory.exists():
        return []
    entries = []
    for path in sorted(directory.glob("clauditseo-*.db"), reverse=True):
        stat = path.stat()
        entries.append({
            "name": path.name,
            "path": str(path),
            "bytes": stat.st_size,
            "created_at": datetime.datetime.fromtimestamp(
                stat.st_mtime).isoformat(timespec="seconds"),
        })
    return entries


def create_backup(conn: sqlite3.Connection, db_path: Path,
                  now: datetime.datetime | None = None) -> dict:
    """Take a verified snapshot. Safe to call while the server is serving."""
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    directory = backup_dir(db_path)
    directory.mkdir(parents=True, exist_ok=True)
    # Never overwrite an existing snapshot. Two backups inside the same second
    # (a double-clicked button) would otherwise collide, and the older one
    # would vanish without a word.
    target = directory / f"clauditseo-{stamp}.db"
    suffix = 2
    while target.exists():
        target = directory / f"clauditseo-{stamp}-{suffix}.db"
        suffix += 1

    # Fold the WAL back in where we can; harmless if other readers block it,
    # because the backup API produces a consistent snapshot regardless.
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        pass

    destination = sqlite3.connect(target)
    try:
        with destination:
            conn.backup(destination)
        integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
        verified = {}
        for table in COUNTED_TABLES:
            try:
                verified[table] = destination.execute(
                    f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                verified[table] = -1
    finally:
        destination.close()

    source = database_stats(conn, db_path)["rows"]
    mismatched = {t: (source[t], verified[t]) for t in COUNTED_TABLES
                  if source.get(t) != verified.get(t)}
    if integrity != "ok" or mismatched:
        # A snapshot that cannot be verified is worse than none, because it
        # will be trusted. Remove it and say why.
        target.unlink(missing_ok=True)
        return {"status": "failed", "integrity": integrity,
                "mismatched_tables": mismatched,
                "reason": "the snapshot did not verify and was discarded"}

    return {
        "status": "ok",
        "name": target.name,
        "path": str(target),
        "bytes": target.stat().st_size,
        "integrity": integrity,
        "rows": verified,
        "created_at": datetime.datetime.fromtimestamp(
            target.stat().st_mtime).isoformat(timespec="seconds"),
    }


def restore_instructions(db_path: Path) -> list[str]:
    """Deliberately instructions rather than a button: restoring overwrites
    every audit recorded since the snapshot, and that should take a
    considered act at the command line, not one click in a browser."""
    return [
        "Stop the server: scripts\\stop-service.ps1",
        f"Copy the chosen snapshot over {db_path.name}, replacing it",
        f"Delete any {db_path.name}-wal and {db_path.name}-shm sidecars",
        "Start the server: scripts\\restart-service.ps1",
        "Migrations re-apply automatically on start",
    ]


def clear_analyst_cache(conn: sqlite3.Connection) -> int:
    """Forget every cached analyst and expert result. Costs tokens to
    regenerate but destroys nothing that cannot be recomputed."""
    count = conn.execute("SELECT COUNT(*) FROM analyst_cache").fetchone()[0]
    with conn:
        conn.execute("DELETE FROM analyst_cache")
    return count
