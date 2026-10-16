"""Date each run-moved finding state by the run that moved it (screen audits
round 4, Record AC-01).

The analysis-state walks wrote `updated_at` with their own clock on every row
they kept, changed or not, so the Record's "since <date>" read the day of the
last re-read for rows that had not moved in weeks. The walks now keep an
unmoved date and stamp a move with its run's time (`runs._moved_at`); this
brings the stored rows to the same rule. A state an operator set (no
`changed_by_run`) keeps the date it was set on.

Idempotent: a row already dated by its run is not touched.
"""


def apply(conn) -> None:
    conn.execute(
        "UPDATE finding_states SET updated_at = ("
        " SELECT COALESCE(a.finished_at, a.started_at) FROM audit_runs a"
        " WHERE a.id = finding_states.changed_by_run)"
        " WHERE changed_by_run IS NOT NULL"
        " AND EXISTS (SELECT 1 FROM audit_runs a WHERE a.id = finding_states.changed_by_run"
        "             AND COALESCE(a.finished_at, a.started_at) IS NOT NULL"
        "             AND COALESCE(a.finished_at, a.started_at) != finding_states.updated_at)")
