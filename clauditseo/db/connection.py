from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI moves a request between the event loop
    # (async deps) and worker threads (sync endpoints); access is sequential
    # within a request, never concurrent on one connection.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    # Concurrent runs wait for the writer instead of failing 'database is locked'.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn
