"""Bring `audit_runs` back into agreement with `create_run` - KI-59, CQ-243.

`0032_run_scope_and_depth.sql` was applied to the operator's database at
02:47:59 UTC on 2026-09-02 as a draft that named its columns `scope`, `depth`
and `scope_url`; the file was then renamed to the `scan_` prefix - because a
column called `scope` would shadow the key `get_run` assembles under that
name - and committed seventeen minutes later. The runner keys on filename
alone, so the committed content never ran there, and every route that
creates a run raised `table audit_runs has no column named scan_scope` on
the live install while the suite, which builds every database from the
files, stayed green.

Python rather than SQL because the repair must look before it alters:
SQLite has no `ADD COLUMN IF NOT EXISTS`, and this must add the three
columns where they are missing and do nothing where `0032` as committed
already added them. It never edits `0032` - that is the mechanism that
caused this.

The draft's three orphan columns are left in place, and that is a decision
rather than an omission: they hold no data (checked on the live database
before this was written - zero rows with any of the three set), `_run_dict`
assigns the assembled `scope` after copying the row so the orphan cannot
shadow it, and dropping a column from a client's database is a write beyond
the repair. They are named here so the next reader knows they are expected.
"""

COLUMNS = ("scan_scope", "scan_depth", "scan_url")


def apply(conn) -> None:
    have = {row[1] for row in conn.execute("PRAGMA table_info(audit_runs)")}
    for col in COLUMNS:
        if col not in have:
            conn.execute(f"ALTER TABLE audit_runs ADD COLUMN {col} TEXT")
