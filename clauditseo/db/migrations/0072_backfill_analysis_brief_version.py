"""Fill `brief_version` on analyses stored before the column (item 249).

The analyst cache is keyed `EXPERT:<tool>#<cache version>#<brief version>`
and written in the same call that stores the report, so the cache row
nearest in time to a report carries the brief version it was written under.
Taken only where one was written within ten minutes of the report; a report
with no such row keeps NULL, which the screen reads as "not recorded" and
does not mark.
"""


def apply(conn) -> None:
    has_cache = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                             " AND name='analyst_cache'").fetchone()
    if not has_cache:
        return
    rows = conn.execute("SELECT rowid, tool_id, created_at FROM expert_reports"
                        " WHERE brief_version IS NULL").fetchall()
    for rowid, tool_id, created_at in rows:
        hit = conn.execute(
            "SELECT task FROM analyst_cache WHERE task LIKE ?"
            " AND abs(julianday(created_at) - julianday(?)) < (10.0 / 1440)"
            " ORDER BY abs(julianday(created_at) - julianday(?)) LIMIT 1",
            (f"EXPERT:{tool_id}#%", created_at, created_at)).fetchone()
        if hit and hit[0].count("#") >= 2:
            conn.execute("UPDATE expert_reports SET brief_version=? WHERE rowid=?",
                         (hit[0].rsplit("#", 1)[1], rowid))
