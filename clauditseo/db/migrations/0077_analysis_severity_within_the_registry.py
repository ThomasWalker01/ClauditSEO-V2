"""Lower a stored legacy analysis row's severity to the registry's for the
same check (screen audits round 3, Local AC-01).

A legacy brief (the local briefs) answers the findings index with a bare code
and its own severity, and the store took it as given: twenty22's
`EXP:local-signals/localbusiness-schema-missing` stood open at Critical,
ranking the part 4 of 81, where the registry's default is Medium. New rows are
capped as they are stored (`checks.capped_severity`); this brings the stored
ones to the same rule. A code no single registered check carries is left as
it is.

Idempotent: a row already at or under its ceiling is not touched.
"""

import logging

log = logging.getLogger(__name__)


def apply(conn) -> None:
    from clauditseo.checks import capped_severity

    rows = conn.execute(
        "SELECT rowid, check_id, severity FROM findings WHERE dimension LIKE 'EXP:%'"
        " AND source='model-judgement'").fetchall()
    changed = 0
    for rowid, code, severity in rows:
        capped = capped_severity(code, severity)
        if capped != severity:
            conn.execute("UPDATE findings SET severity=? WHERE rowid=?", (capped, rowid))
            changed += 1
    if changed:
        log.info("lowered %d analysis rows to their checks' registered severity", changed)
